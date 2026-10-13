"""Pilot XDF dosyasının doğrulanması testi."""

from pathlib import Path
import numpy as np
import pyxdf
import pytest

PILOT_XDF_PATH = Path("data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf")


def test_pilot_xdf_exists():
    assert PILOT_XDF_PATH.exists(), f"Pilot XDF dosyası bulunamadı: {PILOT_XDF_PATH}"


def test_pilot_xdf_xon_stream():
    streams, header = pyxdf.load_xdf(str(PILOT_XDF_PATH))
    assert len(streams) > 0, "XDF dosyasında akış bulunamadı."

    xon_stream = None
    for s in streams:
        name = s["info"]["name"][0]
        stype = s["info"]["type"][0]
        if name.startswith("X.on") and stype == "EEG":
            xon_stream = s
            break

    assert xon_stream is not None, "X.on EEG akışı bulunamadı."

    info = xon_stream["info"]
    time_series = np.asarray(xon_stream["time_series"])
    time_stamps = np.asarray(xon_stream["time_stamps"])

    # 1. Kanal sayısı 11 olmalı
    n_channels = int(info["channel_count"][0])
    assert n_channels == 11, f"Beklenen 11 kanal, bulunan: {n_channels}"
    assert time_series.shape[1] == 11

    # 2. Örnekleme hızı ~250 Hz
    nominal_srate = float(info["nominal_srate"][0])
    effective_srate = float(xon_stream.get("effective_srate", 250.0))
    assert nominal_srate == pytest.approx(250.0, rel=1e-3)
    assert effective_srate == pytest.approx(250.0, rel=1e-2)

    # 3. Örnek sayısı ~17754
    n_samples = len(time_stamps)
    assert n_samples == pytest.approx(17754, abs=50), f"Beklenen ~17754 örnek, bulunan: {n_samples}"

    # 4. Kanal etiketleri sırası
    desc = info["desc"][0]
    chans = desc["channels"][0]["channel"]
    expected_labels = ["F3", "F4", "C3", "Cz", "C4", "P3", "P4", "BIP", "accX", "accY", "accZ"]
    actual_labels = [c["label"][0] for c in chans]
    assert actual_labels == expected_labels, f"Kanal etiketleri uyuşmuyor: {actual_labels}"

    # 5. Cihaz filtreleri
    filters = desc["filters"][0]["filter"]
    f_dict = {f["label"][0]: float(f["value"][0]) for f in filters}
    assert f_dict.get("HighPass") == pytest.approx(0.5)
    assert f_dict.get("LowPass") == pytest.approx(65.0)
