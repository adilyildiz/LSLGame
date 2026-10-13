"""Graz-BCI Kalibrasyon Paradigması, Durum Makinesi ve E2E Simülatör Testleri.

PLAN.md Faz 3 (3.1-3.5) ve agy_tasks/04_faz3_kalibrasyon.md uyarınca:
- Deneme sırası dengesi ve en uzun seri <= 3.
- Durum makinesi aşama süreleri ve marker sırası (sahte saatle doğrulanır).
- Tüm marker isimleri katı ASCII.
- ESC/Abort ile oturum sonlandırma ve loglama.
- Simülatörle uçtan uca (E2E) LSL EEG ve BCI_Markers kayıt ve zaman hizalama doğrulaması (< 20 ms).
- Hiçbir test pencere açmaz (Headless).
"""

import json
from pathlib import Path
import time
from typing import Dict, List, Tuple

import numpy as np
import pylsl
import pytest

from src.acquisition.stream_receiver import XonStreamReceiver
from src.calibration.paradigm import (
    CalibrationStage,
    CalibrationStateMachine,
    CalibrationTiming,
    generate_balanced_sequence,
    load_calibration_config,
)
from src.calibration.run_calibration import CalibrationApp, build_arg_parser
from src.game.ball_roll import MarkerPublisher
from src.simulation.synthetic_eeg import SyntheticEEGSource


def test_balanced_sequence_distribution_and_streak():
    """Her run'da sınıfların dengeli dağılması ve max streak <= 3 kuralı testi."""
    # 1. mi2 profili: 3 sınıf, 20 deneme -> Dağılım: 7, 7, 6 (fark <= 1)
    seq_mi2 = generate_balanced_sequence(["left", "right", "rest"], count=20, seed=42)
    assert len(seq_mi2) == 20
    counts_mi2 = [seq_mi2.count("left"), seq_mi2.count("right"), seq_mi2.count("rest")]
    assert max(counts_mi2) - min(counts_mi2) <= 1
    assert set(counts_mi2) == {6, 7}

    # Streak kuralı: Aynı sınıf en fazla 3 kez ardışık gelebilir
    for i in range(len(seq_mi2) - 3):
        assert not (seq_mi2[i] == seq_mi2[i + 1] == seq_mi2[i + 2] == seq_mi2[i + 3])

    # 2. mi3 profili: 4 sınıf, 20 deneme -> Dağılım: 5, 5, 5, 5
    seq_mi3 = generate_balanced_sequence(["left", "right", "rest", "feet"], count=20, seed=100)
    assert len(seq_mi3) == 20
    for cls in ["left", "right", "rest", "feet"]:
        assert seq_mi3.count(cls) == 5
    for i in range(len(seq_mi3) - 3):
        assert not (seq_mi3[i] == seq_mi3[i + 1] == seq_mi3[i + 2] == seq_mi3[i + 3])

    # 3. mi5 profili: 6 sınıf, 20 deneme -> Dağılım: 4, 4, 3, 3, 3, 3 (fark <= 1)
    classes_mi5 = ["left", "right", "rest", "feet", "both_hands", "arithmetic"]
    seq_mi5 = generate_balanced_sequence(classes_mi5, count=20, seed=2026)
    assert len(seq_mi5) == 20
    counts_mi5 = [seq_mi5.count(c) for c in classes_mi5]
    assert max(counts_mi5) - min(counts_mi5) <= 1
    for i in range(len(seq_mi5) - 3):
        assert not (seq_mi5[i] == seq_mi5[i + 1] == seq_mi5[i + 2] == seq_mi5[i + 3])

    # 4. Determinizm testi: Aynı seed aynı sırayı üretir
    seq_repeat = generate_balanced_sequence(["left", "right", "rest"], count=20, seed=42)
    assert seq_mi2 == seq_repeat


