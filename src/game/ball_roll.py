"""Seviye 1 'Top Yuvarla' (Roll the Ball) BCI Oyunu.

PLAN.md Bölüm 6.2 ve agy_tasks/03_oyun_duzeltmeleri.md uyarınca:
- Minimal prototip (pygame-ce tabanlı).
- Yalnızca 'BCI_Control' LSL akışını dinler, kaynağı bilmez.
- 4'lük bloklar halinde dengeli, rastgele hedef sırası (2 sol + 2 sağ, maks 3 aynı taraf ardışık).
- Yanlış duvara çarpınca ıska (target_miss), zaman aşımında trial_timeout.
- Denemeler arası dinlenme molası (inter_trial_pause).
- Türkçe yazı tipi ve doğru Türkçe ekran metinleri (Skor, Hedef: SAĞ/SOL, SAĞA/SOLA GİT vb.).
- pygame.draw.polygon ile üçgen ok çizimi (yazı tipi glif bağımlılığı yok).
- Oyun olaylarını 'BCI_Markers' LSL akışına ASCII olarak yazar (cue_left, cue_right, target_hit, target_miss, trial_timeout, trial_end).
- Mantık katmanı (BallRollGameLogic) grafik katmanından tamamen ayrıdır; headless test edilebilir.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pylsl

from src.control.contract import ControlReceiver, Direction

logger = logging.getLogger(__name__)

MARKER_STREAM_NAME = "BCI_Markers"
MARKER_STREAM_TYPE = "Markers"

UI_STRINGS: Dict[str, str] = {
    "score": "Skor",
    "target_prefix": "Hedef: ",
    "target_left": "Hedef: SOL",
    "target_right": "Hedef: SAĞ",
    "go_left": "SOLA GİT",
    "go_right": "SAĞA GİT",
    "no_signal": "SİNYAL YOK",
    "simulation": "SİMÜLASYON",
    "cmd_prefix": "BCI Komut: ",
    "cmd_left": "SOL",
    "cmd_right": "SAĞ",
    "cmd_rest": "DİNLENME",
    "hud_template": "İsabet: {hits} / Iska: {misses} / Doğruluk: %{accuracy:.0f}",
    "feedback_hit": "İSABET!",
    "feedback_miss": "ISKA!",
    "feedback_timeout": "ZAMAN AŞIMI!",
    "pause_rest": "Dinlenme...",
}


def get_system_font(size: int, bold: bool = False) -> Any:
    """Türkçe karakterleri destekleyen bir sistem yazı tipi yükler.

    Sırasıyla 'segoeui', 'arial', 'dejavusans' denenir; hiçbiri yoksa varsayılana dönülür.
    """
    import pygame

    if not pygame.font.get_init():
        pygame.font.init()

    for name in ("segoeui", "arial", "dejavusans"):
        try:
            f = pygame.font.SysFont(name, size, bold=bold)
            if f:
                return f
        except Exception:
            pass
    return pygame.font.Font(None, size)


def draw_target_cue(
    screen: Any,
    font: Any,
    center_x: int,
    center_y: int,
    target_side: str,
    color: Tuple[int, int, int],
) -> None:
    """Hedef yön göstergesini (metin ve pygame.draw.polygon üçgen ok) çizer."""
    import pygame

    text_str = UI_STRINGS["go_left"] if target_side == "left" else UI_STRINGS["go_right"]
    text_surf = font.render(text_str, True, color)
    text_w, text_h = text_surf.get_width(), text_surf.get_height()

    arrow_w = 20
    arrow_h = 24
    spacing = 14
    total_w = text_w + spacing + arrow_w
    start_x = center_x - total_w // 2

    if target_side == "left":
        tri_x = start_x
        points = [
            (tri_x, center_y),
            (tri_x + arrow_w, center_y - arrow_h // 2),
            (tri_x + arrow_w, center_y + arrow_h // 2),
        ]
        pygame.draw.polygon(screen, color, points)
        screen.blit(text_surf, (start_x + arrow_w + spacing, center_y - text_h // 2))
    else:
        screen.blit(text_surf, (start_x, center_y - text_h // 2))
        tri_x = start_x + text_w + spacing
        points = [
            (tri_x + arrow_w, center_y),
            (tri_x, center_y - arrow_h // 2),
            (tri_x, center_y + arrow_h // 2),
        ]
        pygame.draw.polygon(screen, color, points)


class MarkerPublisher:
    """LSL üzerinden ASCII olay işaretçileri (markers) yayınlayan sınıf."""

    def __init__(self, stream_name: str = MARKER_STREAM_NAME, source_id: str = "Ball_Roll_Markers"):
        self.stream_name = stream_name
        self.stream_info = pylsl.StreamInfo(
            name=self.stream_name,
            type=MARKER_STREAM_TYPE,
            channel_count=1,
            nominal_srate=0.0,
            channel_format=pylsl.cf_string,
            source_id=source_id,
        )
        self.outlet = pylsl.StreamOutlet(self.stream_info)
        self.history: List[Tuple[str, float]] = []

    def push(self, marker_name: str) -> None:
        """ASCII marker adını yayınlar."""
        # Yalnızca ASCII kontrolü
        if not marker_name.isascii():
            raise ValueError(f"Marker ismi yalnızca ASCII karakter içerebilir: '{marker_name}'")

        timestamp = pylsl.local_clock()
        self.outlet.push_sample([marker_name], timestamp)
        self.history.append((marker_name, timestamp))
        logger.info(f"BCI Marker: {marker_name} @ {timestamp:.3f}")


class BallRollGameLogic:
    """Tamamen headless çalışabilen saf oyun mantığı."""

    def __init__(
        self,
        arena_width: float = 800.0,
        arena_height: float = 500.0,
        ball_speed: float = 240.0,  # piksel/sn
        ball_radius: float = 22.0,
        target_radius: float = 35.0,
        trial_timeout: float = 10.0,
        inter_trial_pause: float = 1.5,
        marker_pub: Optional[MarkerPublisher] = None,
        random_seed: Optional[int] = None,
    ):
        self.arena_width = arena_width
        self.arena_height = arena_height
        self.ball_speed = ball_speed
        self.ball_radius = ball_radius
        self.target_radius = target_radius
        self.trial_timeout = float(trial_timeout)
        self.inter_trial_pause = float(inter_trial_pause)
        self.marker_pub = marker_pub

        self.rng = random.Random(random_seed)

        self.center_x = arena_width / 2.0
        self.center_y = arena_height / 2.0

        self.ball_x = self.center_x
        self.ball_y = self.center_y

        self.hits = 0
        self.misses = 0
        self.score = 0
        self.trial_count = 0
        self.state: str = "active"  # 'active' veya 'pause'
        self.trial_elapsed: float = 0.0
        self.pause_elapsed: float = 0.0
        self.last_outcome: Optional[str] = None  # 'hit', 'miss', 'timeout'

        self.target_side: str = "left"  # 'left' veya 'right'
        self.target_x = 0.0
        self.target_y = self.center_y
        self.last_hit_time: float = 0.0

        self.target_history: List[str] = []
        self.target_queue: List[str] = []

        if self.marker_pub:
            self.marker_pub.push("game_start")

        self.spawn_new_target()

    @property
    def accuracy(self) -> float:
        """Yüzde olarak doğruluk oranı (%0 - %100)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100.0

    @property
    def is_paused(self) -> bool:
        """Denemeler arası mola durumunda mı?"""
        return self.state == "pause"

    @staticmethod
    def generate_balanced_sequence(count: int, seed: Optional[int] = None) -> List[str]:
        """4'lük bloklar halinde dengeli hedef sırası üretir.

        - Her 4'lük blokta 2 sol + 2 sağ.
        - Aynı taraf en fazla 3 kez üst üste gelebilir.
        - `seed` ile tekrarlanabilir.
        """
        rng = random.Random(seed)
        sequence: List[str] = []
        permutations = [
            ["left", "left", "right", "right"],
            ["left", "right", "left", "right"],
            ["left", "right", "right", "left"],
            ["right", "left", "left", "right"],
            ["right", "left", "right", "left"],
            ["right", "right", "left", "left"],
        ]

        while len(sequence) < count:
            valid_perms = []
            for p in permutations:
                combined = sequence[-3:] + p
                has_run_gt_3 = False
                current_run = 1
                for i in range(1, len(combined)):
                    if combined[i] == combined[i - 1]:
                        current_run += 1
                        if current_run > 3:
                            has_run_gt_3 = True
                            break
                    else:
                        current_run = 1
                if not has_run_gt_3:
                    valid_perms.append(p)

            chosen = rng.choice(valid_perms)
            sequence.extend(chosen)

        return sequence[:count]

    def _generate_block(self) -> List[str]:
        """Geçmişe göre kurallara uygun 4'lük bir blok üretir."""
        permutations = [
            ["left", "left", "right", "right"],
            ["left", "right", "left", "right"],
            ["left", "right", "right", "left"],
            ["right", "left", "left", "right"],
            ["right", "left", "right", "left"],
            ["right", "right", "left", "left"],
        ]

        valid_perms = []
        for p in permutations:
            combined = self.target_history[-3:] + p
            has_run_gt_3 = False
            current_run = 1
            for i in range(1, len(combined)):
                if combined[i] == combined[i - 1]:
                    current_run += 1
                    if current_run > 3:
                        has_run_gt_3 = True
                        break
                else:
                    current_run = 1
            if not has_run_gt_3:
                valid_perms.append(p)

        chosen = self.rng.choice(valid_perms)
        return list(chosen)

    def spawn_new_target(self, side: Optional[str] = None) -> str:
        """Yeni bir hedef konumu belirler ve LSL marker gönderir."""
        if side is None:
            if not self.target_queue:
                self.target_queue.extend(self._generate_block())
            side = self.target_queue.pop(0)

        self.target_side = side
        self.target_history.append(side)

        margin = 100.0
        if self.target_side == "left":
            self.target_x = margin
        else:
            self.target_x = self.arena_width - margin

        self.target_y = self.center_y
        self.ball_x = self.center_x
        self.ball_y = self.center_y

        self.trial_count += 1
        self.trial_elapsed = 0.0
        self.pause_elapsed = 0.0
        self.state = "active"

        if self.marker_pub:
            self.marker_pub.push("trial_start")
            cue_marker = f"cue_{self.target_side}"
            self.marker_pub.push(cue_marker)

        return self.target_side

    def update(self, dt: float, command: Dict[str, Any]) -> bool:
        """Bir kare (frame) ilerletir.

        Returns
        -------
        bool: Hedef bu karede vuruldu mu?
        """
        if self.state == "pause":
            self.pause_elapsed += dt
            self.ball_x = self.center_x
            self.ball_y = self.center_y
            if self.pause_elapsed >= self.inter_trial_pause:
                self.spawn_new_target()
            return False

        # Aktif deneme süresini güncelle ve zaman aşımını kontrol et
        self.trial_elapsed += dt
        if self.trial_elapsed >= self.trial_timeout:
            self.misses += 1
            self.last_outcome = "timeout"
            if self.marker_pub:
                self.marker_pub.push("trial_timeout")
                self.marker_pub.push("trial_end")
            self.state = "pause"
            self.pause_elapsed = 0.0
            self.ball_x = self.center_x
            self.ball_y = self.center_y
            return False

        # Hareketi uygula
        vx = 0.0
        has_signal = command.get("has_signal", True)

        if not has_signal:
            vx = 0.0
        else:
            direction = command.get("direction", "rest")
            if "vx" in command and abs(command["vx"]) > 0.01:
                vx = float(command["vx"])
            elif direction == Direction.LEFT.value:
                vx = -1.0
            elif direction == Direction.RIGHT.value:
                vx = 1.0

        # Top pozisyonunu güncelle
        self.ball_x += vx * self.ball_speed * dt

        # Sınırları kontrol et
        min_x = self.ball_radius
        max_x = self.arena_width - self.ball_radius
        self.ball_x = max(min_x, min(max_x, self.ball_x))

        # Çarpışma kontrolü (Hedef)
        dist_to_target = abs(self.ball_x - self.target_x)
        hit_threshold = self.ball_radius + self.target_radius

        if dist_to_target <= hit_threshold:
            self.hits += 1
            self.score = self.hits
            self.last_hit_time = time.time()
            self.last_outcome = "hit"
            if self.marker_pub:
                self.marker_pub.push("target_hit")
                self.marker_pub.push("trial_end")

            self.state = "pause"
            self.pause_elapsed = 0.0
            self.ball_x = self.center_x
            self.ball_y = self.center_y
            return True

        # Iska kontrolü (Yanlış duvara çarpma)
        is_wrong_wall = (self.target_side == "right" and self.ball_x <= min_x) or (
            self.target_side == "left" and self.ball_x >= max_x
        )
        if is_wrong_wall:
            self.misses += 1
            self.last_outcome = "miss"
            if self.marker_pub:
                self.marker_pub.push("target_miss")
                self.marker_pub.push("trial_end")

            self.state = "pause"
            self.pause_elapsed = 0.0
            self.ball_x = self.center_x
            self.ball_y = self.center_y
            return False

        return False


