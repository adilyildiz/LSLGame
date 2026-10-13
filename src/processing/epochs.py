"""Epoklama (Epoching) Modülü.

PLAN.md Faz 4.1 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- Epoklama aralığı: imagery_start + 0.5 ... + 3.5 sn (ilk 0.5 sn reaksiyon süresi atlanır).
- Etiketler cue_* marker'ından alınır.
- Deneme ve run indeksleri takip edilir (GroupKFold için run_indices).
- Sürekli EEG verisinin nedensel veya sıfır-faz filtrelenmesiyle uç transiyentleri önlenir.
- Taban çizgisi (baseline) epokları çıkarımı (ERD/ERS analizi için).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from src.processing.filters import apply_bandpass, apply_notch, filter_eeg
from src.processing.recording import Recording

logger = logging.getLogger(__name__)


@dataclass
class Epochs:
    """Epoklanmış EEG ve meta veri yapısı."""
    data: np.ndarray  # (n_epochs, n_times, n_channels)
    times: np.ndarray  # (n_times,) göreli saniye (tmin...tmax)
    labels: np.ndarray  # (n_epochs,) string etiketler ('left', 'right' vb.)
    run_indices: np.ndarray  # (n_epochs,) int run numaraları
    trial_indices: np.ndarray  # (n_epochs,) int deneme indeksleri
    srate: float
    ch_names: List[str]
    raw_data: Optional[np.ndarray] = None  # (n_epochs, n_times, n_channels) ham/geniş bant
    acc: Optional[np.ndarray] = None  # (n_epochs, n_times, 3)
    baselines: Optional[np.ndarray] = None  # (n_epochs, n_base_times, n_channels)
    meta: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self.data = np.asarray(self.data, dtype=np.float64)
        self.times = np.asarray(self.times, dtype=np.float64)
        self.labels = np.asarray(self.labels, dtype=object)
        self.run_indices = np.asarray(self.run_indices, dtype=int)
        self.trial_indices = np.asarray(self.trial_indices, dtype=int)

    def __len__(self) -> int:
        return len(self.labels)

    def subset(self, indices: Union[Sequence[int], np.ndarray]) -> Epochs:
        """Belirli indekslerdeki epokları içeren alt küme döner."""
        idx = np.asarray(indices)
        sub_data = self.data[idx]
        sub_labels = self.labels[idx]
        sub_runs = self.run_indices[idx]
        sub_trials = self.trial_indices[idx]
        sub_raw = self.raw_data[idx] if self.raw_data is not None else None
        sub_acc = self.acc[idx] if self.acc is not None else None
        sub_baselines = self.baselines[idx] if self.baselines is not None else None
        sub_meta = [self.meta[i] for i in idx] if self.meta else []

        return Epochs(
            data=sub_data,
            times=self.times,
            labels=sub_labels,
            run_indices=sub_runs,
            trial_indices=sub_trials,
            srate=self.srate,
            ch_names=list(self.ch_names),
            raw_data=sub_raw,
            acc=sub_acc,
            baselines=sub_baselines,
            meta=sub_meta,
        )


def extract_epochs(
    recording: Recording,
    tmin: float = 0.5,
    tmax: float = 3.5,
    baseline_tmin: float = -1.5,
    baseline_tmax: float = -0.5,
    filter_mode: Optional[str] = "causal",
    f_low: float = 8.0,
    f_high: float = 30.0,
    notch_freqs: Sequence[float] = (50.0, 100.0),
) -> Epochs:
    """Recording nesnesinden imgeleme epoklarını çıkarır.

    Parametreler:
    - recording: Recording veri yapısı
    - tmin, tmax: imagery_start'a göre epok penceresi (sn)
    - baseline_tmin, baseline_tmax: imagery_start'a göre sabitleme penceresi (sn)
    - filter_mode: 'causal', 'zero_phase' veya None (ham)
    """
    srate = recording.srate
    eeg = recording.eeg
    eeg_ts = recording.eeg_ts
    acc = recording.acc
    ch_names = recording.ch_names
    markers = recording.markers

    # 1. Ham veriye çentik filtresi uygula (50/100 Hz şebeke gürültüsü temizlenir, ancak bant geçiren uygulanmaz)
    # raw_data yalnızca 50/100 Hz çentikten geçmiş olmalıdır (D2 düzeltmesi)
    notch_mode = filter_mode if filter_mode is not None else "causal"
    if notch_freqs:
        raw_eeg_notched = apply_notch(
            eeg,
            srate=srate,
            freqs=notch_freqs,
            mode=notch_mode,
        )
    else:
        raw_eeg_notched = np.array(eeg, copy=True, dtype=np.float64)

    # 2. Sürekli EEG'yi bant geçiren filtreden geçir
    if filter_mode is not None:
        filtered_eeg = apply_bandpass(
            raw_eeg_notched,
            srate=srate,
            f_low=f_low,
            f_high=f_high,
            mode=filter_mode,
        )
    else:
        filtered_eeg = np.array(raw_eeg_notched, copy=True)

    # Denemeleri marker listesinden eşleştir
    # Her imagery_start'tan hemen önce gelen cue_* marker'ı etiketi belirler
    current_run = 0
    current_cue = "unknown"
    cue_ts = 0.0

    epoch_list: List[np.ndarray] = []
    raw_list: List[np.ndarray] = []
    baseline_list: List[np.ndarray] = []
    acc_list: List[np.ndarray] = []
    labels_list: List[str] = []
    run_list: List[int] = []
    trial_list: List[int] = []
    meta_list: List[Dict[str, Any]] = []

    trial_counter = 0

    for ts, m_text in markers:
        if m_text == "run_start":
            pass
        elif m_text == "run_end":
            current_run += 1
        elif m_text.startswith("cue_"):
            current_cue = m_text.replace("cue_", "")
            cue_ts = ts
        elif m_text == "imagery_start":
            t_event = ts
            # Epok zaman penceresi
            t_start = t_event + tmin
            t_end = t_event + tmax
            idx_start = int(np.searchsorted(eeg_ts, t_start))
            idx_end = int(np.searchsorted(eeg_ts, t_end))

            expected_len = int(round((tmax - tmin) * srate))
            if idx_start < 0 or idx_end > len(eeg_ts) or (idx_end - idx_start) <= 0:
                continue

            chunk = filtered_eeg[idx_start:idx_end]
            if len(chunk) < expected_len:
                pad = np.zeros((expected_len - len(chunk), chunk.shape[1]), dtype=chunk.dtype)
                chunk = np.vstack([chunk, pad])
            elif len(chunk) > expected_len:
                chunk = chunk[:expected_len]

            raw_chunk = raw_eeg_notched[idx_start:idx_end]
            if len(raw_chunk) < expected_len:
                pad = np.zeros((expected_len - len(raw_chunk), raw_chunk.shape[1]), dtype=raw_chunk.dtype)
                raw_chunk = np.vstack([raw_chunk, pad])
            elif len(raw_chunk) > expected_len:
                raw_chunk = raw_chunk[:expected_len]

            # Taban çizgisi (baseline) çıkarımı (fixation periyodu)
            b_start = t_event + baseline_tmin
            b_end = t_event + baseline_tmax
            b_idx_start = max(0, int(np.searchsorted(eeg_ts, b_start)))
            b_idx_end = min(len(eeg_ts), int(np.searchsorted(eeg_ts, b_end)))
            b_expected_len = int(round((baseline_tmax - baseline_tmin) * srate))
            b_chunk = filtered_eeg[b_idx_start:b_idx_end]
            if len(b_chunk) < b_expected_len:
                pad = np.zeros((b_expected_len - len(b_chunk), b_chunk.shape[1]), dtype=b_chunk.dtype)
                b_chunk = np.vstack([b_chunk, pad]) if len(b_chunk) > 0 else np.zeros((b_expected_len, chunk.shape[1]))
            elif len(b_chunk) > b_expected_len:
                b_chunk = b_chunk[:b_expected_len]

            # İvmeölçer kesiti
            if acc is not None and len(acc) == len(eeg_ts):
                acc_chunk = acc[idx_start:idx_end]
                if len(acc_chunk) < expected_len:
                    pad = np.zeros((expected_len - len(acc_chunk), acc_chunk.shape[1]), dtype=acc_chunk.dtype)
                    acc_chunk = np.vstack([acc_chunk, pad])
                elif len(acc_chunk) > expected_len:
                    acc_chunk = acc_chunk[:expected_len]
            else:
                acc_chunk = np.zeros((expected_len, 3), dtype=np.float64)

            epoch_list.append(chunk)
            raw_list.append(raw_chunk)
            baseline_list.append(b_chunk)
            acc_list.append(acc_chunk)
            labels_list.append(current_cue)
            run_list.append(current_run)
            trial_list.append(trial_counter)
            meta_list.append({
                "trial_idx": trial_counter,
                "run_idx": current_run,
                "label": current_cue,
                "imagery_start_ts": ts,
                "cue_ts": cue_ts,
            })
            trial_counter += 1

    if not epoch_list:
        raise ValueError("Hiçbir geçerli imgeleme epoku bulunamadı.")

    data_arr = np.stack(epoch_list, axis=0)  # (n_epochs, n_times, n_channels)
    raw_arr = np.stack(raw_list, axis=0)
    base_arr = np.stack(baseline_list, axis=0)
    acc_arr = np.stack(acc_list, axis=0)
    n_times = data_arr.shape[1]
    times_arr = np.linspace(tmin, tmax, n_times)

    return Epochs(
        data=data_arr,
        times=times_arr,
        labels=np.array(labels_list, dtype=object),
        run_indices=np.array(run_list, dtype=int),
        trial_indices=np.array(trial_list, dtype=int),
        srate=srate,
        ch_names=list(ch_names),
        raw_data=raw_arr,
        acc=acc_arr,
        baselines=base_arr,
        meta=meta_list,
    )
