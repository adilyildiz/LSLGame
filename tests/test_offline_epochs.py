"""Epoklama Testleri.

PLAN.md Faz 4.1 ve Görev 06 Madde 8.2 uyarınca:
2. Epoklama: deneme sayısı = marker sayısı. Etiketler cue_* ile birebir eşleşmeli.
"""

import numpy as np
import pytest

from src.processing.epochs import extract_epochs
from src.simulation.offline_dataset import generate_offline_dataset


def test_epoching_counts_and_labels():
    """Epok sayısı cue_* marker sayısı ile eşit olmalı ve etiketler birebir eşleşmeli."""
    n_runs = 3
    trials_per_run = 15
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=n_runs,
        trials_per_run=trials_per_run,
        profile="mi2",
        seed=101,
    )

    # Marker listesindeki cue_* sayısını ve sırasını say
    cue_markers = [m_text for ts, m_text in rec.markers if m_text.startswith("cue_")]
    expected_labels = [m.replace("cue_", "") for m in cue_markers]
    expected_count = n_runs * trials_per_run

    assert len(cue_markers) == expected_count

    # Epokları çıkar
    epochs = extract_epochs(rec, tmin=0.5, tmax=3.5, filter_mode="causal")

    # 1. Epok sayısı == cue marker sayısı
    assert len(epochs) == expected_count, f"Beklenen {expected_count} epok, bulunan: {len(epochs)}"

    # 2. Etiketler cue_* ile birebir aynı
    assert list(epochs.labels) == expected_labels, "Epok etiketleri cue_* marker sırası ile birebir uyuşmuyor."

    # 3. Boyutlar
    # 3.0 saniye * 250 Hz = 750 örnek
    expected_samples = int(round(3.0 * rec.srate))
    assert epochs.data.shape == (expected_count, expected_samples, len(rec.ch_names))

    # 4. Run indeksleri doğru gruplanmış olmalı
    unique_runs = np.unique(epochs.run_indices)
    assert len(unique_runs) == n_runs
    for r in range(n_runs):
        assert np.sum(epochs.run_indices == r) == trials_per_run


def test_epochs_subset():
    """Epochs.subset doğru alt kümeleme yapmalıdır."""
    rec = generate_offline_dataset(n_runs=2, trials_per_run=10, seed=102)
    epochs = extract_epochs(rec)
    sub = epochs.subset([0, 1, 2])
    assert len(sub) == 3
    assert sub.data.shape[0] == 3
    assert list(sub.labels) == list(epochs.labels[:3])
    if sub.raw_data is not None:
        assert sub.raw_data.shape[0] == 3