class BallRollGame:
    """Pygame-ce ile görselleştirilen 'Top Yuvarla' BCI oyunu."""

    def __init__(
        self,
        logic: Optional[BallRollGameLogic] = None,
        control_receiver: Optional[ControlReceiver] = None,
        keyboard_source: Optional[Any] = None,
        headless: bool = False,
    ):
        self.headless = headless
        self.marker_pub = MarkerPublisher() if not (logic and logic.marker_pub) else logic.marker_pub
        self.logic = logic or BallRollGameLogic(marker_pub=self.marker_pub)
        self.receiver = control_receiver
        self.keyboard_source = keyboard_source

        self.running = False
        self.width = int(self.logic.arena_width)
        self.height = int(self.logic.arena_height)

    def run(self, max_seconds: Optional[float] = None) -> None:
        """Oyun döngüsünü başlatır."""
        import pygame

        if self.headless:
            logger.info("Headless modda oyun başlatıldı.")
            self.running = True
            start_t = time.time()
            while self.running:
                dt = 0.02
                cmd = self.receiver.get_command(timeout=0.0) if self.receiver else {}
                self.logic.update(dt, cmd)
                if max_seconds and (time.time() - start_t) >= max_seconds:
                    break
                time.sleep(dt)
            return

        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("LSLGame - Top Yuvarla (Seviye 1)")
        clock = pygame.time.Clock()
        font = get_system_font(24)
        font_large = get_system_font(34, bold=True)

        self.running = True
        logger.info("Pygame penceresi açıldı.")

        try:
            while self.running:
                dt = clock.tick(60) / 1000.0  # saniye

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.running = False

                # Dahili klavye kaynağı varsa, oyun penceresindeki tuş basımlarını kaynağa aktar
                if self.keyboard_source is not None:
                    keys = pygame.key.get_pressed()
                    k_left = keys[pygame.K_LEFT] or keys[pygame.K_a]
                    k_right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
                    k_up = keys[pygame.K_UP] or keys[pygame.K_w]
                    k_down = keys[pygame.K_DOWN] or keys[pygame.K_s]
                    self.keyboard_source.set_keys(left=k_left, right=k_right, up=k_up, down=k_down)

                # BCI kontrol sinyalini oku
                cmd: Dict[str, Any] = {}
                if self.receiver:
                    cmd = self.receiver.get_command(timeout=0.0)
                else:
                    cmd = {"has_signal": False, "direction": Direction.REST.value}

                # Mantığı güncelle
                self.logic.update(dt, cmd)

                # --- Çizim ---
                # Arka plan
                screen.fill((24, 26, 32))

                # Arena sınırları ve zemin çizgisi
                ground_y = int(self.logic.center_y)
                pygame.draw.line(screen, (50, 54, 66), (50, ground_y), (self.width - 50, ground_y), 3)

                # Hedef çizimi (yalnızca aktif denemede)
                target_color = (60, 180, 240) if self.logic.target_side == "left" else (240, 160, 60)
                if self.logic.state == "active":
                    pygame.draw.circle(
                        screen,
                        target_color,
                        (int(self.logic.target_x), int(self.logic.target_y)),
                        int(self.logic.target_radius),
                        width=4,
                    )
                    pygame.draw.circle(
                        screen,
                        (target_color[0] // 3, target_color[1] // 3, target_color[2] // 3),
                        (int(self.logic.target_x), int(self.logic.target_y)),
                        int(self.logic.target_radius) - 6,
                    )

                # Top çizimi
                ball_color = (255, 230, 80)
                pygame.draw.circle(
                    screen,
                    ball_color,
                    (int(self.logic.ball_x), int(self.logic.ball_y)),
                    int(self.logic.ball_radius),
                )
                # Topun içi ışık efekti
                pygame.draw.circle(
                    screen,
                    (255, 255, 200),
                    (int(self.logic.ball_x - 5), int(self.logic.ball_y - 5)),
                    int(self.logic.ball_radius * 0.4),
                )

                # HUD Bilgileri (Sol üst)
                hud_text = UI_STRINGS["hud_template"].format(
                    hits=self.logic.hits,
                    misses=self.logic.misses,
                    accuracy=self.logic.accuracy,
                )
                hud_surf = font_large.render(hud_text, True, (240, 240, 240))
                screen.blit(hud_surf, (30, 20))

                if self.logic.state == "active":
                    target_info = (
                        UI_STRINGS["target_left"]
                        if self.logic.target_side == "left"
                        else UI_STRINGS["target_right"]
                    )
                    t_surf = font.render(target_info, True, target_color)
                else:
                    t_surf = font.render("Mola / Dinlenme", True, (140, 140, 150))
                screen.blit(t_surf, (30, 60))

                # BCI Komut ve Durum Bilgisi (Sağ üst)
                has_signal = cmd.get("has_signal", False) if self.receiver else False
                dir_raw = str(cmd.get("direction", "rest")).lower()
                conf_val = float(cmd.get("confidence", 0.0))

                if not has_signal:
                    control_info = f"{UI_STRINGS['cmd_prefix']}{UI_STRINGS['no_signal']}"
                    c_surf = font.render(control_info, True, (255, 90, 90))
                else:
                    if dir_raw == "left":
                        tr_dir = UI_STRINGS["cmd_left"]
                        cmd_color = (160, 220, 160)
                    elif dir_raw == "right":
                        tr_dir = UI_STRINGS["cmd_right"]
                        cmd_color = (160, 220, 160)
                    else:
                        tr_dir = UI_STRINGS["cmd_rest"]
                        cmd_color = (140, 140, 140)
                    control_info = f"{UI_STRINGS['cmd_prefix']}{tr_dir} (%{conf_val * 100:.0f})"
                    c_surf = font.render(control_info, True, cmd_color)
                screen.blit(c_surf, (self.width - 320, 20))

                # Simülasyon göstergesi
                is_sim = cmd.get("is_simulator", False) or getattr(self.receiver, "is_simulator", False)
                if is_sim:
                    sim_surf = font.render(f"[ {UI_STRINGS['simulation']} ]", True, (255, 190, 60))
                    screen.blit(sim_surf, (self.width - 320, 50))

                # Hedef Yön Oku ve Geri Bildirim (Üst Orta)
                if self.logic.state == "pause":
                    if self.logic.pause_elapsed <= 0.5:
                        # Kısa geri bildirim (~0.5 sn): isabette yeşil, ıskada kırmızı
                        if self.logic.last_outcome == "hit":
                            fb_text = UI_STRINGS["feedback_hit"]
                            fb_color = (60, 220, 100)
                        elif self.logic.last_outcome == "miss":
                            fb_text = UI_STRINGS["feedback_miss"]
                            fb_color = (240, 70, 70)
                        else:
                            fb_text = UI_STRINGS["feedback_timeout"]
                            fb_color = (240, 70, 70)
                        fb_surf = font_large.render(fb_text, True, fb_color)
                        screen.blit(fb_surf, fb_surf.get_rect(center=(self.width // 2, 70)))
                    else:
                        rest_surf = font.render(UI_STRINGS["pause_rest"], True, (150, 150, 160))
                        screen.blit(rest_surf, rest_surf.get_rect(center=(self.width // 2, 70)))
                else:
                    # Aktif deneme: ok ve yön yönergesi çiz
                    draw_target_cue(
                        screen=screen,
                        font=font_large,
                        center_x=self.width // 2,
                        center_y=70,
                        target_side=self.logic.target_side,
                        color=target_color,
                    )

                pygame.display.flip()
        finally:
            if self.keyboard_source is not None:
                self.keyboard_source.stop()
            if self.receiver is not None:
                self.receiver.close()
            pygame.quit()
            logger.info("Oyun kapatıldı.")


if __name__ == "__main__":
    import argparse
    from src.control.keyboard_source import KeyboardControlSource

    parser = argparse.ArgumentParser(description="Top Yuvarla BCI Oyunu")
    parser.add_argument(
        "--standalone-keyboard",
        action="store_true",
        help="LSL bağlantısı yerine klavye kaynağını otomatik başlat",
    )
    args = parser.parse_args()

    receiver = None
    kb_source = None
    if args.standalone_keyboard:
        print("Standalone mod: Dahili KeyboardControlSource başlatılıyor...")
        kb_source = KeyboardControlSource(source_id="Ball_Roll_Standalone_KB")
        kb_source.start()
        print("BCI_Control akışına bağlanılıyor (5 saniye)...")
        receiver = ControlReceiver(source_id="Ball_Roll_Standalone_KB", timeout=5.0)
        print("BCI_Control akışına bağlanıldı.")
    else:
        try:
            print("BCI_Control akışı aranıyor (5 saniye)...")
            receiver = ControlReceiver(timeout=5.0)
            print("BCI_Control akışına bağlanıldı.")
        except TimeoutError:
            print("BCI_Control akışı bulunamadı. Lütfen önce klavye kaynağını veya kod çözücüyü başlatın.")
            print("Örn: python -m src.control.keyboard_source")
            exit(1)

    game = BallRollGame(control_receiver=receiver, keyboard_source=kb_source, headless=False)
    game.run()
