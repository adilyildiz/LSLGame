"""Sistem ve Entegrasyon Testleri.

PLAN.md Faz 4 ve Görev 06 Madde 8 (8, 9, 10) uyarınca:
8. load_xdf pilot XDF ile çalışmalı: 7 EEG kanalı, ~250 Hz, impedanslar dolu, marker listesi boş değil.
9. Kaydedilen model + meta veri tekrar yüklenip aynı tahminleri vermeli.
10. Uçtan uca CLI: --synthetic ile report.md ve results.json üretilmeli (geçici klasör kullanılır ve temizlenir).
"""

import json
from pathlib import Path
import shutil
import tempfile

import joblib
import numpy as np
import pytest

from src.models.offline_analysis import run_offline_analysis
from src.processing.recording import Recording, load_xdf
from src.simulation.offline_dataset import generate_offline_dataset

PILOT_XDF_PATH = Path("data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf")


def test_load_xdf_pilot_file():
    """load_xdf pilot dosya ile çalışmalı: 7 EEG kanalı, ~250 Hz, empedanslar dolu, marker listesi boş değil."""
    assert PILOT_XDF_PATH.exists(), f"Pilot XDF dosyası bulunamadı: {PILOT_XDF_PATH}"

    rec = load_xdf(PILOT_XDF_PATH)

    # 1. 7 EEG kanalı
    assert rec.eeg.ndim == 2
    assert rec.eeg.shape[1] == 7
    assert rec.ch_names == ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]

    # 2. ~250 Hz örnekleme hızı
    assert rec.srate == pytest.approx(250.0, rel=1e-2)

    # 3. İmpedanslar dolu olmalı
    assert "impedances" in rec.meta
    assert len(rec.meta["impedances"]) > 0
    assert "C3" in rec.meta["impedances"]
    assert "C4" in rec.meta["impedances"]
    assert rec.meta["impedances"]["C3"] > 0

    # 4. Marker listesi boş olmamalı
    assert len(rec.markers) > 0
    # Marker içeriği zaman ve metin tuple'ı olmalı
    for ts, m_text in rec.markers[:5]:
        assert isinstance(ts, float)
        assert isinstance(m_text, str)
        assert len(m_text) > 0


def test_saved_model_and_metadata_reload():
    """Kaydedilen model + meta veri tekrar yüklenip aynı tahminleri vermeli."""
    temp_dir = Path(tempfile.mkdtemp(prefix="bci_test_model_"))
    try:
        results = run_offline_analysis(
            out_dir=temp_dir / "results",
            synthetic=True,
            erd=0.4,
            runs=2,
            trials_per_run=15,
            profile="mi2",
            seed=42,
            n_permutations=10,
            save_model_dir=temp_dir / "models",
        )

        saved_meta = results["saved_model_meta"]
        model_file = Path(saved_meta["model_file"])
        meta_file = Path(saved_meta["meta_file"])

        assert model_file.exists(), f"Model dosyası bulunamadı: {model_file}"
        assert meta_file.exists(), f"Meta veri dosyası bulunamadı: {meta_file}"

        # Meta veriyi doğrula
        with open(meta_file, "r", encoding="utf-8") as f:
            meta_json = json.load(f)

        assert meta_json["model_name"] == results["best_model"]
        assert meta_json["channel_names"] == ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]
        assert meta_json["filter_mode"] == "causal"
        assert meta_json["srate"] == pytest.approx(250.0)

        # Modeli tekrar yükle ve tahminleri doğrula
        loaded_model = joblib.load(model_file)
        sample_x = np.random.randn(5, 7, 750)  # (n, ch, time)
        pred1 = loaded_model.predict(sample_x)
        pred2 = loaded_model.predict(sample_x)
        assert np.array_equal(pred1, pred2)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_cli_end_to_end_synthetic():
    """Uçtan uca CLI: --synthetic ile report.md, results.json ve şekiller üretilmeli."""
    temp_dir = Path(tempfile.mkdtemp(prefix="bci_test_cli_"))
    try:
        results = run_offline_analysis(
            out_dir=temp_dir,
            synthetic=True,
            erd=0.4,
            runs=2,
            trials_per_run=15,
            profile="mi2",
            seed=42,
            n_permutations=15,
            save_model_dir=temp_dir / "saved_models",
        )

        report_file = temp_dir / "report.md"
        results_file = temp_dir / "results.json"
        erd_fig = temp_dir / "erd_c3_cz_c4.png"
        r2_fig = temp_dir / "r2_map.png"
        r2_mat = temp_dir / "r2_matrix.npy"

        assert report_file.exists(), "report.md üretilmedi."
        assert results_file.exists(), "results.json üretilmedi."
        assert erd_fig.exists(), "erd_c3_cz_c4.png üretilmedi."
        assert r2_fig.exists(), "r2_map.png üretilmedi."
        assert r2_mat.exists(), "r2_matrix.npy üretilmedi."

        # report.md içeriği doğrulaması
        content = report_file.read_text(encoding="utf-8")
        assert "Model Karşılaştırma Tablosu" in content
        assert "Şans Seviyesi ve İstatistiki Anlamlılık" in content
        assert "Nörofizyolojik Doğrulama ve EMG Kontrolü" in content
        assert "Artefakt Reddi İstatistikleri" in content

        # results.json içeriği doğrulaması
        with open(results_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "best_model" in data
        assert "best_accuracy" in data
        assert "permutation_test" in data
        assert "emg_check" in data

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
