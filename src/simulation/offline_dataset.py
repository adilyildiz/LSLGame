"""Çevrimdışı (Offline) Sentetik Kalibrasyon Verisi Üreteci.

PLAN.md Faz 4 (4.1-4.2), Faz 17.3 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- Gerçek zamanlı DEĞİL; saniyeler içinde bütün bir oturumluk Recording üretir.
- paradigm.py / calibration.yaml zamanlamasını ve marker adlarını birebir kullanır.
- Pembe gürültü (1/f) + μ (9-12 Hz) + β (20 Hz) + 50 Hz şebeke.
- İmgeleme aralığında yumuşak giriş/çıkışlı (~0.5 sn rampa) sınıfa özgü ERD.
- Deneme başına rastgele ERD şiddeti (erd_power_drop +- %50).
- Artefaktlar: F3/F4 göz kırpma, >30 Hz çene/EMG patlamaları, ivmeölçer hareketi.
- Senaryolar: erd_power_drop, n_runs, profile, seed, session_drift, emg_confound.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import signal

from src.calibration.paradigm import (
    CalibrationStateMachine,
    generate_balanced_sequence,
    load_calibration_config,
)
from src.processing.recording import (
    DEFAULT_ACC_CH_NAMES,
    DEFAULT_EEG_CH_NAMES,
    Recording,
)

logger = logging.getLogger(__name__)


def _generate_pink_noise(n_samples: int, n_channels: int, rng: np.random.Generator) -> np.ndarray:
    """FFT tabanlı 1/f (pembe) gürültü üretimi."""
    white = rng.standard_normal((n_channels, n_samples))
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1.0  # DC bileşeni sıfıra bölmeyi engellemek için

    # 1 / sqrt(f) pembe gürültü güç spektrumu genliği
    scale = 1.0 / np.sqrt(freqs)
    scale[0] = 0.0

    fft_white = np.fft.rfft(white, axis=-1)
    fft_pink = fft_white * scale
    pink = np.fft.irfft(fft_pink, n=n_samples, axis=-1)

    # Standart sapmayı tipik EEG arka plan seviyesine (~8 uV) getir
    pink = pink / (np.std(pink, axis=-1, keepdims=True) + 1e-9) * 8.0
    return pink.T  # (n_samples, n_channels)


def _generate_band_oscillations(
    n_samples: int,
    n_channels: int,
    srate: float,
    center_freq: float,
    bandwidth: float,
    std_uv: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Belirli bir bantta (ör. mu veya beta) dar bantlı salınım üretir."""
    white = rng.standard_normal((n_samples, n_channels))
    nyq = 0.5 * srate
    low = max(0.5, center_freq - bandwidth / 2.0) / nyq
    high = min(nyq - 0.5, center_freq + bandwidth / 2.0) / nyq
    sos = signal.butter(3, [low, high], btype="bandpass", output="sos")
    osc = signal.sosfiltfilt(sos, white, axis=0)
    osc = osc / (np.std(osc, axis=0, keepdims=True) + 1e-9) * std_uv
    return osc


