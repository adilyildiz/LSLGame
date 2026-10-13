"""Acquisition modülü ve halka tampon (XonRingBuffer) testleri."""

import numpy as np
import pylsl
import pytest
from src.acquisition.stream_receiver import (
    XonRingBuffer,
    XonStreamReceiver,
    find_xon_stream,
    parse_xon_metadata,
)
from src.simulation.synthetic_eeg import SyntheticEEGSource


def test_ring_buffer_basic():
    # 2 saniyelik tampon, 100 Hz, 3 kanal -> 200 örnek kapasite
    buf = XonRingBuffer(capacity_seconds=2.0, srate=100.0, n_channels=3)
    assert buf.sample_count == 0
    assert not buf.is_ready(1.0)

    # 50 örnek ekle
    chunk1 = np.ones((50, 3), dtype=np.float32)
    ts1 = np.arange(50, dtype=np.float64)
    buf.append(chunk1, ts1)

    assert buf.sample_count == 50
    assert buf.total_samples == 50
    assert not buf.is_ready(1.0)  # 1 sn = 100 örnek gerekir

    # 100 örnek daha ekle (toplam 150)
    chunk2 = np.full((100, 3), 2.0, dtype=np.float32)
    ts2 = np.arange(50, 150, dtype=np.float64)
    buf.append(chunk2, ts2)

    assert buf.sample_count == 150
    assert buf.is_ready(1.0)
    assert not buf.is_ready(2.0)

    # Son 10 örneği al
    data_last10, ts_last10 = buf.get_latest_samples(10)
    assert data_last10.shape == (10, 3)
    assert np.allclose(data_last10, 2.0)
    assert np.allclose(ts_last10, np.arange(140, 150))


def test_ring_buffer_wraparound():
    # 10 örnek kapasiteli küçük tampon
    buf = XonRingBuffer(capacity_seconds=1.0, srate=10.0, n_channels=2)

    # 8 örnek ekle [0..7]
    c1 = np.arange(8).reshape(-1, 1).repeat(2, axis=1).astype(np.float32)
    t1 = np.arange(8, dtype=np.float64)
    buf.append(c1, t1)
    assert buf.sample_count == 8

    # 5 örnek daha ekle [8..12] -> Tampon saracak (wraparound)
    c2 = np.arange(8, 13).reshape(-1, 1).repeat(2, axis=1).astype(np.float32)
    t2 = np.arange(8, 13, dtype=np.float64)
    buf.append(c2, t2)

    # Tampon doldu ve en eski 3 örnek ezildi. İçeride [3..12] olmalı
    assert buf.sample_count == 10
    assert buf.total_samples == 13

    # Son 10 örneği al
    data, ts = buf.get_latest_samples(10)
    assert data.shape == (10, 2)
    expected_ts = np.arange(3, 13)
    assert np.allclose(ts, expected_ts)
    assert np.allclose(data[:, 0], expected_ts)


def test_ring_buffer_get_latest_window():
    buf = XonRingBuffer(capacity_seconds=5.0, srate=250.0, n_channels=11)
    chunk = np.random.randn(500, 11).astype(np.float32)
    ts = np.linspace(0, 2.0, 500)
    buf.append(chunk, ts)

    # 1 saniyelik pencere = 250 örnek
    w_data, w_ts = buf.get_latest_window(1.0)
    assert w_data.shape == (250, 11)
    assert len(w_ts) == 250


def test_parse_xon_metadata():
    info = pylsl.StreamInfo(
        name="X.on-TEST",
        type="EEG",
        channel_count=2,
        nominal_srate=250.0,
        channel_format=pylsl.cf_float32,
        source_id="TEST-123",
    )
    desc = info.desc()
    chans = desc.append_child("channels")
    ch1 = chans.append_child("channel")
    ch1.append_child_value("label", "C3")
    ch1.append_child_value("type", "EEG")
    ch1.append_child_value("unit", "uV")

    ch2 = chans.append_child("channel")
    ch2.append_child_value("label", "accX")
    ch2.append_child_value("type", "AUX")
    ch2.append_child_value("unit", "mg")

    filters = desc.append_child("filters")
    f1 = filters.append_child("filter")
    f1.append_child_value("label", "HighPass")
    f1.append_child_value("unit", "Hz")
    f1.append_child_value("value", "0.5")

    imp = desc.append_child("impedances")
    i1 = imp.append_child("impedance")
    i1.append_child_value("label", "C3")
    i1.append_child_value("unit", "kilo-Ohm")
    i1.append_child_value("value", "16300.0")

    meta = parse_xon_metadata(info)
    assert meta["name"] == "X.on-TEST"
    assert meta["type"] == "EEG"
    assert meta["nominal_srate"] == 250.0
    assert len(meta["channels"]) == 2
    assert meta["channels"][0]["label"] == "C3"
    assert meta["channels"][1]["type"] == "AUX"
    assert len(meta["filters"]) == 1
    assert meta["filters"][0]["value"] == 0.5
    assert "C3" in meta["impedances"]
    assert meta["impedances"]["C3"]["value"] == 16300.0


def test_find_xon_stream_allow_simulator():
    """S5 Testi:
    find_xon_stream allow_simulator=False iken -SIM- içeren akışları atlamalı,
    allow_simulator=True iken bulmalı.
    """
    import time

    source = SyntheticEEGSource(name="X.on-SIM-CHECK5", source_id="SIM-CHECK5-ID")
    time.sleep(0.3)

    # 1. allow_simulator=False iken simülatör elenmeli ve zaman aşımına uğramalı
    with pytest.raises(TimeoutError):
        find_xon_stream(name_prefix="X.on", timeout=1.0, allow_simulator=False)

    # 2. allow_simulator=True iken simülatör bulunmalı
    info = find_xon_stream(name_prefix="X.on", timeout=2.0, allow_simulator=True)
    assert info is not None
    assert "-SIM-" in info.name()

    # 3. XonStreamReceiver is_simulator bayrağı True olmalı
    receiver = XonStreamReceiver(source_id="SIM-CHECK5-ID", allow_simulator=True)
    assert receiver.is_simulator is True
    receiver.close()


def test_find_xon_stream_multiple_matches_warning(caplog):
    """S5 Testi:
    Birden fazla X.on akışı mevcut olduğunda uyarı loglanmalı.
    """
    import logging
    import time

    src1 = SyntheticEEGSource(name="X.on-SIM-MULTI1", source_id="MULTI1")
    src2 = SyntheticEEGSource(name="X.on-SIM-MULTI2", source_id="MULTI2")
    time.sleep(0.3)

    with caplog.at_level(logging.WARNING):
        info = find_xon_stream(name_prefix="X.on", timeout=2.0, allow_simulator=True)
        assert info is not None

    assert any("Birden fazla X.on akışı bulundu" in record.message for record in caplog.records)
