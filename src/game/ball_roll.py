"""Seviye 1 'Top Yuvarla' (Roll the Ball) BCI Oyunu.

PLAN.md Bölüm 6.2 ve agy_tasks/01_faz0_faz2.md uyarınca:
- Minimal prototip (pygame-ce tabanlı).
- Yalnızca 'BCI_Control' LSL akışını dinler, kaynağı bilmez.
- Hedef sol veya sağda belirir; top hedefe ulaşınca skor artar.
- Oyun olaylarını 'BCI_Markers' LSL akışına ASCII olarak yazar (cue_left, cue_right, target_hit vb.).
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
        marker_pub: Optional[MarkerPublisher] = None,
        random_seed: Optional[int] = None,
    ):
        self.arena_width = arena_width
        self.arena_height = arena_height
        self.ball_speed = ball_speed
        self.ball_radius = ball_radius
        self.target_radius = target_radius
        self.marker_pub = marker_pub

        self.rng = random.Random(random_seed)

        self.center_x = arena_width / 2.0
        self.center_y = arena_height / 2.0

        self.ball_x = self.center_x
        self.ball_y = self.center_y

        self.score = 0
        self.trial_count = 0
        self.target_side: str = "left"  # 'left' veya 'right'
        self.target_x = 0.0
        self.target_y = self.center_y

        self.last_hit_time: float = 0.0

        if self.marker_pub:
            self.marker_pub.push("game_start")

        self.spawn_new_target()

    def spawn_new_target(self, side: Optional[str] = None) -> str:
        """Yeni bir hedef konumu belirler ve LSL marker gönderir."""
        if side is None:
            # Alternatif veya rastgele
            side = "right" if self.target_side == "left" else "left"

        self.target_side = side
        margin = 100.0
        if self.target_side == "left":
            self.target_x = margin
        else:
            self.target_x = self.arena_width - margin

        self.target_y = self.center_y
        self.ball_x = self.center_x
        self.ball_y = self.center_y

        self.trial_count += 1

        if self.marker_pub:
            self.marker_pub.push("trial_start")
            cue_marker = f"cue_{self.target_side}"
            self.marker_pub.push(cue_marker)

        return self.target_side

    def update(self, dt: float, command: Dict[str, Any]) -> bool:
        """Bir kare (frame) ilerletir.

        Returns
        -------
        bool: Hedef vuruldu mu?
        """
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

        # Çarpışma kontrolü
        dist_to_target = abs(self.ball_x - self.target_x)
        hit_threshold = self.ball_radius + self.target_radius

        if dist_to_target <= hit_threshold:
            self.score += 1
            self.last_hit_time = time.time()
            if self.marker_pub:
                self.marker_pub.push("target_hit")
                self.marker_pub.push("trial_end")

            # Sonraki hedefi oluştur
            self.spawn_new_target()
            return True

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
        pygame.display.set_caption("LSLGame - Top Yuvarla (Level 1)")
        clock = pygame.time.Clock()
        font = pygame.font.Font(None, 26)
        font_large = pygame.font.Font(None, 36)

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

                # Hedef çizimi
                target_color = (60, 180, 240) if self.logic.target_side == "left" else (240, 160, 60)
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

                # HUD Bilgileri
                score_surf = font_large.render(f"Skor: {self.logic.score}", True, (240, 240, 240))
                screen.blit(score_surf, (30, 25))

                target_info = f"Hedef: {'SOL (Left)' if self.logic.target_side == 'left' else 'SAG (Right)'}"
                t_surf = font.render(target_info, True, target_color)
                screen.blit(t_surf, (30, 65))

                has_signal = cmd.get("has_signal", False) if self.receiver else False
                dir_val = cmd.get("direction", "rest").upper()
                conf_val = cmd.get("confidence", 0.0)

                if not has_signal:
                    control_info = "BCI Komut: SINYAL YOK"
                    c_surf = font.render(control_info, True, (255, 90, 90))
                else:
                    control_info = f"BCI Komut: {dir_val} ({conf_val * 100:.0f}%)"
                    c_surf = font.render(control_info, True, (160, 220, 160) if dir_val != "REST" else (140, 140, 140))
                screen.blit(c_surf, (self.width - 280, 25))

                # Simülasyon göstergesi
                is_sim = cmd.get("is_simulator", False) or getattr(self.receiver, "is_simulator", False)
                if is_sim:
                    sim_surf = font.render("[ SIMULASYON ]", True, (255, 190, 60))
                    screen.blit(sim_surf, (self.width - 280, 55))

                # Hedef Yön Oku
                arrow_text = "◄ SOLA GIT" if self.logic.target_side == "left" else "SAGA GIT ►"
                arrow_surf = font_large.render(arrow_text, True, target_color)
                arrow_rect = arrow_surf.get_rect(center=(self.width // 2, 70))
                screen.blit(arrow_surf, arrow_rect)

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
