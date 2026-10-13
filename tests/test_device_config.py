"""Cihaz yapılandırması (config/device_xon.yaml) doğrulama testleri."""

from pathlib import Path
import pytest
from src.acquisition.stream_receiver import load_xon_config

CONFIG_PATH = Path("config/device_xon.yaml")


def test_config_file_exists():
    assert CONFIG_PATH.exists()


def test_config_contents():
    cfg = load_xon_config(CONFIG_PATH)

    assert "stream" in cfg
    assert cfg["stream"]["type"] == "EEG"
    assert cfg["stream"]["name_prefix"] == "X.on"
    assert cfg["stream"]["nominal_srate"] == 250.0

    assert "channels" in cfg
    assert cfg["channels"]["count"] == 11
    labels = cfg["channels"]["labels"]
    assert labels == ["F3", "F4", "C3", "Cz", "C4", "P3", "P4", "BIP", "accX", "accY", "accZ"]

    indices = cfg["channels"]["indices"]
    assert indices["eeg"] == [0, 1, 2, 3, 4, 5, 6]
    assert indices["bip"] == 7
    assert indices["accelerometer"] == [8, 9, 10]
    assert indices["motor_imagery"]["C3"] == 2
    assert indices["motor_imagery"]["Cz"] == 3
    assert indices["motor_imagery"]["C4"] == 4

    assert "hardware_filters" in cfg
    assert cfg["hardware_filters"]["high_pass_hz"] == 0.5
    assert cfg["hardware_filters"]["low_pass_hz"] == 65.0
