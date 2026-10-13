"""Graz-BCI Kalibrasyon Veri Toplama Aracı.

PLAN.md Faz 3 ve Bölüm 20 uyarınca:
- Pygame tabanlı görsel arayüz (tam ekran / pencere).
- Başlamadan önce kontrol ekranı:
  - X.on akış tespiti (veya simülatör).
  - İmpedans kontrol tablosu (config/device_xon.yaml eşikleriyle).
  - Canlı sinyal kalitesi (son 5 sn, 50 Hz / 10 Hz güç oranı, kanal durumu).
  - C3/Cz/C4 kalite kapısı uyarısı.
  - LabRecorder yönlendirmesi ve dosya adı önerisi.
- Graz-BCI zaman çizelgesi (Fixation -> Cue -> Imagery -> Rest).
- Vektörel polygon oklar ve Türkçe yazı tipleri.
- pygame.display.flip() hemen ardından pylsl.local_clock() ile senkronize marker iletimi.
- Oturum sonunda logs/ dizinine detaylı JSON günlüğü.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pygame
import pylsl

from src.acquisition.stream_receiver import (
    XonStreamReceiver,
    find_xon_stream,
    load_xon_config,
    parse_xon_metadata,
)
from src.calibration.paradigm import (
    CalibrationStage,
    CalibrationStateMachine,
    load_calibration_config,
)
from src.game.ball_roll import MarkerPublisher, get_system_font
from src.signal_quality.quality_metrics import compute_signal_quality

logger = logging.getLogger(__name__)


class CalibrationApp:
    """Kalibrasyon Pygame Arayüzü ve Akış Yöneticisi."""

    def __init__(
        self,
        subject: str = "sub-01",
        session: Optional[str] = None,
        profile: str = "mi2",
        runs: Optional[int] = None,
        seed: Optional[int] = None,
        simulator: bool = False,
        windowed: bool = False,
        config_path: Optional[str] = None,
    ):
        self.subject = subject
        now_str = datetime.now().strftime("%Y%m%d")
        self.session = session or f"ses-{now_str}"
        self.profile = profile
        self.simulator = simulator
        self.windowed = windowed
        self.seed = seed

        # Konfigürasyonları yükle
        self.calib_config = load_calibration_config(config_path)
        try:
            self.xon_config = load_xon_config()
        except Exception:
            self.xon_config = {}

        # Paradigma durum makinesini başlat
        self.sm = CalibrationStateMachine(
            config=self.calib_config,
            profile_name=self.profile,
            n_runs=runs,
            seed=self.seed,
        )

        # Görsel ayarlar
        disp_cfg = self.calib_config.get("display", {})
        self.win_w = int(disp_cfg.get("window_width", 1024))
        self.win_h = int(disp_cfg.get("window_height", 768))
        self.fullscreen = bool(disp_cfg.get("fullscreen", False)) and not self.windowed

        self.bg_color = tuple(disp_cfg.get("bg_color", [20, 20, 20]))
        self.cross_color = tuple(disp_cfg.get("cross_color", [240, 240, 240]))
        self.cue_color = tuple(disp_cfg.get("cue_color", [0, 220, 255]))
        self.text_color = tuple(disp_cfg.get("text_color", [240, 240, 240]))
        self.warn_color = tuple(disp_cfg.get("warning_color", [255, 80, 80]))
        self.succ_color = tuple(disp_cfg.get("success_color", [80, 240, 80]))

        self.cross_size = int(disp_cfg.get("cross_size", 40))
        self.cross_thickness = int(disp_cfg.get("cross_thickness", 4))

        # Marker yayıncısı
        rec_cfg = self.calib_config.get("recording", {})
        self.marker_stream_name = rec_cfg.get("stream_name_markers", "BCI_Markers")
        self.marker_source_id = rec_cfg.get("stream_source_id_markers", "Calibration_Markers")
        self.marker_pub: Optional[MarkerPublisher] = None

        # Donanım ve kalite durumu
        self.stream_info: Optional[pylsl.StreamInfo] = None
        self.metadata: Dict[str, Any] = {}
        self.initial_impedances: Dict[str, Any] = {}
        self.receiver: Optional[XonStreamReceiver] = None
        self.quality_metrics: Dict[str, Dict[str, Any]] = {}

        # Pygame değişkenleri
        self.screen: Any = None
        self.clock: Any = None
        self.font_title: Any = None
        self.font_main: Any = None
        self.font_small: Any = None
        self.font_cue: Any = None

        # Uygulama ekran durumu
        self.app_state: str = "CHECK_SCREEN"  # CHECK_SCREEN, PARADIGM, COMPLETED
        self.running: bool = True
        self.start_timestamp_iso: Optional[str] = None
        self.end_timestamp_iso: Optional[str] = None

    def get_suggested_filename(self, run_index: int = 1) -> str:
        """PLAN 3.5'e uygun kayıt dosya adı önerisini döner."""
        template = self.calib_config.get("recording", {}).get(
            "filename_template",
            "data/{subject}/{session}/{subject}_{session}_task-MI_run-{run:02d}.xdf",
        )
        return template.format(
            subject=self.subject,
            session=self.session,
            run=run_index,
        )

    def init_pygame(self) -> None:
        """Pygame ortamını ve yazı tiplerini hazırlar."""
        pygame.init()
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        if flags == 0:
            self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        else:
            self.screen = pygame.display.set_mode((0, 0), flags)
            self.win_w, self.win_h = self.screen.get_size()

        pygame.display.set_caption(f"Graz-BCI Kalibrasyon — {self.subject} ({self.profile})")
        self.clock = pygame.time.Clock()

        # Sistem yazı tipleri
        self.font_title = get_system_font(28, bold=True)
        self.font_main = get_system_font(20, bold=False)
        self.font_small = get_system_font(15, bold=False)
        self.font_cue = get_system_font(44, bold=True)

    def search_eeg_stream(self, timeout: float = 3.0) -> bool:
        """X.on akışını arar ve meta verilerini okur."""
        try:
            self.stream_info = find_xon_stream(
                config=self.xon_config,
                timeout=timeout,
                allow_simulator=self.simulator,
            )
            self.metadata = parse_xon_metadata(self.stream_info)
            self.initial_impedances = copy.deepcopy(self.metadata.get("impedances", {}))

            # Kalite izleme için receiver oluştur
            self.receiver = XonStreamReceiver(
                stream_info=self.stream_info,
                buffer_duration=6.0,
                allow_simulator=self.simulator,
            )
            self.receiver.start(poll_interval=0.02)
            return True
        except Exception as e:
            logger.warning(f"EEG akışı arama hatası: {e}")
            return False

    def check_motor_channels_quality(self) -> Tuple[bool, List[str]]:
        """C3, Cz, C4 kanallarının kalitesini kontrol eder."""
        critical = ["C3", "Cz", "C4"]
        warnings = []
        if not self.quality_metrics:
            return False, ["Henüz sinyal kalitesi hesaplanmadı."]

        all_ok = True
        for ch in critical:
            q = self.quality_metrics.get(ch)
            if not q:
                all_ok = False
                warnings.append(f"{ch}: Veri yok")
            elif q.get("status") != "green":
                all_ok = False
                st = q.get("status", "unknown")
                warnings.append(f"{ch}: {st.upper()} (50/10: {q.get('ratio_50_to_10_db', 0):.1f} dB)")

        return all_ok, warnings

    def update_live_quality(self) -> None:
        """Son 5 saniyelik veriden canlı kalite metriklerini günceller."""
        if self.receiver is None or not self.receiver.is_running:
            return
        samples, _ = self.receiver.get_window(window_sec=5.0)
        if len(samples) < 250:
            return

        ch_labels = [c.get("label", f"Ch{i}") for i, c in enumerate(self.metadata.get("channels", []))]
        fs = float(self.metadata.get("nominal_srate", 250.0))
        self.quality_metrics = compute_signal_quality(
            samples,
            fs=fs,
            channel_labels=ch_labels if ch_labels else None,
        )

    def draw_check_screen(self) -> None:
        """Başlangıç öncesi donanım, impedans ve kalite kontrol ekranı."""
        self.screen.fill(self.bg_color)
        cx = self.win_w // 2

        # 1. Başlık
        title_surf = self.font_title.render("OTURUM ÖNCESİ KONTROL VE KALİBRASYON HAZIRLIĞI", True, self.text_color)
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, 25))

        # Akış durumu
        stream_name = self.stream_info.name() if self.stream_info else "BULUNAMADI"
        st_color = self.succ_color if self.stream_info else self.warn_color
        st_surf = self.font_small.render(
            f"LSL EEG Akışı: {stream_name} | Katılımcı: {self.subject} | Profil: {self.profile} | Run: {self.sm.total_runs}",
            True,
            st_color,
        )
        self.screen.blit(st_surf, (cx - st_surf.get_width() // 2, 65))

        # 2. İmpedans ve Kalite Tablosu
        y_start = 105
        row_h = 24
        col_x = [40, 110, 240, 340, 440, 540, 650]
        headers = ["Kanal", "İmpedans", "RMS (µV)", "10 Hz Güç", "50 Hz Güç", "50/10 dB", "Durum"]

        for idx, h in enumerate(headers):
            h_surf = self.font_small.render(h, True, (180, 180, 180))
            self.screen.blit(h_surf, (col_x[idx], y_start))

        pygame.draw.line(self.screen, (80, 80, 80), (40, y_start + 20), (self.win_w - 40, y_start + 20), 1)

        # Kanal listesi
        channels = ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]
        imp_thresholds = self.xon_config.get("impedance_thresholds_kohm", {
            "target_cz_level": 20000.0,
            "acceptable": 40000.0,
            "poor": 70000.0,
        })

        for row_i, ch in enumerate(channels):
            curr_y = y_start + 28 + row_i * row_h
            # Kanal Adı
            is_crit = ch in ("C3", "Cz", "C4")
            ch_color = (255, 220, 100) if is_crit else self.text_color
            ch_surf = self.font_main.render(ch + (" *" if is_crit else ""), True, ch_color)
            self.screen.blit(ch_surf, (col_x[0], curr_y))

            # İmpedans
            imp_val = None
            if ch in self.initial_impedances:
                val = self.initial_impedances[ch].get("value")
                try:
                    imp_val = float(val) / 1000.0  # kOhm cinsinden
                except (ValueError, TypeError):
                    imp_val = None

            if imp_val is not None:
                if imp_val <= (imp_thresholds["acceptable"] / 1000.0):
                    imp_c = self.succ_color
                elif imp_val <= (imp_thresholds["poor"] / 1000.0):
                    imp_c = (255, 200, 50)
                else:
                    imp_c = self.warn_color
                imp_str = f"{imp_val:.1f} kΩ"
            else:
                imp_c = (140, 140, 140)
                imp_str = "—"
            imp_surf = self.font_small.render(imp_str, True, imp_c)
            self.screen.blit(imp_surf, (col_x[1], curr_y))

            # Canlı Kalite Metrikleri
            q = self.quality_metrics.get(ch, {})
            if q:
                rms_val = q.get("rms", 0.0)
                p10_val = q.get("power_10hz", 0.0)
                p50_val = q.get("power_50hz", 0.0)
                r_db = q.get("ratio_50_to_10_db", 0.0)
                status = q.get("status", "unknown")

                stat_c = self.succ_color if status == "green" else ((255, 200, 50) if status == "yellow" else self.warn_color)
                stat_text = "İYİ" if status == "green" else ("ORTA" if status == "yellow" else "KÖTÜ")

                self.screen.blit(self.font_small.render(f"{rms_val:.1f}", True, self.text_color), (col_x[2], curr_y))
                self.screen.blit(self.font_small.render(f"{p10_val:.2f}", True, self.text_color), (col_x[3], curr_y))
                self.screen.blit(self.font_small.render(f"{p50_val:.2f}", True, self.text_color), (col_x[4], curr_y))
                self.screen.blit(self.font_small.render(f"{r_db:+.1f}", True, self.text_color), (col_x[5], curr_y))
                self.screen.blit(self.font_small.render(stat_text, True, stat_c), (col_x[6], curr_y))
            else:
                self.screen.blit(self.font_small.render("Hesaplanıyor...", True, (130, 130, 130)), (col_x[2], curr_y))

        # 3. Kritik Motor Kanalları Uyarısı
        c3_cz_c4_ok, warn_list = self.check_motor_channels_quality()
        warn_y = y_start + 28 + len(channels) * row_h + 15
        if not c3_cz_c4_ok and warn_list:
            w_msg = "UYARI: C3, Cz, C4 motor kanallarında gürültü/kablo teması var: " + ", ".join(warn_list[:2])
            w_surf = self.font_small.render(w_msg, True, self.warn_color)
            self.screen.blit(w_surf, (cx - w_surf.get_width() // 2, warn_y))
        else:
            ok_surf = self.font_small.render("C3, Cz, C4 motor kanalları ve impedans kapısı uygun.", True, self.succ_color)
            self.screen.blit(ok_surf, (cx - ok_surf.get_width() // 2, warn_y))

        # 4. LabRecorder Hatırlatması ve Önerilen Dosya Adı
        rec_box_y = warn_y + 35
        suggested_path = self.get_suggested_filename(1)
        rec_title = self.font_main.render("KAYIT HATIRLATMASI (PLAN Bölüm 3.5 & 20):", True, (255, 220, 120))
        self.screen.blit(rec_title, (cx - rec_title.get_width() // 2, rec_box_y))

        rec_inst1 = self.font_small.render(
            "LabRecorder'ı açın, 'X.on' ve 'BCI_Markers' akışlarını seçip kaydı başlatın.",
            True,
            self.text_color,
        )
        self.screen.blit(rec_inst1, (cx - rec_inst1.get_width() // 2, rec_box_y + 25))

        rec_fn = self.font_small.render(f"Önerilen Dosya Adı: {suggested_path}", True, (120, 220, 255))
        self.screen.blit(rec_fn, (cx - rec_fn.get_width() // 2, rec_box_y + 48))

        # 5. Başlama Talimatı
        prompt_y = self.win_h - 60
        prompt_surf = self.font_main.render(
            "Hazır olduğunuzda başlamak için [SPACE] tuşuna basın. Çıkmak için [ESC].",
            True,
            self.succ_color,
        )
        self.screen.blit(prompt_surf, (cx - prompt_surf.get_width() // 2, prompt_y))

    def draw_fixation_cross(self) -> None:
        """Ekranın tam ortasına '+' sabitleme haçı çizer."""
        cx = self.win_w // 2
        cy = self.win_h // 2
        half_s = self.cross_size // 2

        # Yatay çizgi
        pygame.draw.line(
            self.screen,
            self.cross_color,
            (cx - half_s, cy),
            (cx + half_s, cy),
            self.cross_thickness,
        )
        # Dikey çizgi
        pygame.draw.line(
            self.screen,
            self.cross_color,
            (cx, cy - half_s),
            (cx, cy + half_s),
            self.cross_thickness,
        )

    def draw_cue(self, class_name: str) -> None:
        """Sınıfa uygun ipucu (vektörel polygon ok, daire veya metin) çizer."""
        cx = self.win_w // 2
        cy = self.win_h // 2

        if class_name == "left":
            # Sol ok ←
            pts = [(cx - 95, cy), (cx - 35, cy - 35), (cx - 35, cy + 35)]
            pygame.draw.polygon(self.screen, self.cue_color, pts)
        elif class_name == "right":
            # Sağ ok →
            pts = [(cx + 95, cy), (cx + 35, cy - 35), (cx + 35, cy + 35)]
            pygame.draw.polygon(self.screen, self.cue_color, pts)
        elif class_name in ("feet", "foot", "down"):
            # Ayak (aşağı ok) ↓
            pts = [(cx, cy + 95), (cx - 35, cy + 35), (cx + 35, cy + 35)]
            pygame.draw.polygon(self.screen, self.cue_color, pts)
        elif class_name in ("both_hands", "both", "up"):
            # İki el (yukarı ok) ↑
            pts = [(cx, cy - 95), (cx - 35, cy - 35), (cx + 35, cy - 35)]
            pygame.draw.polygon(self.screen, self.cue_color, pts)
        elif class_name == "arithmetic":
            # Aritmetik metni: "100 − 7"
            text_surf = self.font_cue.render("100 − 7", True, self.cue_color)
            self.screen.blit(text_surf, (cx - text_surf.get_width() // 2, cy - 100))
        elif class_name == "rest":
            # Dinlenme metni veya daire
            text_surf = self.font_cue.render("DİNLEN", True, self.cue_color)
            self.screen.blit(text_surf, (cx - text_surf.get_width() // 2, cy - 100))
            pygame.draw.circle(self.screen, self.cue_color, (cx, cy), 35, width=3)
        else:
            text_surf = self.font_cue.render(class_name.upper(), True, self.cue_color)
            self.screen.blit(text_surf, (cx - text_surf.get_width() // 2, cy - 90))

    def draw_hud(self) -> None:
        """Üst köşede dikkat dağıtmayacak şekilde hafif run ve deneme bilgisi."""
        r_txt = f"Run: {self.sm.current_run + 1}/{self.sm.total_runs}"
        t_txt = f"Deneme: {self.sm.current_trial_in_run + 1}/{self.sm.trials_per_run}"
        hud_str = f"{r_txt}  |  {t_txt}"
        hud_surf = self.font_small.render(hud_str, True, (80, 80, 80))
        self.screen.blit(hud_surf, (20, 15))

    def draw_pause_screen(self) -> None:
        """Run arası mola ekranı."""
        self.screen.fill(self.bg_color)
        cx = self.win_w // 2
        cy = self.win_h // 2

        completed_run = self.sm.current_run  # index incremented at end of run
        msg_title = f"MOLA — Run {completed_run}/{self.sm.total_runs} Tamamlandı"
        title_surf = self.font_title.render(msg_title, True, self.succ_color)
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, cy - 70))

        sub_msg = "Gözlerinizi dinlendirin, gevşeyin."
        sub_surf = self.font_main.render(sub_msg, True, self.text_color)
        self.screen.blit(sub_surf, (cx - sub_surf.get_width() // 2, cy - 15))

        next_fn = self.get_suggested_filename(self.sm.current_run + 1)
        fn_surf = self.font_small.render(f"Sonraki Dosya Önerisi: {next_fn}", True, (130, 200, 240))
        self.screen.blit(fn_surf, (cx - fn_surf.get_width() // 2, cy + 30))

        prompt = "Hazır olduğunuzda devam etmek için [SPACE] tuşuna basın. Çıkmak için [ESC]."
        pr_surf = self.font_main.render(prompt, True, (255, 220, 100))
        self.screen.blit(pr_surf, (cx - pr_surf.get_width() // 2, cy + 85))

    def draw_completed_screen(self) -> None:
        """Oturum bitti ekranı."""
        self.screen.fill(self.bg_color)
        cx = self.win_w // 2
        cy = self.win_h // 2

        status_text = "OTURUM YARIDA KESİLDİ" if self.sm.aborted else "KALİBRASYON OTURUMU TAMAMLANDI!"
        st_color = self.warn_color if self.sm.aborted else self.succ_color
        t_surf = self.font_title.render(status_text, True, st_color)
        self.screen.blit(t_surf, (cx - t_surf.get_width() // 2, cy - 60))

        info_text = f"Toplam Tamamlanan Deneme: {len(self.sm.trials_history)} / {self.sm.total_trials}"
        i_surf = self.font_main.render(info_text, True, self.text_color)
        self.screen.blit(i_surf, (cx - i_surf.get_width() // 2, cy - 10))

        log_msg = "Oturum günlüğü logs/ dizinine kaydedildi."
        l_surf = self.font_small.render(log_msg, True, (150, 220, 255))
        self.screen.blit(l_surf, (cx - l_surf.get_width() // 2, cy + 35))

        ex_msg = "Çıkmak için [ESC] veya pencereyi kapatın."
        ex_surf = self.font_small.render(ex_msg, True, (180, 180, 180))
        self.screen.blit(ex_surf, (cx - ex_surf.get_width() // 2, cy + 80))

    def render_current_stage(self, stage: CalibrationStage) -> None:
        """Geçerli aşamayı ekrana çizer."""
        self.screen.fill(self.bg_color)

        if stage == CalibrationStage.FIXATION:
            self.draw_fixation_cross()
            self.draw_hud()
        elif stage == CalibrationStage.CUE:
            self.draw_fixation_cross()
            cls = self.sm.current_class
            if cls:
                self.draw_cue(cls)
            self.draw_hud()
        elif stage == CalibrationStage.IMAGERY:
            # Ok kaybolur, yalnızca + kalır (PLAN 3.1)
            self.draw_fixation_cross()
            self.draw_hud()
        elif stage == CalibrationStage.REST:
            # Boş ekran (PLAN 3.1)
            pass
        elif stage == CalibrationStage.INTER_RUN_PAUSE:
            self.draw_pause_screen()
        elif stage == CalibrationStage.SESSION_END:
            self.draw_completed_screen()

    def save_session_log(self) -> Path:
        """Oturum bilgilerini logs/ altına JSON olarak kaydeder."""
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"calibration_{self.subject}_{self.session}_{now_str}.json"
        log_path = logs_dir / filename

        summary = self.sm.get_session_summary()
        summary["subject"] = self.subject
        summary["session"] = self.session
        summary["start_time_iso"] = self.start_timestamp_iso
        summary["end_time_iso"] = self.end_timestamp_iso
        summary["initial_impedances"] = self.initial_impedances
        summary["is_simulator"] = self.simulator
        summary["suggested_xdf_file"] = self.get_suggested_filename(1)

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Oturum günlüğü kaydedildi: {log_path}")
        print(f"\n[Oturum Günlüğü] Kaydedildi: {log_path}")
        return log_path

    def run(self) -> None:
        """Ana döngü."""
        self.init_pygame()

        # Konsola LabRecorder hatırlatması yaz
        print("=" * 70)
        print("GRAZ-BCI KALİBRASYON VERİ TOPLAMA ARACI BAŞLATILDI")
        print(f"Katılımcı: {self.subject} | Oturum: {self.session} | Profil: {self.profile}")
        print(f"[LabRecorder Önerisi] Kayıt dosyası: {self.get_suggested_filename(1)}")
        print("=" * 70)

        # EEG Akışını bul
        print("\nEEG akışı aranıyor...")
        eeg_found = self.search_eeg_stream(timeout=4.0)
        if eeg_found:
            print(f"EEG akışı bağlandı: {self.stream_info.name()}")
        else:
            print("UYARI: EEG akışı bulunamadı. Simülatör veya cihazı başlatınız.")

        # MarkerPublisher başlat
        self.marker_pub = MarkerPublisher(
            stream_name=self.marker_stream_name,
            source_id=self.marker_source_id,
        )

        last_quality_check = 0.0

        try:
            while self.running:
                now_wall = time.time()

                # Olayları işle
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        if self.sm.is_session_active:
                            self._handle_abort()
                        self.running = False

                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            if self.app_state == "CHECK_SCREEN":
                                self.running = False
                            elif self.app_state == "PARADIGM":
                                self._handle_abort()
                                self.app_state = "COMPLETED"
                            elif self.app_state == "COMPLETED":
                                self.running = False

                        elif event.key == pygame.K_SPACE:
                            if self.app_state == "CHECK_SCREEN":
                                self._start_paradigm()
                            elif self.app_state == "PARADIGM" and self.sm.stage == CalibrationStage.INTER_RUN_PAUSE:
                                self._resume_next_run()

                # Ekran duruma göre çizim ve güncelleme
                if self.app_state == "CHECK_SCREEN":
                    if now_wall - last_quality_check >= 0.5:
                        self.update_live_quality()
                        last_quality_check = now_wall

                    self.draw_check_screen()
                    pygame.display.flip()
                    self.clock.tick(30)

                elif self.app_state == "PARADIGM":
                    now_lsl = pylsl.local_clock()

                    # Aşama geçişi var mı kontrol et
                    if self.sm.is_run_active and self.sm.should_transition(now_lsl):
                        # Bir sonraki aşamayı belirle ve ekranı çiz
                        next_stage, _ = self.sm.peek_next_stage()
                        self.render_current_stage(next_stage)

                        # PLAN 3.1 & Görev 04 Kuralı:
                        # Marker zaman damgası, ekranın gerçekten güncellendiği ana
                        # (pygame.display.flip() çağrısından hemen sonra) pylsl.local_clock() ile alınmalı.
                        pygame.display.flip()
                        flip_timestamp = pylsl.local_clock()

                        # Durum makinesini flip zamanıyla ilerlet ve marker'ları ilet
                        _, markers = self.sm.commit_transition(flip_timestamp)
                        for m in markers:
                            self.marker_pub.push(m, timestamp=flip_timestamp)

                        if self.sm.is_completed:
                            self.app_state = "COMPLETED"
                            self.end_timestamp_iso = datetime.now().isoformat()
                            self.save_session_log()

                    else:
                        # Aşama içi normal ekran güncellemesi
                        self.render_current_stage(self.sm.stage)
                        pygame.display.flip()

                    self.clock.tick(60)

                elif self.app_state == "COMPLETED":
                    self.draw_completed_screen()
                    pygame.display.flip()
                    self.clock.tick(30)

        finally:
            if self.receiver is not None and self.receiver.is_running:
                self.receiver.stop()
            pygame.quit()

    def _start_paradigm(self) -> None:
        """Kontrol ekranından paradigmaya geçer."""
        # Alıcı arka plan yükünü sonlandır
        if self.receiver is not None and self.receiver.is_running:
            self.receiver.stop()

        self.app_state = "PARADIGM"
        self.start_timestamp_iso = datetime.now().isoformat()

        # İlk ekranı hazırla ve flip et
        self.render_current_stage(CalibrationStage.FIXATION)
        pygame.display.flip()
        flip_ts = pylsl.local_clock()

        # Session ve Run 1'i başlat
        m1 = self.sm.start_session(flip_ts)
        m2 = self.sm.start_run(flip_ts)
        for m in m1 + m2:
            self.marker_pub.push(m, timestamp=flip_ts)

    def _resume_next_run(self) -> None:
        """Moladan sonraki run'ı başlatır."""
        self.render_current_stage(CalibrationStage.FIXATION)
        pygame.display.flip()
        flip_ts = pylsl.local_clock()

        markers = self.sm.resume_after_pause(flip_ts)
        for m in markers:
            self.marker_pub.push(m, timestamp=flip_ts)

    def _handle_abort(self) -> None:
        """ESC ile oturumun güvenle sonlandırılması."""
        flip_ts = pylsl.local_clock()
        markers = self.sm.abort(flip_ts)
        if self.marker_pub:
            for m in markers:
                self.marker_pub.push(m, timestamp=flip_ts)
        self.end_timestamp_iso = datetime.now().isoformat()
        self.save_session_log()


def build_arg_parser() -> argparse.ArgumentParser:
    """Komut satırı argüman ayrıştırıcısını kurar."""
    parser = argparse.ArgumentParser(
        description="Graz-BCI Motor İmgeleme Kalibrasyon Veri Toplama Aracı",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--subject", type=str, default="sub-01", help="Katılımcı kodu (örn. sub-01)")
    parser.add_argument("--session", type=str, default=None, help="Oturum kodu (örn. ses-20261015)")
    parser.add_argument(
        "--profile",
        type=str,
        default="mi2",
        choices=["mi2", "mi3", "mi5"],
        help="Oturum profili (mi2: sol/sağ/dinlen, mi3: +ayak, mi5: +iki el/aritmetik)",
    )
    parser.add_argument("--simulator", action="store_true", help="Sentetik simülatör akışlarına izin ver")
    parser.add_argument("--runs", type=int, default=None, help="Çalıştırılacak run sayısı (profil varsayılanını ezer)")
    parser.add_argument("--seed", type=int, default=None, help="Rastgelelik tohumu (seed)")
    parser.add_argument("--windowed", action="store_true", help="Tam ekran yerine pencere modunda çalıştır")
    parser.add_argument("--config", type=str, default=None, help="Özel calibration.yaml konfigürasyon yolu")
    return parser


def main() -> None:
    """Giriş noktası."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_arg_parser()
    args = parser.parse_args()

    app = CalibrationApp(
        subject=args.subject,
        session=args.session,
        profile=args.profile,
        runs=args.runs,
        seed=args.seed,
        simulator=args.simulator,
        windowed=args.windowed,
        config_path=args.config,
    )
    app.run()


if __name__ == "__main__":
    main()
