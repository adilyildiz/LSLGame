"""Artefakt Tespiti ve Reddi Modülü.

PLAN.md Faz 4.1 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- Etiket kullanmadan (etiketsiz/denetimsiz) eşik belirleme.
- Genlik eşiği (peak-to-peak ve mutlak genlik).
- F3/F4 göz kırpma (blink) tespiti.
- >20 Hz EMG gücü (robust z-skor / MAD tabanlı).
- İvmeölçer hareket eşiği (baş kımıldamaları).
- Her reddin nedeni detaylı raporlanır.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import signal

from src.processing.epochs import Epochs

logger = logging.getLogger(__name__)


def detect_artifacts(
    epochs: Epochs,
    amplitude_threshold_uv: float = 95.0,
    peak_to_peak_threshold_uv: float = 160.0,
    blink_threshold_uv: float = 85.0,
    emg_z_threshold: float = 2.8,
    acc_std_threshold_mg: float = 35.0,
) -> Tuple[List[int], List[int], Dict[int, List[str]], Dict[str, Any]]:
    """Epoklar üzerinde etiketsiz artefakt tespiti yapar.

    Dönüş:
    - rejected_indices: Reddedilen epok indeksleri
    - clean_indices: Temiz epok indeksleri
    - reasons: {epoch_idx: ['blink', 'amplitude', ...]}
    - summary: İstatistik özeti
    """
    n_epochs = len(epochs)
    data = epochs.data  # (n_epochs, n_times, n_channels)
    raw_data = epochs.raw_data if epochs.raw_data is not None else data
    acc = epochs.acc  # (n_epochs, n_times, 3)
    srate = epochs.srate
    ch_names = epochs.ch_names

    f3_idx = ch_names.index("F3") if "F3" in ch_names else 0
    f4_idx = ch_names.index("F4") if "F4" in ch_names else 1

    reasons: Dict[int, List[str]] = {}

    # 1. & 2. Genlik ve Göz Kırpma (Blink) Kontrolleri (Ham geniş bant üzerinden)
    for i in range(n_epochs):
        ep_raw = raw_data[i]  # (n_times, n_channels)
        ep_filt = data[i]
        ep_reasons = []

        # Mutlak tepe genliği (hem ham hem filtrelenmiş kontrol edilir)
        max_abs = max(float(np.max(np.abs(ep_raw))), float(np.max(np.abs(ep_filt))))
        ptp = max(float(np.max(np.ptp(ep_raw, axis=0))), float(np.max(np.ptp(ep_filt, axis=0))))

        if max_abs > amplitude_threshold_uv or ptp > peak_to_peak_threshold_uv:
            ep_reasons.append("amplitude")

        # F3/F4 göz kırpma tespiti (özellikle ham sinyalde yavaş büyük tepe)
        f3_max = max(float(np.max(np.abs(ep_raw[:, f3_idx]))), float(np.max(np.abs(ep_filt[:, f3_idx]))))
        f4_max = max(float(np.max(np.abs(ep_raw[:, f4_idx]))), float(np.max(np.abs(ep_filt[:, f4_idx]))))
        if f3_max > blink_threshold_uv or f4_max > blink_threshold_uv:
            ep_reasons.append("blink")

        if ep_reasons:
            reasons[i] = ep_reasons

    # 3. >20 Hz EMG Gücü (Robust z-skor)
    # 25-60 Hz arası filtre uygula
    nyq = 0.5 * srate
    if nyq > 26.0:
        high_cutoff = min(nyq - 1.0, 60.0)
        sos_emg = signal.butter(3, [25.0 / nyq, high_cutoff / nyq], btype="bandpass", output="sos")
        emg_powers = np.zeros(n_epochs, dtype=np.float64)

        for i in range(n_epochs):
            # Kanallar üzerinden ortalama RMS
            filtered = signal.sosfilt(sos_emg, data[i], axis=0)
            emg_powers[i] = np.mean(np.var(filtered, axis=0))

        med = np.median(emg_powers)
        mad = np.median(np.abs(emg_powers - med))
        scale = 1.4826 * mad
        if scale > 1e-9:
            z_scores = (emg_powers - med) / scale
            for i in range(n_epochs):
                if z_scores[i] > emg_z_threshold:
                    if i not in reasons:
                        reasons[i] = []
                    if "emg" not in reasons[i]:
                        reasons[i].append("emg")

    # 4. İvmeölçer Hareket Kontrolü
    if acc is not None and acc.shape[0] == n_epochs:
        for i in range(n_epochs):
            ep_acc = acc[i]  # (n_times, 3)
            acc_std = np.max(np.std(ep_acc, axis=0))
            if acc_std > acc_std_threshold_mg:
                if i not in reasons:
                    reasons[i] = []
                if "movement" not in reasons[i]:
                    reasons[i].append("movement")

    rejected_indices = sorted(list(reasons.keys()))
    clean_indices = [i for i in range(n_epochs) if i not in reasons]

    # İstatistik özeti
    reason_counts = {"amplitude": 0, "blink": 0, "emg": 0, "movement": 0}
    for r_list in reasons.values():
        for r in r_list:
            reason_counts[r] = reason_counts.get(r, 0) + 1

    summary = {
        "total_epochs": n_epochs,
        "rejected_epochs": len(rejected_indices),
        "clean_epochs": len(clean_indices),
        "rejection_ratio": len(rejected_indices) / max(1, n_epochs),
        "reasons_breakdown": reason_counts,
    }

    return rejected_indices, clean_indices, reasons, summary


def reject_artifacts(
    epochs: Epochs,
    amplitude_threshold_uv: float = 95.0,
    peak_to_peak_threshold_uv: float = 160.0,
    blink_threshold_uv: float = 85.0,
    emg_z_threshold: float = 2.8,
    acc_std_threshold_mg: float = 35.0,
) -> Tuple[Epochs, Dict[str, Any]]:
    """Artefaktlı epokları ayıklar ve temiz Epochs nesnesi döner."""
    rejected_indices, clean_indices, reasons, summary = detect_artifacts(
        epochs=epochs,
        amplitude_threshold_uv=amplitude_threshold_uv,
        peak_to_peak_threshold_uv=peak_to_peak_threshold_uv,
        blink_threshold_uv=blink_threshold_uv,
        emg_z_threshold=emg_z_threshold,
        acc_std_threshold_mg=acc_std_threshold_mg,
    )

    clean_epochs = epochs.subset(clean_indices)
    report = {
        "rejected_indices": rejected_indices,
        "clean_indices": clean_indices,
        "reasons": reasons,
        "summary": summary,
    }
    return clean_epochs, report