def test_state_machine_virtual_clock_timeline_and_markers():
    """Sahte saatle durum makinesinin tam aşama süreleri ve marker sırası testi."""
    cfg = {
        "timing": {
            "fixation_sec": 2.0,
            "cue_sec": 1.0,
            "imagery_sec": 4.0,
            "rest_min_sec": 2.0,
            "rest_max_sec": 2.0,
            "inter_run_pause_sec": 30.0,
        },
        "run": {
            "trials_per_run": 2,
            "max_consecutive_same_class": 3,
        },
        "profiles": {
            "mi2": {
                "classes": ["left", "right"],
                "default_runs": 2,
            }
        },
    }

    sm = CalibrationStateMachine(config=cfg, profile_name="mi2", n_runs=2, seed=42)
    t = 1000.0

    # 1. Oturum Başlangıcı
    m_sess = sm.start_session(t)
    assert m_sess == ["session_start"]
    assert sm.stage == CalibrationStage.RUN_READY

    # 2. Run 1 Başlangıcı
    m_run1 = sm.start_run(t)
    assert m_run1 == ["run_start", "trial_start", "fixation_start"]
    assert sm.stage == CalibrationStage.FIXATION
    assert sm.current_trial_in_run == 0
    c0 = sm.current_class

    # Fixation süresince geçiş olmamalı
    assert not sm.should_transition(t + 1.99)
    assert sm.update(t + 1.99) == []

    # t + 2.0: Fixation biter -> Cue başlar
    t += 2.0
    assert sm.should_transition(t)
    _, m_cue = sm.commit_transition(t)
    assert m_cue == [f"cue_{c0}"]
    assert sm.stage == CalibrationStage.CUE

    # t + 1.0 (t=1003.0): Cue biter -> Imagery başlar
    t += 1.0
    _, m_img = sm.commit_transition(t)
    assert m_img == ["imagery_start"]
    assert sm.stage == CalibrationStage.IMAGERY

    # t + 4.0 (t=1007.0): Imagery biter -> Rest başlar
    t += 4.0
    _, m_rest = sm.commit_transition(t)
    assert m_rest == ["imagery_end", "rest_start"]
    assert sm.stage == CalibrationStage.REST

    # t + 2.0 (t=1009.0): Rest biter -> 1. Deneme biter, 2. Deneme başlar
    t += 2.0
    c1 = sm.run_sequences[0][1]
    _, m_t2 = sm.commit_transition(t)
    assert m_t2 == ["trial_end", "trial_start", "fixation_start"]
    assert sm.stage == CalibrationStage.FIXATION
    assert sm.current_trial_in_run == 1

    # 2. denemeyi sm.update ile tek seferde 2.0 sn ilerlet
    t += 2.0
    m_step_cue = sm.update(t)
    assert m_step_cue == [f"cue_{c1}"]

    t += 1.0
    assert sm.update(t) == ["imagery_start"]

    t += 4.0
    assert sm.update(t) == ["imagery_end", "rest_start"]

    # Rest bitince run 1 biter, mola başlar
    t += 2.0
    m_pause = sm.update(t)
    assert m_pause == ["trial_end", "run_end", "pause_start"]
    assert sm.stage == CalibrationStage.INTER_RUN_PAUSE
    assert sm.is_paused is True
    assert sm.current_run == 1  # 2. run'a hazırlandı

    # 3. Moladan sonra Run 2'ye başlama
    t += 10.0
    m_run2 = sm.resume_after_pause(t)
    assert m_run2 == ["pause_end", "run_start", "trial_start", "fixation_start"]
    assert sm.stage == CalibrationStage.FIXATION

    # Run 2'nin 2 denemesini hızlıca tamamla
    # Deneme 1: fix(2) + cue(1) + img(4) + rest(2) = 9s
    t += 9.0
    m_r2_t1 = sm.update(t)
    assert "trial_end" in m_r2_t1
    assert "trial_start" in m_r2_t1

    # Deneme 2: fix(2) + cue(1) + img(4) + rest(2) = 9s -> Run 2 ve Oturum biter
    t += 9.0
    m_end = sm.update(t)
    assert m_end == ["cue_" + sm.run_sequences[1][1], "imagery_start", "imagery_end", "rest_start", "trial_end", "run_end", "session_end"]
    assert sm.stage == CalibrationStage.SESSION_END
    assert sm.is_completed is True


