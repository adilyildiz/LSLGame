"""BCI_Control sözleşmesi, ayrık/sürekli mod ve klavye kaynağı testleri."""

import time
import numpy as np
import pytest
from src.control.contract import (
    ControlMode,
    ControlReceiver,
    ControlSender,
    Direction,
    create_control_stream_info,
    identify_control_mode,
)
from src.control.keyboard_source import KeyboardControlSource


def test_control_info_creation():
    info_disc = create_control_stream_info(ControlMode.DISCRETE)
    assert info_disc.channel_count() == 5
    assert identify_control_mode(info_disc) == ControlMode.DISCRETE

    info_cont = create_control_stream_info(ControlMode.CONTINUOUS)
    assert info_cont.channel_count() == 2
    assert identify_control_mode(info_cont) == ControlMode.CONTINUOUS


def test_discrete_sender_receiver():
    sender = ControlSender(mode=ControlMode.DISCRETE, source_id="TEST_DISC_SENDER")
    receiver = ControlReceiver(source_id="TEST_DISC_SENDER", timeout=5.0)

    # 1. Sol komutu gönder ve al (LSL ilk bağlantı el sıkışması ~3.5 sn sürebilir)
    cmd = None
    start = time.time()
    while time.time() - start < 5.0:
        sender.send_discrete(p_left=0.85, p_right=0.05, p_up=0.0, p_down=0.0, p_rest=0.10)
        cmd = receiver.get_command(timeout=0.05, threshold=0.5)
        if cmd["has_signal"]:
            break
        time.sleep(0.04)

    assert cmd is not None
    assert cmd["has_signal"] is True
    assert cmd["direction"] == Direction.LEFT.value
    assert cmd["confidence"] == pytest.approx(0.85)
    assert cmd["vx"] < 0

    # 2. Dinlenme komutu gönder ve al
    start = time.time()
    cmd2 = None
    while time.time() - start < 5.0:
        sender.send_discrete(p_left=0.1, p_right=0.1, p_up=0.0, p_down=0.0, p_rest=0.8)
        cmd2 = receiver.get_command(timeout=0.05, threshold=0.5)
        if cmd2["has_signal"] and cmd2["direction"] == Direction.REST.value:
            break
        time.sleep(0.04)

    assert cmd2 is not None
    assert cmd2["direction"] == Direction.REST.value

    receiver.close()


def test_continuous_sender_receiver():
    sender = ControlSender(mode=ControlMode.CONTINUOUS, source_id="TEST_CONT_SENDER")
    receiver = ControlReceiver(source_id="TEST_CONT_SENDER", timeout=5.0)

    # Sağa hareket (vx=0.8, vy=0.0)
    cmd = None
    start = time.time()
    while time.time() - start < 5.0:
        sender.send_continuous(vx=0.8, vy=0.0)
        cmd = receiver.get_command(timeout=0.05, threshold=0.3)
        if cmd["has_signal"]:
            break
        time.sleep(0.04)

    assert cmd is not None
    assert cmd["has_signal"] is True
    assert cmd["direction"] == Direction.RIGHT.value
    assert cmd["vx"] == pytest.approx(0.8)

    receiver.close()


def test_keyboard_source_emission():
    # Klavye kaynağını başlatıp tuş simülasyonu yap
    kb = KeyboardControlSource(mode=ControlMode.DISCRETE, source_id="TEST_KB_SOURCE")
    kb.start()
    receiver = ControlReceiver(source_id="TEST_KB_SOURCE", timeout=5.0)

    # Sağa bas
    kb.set_keys(right=True)
    cmd = None
    start = time.time()
    while time.time() - start < 5.0:
        cmd = receiver.get_command(timeout=0.05)
        if cmd["has_signal"] and cmd["direction"] == Direction.RIGHT.value:
            break
        time.sleep(0.04)

    assert cmd is not None
    assert cmd["direction"] == Direction.RIGHT.value

    # Tuşu bırak (dinlenme)
    kb.set_keys(right=False)
    cmd_rest = None
    start = time.time()
    while time.time() - start < 5.0:
        cmd_rest = receiver.get_command(timeout=0.05)
        if cmd_rest["has_signal"] and cmd_rest["direction"] == Direction.REST.value:
            break
        time.sleep(0.04)

    assert cmd_rest is not None
    assert cmd_rest["direction"] == Direction.REST.value

    kb.stop()
    receiver.close()


