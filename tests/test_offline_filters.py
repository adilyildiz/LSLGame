"""Filtreleme ve StatefulFilter Testleri.

PLAN.md Faz 4.1, Faz 5.1 ve Görev 06 Madde 8.1 uyarınca:
1. StatefulFilter: blok blok == tek seferde (hata < 1e-6).
2. zero_phase ve causal ayrı fonksiyonlar olarak test edilir.
"""

import numpy as np
import pytest

from src.processing.filters import (
    StatefulFilter,
    apply_bandpass,
    apply_notch,
    filter_eeg,
)


def test_stateful_filter_equivalence():
    """StatefulFilter: blok blok filtreleme == tek seferde filtreleme (hata < 1e-6)."""
    srate = 250.0
    n_channels = 7
    n_samples = 2500
    rng = np.random.default_rng(123)
    data = rng.standard_normal((n_samples, n_channels)) * 20.0

    # 1. Tek seferde filtreleme
    sf_full = StatefulFilter(srate=srate, n_channels=n_channels, f_low=8.0, f_high=30.0, order=4)
    y_full = sf_full.filter_full(data)

    # 2. Blok blok filtreleme (çeşitli blok boyutları ile)
    sf_chunked = StatefulFilter(srate=srate, n_channels=n_channels, f_low=8.0, f_high=30.0, order=4)
    chunk_sizes = [25, 50, 100, 250, 125, 200, 500, 750, 500]  # Toplam 2500
    assert sum(chunk_sizes) == n_samples

    y_chunks = []
    idx = 0
    for sz in chunk_sizes:
        chunk = data[idx : idx + sz]
        out_chunk = sf_chunked.filter_block(chunk)
        y_chunks.append(out_chunk)
        idx += sz

    y_stitched = np.vstack(y_chunks)

    max_err = np.max(np.abs(y_full - y_stitched))
    assert max_err < 1e-6, f"Blok blok filtreleme tek seferlik filtrelemeyle uyuşmuyor: hata={max_err}"


def test_causal_vs_zero_phase_functions():
    """zero_phase ve causal ayrı fonksiyonlar/modlar olarak çalışmalı ve farklı çıktılar üretmeli."""
    srate = 250.0
    n_samples = 1000
    rng = np.random.default_rng(456)
    data = rng.standard_normal((n_samples, 7))

    # Bant geçiren
    out_causal_bp = apply_bandpass(data, srate=srate, f_low=8.0, f_high=30.0, mode="causal")
    out_zp_bp = apply_bandpass(data, srate=srate, f_low=8.0, f_high=30.0, mode="zero_phase")

    assert out_causal_bp.shape == data.shape
    assert out_zp_bp.shape == data.shape
    # Nedensel ve sıfır faz filtreler faz kayması nedeniyle farklı olmalıdır
    diff_bp = np.max(np.abs(out_causal_bp - out_zp_bp))
    assert diff_bp > 1e-3, "Causal ve zero_phase filtre çıktıları birbirinden farklı olmalıdır."

    # Çentik filtresi
    out_causal_notch = apply_notch(data, srate=srate, freqs=(50.0, 100.0), mode="causal")
    out_zp_notch = apply_notch(data, srate=srate, freqs=(50.0, 100.0), mode="zero_phase")

    assert out_causal_notch.shape == data.shape
    assert out_zp_notch.shape == data.shape

    # filter_eeg birleşik fonksiyonu
    out_comb = filter_eeg(data, srate=srate, mode="causal")
    assert out_comb.shape == data.shape


def test_stateful_filter_reset():
    """reset() çağrısı filtre durumunu sıfırlamalıdır."""
    sf = StatefulFilter(srate=250.0, n_channels=7)
    x = np.ones((100, 7))
    out1 = sf.filter_block(x)
    sf.reset()
    out2 = sf.filter_block(x)
    assert np.allclose(out1, out2, atol=1e-12)
