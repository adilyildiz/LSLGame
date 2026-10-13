"""Sentetik EEG ve Uçtan Uca (End-to-End) Acquisition Entegrasyon Testi."""

import time
import numpy as np
from scipy import signal
import pytest

from src.acquisition.stream_receiver import XonStreamReceiver, parse_xon_metadata
from src.simulation.synthetic_eeg import SyntheticEEGSource


def _compute_band_power(sig: np.ndarray, fs: float, low: float, high: float) -> float:
    """Welch PSD ile frekans bandı gücünü hesaplar."""
    freqs, psd = signal.welch(sig, fs=fs, nperseg=min(len(sig), int(fs)))
    idx = np.logical_and(freqs >= low, freqs <= high)
    return float(np.trapezoid(psd[idx], freqs[idx]))


def test_synthetic_eeg_metadata_and_streams():
    source = SyntheticEEGSource(name="X.on-SIM-META", srate=250.0)
    meta = parse_xon_metadata(source.stream_info)

    assert meta["name"] == "X.on-SIM-META"
    assert meta["type"] == "EEG"
    assert meta["channel_count"] == 11
    assert meta["nominal_srate"] == 250.0
    assert len(meta["channels"]) == 11
    assert meta["channels"][2]["label"] == "C3"
    assert meta["channels"][4]["label"] == "C4"
    assert "C3" in meta["impedances"]
    assert "C4" in meta["impedances"]
    assert len(meta["filters"]) >= 2


def test_synthetic_eeg_end_to_end_left_class_erd():
    """Uçtan uca test:
    Sentetik EEG yayınla (sol sınıfı) -> Acquisition modülü alıp 2 sn veri biriktirsin ->
    Sol sınıfında C4'ün 8–30 Hz gücü C3'ünkünden belirgin düşük olsun.
    """
    source = SyntheticEEGSource(name="X.on-SIM-E2E", srate=250.0)
    source.set_class("left")
    source.start()

    receiver = XonStreamReceiver(
        stream_info=source.stream_info,
        buffer_duration=5.0,
    )
    receiver.start(poll_interval=0.01)

    try:
        # 2 saniyelik veri (500 örnek) birikene kadar bekle (en fazla 4 saniye)
        start_wait = time.time()
        while not receiver.ring_buffer.is_ready(2.0):
            time.sleep(0.05)
            if time.time() - start_wait > 5.0:
                pytest.fail("2 saniyelik veri biriktirilemedi, zaman aşımı.")

        # 2 saniyelik pencereyi çek
        data, timestamps = receiver.ring_buffer.get_latest_window(2.0)
        assert data.shape == (500, 11), f"Beklenen (500, 11), alınan: {data.shape}"

        # Kanal indeksleri: C3 -> 2, C4 -> 4
        c3_sig = data[:, 2]
        c4_sig = data[:, 4]

        # 8–30 Hz band gücünü hesapla
        p_c3 = _compute_band_power(c3_sig, fs=250.0, low=8.0, high=30.0)
        p_c4 = _compute_band_power(c4_sig, fs=250.0, low=8.0, high=30.0)

        # 'left' sınıfında kontralateral ERD sebebiyle C4 gücü C3'ten belirgin düşük olmalı
        # Güç düşüşü hedefi: en az %25 - %40 daha düşük
        power_ratio = p_c4 / p_c3
        assert p_c4 < p_c3, (
            f"C4 gücü ({p_c4:.2f}) C3 gücünden ({p_c3:.2f}) düşük değil! Oran: {power_ratio:.3f}"
        )
        assert power_ratio <= 0.80, (
            f"C4 gücündeki düşüş belirgin değil. C4/C3 oranı: {power_ratio:.3f} (beklenen <= 0.80)"
        )

    finally:
        receiver.close()
        source.stop()
