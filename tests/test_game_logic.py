"""Top Yuvarla oyunu mantık, kural ve marker testleri (Headless)."""

import pytest
from src.game.ball_roll import BallRollGameLogic, MarkerPublisher, UI_STRINGS


def test_game_logic_headless_movement_and_scoring():
    """Temel hareket, isabet ve denemeler arası mola geçişi testi."""
    marker_pub = MarkerPublisher(source_id="TEST_MARKERS")
    logic = BallRollGameLogic(
        arena_width=800.0,
        arena_height=500.0,
        ball_speed=500.0,
        inter_trial_pause=1.5,
        marker_pub=marker_pub,
        random_seed=42,
    )

    assert logic.score == 0
    assert logic.hits == 0
    assert logic.misses == 0
    assert logic.trial_count == 1
    # Hedef sol veya sağda olmalı
    assert logic.target_side in ("left", "right")

    initial_target_side = logic.target_side

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
    assert logic.hits == 1
    assert logic.state == "pause"
    assert logic.ball_x == logic.center_x

    # Mola süresi (1.5 sn) tamamlanınca sonraki denemeye geçmeli
    logic.update(dt=1.51, command={"direction": "rest"})
    assert logic.state == "active"
    assert logic.trial_count == 2


def test_target_sequence_balanced_and_constrained():
    """40 denemelik bir sırada:
    - Sol ve sağ sayıları eşit (20 sol, 20 sağ).
    - En uzun aynı-taraf serisi <= 3.
    - Sıra kesin sağ-sol değişimi DEĞİL.
    """
    # 1. generate_balanced_sequence testi
    seq = BallRollGameLogic.generate_balanced_sequence(count=40, seed=42)
    assert len(seq) == 40
    assert seq.count("left") == 20
    assert seq.count("right") == 20

    max_run = 1
    current_run = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    assert max_run <= 3, f"En uzun seri 3'ten büyük olamaz: {max_run}"

    strict_alternation_lr = ["left", "right"] * 20
    strict_alternation_rl = ["right", "left"] * 20
    assert seq != strict_alternation_lr, "Sıra kesin sol-sağ ardışık olmamalı."
    assert seq != strict_alternation_rl, "Sıra kesin sağ-sol ardışık olmamalı."

    # 2. Oyun mantığındaki spawn_new_target döngüsü üzerinden doğrulama
    logic = BallRollGameLogic(random_seed=123)
    spawned_seq = [logic.target_side]
    for _ in range(39):
        spawned_seq.append(logic.spawn_new_target())

    assert len(spawned_seq) == 40
    assert spawned_seq.count("left") == 20
    assert spawned_seq.count("right") == 20

    max_run_spawned = 1
    cur_run = 1
    for i in range(1, len(spawned_seq)):
        if spawned_seq[i] == spawned_seq[i - 1]:
            cur_run += 1
            max_run_spawned = max(max_run_spawned, cur_run)
        else:
            cur_run = 1
    assert max_run_spawned <= 3, f"Spawn serisinde en uzun seri 3'ten büyük olamaz: {max_run_spawned}"
    assert spawned_seq != strict_alternation_lr
    assert spawned_seq != strict_alternation_rl


def test_wrong_direction_results_in_miss():
    """Yanlış yöne sürekli giden oyuncu: isabet 0, ıska > 0 olmalı."""
    marker_pub = MarkerPublisher(source_id="TEST_WRONG_DIR")
    logic = BallRollGameLogic(
        arena_width=800.0,
        ball_speed=400.0,
        marker_pub=marker_pub,
        random_seed=42,
    )

    initial_target = logic.target_side
    wrong_direction = "left" if initial_target == "right" else "right"
    cmd = {"direction": wrong_direction, "confidence": 1.0}

    # Yanlış duvara çarpana kadar güncelle
    missed = False
    for _ in range(100):
        logic.update(dt=0.02, command=cmd)
        if logic.misses > 0:
            missed = True
            break

    assert missed is True, "Top yanlış duvara çarptığında ıska oluşmadı."
    assert logic.hits == 0
    assert logic.score == 0
    assert logic.misses == 1
    assert logic.state == "pause"
    assert logic.ball_x == logic.center_x

    # Marker sırasını kontrol et: trial_start, cue_*, target_miss, trial_end
    marker_names = [m[0] for m in marker_pub.history]
    assert "trial_start" in marker_names
    assert f"cue_{initial_target}" in marker_names
    assert "target_miss" in marker_names
    assert "trial_end" in marker_names

    miss_idx = marker_names.index("target_miss")
    end_idx = marker_names.index("trial_end")
    assert miss_idx < end_idx, "target_miss, trial_end marker'ından önce gelmeli."


def test_idle_player_trial_timeout():
    """Hiç hareket etmeyen oyuncu: 10 sn sonra trial_timeout oluşmalı."""
    marker_pub = MarkerPublisher(source_id="TEST_TIMEOUT")
    logic = BallRollGameLogic(
        trial_timeout=10.0,
        marker_pub=marker_pub,
        random_seed=42,
    )

    cmd = {"direction": "rest", "confidence": 1.0}

    # 9.9 sn ilerlet (99 x 0.1s)
    for _ in range(99):
        logic.update(dt=0.1, command=cmd)

    assert logic.misses == 0
    assert logic.state == "active"

    # 0.2 sn daha ilerlet (toplam 10.1 sn >= 10.0 sn)
    logic.update(dt=0.2, command=cmd)

    assert logic.misses == 1
    assert logic.hits == 0
    assert logic.state == "pause"
    assert logic.ball_x == logic.center_x

    marker_names = [m[0] for m in marker_pub.history]
    assert "trial_timeout" in marker_names
    assert "trial_end" in marker_names
    assert marker_names.index("trial_timeout") < marker_names.index("trial_end")