def test_control_receiver_sample_retention_and_staleness():
    """S1 Testi:
    20 Hz gönderim ve 60 Hz okuma senaryosunda hareketli kare oranı >= %90 olmalı.
    Gönderim durduktan 0.3 sn sonra 'rest' ve has_signal=False dönmeli.
    """
    import threading

    sender = ControlSender(mode=ControlMode.DISCRETE, source_id="TEST_S1_RETENTION")
    receiver = ControlReceiver(source_id="TEST_S1_RETENTION", stale_after=0.3, timeout=5.0)

    running = True

    def sender_loop():
        while running:
            sender.send_discrete(p_left=1.0, p_right=0.0, p_up=0.0, p_down=0.0, p_rest=0.0)
            time.sleep(0.05)  # 20 Hz

    th = threading.Thread(target=sender_loop, daemon=True)
    th.start()

    try:
        # İlk sinyali bekle
        start_t = time.time()
        while time.time() - start_t < 3.0:
            c = receiver.get_command(timeout=0.05)
            if c["has_signal"]:
                break
            time.sleep(0.02)

        # 60 FPS hızında 60 kare (1 saniye) oku
        frames = []
        for _ in range(60):
            c = receiver.get_command(timeout=0.0)
            frames.append(c)
            time.sleep(1.0 / 60.0)

        # Hareketli kare oranı >= %90 olmalı
        moving_frames = sum(
            1 for f in frames if f["direction"] == Direction.LEFT.value and f["has_signal"]
        )
        moving_ratio = moving_frames / len(frames)
        assert moving_ratio >= 0.90, (
            f"Hareketli kare oranı çok düşük: {moving_ratio:.1%} ({moving_frames}/{len(frames)}). Beklenen >= %90"
        )
    finally:
        running = False
        th.join(timeout=1.0)

    # Gönderim durduktan sonra stale_after (0.3 sn) geçmesini bekle
    time.sleep(0.35)
    cmd_after = receiver.get_command(timeout=0.0)

    assert cmd_after["has_signal"] is False, "Sinyal kesildikten sonra has_signal=False olmalıydı."
    assert cmd_after["direction"] == Direction.REST.value, "Sinyal kesildikten sonra yön rest olmalıydı."

    receiver.close()


def test_control_receiver_timeout_nonexistent_and_closed_stream():
    """S2 Testi:
    Var olmayan veya kapatılmış bir akışa bağlanma girişimi, belirtilen zaman aşımı + 2 sn
    içinde TimeoutError ile bitmeli. Testin tamamına üst sınır konulur.
    """
    import pylsl

    test_start = time.time()
    max_test_duration = 8.0

    # 1. Var olmayan akışa bağlanma (timeout = 1.0 sn)
    t0 = time.time()
    with pytest.raises(TimeoutError):
        ControlReceiver(source_id="NON_EXISTENT_STREAM_S2_CHECK", timeout=1.0)
    elapsed_nonexistent = time.time() - t0
    assert elapsed_nonexistent <= 1.0 + 2.0, (
        f"Var olmayan akış için zaman aşımı süresi aşıldı: {elapsed_nonexistent:.2f} sn"
    )

    # 2. Kapatılmış / silinmiş akışa bağlanma (timeout = 1.0 sn)
    temp_sender = ControlSender(mode=ControlMode.DISCRETE, source_id="TEMP_CLOSED_S2_CHECK")
    resolved = pylsl.resolve_byprop("source_id", "TEMP_CLOSED_S2_CHECK", timeout=3.0)
    assert len(resolved) > 0, "Geçici akış resolve edilemedi."

    # Akışı kapat
    temp_sender.outlet = None
    del temp_sender
    time.sleep(0.3)

    t1 = time.time()
    with pytest.raises(TimeoutError):
        ControlReceiver(stream_info=resolved[0], timeout=1.0)
    elapsed_closed = time.time() - t1
    assert elapsed_closed <= 1.0 + 2.0, (
        f"Kapatılmış akış için zaman aşımı süresi aşıldı: {elapsed_closed:.2f} sn"
    )

    total_test_time = time.time() - test_start
    assert total_test_time < max_test_duration, (
        f"Test toplam üst sınırı aştı: {total_test_time:.2f} sn"
    )


def test_standalone_keyboard_workflow():
    """S3 Testi:
    Standalone modda klavye kaynağı ile BCI_Control üzerinden oyun mantığı tam zincir testi.
    """
    from src.game.ball_roll import BallRollGameLogic

    kb = KeyboardControlSource(mode=ControlMode.DISCRETE, source_id="TEST_STANDALONE_KB_E2E")
    kb.start()

    receiver = ControlReceiver(source_id="TEST_STANDALONE_KB_E2E", timeout=5.0)
    logic = BallRollGameLogic(arena_width=800.0, ball_speed=240.0)

    try:
        # Sol tuşa bas
        kb.set_keys(left=True)
        cmd = None
        start = time.time()
        while time.time() - start < 3.0:
            cmd = receiver.get_command(timeout=0.05)
            if cmd["has_signal"] and cmd["direction"] == Direction.LEFT.value:
                break
            time.sleep(0.02)

        assert cmd is not None
        assert cmd["direction"] == Direction.LEFT.value

        initial_ball_x = logic.ball_x
        # 10 kare mantığı güncelle
        for _ in range(10):
            cmd_frame = receiver.get_command(timeout=0.0)
            logic.update(dt=0.016, command=cmd_frame)

        # Top sola hareket etmiş olmalı
        assert logic.ball_x < initial_ball_x, "Top sol komutuyla sola hareket etmedi."

    finally:
        kb.stop()
        receiver.close()
