"""Sinyal kalitesi metrikleri ve flatline tespiti testleri."""

import numpy as np
import pytest
from src.signal_quality.quality_metrics import (
    compute_signal_quality,
    format_quality_table,
)


def test_quality_metrics_pure_tones():
    fs = 250.0
    duration = 3.0
    n_samples = int(fs * duration)
    t = np.arange(n_samples) / fs

    # 3 kanal oluştur:
    # Ch 0: Temiz 10 Hz sinüs (alfa/mu ritmi simülasyonu)
    # Ch 1: Baskın 50 Hz sinüs (şebeke gürültüsü)
    # Ch 2: Flatline (tamamen 0)
    data = np.zeros((n_samples, 3), dtype=np.float64)
    data[:, 0] = 20.0 * np.sin(2 * np.pi * 10.0 * t) + np.random.randn(n_samples) * 0.5
    data[:, 1] = 20.0 * np.sin(2 * np.pi * 50.0 * t) + np.random.randn(n_samples) * 0.5
    data[:, 2] = 0.0

    labels = ["Sig_10Hz", "Sig_50Hz", "Flatline"]
    metrics = compute_signal_quality(data, fs=fs, channel_labels=labels)

    # 1. 10 Hz kanalı: 10 Hz gücü 50 Hz gücünden belirgin yüksek olmalı (oran < 0 dB)
    m10 = metrics["Sig_10Hz"]
    assert m10["power_10hz"] > m10["power_50hz"] * 5
    assert m10["ratio_50_to_10_db"] < -5.0
    assert not m10["is_flatline"]
    assert m10["status"] == "green"

    # 2. 50 Hz kanalı: 50 Hz gücü 10 Hz gücünden belirgin yüksek olmalı (oran > 0 dB)
    m50 = metrics["Sig_50Hz"]
    assert m50["power_50hz"] > m50["power_10hz"] * 5
    assert m50["ratio_50_to_10_db"] > 5.0
    assert not m50["is_flatline"]
    assert m50["status"] in ("yellow", "red")

    # 3. Flatline kanalı: is_flatline True olmalı ve kırmızı durum
    m_flat = metrics["Flatline"]
    assert m_flat["is_flatline"] is True
    assert m_flat["status"] == "red"

    # Tablo formatlama testi
    table_str = format_quality_table(metrics)
    assert "Sig_10Hz" in table_str
    assert "Flatline" in table_str
    assert "EVET" in table_str