def test_inter_trial_pause_ignores_commands():
    """Mola sırasında gelen komutlar topu hareket ettirmemeli."""
    logic = BallRollGameLogic(
        ball_speed=400.0,
        inter_trial_pause=1.5,
        random_seed=42,
    )

    # Hedefe ulaştırarak molaya sok
    cmd = {"direction": logic.target_side, "confidence": 1.0}
    for _ in range(100):
        if logic.update(dt=0.02, command=cmd):
            break

    assert logic.hits == 1
    assert logic.state == "pause"
    assert logic.ball_x == logic.center_x

    # Mola sırasında hareket komutu gönder (0.5 sn)
    move_cmd = {"direction": "left", "vx": -1.0}
    for _ in range(25):  # 25 x 0.02 = 0.5s < 1.5s
        logic.update(dt=0.02, command=move_cmd)
        assert logic.ball_x == logic.center_x, "Mola sırasında top hareket etti!"

    assert logic.state == "pause"

    # Molayı tamamla (1.1 sn daha ilerlet -> toplam 1.6s > 1.5s)
    logic.update(dt=1.1, command={"direction": "rest"})

    assert logic.state == "active"
    assert logic.trial_count == 2

    # Artık hareket etmeli
    logic.update(dt=0.1, command={"direction": "left", "vx": -1.0})
    assert logic.ball_x < logic.center_x, "Mola bittikten sonra top hareket etmedi."


def test_ui_strings_contain_turkish_characters():
    """Ekranda kullanılan metinlerin Türkçe karakter içerdiğini kontrol eden test (pencere açmaz)."""
    required_keys = [
        "score",
        "target_left",
        "target_right",
        "go_left",
        "go_right",
        "no_signal",
        "simulation",
        "cmd_left",
        "cmd_right",
        "cmd_rest",
        "cmd_prefix",
        "hud_template",
    ]
    for k in required_keys:
        assert k in UI_STRINGS, f"UI_STRINGS içinde eksik anahtar: {k}"

    assert UI_STRINGS["score"] == "Skor"
    assert "Hedef: SAĞ" in UI_STRINGS["target_right"]
    assert "Hedef: SOL" in UI_STRINGS["target_left"]
    assert "SAĞA GİT" in UI_STRINGS["go_right"]
    assert "SOLA GİT" in UI_STRINGS["go_left"]
    assert "SİNYAL YOK" in UI_STRINGS["no_signal"]
    assert "SİMÜLASYON" in UI_STRINGS["simulation"]
    assert "SAĞ" in UI_STRINGS["cmd_right"]
    assert "SOL" in UI_STRINGS["cmd_left"]
    assert "DİNLENME" in UI_STRINGS["cmd_rest"]
    assert "İsabet" in UI_STRINGS["hud_template"]
    assert "Iska" in UI_STRINGS["hud_template"]
    assert "Doğruluk" in UI_STRINGS["hud_template"]

    # Türkçe karakterler: ğ, Ğ, ı, İ, ö, Ö, ü, Ü, ş, Ş, ç, Ç
    turkish_chars = set("ğĞıİöÖüÜşŞçÇ")
    all_text = " ".join(UI_STRINGS.values())
    present_turkish = set(all_text) & turkish_chars
    assert len(present_turkish) > 0, "Metinlerde hiçbir Türkçe karakter bulunamadı!"
    assert "Ğ" in present_turkish or "ğ" in present_turkish, "'Ğ'/'ğ' karakteri bulunamadı."
    assert "İ" in present_turkish or "ı" in present_turkish, "'İ'/'ı' karakteri bulunamadı."

    # Eski hatalı ASCII yazımların bulunmadığını doğrula
    assert "SAGA GIT" not in all_text
    assert "SINYAL YOK" not in all_text
    assert "SIMULASYON" not in all_text


def test_markers_are_pure_ascii_and_proper_sequence():
    """LSL marker'larının saf ASCII olduğunu ve doğru sırada yayınlandığını doğrular."""
    marker_pub = MarkerPublisher(source_id="TEST_ASCII_MARKERS")
    logic = BallRollGameLogic(
        marker_pub=marker_pub,
        inter_trial_pause=1.5,
        random_seed=42,
    )

    initial_side = logic.target_side
    cmd = {"direction": initial_side, "confidence": 1.0}
    for _ in range(100):
        if logic.update(dt=0.02, command=cmd):
            break

    # Tüm marker'lar ASCII olmalı
    for marker_name, _ in marker_pub.history:
        assert marker_name.isascii(), f"Marker ASCII değil: {marker_name}"
        assert all(c.isalnum() or c in ("_", "-") for c in marker_name)

    names = [m[0] for m in marker_pub.history]
    assert names[0] == "game_start"
    assert names[1] == "trial_start"
    assert names[2] == f"cue_{initial_side}"
    assert names[3] == "target_hit"
    assert names[4] == "trial_end"
