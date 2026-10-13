"""Top Yuvarla oyunu mantık ve marker testleri (Headless)."""

import pytest
from src.game.ball_roll import BallRollGameLogic, MarkerPublisher


def test_game_logic_headless_movement_and_scoring():
    marker_pub = MarkerPublisher(source_id="TEST_MARKERS")
    logic = BallRollGameLogic(
        arena_width=800.0,
        arena_height=500.0,
        ball_speed=500.0,
        marker_pub=marker_pub,
    )

    assert logic.score == 0
    assert logic.trial_count == 1
    # Hedef sol veya sağda olmalı
    assert logic.target_side in ("left", "right")

    initial_target_side = logic.target_side
    initial_target_x = logic.target_x

    # Hedefe doğru hareket ettir
    cmd = {"direction": initial_target_side, "confidence": 1.0}

    hit = False
    # En fazla 2 saniye (100 adım x 0.02s) simüle et
    for _ in range(100):
        hit = logic.update(dt=0.02, command=cmd)
        if hit:
            break

    assert hit is True, "Top hedefe ulaşamadı."
    assert logic.score == 1
    assert logic.trial_count == 2
    # Yeni hedef ters tarafta olmalı
    assert logic.target_side != initial_target_side


def test_markers_are_pure_ascii():
    marker_pub = MarkerPublisher(source_id="TEST_ASCII_MARKERS")
    logic = BallRollGameLogic(marker_pub=marker_pub)

    # Bir vuruş simüle et
    logic.update(dt=0.02, command={"direction": logic.target_side})

    for marker_name, ts in marker_pub.history:
        assert marker_name.isascii(), f"Marker ASCII değil: {marker_name}"
        # Boşluk veya bozuk karakter olmamalı
        assert all(c.isalnum() or c in ("_", "-") for c in marker_name)