def generate_offline_dataset(
    erd_power_drop: float = 0.4,
    n_runs: int = 4,
    trials_per_run: int = 20,
    profile: str = "mi2",
    classes: Optional[Sequence[str]] = None,
    seed: Optional[int] = 42,
    srate: float = 250.0,
    mu_peak_hz: float = 10.0,
    beta_peak_hz: float = 20.0,
    artifact_rate: float = 0.15,
    session_drift: float = 0.0,
    emg_confound: bool = False,
    emg_amplitude: float = 65.0,
    pause_between_runs_sec: float = 5.0,
) -> Recording:
    """Çevrimdışı sentetik bir kalibrasyon oturumu üretir.

    Parametreler:
    - erd_power_drop: Ortalama ERD güç düşüş oranı (0.0 = sinyal yok / şans seviyesi, 0.4 = belirgin ERD).
    - n_runs: Run sayısı (varsayılan 4).
    - trials_per_run: Run başına deneme sayısı (varsayılan 20).
    - profile: Paradigma profili ("mi2", "mi3", "mi5").
    - seed: Tekrarlanabilirlik tohumu.
    - srate: Örnekleme hızı (250 Hz).
    - mu_peak_hz: Kişiye özgü mu tepe frekansı (9-12 Hz arası).
    - beta_peak_hz: Beta tepe frekansı (varsayılan 20 Hz).
    - artifact_rate: Artefaktlı deneme oranı (varsayılan %15).
    - session_drift: Oturumlar/runlar arası kazanç kayması oranı (0.0-0.3).
    - emg_confound: True ise sınıf bilgisi mu/beta'da değil, yalnızca >30 Hz kas aktivitesinde bulunur.
    - emg_amplitude: emg_confound senaryosundaki kas patlaması genliği (uV, varsayılan 65.0).
    """
    rng = np.random.default_rng(seed)

    # Paradigma konfigürasyonu
    try:
        calib_cfg = load_calibration_config()
    except Exception:
        calib_cfg = {}

    timing_cfg = calib_cfg.get("timing", {})
    fixation_sec = float(timing_cfg.get("fixation_sec", 2.0))
    cue_sec = float(timing_cfg.get("cue_sec", 1.0))
    imagery_sec = float(timing_cfg.get("imagery_sec", 4.0))
    rest_min_sec = float(timing_cfg.get("rest_min_sec", 1.5))
    rest_max_sec = float(timing_cfg.get("rest_max_sec", 3.0))

    profiles = calib_cfg.get("profiles", {})
    if classes is not None:
        classes = list(classes)
    elif profile in profiles:
        classes = list(profiles[profile].get("classes", ["left", "right", "rest"]))
    elif profile == "mi2":
        classes = ["left", "right", "rest"]
    elif profile == "mi3":
        classes = ["left", "right", "rest", "feet"]
    elif profile == "mi5":
        classes = ["left", "right", "rest", "feet", "both_hands", "arithmetic"]
    else:
        classes = ["left", "right", "rest"]

    # Kanal eşleme
    ch_names = list(DEFAULT_EEG_CH_NAMES)  # ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]
    c3_idx = ch_names.index("C3")
    cz_idx = ch_names.index("Cz")
    c4_idx = ch_names.index("C4")
    f3_idx = ch_names.index("F3")
    f4_idx = ch_names.index("F4")
    p3_idx = ch_names.index("P3")
    p4_idx = ch_names.index("P4")

    # Markerlar ve deneme zaman çizelgesini oluştur
    markers: List[Tuple[float, str]] = []
    trial_records: List[Dict[str, Any]] = []

    current_time = 100.0  # Başlangıç LSL zamanı
    markers.append((current_time, "session_start"))
    current_time += 1.0

    global_trial = 0
    artifact_trials_meta: Dict[int, str] = {}

    for run_idx in range(n_runs):
        run_seed = (seed + run_idx * 1000) if seed is not None else None
        seq = generate_balanced_sequence(classes=classes, count=trials_per_run, seed=run_seed)

        markers.append((current_time, "run_start"))
        current_time += 0.5

        for trial_in_run, cls in enumerate(seq):
            t_trial_start = current_time
            markers.append((t_trial_start, "trial_start"))
            markers.append((t_trial_start, "fixation_start"))
            current_time += fixation_sec

            t_cue = current_time
            markers.append((t_cue, f"cue_{cls}"))
            current_time += cue_sec

            t_imagery_start = current_time
            markers.append((t_imagery_start, "imagery_start"))
            current_time += imagery_sec

            t_imagery_end = current_time
            markers.append((t_imagery_end, "imagery_end"))
            markers.append((t_imagery_end, "rest_start"))

            rest_dur = float(rng.uniform(rest_min_sec, rest_max_sec))
            current_time += rest_dur

            t_trial_end = current_time
            markers.append((t_trial_end, "trial_end"))

            # Artefakt belirleme
            has_artifact = bool(rng.random() < artifact_rate)
            artifact_type = "none"
            if has_artifact:
                # 3 tip artefakt: blink, emg, movement
                artifact_type = rng.choice(["blink", "emg", "movement"])
                artifact_trials_meta[global_trial] = artifact_type

            # Deneme başına ERD varyasyonu (+-%50)
            if erd_power_drop > 0.0 and not emg_confound:
                drop_scale = float(rng.uniform(0.5, 1.5))
                effective_drop = min(0.95, max(0.05, erd_power_drop * drop_scale))
            else:
                effective_drop = 0.0

            trial_records.append({
                "global_trial": global_trial,
                "run": run_idx,
                "trial_in_run": trial_in_run,
                "class": cls,
                "t_trial_start": t_trial_start,
                "t_fixation_start": t_trial_start,
                "t_cue": t_cue,
                "t_imagery_start": t_imagery_start,
                "t_imagery_end": t_imagery_end,
                "t_rest_start": t_imagery_end,
                "t_trial_end": t_trial_end,
                "has_artifact": has_artifact,
                "artifact_type": artifact_type,
                "effective_drop": effective_drop,
            })
            global_trial += 1

        markers.append((current_time, "run_end"))
        current_time += 0.5
        if run_idx < n_runs - 1:
            markers.append((current_time, "pause_start"))
            current_time += pause_between_runs_sec
            markers.append((current_time, "pause_end"))
            current_time += 0.5

    markers.append((current_time, "session_end"))
    current_time += 1.0

    total_duration = current_time - 100.0
    n_total_samples = int(np.ceil(total_duration * srate))
    eeg_ts = 100.0 + np.arange(n_total_samples) / srate

    # 1. Temel arka plan pembe gürültü
    pink_noise = _generate_pink_noise(n_total_samples, len(ch_names), rng)

    # 2. Mu ve Beta salınımları
    mu_osc = _generate_band_oscillations(
        n_total_samples, len(ch_names), srate, center_freq=mu_peak_hz, bandwidth=2.5, std_uv=12.0, rng=rng
    )
    beta_osc = _generate_band_oscillations(
        n_total_samples, len(ch_names), srate, center_freq=beta_peak_hz, bandwidth=4.0, std_uv=6.0, rng=rng
    )

    # 3. 50 Hz şebeke gürültüsü
    line_noise_amp = 2.5  # uV
    line_noise = line_noise_amp * np.sin(2 * np.pi * 50.0 * eeg_ts[:, None] + rng.uniform(0, 2 * np.pi, len(ch_names)))

    # ERD Modülasyon Zarfları (kanal x zaman)
    # 1.0 = tam güç, 0.6 = %40 düşüş (ERD)
    mu_envelope = np.ones((n_total_samples, len(ch_names)), dtype=np.float64)
    beta_envelope = np.ones((n_total_samples, len(ch_names)), dtype=np.float64)

    # EMG ek sinyal dizisi (n_total_samples, len(ch_names))
    emg_signal = np.zeros((n_total_samples, len(ch_names)), dtype=np.float64)

    # İvmeölçer sinyali: varsayılan (0, 0, 1000 mg)
    acc = np.zeros((n_total_samples, 3), dtype=np.float64)
    acc[:, 0] = rng.normal(0.0, 5.0, n_total_samples)
    acc[:, 1] = rng.normal(0.0, 5.0, n_total_samples)
    acc[:, 2] = 1000.0 + rng.normal(0.0, 5.0, n_total_samples)

    ramp_samples = int(0.5 * srate)

    for tr in trial_records:
        cls = tr["class"]
        drop = tr["effective_drop"]
        t_start = tr["t_imagery_start"]
        t_end = tr["t_imagery_end"]

        idx_start = int(round((t_start - 100.0) * srate))
        idx_end = int(round((t_end - 100.0) * srate))
        dur_samples = idx_end - idx_start

        if dur_samples <= 0 or idx_end > n_total_samples:
            continue

        # Rampa oluştur (girişte 0->1, çıkışta 1->0)
        ramp_in = np.linspace(0.0, 1.0, min(ramp_samples, dur_samples // 2))
        ramp_out = np.linspace(1.0, 0.0, min(ramp_samples, dur_samples // 2))
        flat_len = dur_samples - len(ramp_in) - len(ramp_out)
        flat = np.ones(max(0, flat_len))
        envelope_weight = np.concatenate([ramp_in, flat, ramp_out])[:dur_samples]

        # Sınıfa özgü ERD düşüşleri (mu ve beta genliğinde drop çarpanı)
        # Güç P ~ A^2 -> güç düşüşü drop ise genlik çarpanı sqrt(1 - drop)
        amp_factor = np.sqrt(max(0.01, 1.0 - drop))

        if not emg_confound and drop > 0.0:
            ers_amp = 0.25 * drop
            if cls == "left":
                # Sol el -> kontralateral C4 ERD
                mu_envelope[idx_start:idx_end, c4_idx] -= (1.0 - amp_factor) * envelope_weight
                beta_envelope[idx_start:idx_end, c4_idx] -= (1.0 - amp_factor) * envelope_weight
                # İpsilateral C3 hafif senkronizasyon (ERS, drop ile orantılı)
                mu_envelope[idx_start:idx_end, c3_idx] += ers_amp * envelope_weight
            elif cls == "right":
                # Sağ el -> kontralateral C3 ERD
                mu_envelope[idx_start:idx_end, c3_idx] -= (1.0 - amp_factor) * envelope_weight
                beta_envelope[idx_start:idx_end, c3_idx] -= (1.0 - amp_factor) * envelope_weight
                # İpsilateral C4 hafif ERS (drop ile orantılı)
                mu_envelope[idx_start:idx_end, c4_idx] += ers_amp * envelope_weight
            elif cls == "feet":
                # Ayak -> verteks Cz ERD
                mu_envelope[idx_start:idx_end, cz_idx] -= (1.0 - amp_factor) * envelope_weight
                beta_envelope[idx_start:idx_end, cz_idx] -= (1.0 - amp_factor) * envelope_weight
            elif cls == "both_hands":
                # İki el -> C3 ve C4 ikili ERD
                mu_envelope[idx_start:idx_end, c3_idx] -= (1.0 - amp_factor) * envelope_weight
                beta_envelope[idx_start:idx_end, c3_idx] -= (1.0 - amp_factor) * envelope_weight
                mu_envelope[idx_start:idx_end, c4_idx] -= (1.0 - amp_factor) * envelope_weight
                beta_envelope[idx_start:idx_end, c4_idx] -= (1.0 - amp_factor) * envelope_weight
            elif cls == "arithmetic":
                # Aritmetik -> frontal ve paryetal modülasyon
                mu_envelope[idx_start:idx_end, f3_idx] -= (1.0 - amp_factor) * 0.8 * envelope_weight
                mu_envelope[idx_start:idx_end, f4_idx] -= (1.0 - amp_factor) * 0.8 * envelope_weight
                mu_envelope[idx_start:idx_end, p3_idx] -= (1.0 - amp_factor) * 0.8 * envelope_weight
                mu_envelope[idx_start:idx_end, p4_idx] -= (1.0 - amp_factor) * 0.8 * envelope_weight
            elif cls == "rest":
                # Dinlenme: ERD yok
                pass
        elif emg_confound:
            # EMG Confound Senaryosu:
            # Beyin ritimlerinde sınıf farkı YOK.
            # Sınıf bilgisi YALNIZCA >30 Hz kas aktivitesinde mevcut!
            if cls == "left":
                # C4/paryetal kas patlaması (35-45 Hz)
                t_vec = eeg_ts[idx_start:idx_end]
                emg_burst = emg_amplitude * np.sin(2 * np.pi * 38.0 * t_vec) * envelope_weight
                emg_signal[idx_start:idx_end, c4_idx] += emg_burst
                emg_signal[idx_start:idx_end, p4_idx] += 0.5 * emg_burst
            elif cls == "right":
                # C3/paryetal kas patlaması
                t_vec = eeg_ts[idx_start:idx_end]
                emg_burst = emg_amplitude * np.sin(2 * np.pi * 38.0 * t_vec) * envelope_weight
                emg_signal[idx_start:idx_end, c3_idx] += emg_burst
                emg_signal[idx_start:idx_end, p3_idx] += 0.5 * emg_burst
            elif cls == "rest":
                # Kas aktivitesi yok
                pass

        # Belirlenen denemelere artefakt ekle
        if tr["has_artifact"]:
            art_type = tr["artifact_type"]
            # Artefakt imgeleme penceresi içinde oluşsun (epoklar tarafından yakalanabilmesi için)
            art_center_t = float(rng.uniform(tr["t_imagery_start"] + 0.8, tr["t_imagery_end"] - 0.8))
            art_center_idx = int(round((art_center_t - 100.0) * srate))

            if art_type == "blink":
                # Göz kırpma: F3 ve F4 kanallarında yavaş, büyük pozitif tepe (0.3 sn, ~120 uV)
                blink_len = int(0.35 * srate)
                b_start = max(0, art_center_idx - blink_len // 2)
                b_end = min(n_total_samples, b_start + blink_len)
                actual_len = b_end - b_start
                if actual_len > 0:
                    blink_wave = 130.0 * np.sin(np.pi * np.linspace(0, 1, actual_len)) ** 2
                    pink_noise[b_start:b_end, f3_idx] += blink_wave
                    pink_noise[b_start:b_end, f4_idx] += blink_wave * 0.95
                    # C3/C4'e hafif yayılma
                    pink_noise[b_start:b_end, c3_idx] += blink_wave * 0.15
                    pink_noise[b_start:b_end, c4_idx] += blink_wave * 0.15

            elif art_type == "emg":
                # Çene sıkma / EMG: Tüm kanallarda >30 Hz yüksek güç patlaması (0.5 sn)
                emg_len = int(0.5 * srate)
                e_start = max(0, art_center_idx - emg_len // 2)
                e_end = min(n_total_samples, e_start + emg_len)
                actual_len = e_end - e_start
                if actual_len > 0:
                    t_slice = eeg_ts[e_start:e_end]
                    # Yüksek frekanslı çoklu tonlar + gürültü
                    burst = (
                        rng.normal(0, 45.0, (actual_len, len(ch_names)))
                        + 35.0 * np.sin(2 * np.pi * 42.0 * t_slice[:, None])
                        + 25.0 * np.sin(2 * np.pi * 58.0 * t_slice[:, None])
                    )
                    emg_signal[e_start:e_end, :] += burst

            elif art_type == "movement":
                # İvmeölçer hareketi: baş sarsıntısı / kımıldama
                mov_len = int(0.8 * srate)
                m_start = max(0, art_center_idx - mov_len // 2)
                m_end = min(n_total_samples, m_start + mov_len)
                actual_len = m_end - m_start
                if actual_len > 0:
                    spike = 800.0 * np.sin(np.pi * np.linspace(0, 2, actual_len))
                    acc[m_start:m_end, 0] += spike
                    acc[m_start:m_end, 1] += spike * 0.5
                    acc[m_start:m_end, 2] += spike * 0.8
                    # EEG'ye hareket artefaktı kayması
                    slow_drift = 90.0 * np.sin(np.pi * np.linspace(0, 1, actual_len))
                    pink_noise[m_start:m_end, :] += slow_drift[:, None]

    # Zarf sınırlandırma (negatif olamaz)
    mu_envelope = np.clip(mu_envelope, 0.05, 2.0)
    beta_envelope = np.clip(beta_envelope, 0.05, 2.0)

    # Oturum / run bazlı kayma (session_drift)
    if session_drift > 0.0:
        for run_idx in range(n_runs):
            run_gain = 1.0 + session_drift * (run_idx / max(1, n_runs - 1) - 0.5)
            # Run zaman aralığını bul
            run_trials = [t for t in trial_records if t["run"] == run_idx]
            if run_trials:
                r_start = int(round((run_trials[0]["t_trial_start"] - 100.0) * srate))
                r_end = int(round((run_trials[-1]["t_trial_end"] - 100.0) * srate))
                mu_envelope[r_start:r_end, :] *= run_gain
                beta_envelope[r_start:r_end, :] *= run_gain

    # Toplam EEG sinyali
    eeg = pink_noise + (mu_osc * mu_envelope) + (beta_osc * beta_envelope) + line_noise + emg_signal

    meta: Dict[str, Any] = {
        "synthetic": True,
        "erd_power_drop": erd_power_drop,
        "n_runs": n_runs,
        "trials_per_run": trials_per_run,
        "profile": profile,
        "seed": seed,
        "srate": srate,
        "mu_peak_hz": mu_peak_hz,
        "beta_peak_hz": beta_peak_hz,
        "session_drift": session_drift,
        "emg_confound": emg_confound,
        "emg_amplitude": emg_amplitude,
        "artifact_trials": artifact_trials_meta,
        "trial_records": trial_records,
        "impedances": {
            "F3": 25000.0,
            "F4": 28000.0,
            "C3": 21000.0,
            "Cz": 18000.0,
            "C4": 22000.0,
            "P3": 30000.0,
            "P4": 31000.0,
        },
        "subject": "sim-01",
        "session": "ses-01",
    }

    return Recording(
        eeg=eeg,
        eeg_ts=eeg_ts,
        acc=acc,
        srate=srate,
        ch_names=ch_names,
        markers=markers,
        meta=meta,
    )
