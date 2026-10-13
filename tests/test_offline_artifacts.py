"""Artefakt Tespiti ve Reddi Testleri.

PLAN.md Faz 4.1 ve Görev 06 Madde 8.3 uyarınca:
3. Artefakt reddi: üretecin işaretlediği artefaktlı denemelerin >= %80'i yakalanmalı.
   Temiz denemelerin <= %10'u yanlışlıkla reddedilmeli.
   Eşikler etiket kullanmadan belirlenmeli ve her reddin nedeni raporlanmalı.
"""

import numpy as np
import pytest

from src.processing.artifacts import detect_artifacts, reject_artifacts
from src.processing.epochs import extract_epochs
from src.simulation.offline_dataset import generate_offline_dataset


def test_artifact_rejection_sensitivity_and_specificity():
    """Artefaktlı denemelerin en az %80'i yakalanmalı, temizlerin en fazla %10'u reddedilmeli."""
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=4,
        trials_per_run=20,
        artifact_rate=0.20,
        seed=777,
    )
    epochs = extract_epochs(rec)

    rejected_indices, clean_indices, reasons, summary = detect_artifacts(epochs)

    gt_artifacts = set(rec.meta["artifact_trials"].keys())
    assert len(gt_artifacts) > 0, "Sentetik veride artefakt bulunmalıdır."

    rej_set = set(rejected_indices)
    # Doğru pozitifler (yakalanan artefaktlar)
    true_positives = gt_artifacts.intersection(rej_set)
    sensitivity = len(true_positives) / len(gt_artifacts)

    # Yanlış pozitifler (yanlışlıkla reddedilen temiz denemeler)
    clean_gt = set(range(len(epochs))) - gt_artifacts
    false_positives = rej_set - gt_artifacts
    fp_rate = len(false_positives) / len(clean_gt)

    assert sensitivity >= 0.80, f"Artefakt yakalama duyarlılığı <%80: {sensitivity:.2%}"
    assert fp_rate <= 0.10, f"Yanlış pozitif oranı >%10: {fp_rate:.2%}"

    # Reddetme nedenlerinin varlığı ve formatı
    assert len(reasons) == len(rejected_indices)
    for idx, r_list in reasons.items():
        assert len(r_list) > 0
        for r in r_list:
            assert r in ("amplitude", "blink", "emg", "movement")

    # reject_artifacts fonksiyonu Epochs subset dönmeli
    clean_ep, rep = reject_artifacts(epochs)
    assert len(clean_ep) == len(clean_indices)
    assert rep["summary"]["clean_epochs"] == len(clean_indices)