def test_all_marker_names_are_strict_ascii():
    """Tüm profillerde üretilen marker adlarının kesinlikle ASCII olduğunu doğrular."""
    profiles = ["mi2", "mi3", "mi5"]
    cfg = load_calibration_config()

    all_markers_seen = set()

    for p in profiles:
        sm = CalibrationStateMachine(config=cfg, profile_name=p, n_runs=1, seed=1)
        m_sess = sm.start_session(0.0)
        m_run = sm.start_run(0.0)
        all_markers_seen.update(m_sess)
        all_markers_seen.update(m_run)

        # 20 denemeyi adım adım koştur
        t = 0.0
        for _ in range(sm.trials_per_run):
            t += sm.timing.fixation_sec
            all_markers_seen.update(sm.update(t))
            t += sm.timing.cue_sec
            all_markers_seen.update(sm.update(t))
            t += sm.timing.imagery_sec
            all_markers_seen.update(sm.update(t))
            t += 3.0
            all_markers_seen.update(sm.update(t))

    for marker in all_markers_seen:
        assert marker.isascii(), f"Marker ismi ASCII değil: {marker}"
        # Türkçe karakter, boşluk veya özel karakter olmamalı
        assert " " not in marker
        assert marker.lower() == marker


def test_session_abort_saves_proper_log_and_markers(tmp_path):
    """ESC / abort durumunda session_end iletilmesi ve aborted bayrağının kaydedilmesi."""
    sm = CalibrationStateMachine(profile_name="mi2", n_runs=2, seed=42)
    sm.start_session(10.0)
    sm.start_run(10.0)

    # İkinci denemede iken oturum yarıda kesilsin
    m_abort = sm.abort(timestamp=15.0)
    assert m_abort == ["session_end"]
    assert sm.aborted is True
    assert sm.is_session_active is False
    assert sm.stage == CalibrationStage.SESSION_END

    summary = sm.get_session_summary()
    assert summary["aborted"] is True
    assert summary["is_completed"] is False
    assert summary["session_end_time"] == 15.0


def test_calibration_app_filename_and_quality_check():
    """CalibrationApp yardımcı metotlarının mantık doğrulaması (Headless)."""
    app = CalibrationApp(
        subject="sub-02",
        session="ses-20261016",
        profile="mi3",
        simulator=True,
    )

    suggested = app.get_suggested_filename(run_index=1)
    assert suggested == "data/sub-02/ses-20261016/sub-02_ses-20261016_task-MI_run-01.xdf"

    suggested_run3 = app.get_suggested_filename(run_index=3)
    assert suggested_run3 == "data/sub-02/ses-20261016/sub-02_ses-20261016_task-MI_run-03.xdf"

    # Kalite kontrolü simülasyonu
    app.quality_metrics = {
        "C3": {"status": "green", "ratio_50_to_10_db": 1.2},
        "Cz": {"status": "green", "ratio_50_to_10_db": 0.8},
        "C4": {"status": "yellow", "ratio_50_to_10_db": 6.5},
    }
    all_ok, warns = app.check_motor_channels_quality()
    assert all_ok is False
    assert any("C4" in w for w in warns)

    # Hepsi yeşil olduğunda
    app.quality_metrics["C4"]["status"] = "green"
    all_ok, warns = app.check_motor_channels_quality()
    assert all_ok is True
    assert len(warns) == 0


