"""Sinyal Kalitesi Analizi ve Metrik Hesaplama Modülü.

Kanal başına:
- RMS genlik (µV)
- 10 Hz bant gücü (8–12 Hz, alfa / mu ritmi)
- 50 Hz şebeke gürültüsü bant gücü (48–52 Hz)
- 50 Hz / 10 Hz güç oranı (dB)
- Flatline (düz çizgi) tespiti
- Sinyal kalite durumu (green, yellow, red)
hesaplar ve konsol çıktısı üretir.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL_LABELS = [
    "F3", "F4", "C3", "Cz", "C4", "P3", "P4", "BIP", "accX", "accY", "accZ"
]


def _band_power(
    freqs: np.ndarray,
    psd: np.ndarray,
    band: Tuple[float, float],
) -> float:
    """Belirtilen frekans bandındaki gücü Simpson / trapezoidal integral ile hesaplar."""
    low, high = band
    idx = np.logical_and(freqs >= low, freqs <= high)
    if not np.any(idx):
        return 0.0
    return float(np.trapezoid(psd[idx], freqs[idx]))


def compute_signal_quality(
    data: np.ndarray,
    fs: float = 250.0,
    channel_labels: Optional[List[str]] = None,
    flatline_std_threshold: float = 0.2,
    clipping_threshold_uv: float = 400.0,
) -> Dict[str, Dict[str, Any]]:
    """Çok kanallı veri için kalite metriklerini hesaplar.

    Parameters
    ----------
    data : np.ndarray
        (n_samples, n_channels) veya (n_channels, n_samples) boyutunda dizi.
    fs : float
        Örnekleme frekansı (Hz), varsayılan 250.0.
    channel_labels : list of str, optional
        Kanal etiketleri.
    flatline_std_threshold : float
        Flatline tespiti için standart sapma eşiği (µV).
    clipping_threshold_uv : float
        Kırpılma / aşırı genlik eşiği (µV).

    Returns
    -------
    dict:
        {
            channel_name: {
                'rms': float,
                'power_10hz': float,
                'power_50hz': float,
                'ratio_50_to_10_db': float,
                'is_flatline': bool,
                'is_clipping': bool,
                'status': 'green' | 'yellow' | 'red'
            }
        }
    """
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, np.newaxis]

    # Eğer şekil (n_channels, n_samples) ise ve n_channels < n_samples ise çevir
    if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 16:
        arr = arr.T

    n_samples, n_channels = arr.shape
    if channel_labels is None:
        if n_channels == len(DEFAULT_CHANNEL_LABELS):
            channel_labels = DEFAULT_CHANNEL_LABELS
        else:
            channel_labels = [f"Ch{i+1}" for i in range(n_channels)]

    results: Dict[str, Dict[str, Any]] = {}

    # Welch PSD için nperseg belirleme
    nperseg = min(n_samples, int(2.0 * fs)) if n_samples >= int(fs) else max(16, n_samples)

    for i in range(n_channels):
        ch_name = channel_labels[i] if i < len(channel_labels) else f"Ch{i+1}"
        sig = arr[:, i]

        # Temel istatistikler
        std_val = float(np.std(sig))
        peak_to_peak = float(np.ptp(sig)) if len(sig) > 0 else 0.0
        dc_offset = float(np.mean(sig))
        ac_sig = sig - dc_offset
        rms_val = float(np.sqrt(np.mean(ac_sig**2))) if len(ac_sig) > 0 else 0.0

        is_flatline = std_val < flatline_std_threshold or peak_to_peak < flatline_std_threshold
        is_clipping = bool(np.max(np.abs(sig)) >= clipping_threshold_uv)

        # İvmeölçer kanalları EEG kriterlerine tabi tutulmaz
        is_aux = ch_name.lower().startswith("acc")

        if is_flatline:
            p_10 = 0.0
            p_50 = 0.0
            ratio_db = 0.0
            status = "red" if not is_aux else ("yellow" if std_val < 0.01 else "green")
        else:
            if n_samples >= 16:
                freqs, psd = signal.welch(ac_sig, fs=fs, nperseg=nperseg)
                p_10 = _band_power(freqs, psd, (8.0, 12.0))
                p_50 = _band_power(freqs, psd, (48.0, 52.0))

                eps = 1e-12
                ratio_db = float(10.0 * np.log10((p_50 + eps) / (p_10 + eps)))
            else:
                p_10 = 0.0
                p_50 = 0.0
                ratio_db = 0.0

            # Durum değerlendirmesi (özellikle EEG kanalları için)
            if is_aux:
                status = "green"
            elif is_clipping:
                status = "red"
            elif ratio_db > 10.0 or rms_val > 100.0:
                status = "yellow"
            elif ratio_db <= 3.0 and (3.0 <= rms_val <= 70.0):
                status = "green"
            else:
                status = "yellow"

        results[ch_name] = {
            "channel_index": i,
            "rms": rms_val,
            "power_10hz": p_10,
            "power_50hz": p_50,
            "ratio_50_to_10_db": ratio_db,
            "is_flatline": is_flatline,
            "is_clipping": is_clipping,
            "status": status,
        }

    return results


def format_quality_table(metrics: Dict[str, Dict[str, Any]]) -> str:
    """Kalite metriklerini okunabilir bir ASCII tablo formatında döner."""
    header = (
        f"{'Kanal':<8} | {'RMS (µV)':<10} | {'10 Hz Gücü':<12} | "
        f"{'50 Hz Gücü':<12} | {'50/10 (dB)':<10} | {'Flatline':<9} | {'Durum':<8}"
    )
    sep = "-" * len(header)
    lines = [sep, header, sep]

    status_icons = {
        "green": "[OK]  YEŞİL",
        "yellow": "[WARN] SARI",
        "red": "[ERR] KIRMIZI",
    }

    for ch_name, m in metrics.items():
        st_text = status_icons.get(m["status"], m["status"])
        flat_text = "EVET" if m["is_flatline"] else "HAYIR"
        line = (
            f"{ch_name:<8} | "
            f"{m['rms']:<10.2f} | "
            f"{m['power_10hz']:<12.2e} | "
            f"{m['power_50hz']:<12.2e} | "
            f"{m['ratio_50_to_10_db']:<+10.1f} | "
            f"{flat_text:<9} | "
            f"{st_text}"
        )
        lines.append(line)

    lines.append(sep)
    return "\n".join(lines)


def print_quality_report(metrics: Dict[str, Dict[str, Any]]) -> None:
    """Kalite tablosunu standart çıktıya yazdırır."""
    print(format_quality_table(metrics))


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import pyxdf

    parser = argparse.ArgumentParser(description="X.on Sinyal Kalitesi Aracı")
    parser.add_argument(
        "--xdf",
        type=str,
        default="data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf",
        help="Analiz edilecek XDF dosya yolu",
    )
    args = parser.parse_args()

    xdf_path = Path(args.xdf)
    if not xdf_path.exists():
        print(f"XDF dosyası bulunamadı: {xdf_path}")
        exit(1)

    print(f"Yükleniyor: {xdf_path}")
    streams, _ = pyxdf.load_xdf(str(xdf_path))
    xon_stream = None
    for s in streams:
        if s["info"]["name"][0].startswith("X.on") and s["info"]["type"][0] == "EEG":
            xon_stream = s
            break

    if xon_stream is None:
        print("XDF içinde X.on EEG akışı bulunamadı.")
        exit(1)

    data = np.array(xon_stream["time_series"], dtype=np.float32)
    srate = float(xon_stream["info"]["nominal_srate"][0])
    metrics = compute_signal_quality(data, fs=srate)
    print_quality_report(metrics)
