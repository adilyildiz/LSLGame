"""Nörofizyolojik Doğrulama ve ERD/ERS Analizi Modülü.

PLAN.md Faz 4.2 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- C3, Cz, C4 için sınıf başına ERD/ERS zaman-frekans haritaları (referans: sabitleme dönemi). Çıktı PNG.
- Kanal x Frekans r² (Fisher) ayırt edicilik haritası. Çıktı PNG + sayısal matris.
- EMG kontrolü: 30-45 Hz bandında sınıflar arası fark permütasyon testiyle kontrol edilir.
  p < 0.05 ise açık bir UYARI üretilir (kas karıştırıcısı tespiti).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use("Agg")  # Başsız (headless) çalıştırma
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal, stats

from src.processing.epochs import Epochs

logger = logging.getLogger(__name__)


def compute_erd_time_frequency(
    epochs: Epochs,
    channels: Sequence[str] = ("C3", "Cz", "C4"),
    fmin: float = 6.0,
    fmax: float = 32.0,
    nperseg: int = 64,
    noverlap: int = 56,
) -> Dict[str, Dict[str, Any]]:
    """C3, Cz, C4 için sınıflara göre zaman-frekans ERD/ERS haritalarını hesaplar.

    Formül: ERD% = (A - R) / R * 100
    - A: İmgeleme dönemindeki zaman-frekans gücü
    - R: Sabitleme (fixation baseline) referans gücü
    """
    srate = epochs.srate
    ch_names = epochs.ch_names
    unique_classes = sorted(list(set(epochs.labels)))

    results: Dict[str, Dict[str, Any]] = {}

    for ch in channels:
        if ch not in ch_names:
            continue
        ch_idx = ch_names.index(ch)
        results[ch] = {}

        for cls in unique_classes:
            cls_mask = (epochs.labels == cls)
            if not np.any(cls_mask):
                continue

            # Aktif imgeleme epokları (n_cls_epochs, n_times)
            cls_data = epochs.data[cls_mask, :, ch_idx]

            # Spektrogram hesapla
            # fs=srate, frekanslar fmin...fmax aralığında filtrelenir
            f, t, Sxx = signal.spectrogram(
                cls_data,
                fs=srate,
                nperseg=nperseg,
                noverlap=noverlap,
                axis=-1,
                scaling="spectrum",
            )
            # Sxx: (n_cls_epochs, n_freqs, n_times)
            freq_mask = (f >= fmin) & (f <= fmax)
            f_sub = f[freq_mask]
            P_active = np.mean(Sxx[:, freq_mask, :], axis=0)  # (n_freqs_sub, n_times)

            # Referans güç (baseline)
            if epochs.baselines is not None and epochs.baselines.shape[0] == len(epochs):
                cls_base = epochs.baselines[cls_mask, :, ch_idx]
                f_b, _, Sxx_b = signal.spectrogram(
                    cls_base,
                    fs=srate,
                    nperseg=nperseg,
                    noverlap=noverlap,
                    axis=-1,
                    scaling="spectrum",
                )
                freq_mask_b = (f_b >= fmin) & (f_b <= fmax)
                # (n_epochs, n_freqs, n_times) -> (n_freqs, 1)
                P_base = np.mean(Sxx_b[:, freq_mask_b, :], axis=(0, 2))[:, None]
            else:
                # Baseline yoksa imgelemenin ilk 0.5 saniyesi referans alınır
                P_base = np.mean(P_active[:, :max(1, int(P_active.shape[1] * 0.15))], axis=1, keepdims=True)

            P_base = np.maximum(P_base, 1e-12)
            erd_map = np.squeeze(((P_active - P_base) / P_base) * 100.0)  # (n_freqs, n_times)

            results[ch][cls] = {
                "erd": erd_map,
                "freqs": f_sub,
                "times": t + epochs.times[0],
            }

    return results


def plot_erd_time_frequency(
    erd_data: Dict[str, Dict[str, Any]],
    output_png: Union[str, Path],
    title_suffix: str = "",
) -> None:
    """ERD/ERS haritalarını PNG olarak çizer ve kaydeder."""
    channels = [ch for ch in ("C3", "Cz", "C4") if ch in erd_data]
    if not channels:
        return

    first_ch = channels[0]
    classes = list(erd_data[first_ch].keys())
    if not classes:
        return

    n_rows = len(classes)
    n_cols = len(channels)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3 * n_rows), squeeze=False)
    vmax = 60.0
    vmin = -60.0

    im = None
    for r, cls in enumerate(classes):
        for c, ch in enumerate(channels):
            ax = axes[r, c]
            if cls in erd_data[ch]:
                entry = erd_data[ch][cls]
                erd = entry["erd"]
                freqs = entry["freqs"]
                times = entry["times"]

                im = ax.pcolormesh(
                    times,
                    freqs,
                    erd,
                    cmap="RdBu_r",
                    vmin=vmin,
                    vmax=vmax,
                    shading="auto",
                )
                ax.set_title(f"{ch} — {cls}")
                ax.set_ylabel("Frekans (Hz)")
                if r == n_rows - 1:
                    ax.set_xlabel("Zaman (sn)")
            else:
                ax.axis("off")

    fig.subplots_adjust(right=0.88, hspace=0.35, wspace=0.25)
    cbar_ax = fig.add_axes([0.90, 0.15, 0.02, 0.7])
    cbar = fig.colorbar(im, cax=cbar_ax)
    cbar.set_label("ERD / ERS (%) [Mavi: ERD, Kırmızı: ERS]")

    fig.suptitle(f"Zaman-Frekans ERD/ERS Haritaları {title_suffix}".strip(), fontsize=14)
    out_path = Path(output_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def compute_r2_map(
    epochs: Epochs,
    fmin: float = 4.0,
    fmax: float = 35.0,
    n_fft: int = 128,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Kanal x Frekans r² (veya Fisher ayırt edicilik) matrisini hesaplar.

    Dönüş:
    - r2_matrix: (n_channels, n_freqs)
    - freqs: (n_freqs,)
    - ch_names: kanal adları
    """
    srate = epochs.srate
    data = epochs.data  # (n_epochs, n_times, n_channels)
    ch_names = epochs.ch_names
    labels = epochs.labels
    unique_classes = sorted(list(set(labels)))

    n_epochs, n_times, n_channels = data.shape

    # Welch PSD hesapla
    # freqs: (n_freqs,), psd: (n_epochs, n_channels, n_freqs)
    f, psd = signal.welch(
        data,
        fs=srate,
        nperseg=min(n_fft, n_times),
        axis=1,
        scaling="density",
    )
    # psd boyutu: (n_epochs, n_freqs, n_channels) -> transpoze et: (n_epochs, n_channels, n_freqs)
    psd = np.swapaxes(psd, 1, 2)

    freq_mask = (f >= fmin) & (f <= fmax)
    f_sub = f[freq_mask]
    psd_sub = psd[:, :, freq_mask]  # (n_epochs, n_channels, n_freqs_sub)

    n_freqs = len(f_sub)
    r2_mat = np.zeros((n_channels, n_freqs), dtype=np.float64)

    # 2-sınıf ise signed r², >2 sınıf ise tek yönlü ANOVA F / eta^2
    if len(unique_classes) == 2:
        c1, c2 = unique_classes[0], unique_classes[1]
        m1 = (labels == c1)
        m2 = (labels == c2)

        for ch in range(n_channels):
            for fi in range(n_freqs):
                x1 = psd_sub[m1, ch, fi]
                x2 = psd_sub[m2, ch, fi]
                # Nokta-çift serili r^2
                mean1, mean2 = np.mean(x1), np.mean(x2)
                var1, var2 = np.var(x1), np.var(x2)
                n1, n2 = len(x1), len(x2)
                pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
                denom = (n1 + n2) * pooled_var + (n1 * n2 / (n1 + n2)) * ((mean1 - mean2) ** 2)
                if denom > 1e-12:
                    val = (n1 * n2 * ((mean1 - mean2) ** 2)) / ((n1 + n2) * denom)
                    # Yön: c1 > c2 ise pozitif
                    direction = 1.0 if mean1 >= mean2 else -1.0
                    r2_mat[ch, fi] = direction * val
    else:
        # Çok sınıflı durum: One-way ANOVA F-değeri / eta^2
        for ch in range(n_channels):
            for fi in range(n_freqs):
                groups = [psd_sub[labels == c, ch, fi] for c in unique_classes if np.sum(labels == c) > 0]
                if len(groups) > 1:
                    f_val, _ = stats.f_oneway(*groups)
                    if np.isfinite(f_val):
                        # F-skorunu normalize et (eta-kare yaklaşımı)
                        df_between = len(groups) - 1
                        df_within = n_epochs - len(groups)
                        eta2 = (f_val * df_between) / (f_val * df_between + df_within)
                        r2_mat[ch, fi] = eta2

    return r2_mat, f_sub, ch_names


