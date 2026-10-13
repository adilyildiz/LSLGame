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

    # Hepsi yeşil ama impedans bilgisi yok -> kapı geçilmemeli
    app.quality_metrics["C4"]["status"] = "green"
    all_ok, warns = app.check_motor_channels_quality()
    assert all_ok is False
    assert any("impedans bilgisi yok" in w for w in warns)

    # Pilot kayıttaki gibi C3/C4 impedansı yüksek -> kapı geçilmemeli
    app.initial_impedances = {"C3": {"value": 66900.0}, "Cz": {"value": 16300.0}, "C4": {"value": 67600.0}}
    all_ok, warns = app.check_motor_channels_quality()
    assert all_ok is False
    assert any("C3" in w and "impedans" in w for w in warns)

    # Kalite yeşil ve impedanslar kabul eşiğinin altında -> kapı geçilir
    app.initial_impedances = {"C3": {"value": 18000.0}, "Cz": {"value": 16300.0}, "C4": {"value": 19000.0}}
    all_ok, warns = app.check_motor_channels_quality()
    assert all_ok is True
    assert len(warns) == 0


def test_e2e_calibration_simulator_recording_and_alignment():
    """K4 Gerçek Hizalama Testi:
    1. sync_channel=True ile simülatör başlatılır.
    2. En az 10 olayda zaman damgası ts = pylsl.local_clock() alınır, hemen ardından
       set_class(...) çağrılır ve cue_* marker'ı timestamp=ts ile gönderilir.
    3. Kaydedilen EEG'de BIP kanalındaki (indeks 7) basamağın ilk örneğinin zaman damgası bulunur.
    4. Her olay için gecikme = basamak_ts - marker_ts.
    5. Kabul: tüm olaylarda -4 ms <= gecikme <= 12 ms. EEG ardışık damga farkı en fazla 6 ms.
    """
    start_test_time = time.time()
    unique_id = f"K4-ALIGN-{int(time.time() * 1000)}"

    # 1. sync_channel=True ile simülatör başlat
    source = SyntheticEEGSource(
        name=f"X.on-SIM-ALIGN-{unique_id}",
        srate=250.0,
        random_seed=42,
        source_id=f"SIM-ALIGN-{unique_id}",
        sync_channel=True,
    )
    source.start()

    marker_pub = MarkerPublisher(
        stream_name=f"BCI_Markers_Align_{unique_id}",
        source_id=f"MARKER-ALIGN-{unique_id}",
    )

    # 2. LSL Inlet'leri aç ve bağlantının kurulduğunu garanti et
    eeg_streams = pylsl.resolve_byprop("source_id", source.source_id, timeout=3.0)
    assert eeg_streams, f"EEG akışı bulunamadı: {source.source_id}"
    eeg_inlet = pylsl.StreamInlet(eeg_streams[0], max_buflen=30)
    eeg_inlet.open_stream(3.0)

    marker_streams = pylsl.resolve_byprop("source_id", marker_pub.stream_info.source_id(), timeout=3.0)
    assert marker_streams, f"Marker akışı bulunamadı: {marker_pub.stream_info.source_id()}"
    marker_inlet = pylsl.StreamInlet(marker_streams[0], max_buflen=30)
    marker_inlet.open_stream(3.0)

    time.sleep(0.15)

    # 2. En az 10 olayda ts = pylsl.local_clock() -> set_class -> marker_pub.push
    from src.simulation.synthetic_eeg import CLASS_CODES
    test_sequence = [
        "left", "rest", "right", "rest", "down", "rest",
        "up", "rest", "left", "rest", "right", "rest",
    ]
    events_sent = []

    try:
        for cls in test_sequence:
            ts = pylsl.local_clock()
            source.set_class(cls, timestamp=ts)
            marker_name = f"cue_{cls}"
            marker_pub.push(marker_name, timestamp=ts)
            events_sent.append((marker_name, cls, ts))
            time.sleep(0.08)

        time.sleep(0.25)
        source.stop()

        # Kaydedilen EEG ve Marker verilerini çek
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

        # Doğrulamalar
        eeg_ts_arr = np.array(recorded_eeg_timestamps)
        eeg_data_arr = np.array(recorded_eeg_samples)
        assert len(eeg_ts_arr) > 100, f"Yetersiz EEG örneği: {len(eeg_ts_arr)}"
        assert len(recorded_markers) == len(test_sequence)

        # 5a. EEG ardışık damga farkı en fazla 6 ms
        diffs_ms = np.diff(eeg_ts_arr) * 1000.0
        max_diff = float(np.max(diffs_ms))
        min_diff = float(np.min(diffs_ms))
        assert max_diff <= 6.0, f"EEG ardışık damga farkı 6 ms'yi aştı: {max_diff:.2f} ms (min: {min_diff:.2f} ms)"

        # 3 & 4. BIP kanalındaki (indeks 7) basamağın ilk örneğinin zaman damgası ve gecikme hesabı
        bip_channel = eeg_data_arr[:, 7]
        latencies_ms = []

        for m_name, target_cls, marker_ts in events_sent:
            target_code = CLASS_CODES[target_cls]
            # m_ts etrafında arama penceresi [-20 ms, +60 ms]
            win_mask = (eeg_ts_arr >= marker_ts - 0.02) & (eeg_ts_arr <= marker_ts + 0.06)
            win_indices = np.where(win_mask)[0]

            step_idx = None
            for idx in win_indices:
                if idx > 0 and bip_channel[idx] == target_code and bip_channel[idx - 1] != target_code:
                    step_idx = idx
                    break

            assert step_idx is not None, f"Olay {m_name} (ts={marker_ts:.4f}) için BIP basamağı bulunamadı!"
            basamak_ts = eeg_ts_arr[step_idx]
            latency = (basamak_ts - marker_ts) * 1000.0
            latencies_ms.append(latency)

            # 5b. -4 ms <= gecikme <= 12 ms
            assert -4.0 <= latency <= 12.0, (
                f"Olay {m_name}: gecikme ({latency:.2f} ms) kabul sınırları [-4 ms, 12 ms] dışında!"
            )

        print(
            f"\n[K4 Hizalama Testi] Örnek Sayısı: {len(latencies_ms)} | "
            f"Gecikme Min: {min(latencies_ms):.2f} ms | "
            f"Ortalama: {np.mean(latencies_ms):.2f} ms | "
            f"Maks: {max(latencies_ms):.2f} ms | "
            f"Maks Ardışık Damga Farkı: {max_diff:.2f} ms"
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

