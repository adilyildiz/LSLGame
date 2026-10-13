"""Ortak Veri Yapısı (Recording) ve XDF Yükleyici.

PLAN.md Faz 4.1 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- Recording dataclass: eeg (n_samples x 7), eeg_ts, acc (n_samples x 3), srate, ch_names, markers, meta.
- load_xdf: device_xon.yaml kurallarına göre X.on ve marker akışlarını ayrıştırır,
  empedans ve kanal bilgilerini çıkarır, pyxdf ile saat eşleme ve dejitter uygular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pyxdf
import yaml

logger = logging.getLogger(__name__)

DEFAULT_EEG_CH_NAMES = ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]
DEFAULT_ACC_CH_NAMES = ["accX", "accY", "accZ"]


@dataclass
class Recording:
    """Ortak BCI kayıt veri yapısı."""
    eeg: np.ndarray  # (n_samples, 7) mikrovolt (uV)
    eeg_ts: np.ndarray  # (n_samples,) LSL zaman damgaları
    acc: np.ndarray  # (n_samples, 3) ivmeölçer verisi
    srate: float  # Örnekleme frekansı (Hz)
    ch_names: List[str]  # EEG kanal adları
    markers: List[Tuple[float, str]]  # [(zaman_damgası, marker_metni), ...]
    meta: Dict[str, Any] = field(default_factory=dict)  # İmpedans, oturum, run, dosya yolu vb.

    def __post_init__(self):
        self.eeg = np.asarray(self.eeg, dtype=np.float64)
        self.eeg_ts = np.asarray(self.eeg_ts, dtype=np.float64)
        self.acc = np.asarray(self.acc, dtype=np.float64)
        if self.eeg.ndim != 2:
            raise ValueError(f"EEG matrisi 2 boyutlu olmalıdır: {self.eeg.shape}")
        if self.eeg.shape[0] != len(self.eeg_ts):
            raise ValueError(f"EEG örnek sayısı ({self.eeg.shape[0]}) ile zaman damgası ({len(self.eeg_ts)}) uyuşmuyor.")
        if self.acc.ndim != 2:
            raise ValueError(f"İvmeölçer matrisi 2 boyutlu olmalıdır: {self.acc.shape}")


def _load_device_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    if config_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        config_path = project_root / "config" / "device_xon.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def _parse_impedances_from_desc(desc: Any) -> Dict[str, float]:
    """XDF akış desc alanından empedans sözlüğünü çıkarır."""
    impedances: Dict[str, float] = {}
    if not isinstance(desc, dict):
        return impedances

    imp_list = desc.get("impedances", [])
    if not imp_list or not isinstance(imp_list, list):
        return impedances

    first_imp = imp_list[0]
    if not isinstance(first_imp, dict):
        return impedances

    entries = first_imp.get("impedance", [])
    if not isinstance(entries, list):
        return impedances

    for entry in entries:
        if isinstance(entry, dict) and "label" in entry and "value" in entry:
            label = str(entry["label"][0]) if isinstance(entry["label"], list) else str(entry["label"])
            val_raw = entry["value"][0] if isinstance(entry["value"], list) else entry["value"]
            try:
                impedances[label] = float(val_raw)
            except (ValueError, TypeError):
                continue
    return impedances


def load_xdf(
    path: Union[str, Path],
    config_path: Optional[Union[str, Path]] = None,
    dejitter_timestamps: bool = True,
) -> Recording:
    """XDF dosyasını yükleyip standart Recording nesnesine dönüştürür.

    Kurallar:
    - X.on akışı device_xon.yaml kuralıyla bulunur (name_prefix 'X.on', type 'EEG').
    - Marker akışı önce 'BCI_Markers' adıyla, yoksa type='Markers' olarak aranır.
    - pyxdf saat eşleme ve dejitter açık olarak çalışır.
    - Empedanslar meta veriye eklenir.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"XDF dosyası bulunamadı: {file_path}")

    device_cfg = _load_device_config(config_path)
    stream_cfg = device_cfg.get("stream", {})
    channels_cfg = device_cfg.get("channels", {})

    expected_prefix = stream_cfg.get("name_prefix", "X.on")
    expected_type = stream_cfg.get("type", "EEG")

    # Kanal indeksleri
    indices_cfg = channels_cfg.get("indices", {})
    eeg_indices = indices_cfg.get("eeg", [0, 1, 2, 3, 4, 5, 6])
    acc_indices = indices_cfg.get("accelerometer", [8, 9, 10])
    ch_labels = channels_cfg.get("labels", DEFAULT_EEG_CH_NAMES + ["BIP"] + DEFAULT_ACC_CH_NAMES)
    eeg_ch_names = [ch_labels[i] for i in eeg_indices] if ch_labels and len(ch_labels) > max(eeg_indices) else DEFAULT_EEG_CH_NAMES

    # pyxdf ile yükle (saat senkronizasyonu ve dejitter etkin)
    streams, header = pyxdf.load_xdf(str(file_path), dejitter_timestamps=dejitter_timestamps)
    if not streams:
        raise ValueError(f"XDF dosyasında akış bulunamadı: {file_path}")

    # 1. X.on EEG akışını bul
    xon_stream = None
    for s in streams:
        s_info = s.get("info", {})
        s_name = s_info.get("name", [""])[0]
        s_type = s_info.get("type", [""])[0]
        if s_name.startswith(expected_prefix) and s_type == expected_type:
            xon_stream = s
            break

    # Alternatif: sadece type == 'EEG' olan ilk akış
    if xon_stream is None:
        for s in streams:
            if s.get("info", {}).get("type", [""])[0] == expected_type:
                xon_stream = s
                break

    if xon_stream is None:
        raise ValueError(f"X.on EEG akışı dosyada bulunamadı: {file_path}")

    # 2. Marker akışını bul
    marker_stream = None
    # Önce BCI_Markers adıyla ara
    for s in streams:
        s_name = s.get("info", {}).get("name", [""])[0]
        if s_name == "BCI_Markers":
            marker_stream = s
            break

    # Yoksa type == 'Markers' veya adında Marker geçen akışı ara
    if marker_stream is None:
        for s in streams:
            s_info = s.get("info", {})
            s_name = s_info.get("name", [""])[0]
            s_type = s_info.get("type", [""])[0]
            # [time] türev akışlarını hariç tut
            if "[time]" in s_name:
                continue
            if s_type == "Markers" or "Marker" in s_name:
                marker_stream = s
                break

    # Veri dizilerini al
    time_series = np.asarray(xon_stream["time_series"])
    time_stamps = np.asarray(xon_stream["time_stamps"])

    if time_series.ndim != 2:
        raise ValueError(f"Beklenmeyen X.on veri matrisi boyutu: {time_series.shape}")

    eeg_data = time_series[:, eeg_indices]

    if time_series.shape[1] > max(acc_indices):
        acc_data = time_series[:, acc_indices]
    else:
        acc_data = np.zeros((len(time_stamps), 3), dtype=np.float64)

    # Örnekleme hızı
    nominal_srate = float(xon_stream["info"].get("nominal_srate", [250.0])[0])
    effective_srate = float(xon_stream.get("effective_srate", nominal_srate or 250.0))
    srate = effective_srate if effective_srate > 0 else nominal_srate

    # Marker listesi oluştur
    markers: List[Tuple[float, str]] = []
    if marker_stream is not None:
        m_ts = np.asarray(marker_stream.get("time_stamps", []))
        m_series = marker_stream.get("time_series", [])
        for ts, item in zip(m_ts, m_series):
            # item liste veya string olabilir
            if isinstance(item, (list, tuple, np.ndarray)):
                val = str(item[0]) if len(item) > 0 else ""
            else:
                val = str(item)
            val = val.strip()
            if val:
                markers.append((float(ts), val))
        markers.sort(key=lambda x: x[0])

    # Meta veriler
    desc = xon_stream["info"].get("desc", [{}])[0]
    impedances = _parse_impedances_from_desc(desc)

    # Dosya adından sub/ses/run çıkarımı
    fname = file_path.name
    sub_match = re.search(r"sub-([A-Za-z0-9]+)", fname)
    ses_match = re.search(r"ses-([A-Za-z0-9]+)", fname)
    run_match = re.search(r"run-(\d+)", fname)

    meta: Dict[str, Any] = {
        "source_file": str(file_path),
        "subject": sub_match.group(1) if sub_match else "unknown",
        "session": ses_match.group(1) if ses_match else "unknown",
        "run": int(run_match.group(1)) if run_match else 1,
        "impedances": impedances,
        "nominal_srate": nominal_srate,
        "effective_srate": effective_srate,
        "stream_name": xon_stream["info"].get("name", [""])[0],
        "channel_count": int(xon_stream["info"].get("channel_count", [11])[0]),
    }

    return Recording(
        eeg=eeg_data,
        eeg_ts=time_stamps,
        acc=acc_data,
        srate=srate,
        ch_names=list(eeg_ch_names),
        markers=markers,
        meta=meta,
    )