def plot_r2_map(
    r2_mat: np.ndarray,
    freqs: np.ndarray,
    ch_names: List[str],
    output_png: Union[str, Path],
    title: str = "Kanal × Frekans Ayırt Edicilik (r²) Haritası",
) -> None:
    """r² haritasını PNG olarak kaydeder."""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    vlim = max(0.1, np.max(np.abs(r2_mat)))

    im = ax.imshow(
        r2_mat,
        aspect="auto",
        cmap="coolwarm",
        vmin=-vlim,
        vmax=vlim,
        extent=[freqs[0], freqs[-1], len(ch_names) - 0.5, -0.5],
    )
    ax.set_yticks(np.arange(len(ch_names)))
    ax.set_yticklabels(ch_names)
    ax.set_xlabel("Frekans (Hz)")
    ax.set_ylabel("Kanal")
    ax.set_title(title)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Signed r² / Ayırt Edicilik Skoru")

    out_path = Path(output_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def check_emg_confound(
    epochs: Epochs,
    fmin: float = 30.0,
    fmax: float = 45.0,
    n_permutations: int = 500,
    seed: Optional[int] = 42,
) -> Tuple[float, bool, str, Dict[str, Any]]:
    """30-45 Hz bandında sınıflar arası güç farkını permütasyon testiyle denetler.

    PLAN 4.2 ve Görev 07 (D2) uyarınca:
    EMG kontrolü bant geçiren filtreden geçmiş epochs.data yerine, yalnızca
    50/100 Hz çentikten geçmiş geniş bantlı epochs.raw_data üzerinde çalışır.
    Eğer 30-45 Hz kas (EMG) bandında sınıflar arası fark istatistiksel olarak
    anlamlıysa (p < 0.05), sınıflandırma başarısının beyin ritminden değil kas
    aktivitesinden kaynaklandığını belirten açık bir UYARI üretir.

    Dönüş:
    - p_value: Permütasyon p değeri
    - has_warning: bool (p < 0.05 ise True)
    - warning_msg: Uyarı mesajı metni
    - details: Sayısal istatistikler
    """
    if epochs.raw_data is None:
        raise ValueError("EMG kontrolü için Epochs.raw_data gereklidir (raw_data None olamaz).")

    srate = epochs.srate
    data = epochs.raw_data  # (n_epochs, n_times, n_channels)
    labels = epochs.labels
    ch_names = epochs.ch_names
    unique_classes = sorted(list(set(labels)))

    if len(unique_classes) < 2:
        return 1.0, False, "", {}

    # 30-45 Hz band gücünü hesapla
    nyq = 0.5 * srate
    if nyq <= fmin:
        return 1.0, False, "", {}

    high = min(nyq - 0.5, fmax)
    sos = signal.butter(3, [fmin / nyq, high / nyq], btype="bandpass", output="sos")

    n_epochs, n_times, n_channels = data.shape
    emg_powers = np.zeros((n_epochs, n_channels), dtype=np.float64)

    for i in range(n_epochs):
        filt = signal.sosfilt(sos, data[i], axis=0)
        # Kanal bazında log-güç
        emg_powers[i] = np.log(np.var(filt, axis=0) + 1e-12)

    def _calc_max_f(lbls: np.ndarray) -> float:
        max_f = 0.0
        for ch in range(n_channels):
            groups = [emg_powers[lbls == c, ch] for c in unique_classes if np.sum(lbls == c) > 0]
            if len(groups) > 1:
                f_val, _ = stats.f_oneway(*groups)
                if np.isfinite(f_val) and f_val > max_f:
                    max_f = float(f_val)
        return max_f

    # Gözlenen test istatistiği: Kanallar arası maksimum One-way ANOVA F değeri
    f_obs = _calc_max_f(labels)

    # Permütasyon testi
    rng = np.random.default_rng(seed)
    perm_f = np.zeros(n_permutations, dtype=np.float64)

    perm_labels = np.array(labels, copy=True)
    for b in range(n_permutations):
        rng.shuffle(perm_labels)
        perm_f[b] = _calc_max_f(perm_labels)

    p_value = float(np.sum(perm_f >= f_obs) + 1) / float(n_permutations + 1)
    has_warning = bool(p_value < 0.05)

    if has_warning:
        warning_msg = (
            f"UYARI: 30-45 Hz kas (EMG) bandında sınıflar arası anlamlı fark tespit edildi "
            f"(p={p_value:.4f}, F={f_obs:.2f}). Sınıflandırma başarısı beyin ritimlerinden "
            f"değil, kas aktivitesinden (çene/yüz) kaynaklanıyor olabilir!"
        )
        logger.warning(warning_msg)
    else:
        warning_msg = (
            f"EMG Kontrolü Geçti: 30-45 Hz bandında sınıflar arası anlamlı fark tespit edilmedi "
            f"(p={p_value:.4f}, F={f_obs:.2f}). Kas karıştırıcısı riski düşük."
        )

    # Ortalama log-güçler (tüm kanallar üzerinden özet)
    mean_powers_across_channels = np.mean(emg_powers, axis=1)
    details = {
        "p_value": p_value,
        "f_stat": float(f_obs),
        "f_perm_95": float(np.percentile(perm_f, 95)),
        "class_means": {c: float(np.mean(mean_powers_across_channels[labels == c])) for c in unique_classes},
        "has_warning": has_warning,
    }

    return p_value, has_warning, warning_msg, details
