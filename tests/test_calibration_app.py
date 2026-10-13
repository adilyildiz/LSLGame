"""CalibrationApp Gerçek Entegrasyon Testi (Mock Yok).

agy_tasks/05_faz3_denetim_duzeltmeleri.md K2 uyarınca:
- Pencere açılmaz: os.environ["SDL_VIDEODRIVER"] = "dummy" (pygame import edilmeden önce ayarlanır).
- Gerçek CalibrationApp nesnesi gerçek SyntheticEEGSource ile uçtan uca test edilir:
  1. search_eeg_stream() True dönmeli.
  2. update_live_quality() hatasız çalışmalı ve 7 EEG kanalı için metrik üretmeli.
  3. draw_check_screen() hatasız çalışmalı.
  4. Paradigma kısa sürelerle (~0.1-0.2 sn, 1 run, mi2) gerçek run() döngüsü üzerinden tamamlanmalı (SPACE enjeksiyonu).
  5. Oturum JSON günlüğü logs/ altında oluşmalı ve deneme listesini içermeli; test sonunda dosya temizlenmeli.
  6. Her draw_cue(sinif) ('left', 'right', 'feet', 'both_hands', 'arithmetic', 'rest') ve draw_pause_screen() hatasız çalışmalı.
"""

import os
os.environ["SDL_VIDEODRIVER"] = "dummy"

import json
from pathlib import Path
import threading
import time
import pytest
import pygame

from src.calibration.run_calibration import CalibrationApp
from src.simulation.synthetic_eeg import SyntheticEEGSource


def test_calibration_app_full_integration_real_hardware_simulator():
    """CalibrationApp gerçek entegrasyon testi (K2)."""
    start_time = time.time()
    unique_id = f"APP-INT-{int(time.time() * 1000)}"

    # Gerçek SyntheticEEGSource başlat
    source = SyntheticEEGSource(
        name=f"X.on-SIM-APP-{unique_id}",
        source_id=f"SIM-APP-{unique_id}",
        srate=250.0,
        sync_channel=True,
    )
    source.start()

    # Hızlı tamamlama için kısa süreli yapılandırma
    short_config = {
        "timing": {
            "fixation_sec": 0.1,
            "cue_sec": 0.1,
            "imagery_sec": 0.15,
            "rest_min_sec": 0.1,
            "rest_max_sec": 0.1,
            "inter_run_pause_sec": 0.2,
        },
        "run": {
            "trials_per_run": 3,
            "max_consecutive_same_class": 3,
        },
        "profiles": {
            "mi2": {
                "classes": ["left", "right", "rest"],
                "default_runs": 1,
            }
        },
        "display": {
            "fullscreen": False,
            "window_width": 640,
            "window_height": 480,
        },
        "recording": {
            "stream_name_markers": f"BCI_Markers_{unique_id}",
            "stream_source_id_markers": f"Markers_{unique_id}",
        },
    }

    app = CalibrationApp(
        subject="sub-k2",
        session="ses-test",
        profile="mi2",
        simulator=True,
        windowed=True,
        config_path=short_config,
    )

    created_log_file = None

    try:
        # 1. search_eeg_stream() True dönmeli
        found = app.search_eeg_stream(timeout=4.0)
        assert found is True, "search_eeg_stream() True dönmedi!"
        assert app.stream_info is not None
        assert app.receiver is not None
        assert app.receiver.is_running is True
        # Tam meta veri (impedanslar) bağlı inlet'ten okunmalı; resolve sonucu <desc> içermez
        assert len(app.initial_impedances) == 9, f"İmpedanslar okunamadı: {app.initial_impedances}"

        # 2. update_live_quality() hatasız çalışmalı ve 7 EEG kanalı için metrik üretmeli
        wait_start = time.time()
        while not app.receiver.ring_buffer.is_ready(1.0) and time.time() - wait_start < 4.0:
            time.sleep(0.05)

        app.update_live_quality()
        eeg_channels = ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]
        for ch in eeg_channels:
            assert ch in app.quality_metrics, f"{ch} kanalı kalite metriklerinde bulunamadı!"
            q = app.quality_metrics[ch]
            assert "rms" in q, f"{ch} için rms metriği yok!"
            assert "status" in q, f"{ch} için status metriği yok!"
            assert q["status"] in ("green", "yellow", "red")

        # 3. draw_check_screen() hatasız çalışmalı
        app.init_pygame()
        app.draw_check_screen()

        # 6. Her draw_cue(sinif) ve draw_pause_screen() hatasız çalışmalı
        classes_to_draw = ["left", "right", "feet", "both_hands", "arithmetic", "rest"]
        for cls in classes_to_draw:
            app.draw_cue(cls)
        app.draw_pause_screen()

        # 4. Paradigma gerçek run() döngüsü üzerinden tamamlanmalı (SPACE enjeksiyonu)
        def inject_space_event():
            time.sleep(0.15)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

        t = threading.Thread(target=inject_space_event, daemon=True)
        t.start()

        # Güvenlik zaman aşımı 20 saniye
        app.run(max_seconds=20.0)

        # Durum makinesinin tamamlandığını ve tüm denemelerin işlendiğini doğrula
        assert app.sm.is_completed is True, "Paradigma run() döngüsü tamamlanamadı!"
        assert len(app.sm.trials_history) == 3, f"Beklenen 3 deneme, tamamlanan: {len(app.sm.trials_history)}"

        # 5. Oturum JSON günlüğü logs/ altında oluşmalı ve deneme listesini içermeli
        assert app.last_saved_log_path is not None, "Oturum günlüğü yolu kaydedilmedi!"
        created_log_file = app.last_saved_log_path
        assert created_log_file.exists(), f"Günlük dosyası bulunamadı: {created_log_file}"

        with open(created_log_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)

        assert log_data["subject"] == "sub-k2"
        assert log_data["is_completed"] is True
        assert "trials" in log_data
        assert isinstance(log_data["trials"], list)
        assert len(log_data["trials"]) == 3
        for trial in log_data["trials"]:
            assert "class" in trial or "class_name" in trial
            assert "timestamps" in trial

    finally:
        # Temizlik: Yalnızca bu test tarafından oluşturulan günlük dosyasını sil
        if created_log_file and created_log_file.exists():
            try:
                created_log_file.unlink()
            except Exception:
                pass

        if app.receiver and app.receiver.is_running:
            app.receiver.stop()
        source.stop()

    total_duration = time.time() - start_time
    assert total_duration < 30.0, f"Test süresi 30 saniyeyi aştı: {total_duration:.2f} sn"
