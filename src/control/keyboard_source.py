"""Klavye Kontrol Kaynağı (Keyboard Control Source).

Ok tuşları ile 'BCI_Control' LSL akışını yayınlar.
Oyun motorunu BCI kod çözücüden bağımsız olarak test etmek için kullanılır.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Union

import pylsl

from src.control.contract import ControlMode, ControlSender, DEFAULT_SRATE

logger = logging.getLogger(__name__)


class KeyboardControlSource:
    """Ok tuşları durumunu BCI_Control akışına dönüştüren yayınlayıcı."""

    def __init__(
        self,
        mode: Union[ControlMode, str] = ControlMode.DISCRETE,
        srate: float = DEFAULT_SRATE,
        source_id: str = "Keyboard_Control_Source",
    ):
        self.mode = ControlMode(mode)
        self.srate = float(srate)
        self.sender = ControlSender(mode=self.mode, srate=self.srate, source_id=source_id)

        # Aktif yön durumu
        self._key_left = False
        self._key_right = False
        self._key_up = False
        self._key_down = False

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_keys(
        self,
        left: bool = False,
        right: bool = False,
        up: bool = False,
        down: bool = False,
    ) -> None:
        """Klavye tuşlarının basılma durumunu günceller."""
        with self._lock:
            self._key_left = bool(left)
            self._key_right = bool(right)
            self._key_up = bool(up)
            self._key_down = bool(down)

    def step(self) -> None:
        """Aktif duruma göre tek bir BCI_Control örneği yayınlar."""
        with self._lock:
            l, r, u, d = self._key_left, self._key_right, self._key_up, self._key_down

        if self.mode == ControlMode.DISCRETE:
            if l:
                self.sender.send_discrete(p_left=1.0, p_right=0.0, p_up=0.0, p_down=0.0, p_rest=0.0)
            elif r:
                self.sender.send_discrete(p_left=0.0, p_right=1.0, p_up=0.0, p_down=0.0, p_rest=0.0)
            elif u:
                self.sender.send_discrete(p_left=0.0, p_right=0.0, p_up=1.0, p_down=0.0, p_rest=0.0)
            elif d:
                self.sender.send_discrete(p_left=0.0, p_right=0.0, p_up=0.0, p_down=1.0, p_rest=0.0)
            else:
                self.sender.send_discrete(p_left=0.0, p_right=0.0, p_up=0.0, p_down=0.0, p_rest=1.0)
        else:
            # Sürekli mod
            vx = 0.0
            vy = 0.0
            if l:
                vx -= 1.0
            if r:
                vx += 1.0
            if u:
                vy += 1.0
            if d:
                vy -= 1.0
            self.sender.send_continuous(vx=vx, vy=vy)

    def _loop(self) -> None:
        dt = 1.0 / self.srate
        next_time = time.perf_counter()
        while self._running:
            self.step()
            next_time += dt
            sleep_dur = next_time - time.perf_counter()
            if sleep_dur > 0:
                time.sleep(sleep_dur)
            else:
                next_time = time.perf_counter()

    def start(self) -> None:
        """Arka plan yayın döngüsünü başlatır."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"KeyboardControlSource başlatıldı ({self.mode.value} mod, {self.srate} Hz).")

    def stop(self) -> None:
        """Arka plan yayın döngüsünü durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("KeyboardControlSource durduruldu.")

    def __enter__(self) -> KeyboardControlSource:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


def run_interactive_keyboard_source(mode: str = "discrete") -> None:
    """Pygame kullanarak klavye girişlerini yakalayan etkileşimli kontrol penceresi."""
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((400, 240))
    pygame.display.set_caption("BCI_Control - Klavye Kaynağı")
    font = pygame.font.Font(None, 24)
    clock = pygame.time.Clock()

    source = KeyboardControlSource(mode=mode, srate=20.0)
    source.start()

    print(f"=== Klavye Kontrol Kaynağı Aktif ({mode} mod) ===")
    print("Ok tuşlarına basarak BCI_Control akışını yönlendirin.")
    print("Kapatmak için pencereyi kapatın veya ESC'ye basın.")

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            keys = pygame.key.get_pressed()
            k_left = keys[pygame.K_LEFT] or keys[pygame.K_a]
            k_right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
            k_up = keys[pygame.K_UP] or keys[pygame.K_w]
            k_down = keys[pygame.K_DOWN] or keys[pygame.K_s]

            source.set_keys(left=k_left, right=k_right, up=k_up, down=k_down)

            screen.fill((30, 30, 35))
            txt_title = font.render(f"BCI_Control Klavye Kaynagi ({mode})", True, (240, 240, 240))
            screen.blit(txt_title, (20, 20))

            status_str = "DURUM: "
            if k_left:
                status_str += "SOL (Left)"
            elif k_right:
                status_str += "SAG (Right)"
            elif k_up:
                status_str += "YUKARI (Up)"
            elif k_down:
                status_str += "ASAGI (Down)"
            else:
                status_str += "DINLENME (Rest)"

            txt_st = font.render(status_str, True, (80, 220, 100))
            screen.blit(txt_st, (20, 70))

            info1 = font.render("Ok tuslari veya WASD ile kontrol edin", True, (180, 180, 180))
            info2 = font.render("ESC: Cikis", True, (140, 140, 140))
            screen.blit(info1, (20, 130))
            screen.blit(info2, (20, 160))

            pygame.display.flip()
            clock.tick(30)
    finally:
        source.stop()
        pygame.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BCI_Control Klavye Kaynağı")
    parser.add_argument(
        "--mode",
        choices=["discrete", "continuous"],
        default="discrete",
        help="Kontrol modu (discrete / continuous)",
    )
    args = parser.parse_args()
    run_interactive_keyboard_source(mode=args.mode)