def test_e2e_calibration_simulator_recording_and_alignment():
    """Simülatörle Uçtan Uca (E2E) Kayıt ve Zaman Damgası Hizalama Testi (< 30 sn).

    Doğrulamalar:
    1. SyntheticEEGSource ve MarkerPublisher eşzamanlı çalışır.
    2. Paradigma kısaltılmış sürelerle (fix 0.05s, cue 0.05s, img 0.1s, rest 0.05s) koşturulur.
    3. Simülatör sınıfı ipucuna göre set_class ile değiştirilir.
    4. Her imagery_start - imagery_end aralığında EEG örnekleri mevcuttur.
    5. Marker sırası doğrulanır.
    6. Deneme sayıları sınıflar arasında dengelidir.
    7. PLAN Faz 3 çıkış kriteri: EEG ve Marker zaman damgaları aynı LSL saatindedir ve
       hizalama farkı < 20 ms'dir (250 Hz için örnek aralığı 4 ms).
    """
    start_test_time = time.time()

    # 1. Simülatör ve MarkerPublisher başlat
    unique_id = f"TEST-CALIB-{int(time.time() * 1000)}"
    source = SyntheticEEGSource(
        name=f"X.on-SIM-E2E-{unique_id}",
        srate=250.0,
        random_seed=42,
        source_id=f"SIM-SOURCE-{unique_id}",
    )
    source.start()

    marker_pub = MarkerPublisher(
        stream_name=f"BCI_Markers_Test_{unique_id}",
        source_id=f"MARKER-PUB-{unique_id}",
    )

    # 2. LSL Inlet'leri aç ve bağlantının kurulduğunu garanti et
    eeg_streams = pylsl.resolve_byprop("source_id", source.source_id, timeout=3.0)
    assert eeg_streams, f"EEG akışı bulunamadı: {source.source_id}"
    eeg_inlet = pylsl.StreamInlet(eeg_streams[0], max_buflen=30)
    eeg_inlet.open_stream(timeout=3.0)

    marker_streams = pylsl.resolve_byprop("source_id", marker_pub.stream_info.source_id(), timeout=3.0)
    assert marker_streams, f"Marker akışı bulunamadı: {marker_pub.stream_info.source_id()}"
    marker_inlet = pylsl.StreamInlet(marker_streams[0], max_buflen=30)
    marker_inlet.open_stream(timeout=3.0)

    # 3. Kısaltılmış sürelerle durum makinesi
    cfg = {
        "timing": {
            "fixation_sec": 0.05,
            "cue_sec": 0.05,
            "imagery_sec": 0.10,
            "rest_min_sec": 0.05,
            "rest_max_sec": 0.05,
            "inter_run_pause_sec": 0.1,
        },
        "run": {
            "trials_per_run": 6,
            "max_consecutive_same_class": 3,
        },
        "profiles": {
            "mi2": {
                "classes": ["left", "right", "rest"],
                "default_runs": 1,
            }
        },
    }

    sm = CalibrationStateMachine(config=cfg, profile_name="mi2", n_runs=1, seed=777)

    # 4. Paradigmayı koştur ve LSL marker'larını bas
    t_start = pylsl.local_clock()
    for m in sm.start_session(t_start):
        marker_pub.push(m, timestamp=t_start)

    for m in sm.start_run(t_start):
        marker_pub.push(m, timestamp=t_start)

    trials_seen_classes: List[str] = []

    try:
        while not sm.is_completed:
            now_lsl = pylsl.local_clock()
            if sm.should_transition(now_lsl):
                # Bir sonraki aşamaya geç
                stage, markers = sm.commit_transition(now_lsl)
                for m in markers:
                    marker_pub.push(m, timestamp=now_lsl)

                # İpucu veya imgeleme aşamasında simülatör durumunu güncelle
                cls = sm.current_class
                if stage == CalibrationStage.CUE and cls:
                    source.set_class(cls)
                    trials_seen_classes.append(cls)
                elif stage == CalibrationStage.REST:
                    source.set_class("rest")

            # CPU'yu rahatlatmak için çok kısa bekle
            time.sleep(0.01)

        # Paradigma bittiğinde EEG veri üretimini durdur
        source.stop()
        time.sleep(0.05)

        # 5. Kaydedilen EEG ve Marker verilerini çek
        recorded_eeg_samples: List[List[float]] = []
        recorded_eeg_timestamps: List[float] = []
        while True:
            chunk, ts_chunk = eeg_inlet.pull_chunk(timeout=0.05)
            if not chunk:
                break
            recorded_eeg_samples.extend(chunk)
            recorded_eeg_timestamps.extend(ts_chunk)

        recorded_markers: List[Tuple[str, float]] = []
        while True:
            sample, ts = marker_inlet.pull_sample(timeout=0.05)
            if sample is None:
                break
            recorded_markers.append((sample[0], ts))

        # 6. Doğrulamalar:
        # A) Marker listesi sırası ve bütünlüğü
        marker_names = [m[0] for m in recorded_markers]
        assert "session_start" in marker_names
        assert "run_start" in marker_names
        assert "run_end" in marker_names
        assert "session_end" in marker_names
        assert marker_names.count("trial_start") == 6
        assert marker_names.count("imagery_start") == 6
        assert marker_names.count("imagery_end") == 6
        assert marker_names.count("trial_end") == 6

        # B) Sınıf dengesi (6 deneme / 3 sınıf = her biri 2 deneme)
        assert len(trials_seen_classes) == 6
        assert trials_seen_classes.count("left") == 2
        assert trials_seen_classes.count("right") == 2
        assert trials_seen_classes.count("rest") == 2

        # C) Her imagery_start - imagery_end aralığında EEG örnekleri var mı?
        # D) Zaman damgası hizalama hatası < 20 ms (PLAN Faz 3 çıkış kriteri)
        eeg_ts_arr = np.array(recorded_eeg_timestamps)
        assert len(eeg_ts_arr) > 100, f"Yetersiz EEG örneği: {len(eeg_ts_arr)}"

        imagery_start_times = [m[1] for m in recorded_markers if m[0] == "imagery_start"]
        imagery_end_times = [m[1] for m in recorded_markers if m[0] == "imagery_end"]

        for trial_i, (t_img_start, t_img_end) in enumerate(zip(imagery_start_times, imagery_end_times)):
            # Bu aralıktaki EEG örnekleri
            mask = (eeg_ts_arr >= t_img_start) & (eeg_ts_arr <= t_img_end)
            n_samples_in_interval = np.sum(mask)

            assert n_samples_in_interval > 0, (
                f"Deneme {trial_i}: imagery_start ({t_img_start:.3f}) ile "
                f"imagery_end ({t_img_end:.3f}) arasında hiç EEG örneği bulunamadı!"
            )

            # Zaman damgası hizalama kontrolü:
            # En yakın EEG örneğinin zaman farkı (250 Hz'de örnekler her 4 ms'de bir gelir; maks jitter < 20 ms olmalı)
            min_diff_start = np.min(np.abs(eeg_ts_arr - t_img_start))
            assert min_diff_start < 0.020, (
                f"Deneme {trial_i}: EEG ve marker zaman hizalama farkı 20 ms'yi aştı: {min_diff_start * 1000:.2f} ms"
            )

    finally:
        source.stop()
        eeg_inlet.close_stream()
        marker_inlet.close_stream()

    total_dur = time.time() - start_test_time
    assert total_dur < 30.0, f"Test süresi 30 saniyeyi aştı: {total_dur:.2f} s"


