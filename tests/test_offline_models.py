"""Model Başarımı, Sanity ve EMG Karıştırıcı Testleri.

PLAN.md Faz 4.3, 4.4, Faz 17.3 ve Görev 06 Madde 8 (4, 5, 6, 7) uyarınca:
4. Sinyal varken: erd_power_drop=0.4, mi2 (left/right), 4 run -> en az bir model CV >= %75, perm p < 0.05.
5. Sinyal yokken (Sanity, PLAN 17.3): erd_power_drop=0.0 -> tüm modeller %35-%65 arası şans seviyesinde, perm p > 0.05.
6. Etiket karıştırma: etiketler karıştırılınca doğruluk şans seviyesine düşmeli.
7. EMG karıştırıcı: emg_confound senaryosunda EMG uyarısı üretilmeli, normal senaryoda üretilmemeli.
"""

import numpy as np
import pytest

from src.models.evaluation import evaluate_session_cv
from src.models.pipelines import build_pipelines
from src.processing.epochs import extract_epochs
from src.processing.erd_analysis import check_emg_confound
from src.simulation.offline_dataset import generate_offline_dataset


def test_signal_present_accuracy_and_permutation():
    """Sinyal varken (erd=0.4, 2 sınıf, 4 run) en az bir model >= %75 olmalı ve p < 0.05."""
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)
    models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)

    results = evaluate_session_cv(models, epochs, n_permutations=25, seed=42)

    best_acc = results["best_accuracy"]
    perm_p = results["permutation_test"]["p_value"]

    assert best_acc >= 0.75, f"En iyi model doğruluğu <%75: {best_acc:.2%}"
    assert perm_p < 0.05, f"Permütasyon testi p-değeri >= 0.05: {perm_p:.4f}"


def test_no_signal_sanity_leakage_check():
    """Sinyal yokken (erd=0.0, PLAN 17.3) tüm modeller şans seviyesinde (%35-%65) kalmalı ve p > 0.05 olmalı."""
    rec = generate_offline_dataset(
        erd_power_drop=0.0,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)
    models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)

    results = evaluate_session_cv(models, epochs, n_permutations=25, seed=42)

    perm_p = results["permutation_test"]["p_value"]
    assert perm_p > 0.05, f"Sinyal yokken permütasyon p < 0.05 çıktı (veri sızıntısı şüphesi): {perm_p:.4f}"

    for m_name, m_res in results["models"].items():
        acc = m_res["accuracy"]
        assert 0.35 <= acc <= 0.65, f"Model {m_name} şans aralığında (%35-%65) değil: {acc:.2%}"


def test_label_shuffling_drops_to_chance():
    """Gerçek veride etiketler karıştırılınca doğruluk şans seviyesine düşmeli."""
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)

    # Etiketleri karıştır
    rng = np.random.default_rng(999)
    shuffled_labels = rng.permutation(epochs.labels)
    epochs_shuffled = extract_epochs(rec)
    epochs_shuffled.labels = shuffled_labels

    models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)
    results = evaluate_session_cv(models, epochs_shuffled, n_permutations=0, seed=42)

    for m_name, m_res in results["models"].items():
        acc = m_res["accuracy"]
        assert 0.35 <= acc <= 0.65, f"Karıştırılmış etiketlerde {m_name} şans seviyesine düşmedi: {acc:.2%}"


def test_emg_confound_detection():
    """emg_confound senaryosunda EMG uyarısı üretilmeli, normal senaryoda üretilmemeli."""
    # 1. Normal senaryo
    rec_normal = generate_offline_dataset(erd_power_drop=0.4, emg_confound=False, seed=42)
    ep_normal = extract_epochs(rec_normal, filter_mode=None)
    p_norm, warn_norm, msg_norm, _ = check_emg_confound(ep_normal, n_permutations=50, seed=42)

    assert not warn_norm, f"Normal senaryoda sahte EMG uyarısı üretildi: p={p_norm:.4f}"
    assert p_norm >= 0.05

    # 2. EMG Confound senaryosu (yalnızca kas aktivitesiyle ayrışan sınıflar)
    rec_emg = generate_offline_dataset(erd_power_drop=0.0, emg_confound=True, seed=42)
    ep_emg = extract_epochs(rec_emg, filter_mode=None)
    p_emg, warn_emg, msg_emg, _ = check_emg_confound(ep_emg, n_permutations=50, seed=42)

    assert warn_emg, f"EMG confound senaryosunda uyarı üretilmedi: p={p_emg:.4f}"
    assert p_emg < 0.05
    assert "UYARI" in msg_emg
