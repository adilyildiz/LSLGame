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
    receiver = ControlReceiver(stream_info=sender.stream_info)

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
    receiver = ControlReceiver(stream_info=sender.stream_info)

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
    receiver = ControlReceiver(stream_info=kb.sender.stream_info)

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