def test_calibration_config_file_integrity_and_cli_parsing():
    """Yapılandırma dosyasının PLAN 3.1-3.3 ile uyumu ve CLI argüman ayrıştırma testi."""
    cfg = load_calibration_config()

    # PLAN 3.1 Süreleri
    assert cfg["timing"]["fixation_sec"] == 2.0
    assert cfg["timing"]["cue_sec"] == 1.0
    assert cfg["timing"]["imagery_sec"] == 4.0
    assert cfg["timing"]["rest_min_sec"] == 1.5
    assert cfg["timing"]["rest_max_sec"] == 3.0
    assert cfg["timing"]["inter_run_pause_sec"] == 60.0

    # PLAN 3.2 Miktarlar
    assert cfg["run"]["trials_per_run"] == 20
    assert cfg["run"]["max_consecutive_same_class"] == 3

    # PLAN 3.3 Profiller
    assert "mi2" in cfg["profiles"]
    assert "mi3" in cfg["profiles"]
    assert "mi5" in cfg["profiles"]
    assert cfg["profiles"]["mi2"]["classes"] == ["left", "right", "rest"]
    assert "feet" in cfg["profiles"]["mi3"]["classes"]
    assert "both_hands" in cfg["profiles"]["mi5"]["classes"]
    assert "arithmetic" in cfg["profiles"]["mi5"]["classes"]

    # CLI Argüman Ayrıştırma
    parser = build_arg_parser()
    args = parser.parse_args([
        "--subject", "sub-05",
        "--session", "ses-20261020",
        "--profile", "mi5",
        "--runs", "10",
        "--seed", "999",
        "--simulator",
        "--windowed",
    ])
    assert args.subject == "sub-05"
    assert args.session == "ses-20261020"
    assert args.profile == "mi5"
    assert args.runs == 10
    assert args.seed == 999
    assert args.simulator is True
    assert args.windowed is True

