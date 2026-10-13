"""Graz-BCI Kalibrasyon Paradigması ve Durum Makinesi Modülü.

PLAN.md Faz 3 (3.1-3.5) ve Bölüm 20 uyarınca:
- Headless test edilebilir saf mantık katmanı.
- Dengeli ve kısıtlı (en fazla 3 aynı sınıf ardışık) deneme sırası üretimi.
- Durum makinesi: fixation (2s) -> cue (1s) -> imagery (4s) -> rest (1.5-3s).
- Run ve oturum akış yönetimi (run_start, run_end, pause_start, pause_end, session_start, session_end).
- Katı ASCII marker adlandırması.
- Sahte saat (virtual clock) veya gerçek saatle ilerleyebilme.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import yaml

logger = logging.getLogger(__name__)


class CalibrationStage(str, Enum):
    """Kalibrasyon akışının aşamaları."""
    IDLE = "idle"
    RUN_READY = "run_ready"
    FIXATION = "fixation"
    CUE = "cue"
    IMAGERY = "imagery"
    REST = "rest"
    INTER_RUN_PAUSE = "inter_run_pause"
    SESSION_END = "session_end"


@dataclass
class CalibrationTiming:
    """Aşama süreleri yapılandırması (saniye)."""
    fixation_sec: float = 2.0
    cue_sec: float = 1.0
    imagery_sec: float = 4.0
    rest_min_sec: float = 1.5
    rest_max_sec: float = 3.0
    inter_run_pause_sec: float = 60.0


@dataclass
class TrialInfo:
    """Tek bir denemeye ait bilgiler."""
    run_index: int
    trial_in_run: int
    global_trial_index: int
    class_name: str
    rest_duration: float
    timestamps: Dict[str, float] = field(default_factory=dict)


def load_calibration_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Kalibrasyon yapılandırma dosyasını yükler."""
    if config_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        config_path = project_root / "config" / "calibration.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Kalibrasyon konfigürasyon dosyası bulunamadı: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_balanced_sequence(
    classes: Sequence[str],
    count: int = 20,
    seed: Optional[int] = None,
    max_streak: int = 3,
) -> List[str]:
    """Her run için dengeli ve kısıtlanmış deneme sırası üretir.

    Kurallar:
    - Sınıflar dengeli olmalı: (count / sınıf sayısı; tam bölünmüyorsa fark en fazla 1).
    - Sıra karıştırılmış olmalı.
    - Aynı sınıf en fazla max_streak (varsayılan 3) kez üst üste gelebilir.
    - seed ile tekrarlanabilir.
    """
    if not classes:
        raise ValueError("Sınıf listesi boş olamaz.")
    if count <= 0:
        raise ValueError(f"Deneme sayısı pozitif olmalıdır: {count}")
    if max_streak < 1:
        raise ValueError(f"max_streak en az 1 olmalıdır: {max_streak}")

    n_classes = len(classes)
    if n_classes == 1 and count > max_streak:
        raise ValueError("Tek sınıf ile max_streak kısıtı sağlanamaz.")

    rng = random.Random(seed)

    # 1. Dengeli sınıf dağılımı (fark en fazla 1)
    base_count = count // n_classes
    remainder = count % n_classes

    # Kalanları dağıtırken deterministik ama tohumlu sıralama
    indices = list(range(n_classes))
    rng.shuffle(indices)

    counts = {cls: base_count for cls in classes}
    for i in range(remainder):
        counts[classes[indices[i]]] += 1

    # Havuz oluştur
    pool: List[str] = []
    for cls in classes:
        pool.extend([cls] * counts[cls])

    # 2. Şartı sağlayan karıştırma (rejection sampling)
    max_attempts = 2000
    for _ in range(max_attempts):
        candidate = list(pool)
        rng.shuffle(candidate)

        streak = 1
        valid = True
        for i in range(1, len(candidate)):
            if candidate[i] == candidate[i - 1]:
                streak += 1
                if streak > max_streak:
                    valid = False
                    break
            else:
                streak = 1

        if valid:
            return candidate

    # Çok nadir durumda (fallback: greedy backtrack)
    logger.warning("Rejection sampling limiti aşıldı, greedy dizilim deneniyor.")
    remaining = counts.copy()
    result: List[str] = []
    for _ in range(count):
        # Son max_streak eleman aynıysa o sınıf hariç tutulur
        blocked: Optional[str] = None
        if len(result) >= max_streak and len(set(result[-max_streak:])) == 1:
            blocked = result[-1]

        candidates = [c for c, cnt in remaining.items() if cnt > 0 and c != blocked]
        if not candidates:
            # Geri dönüş kuralı: en çok kalanı seç
            candidates = [c for c, cnt in remaining.items() if cnt > 0]
        chosen = rng.choice(candidates)
        result.append(chosen)
        remaining[chosen] -= 1

    return result


class CalibrationStateMachine:
    """Kalibrasyon protokolü için zaman ve aşama durum makinesi."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        profile_name: str = "mi2",
        n_runs: Optional[int] = None,
        seed: Optional[int] = None,
    ):
        if config is None:
            try:
                config = load_calibration_config()
            except Exception:
                config = {}

        self.config = copy.deepcopy(config)
        self.profile_name = profile_name
        self.seed = seed
        self.rng = random.Random(seed)

        # Zamanlama
        timing_cfg = self.config.get("timing", {})
        self.timing = CalibrationTiming(
            fixation_sec=float(timing_cfg.get("fixation_sec", 2.0)),
            cue_sec=float(timing_cfg.get("cue_sec", 1.0)),
            imagery_sec=float(timing_cfg.get("imagery_sec", 4.0)),
            rest_min_sec=float(timing_cfg.get("rest_min_sec", 1.5)),
            rest_max_sec=float(timing_cfg.get("rest_max_sec", 3.0)),
            inter_run_pause_sec=float(timing_cfg.get("inter_run_pause_sec", 60.0)),
        )

        # Profil ve sınıflar
        profiles = self.config.get("profiles", {})
        if profile_name in profiles:
            p_data = profiles[profile_name]
            self.classes = list(p_data.get("classes", ["left", "right", "rest"]))
            default_runs = int(p_data.get("default_runs", 4))
        else:
            self.classes = ["left", "right", "rest"]
            default_runs = 4

        self.n_runs = int(n_runs) if n_runs is not None else default_runs
        run_cfg = self.config.get("run", {})
        self.trials_per_run = int(run_cfg.get("trials_per_run", 20))
        self.max_streak = int(run_cfg.get("max_consecutive_same_class", 3))

        # Tüm run'lar için sıraları önceden üret
        self.run_sequences: List[List[str]] = []
        for r in range(self.n_runs):
            run_seed = (self.seed + r * 1000) if self.seed is not None else None
            seq = generate_balanced_sequence(
                classes=self.classes,
                count=self.trials_per_run,
                seed=run_seed,
                max_streak=self.max_streak,
            )
            self.run_sequences.append(seq)

        # Durum değişkenleri
        self.stage = CalibrationStage.IDLE
        self.current_run = 0
        self.current_trial_in_run = 0
        self.global_trial_index = 0

        self.stage_start_time = 0.0
        self.stage_duration = 0.0
        self.current_rest_duration = 0.0

        self.is_session_active = False
        self.is_run_active = False
        self.is_paused = False
        self.is_completed = False
        self.aborted = False

        self.session_start_time: Optional[float] = None
        self.session_end_time: Optional[float] = None

        self.current_trial_timestamps: Dict[str, float] = {}
        self.trials_history: List[Dict[str, Any]] = []

    @property
    def total_runs(self) -> int:
        return self.n_runs

    @property
    def total_trials(self) -> int:
        return self.n_runs * self.trials_per_run

    @property
    def current_class(self) -> Optional[str]:
        if 0 <= self.current_run < len(self.run_sequences):
            seq = self.run_sequences[self.current_run]
            if 0 <= self.current_trial_in_run < len(seq):
                return seq[self.current_trial_in_run]
        return None

    def _sample_rest_duration(self) -> float:
        return self.rng.uniform(self.timing.rest_min_sec, self.timing.rest_max_sec)

    def start_session(self, timestamp: float) -> List[str]:
        """Oturumu başlatır."""
        self.session_start_time = timestamp
        self.is_session_active = True
        self.stage = CalibrationStage.RUN_READY
        self.current_run = 0
        self.current_trial_in_run = 0
        self.global_trial_index = 0
        marker = "session_start"
        self._validate_marker(marker)
        return [marker]

    def start_run(self, timestamp: float) -> List[str]:
        """Geçerli run'ı başlatır ve ilk denemenin fixation aşamasına geçer."""
        if not self.is_session_active:
            raise RuntimeError("Oturum başlatılmadan run başlatılamaz.")

        markers: List[str] = []
        if self.stage == CalibrationStage.INTER_RUN_PAUSE or self.is_paused:
            markers.append("pause_end")
            self.is_paused = False

        markers.append("run_start")
        self.is_run_active = True
        self.current_trial_in_run = 0

        # İlk denemeye gir
        self.current_rest_duration = self._sample_rest_duration()
        self.current_trial_timestamps = {
            "trial_start": timestamp,
            "fixation_start": timestamp,
        }
        self.stage = CalibrationStage.FIXATION
        self.stage_start_time = timestamp
        self.stage_duration = self.timing.fixation_sec

        markers.extend(["trial_start", "fixation_start"])
        for m in markers:
            self._validate_marker(m)
        return markers

    def resume_after_pause(self, timestamp: float) -> List[str]:
        """Mola sonrasında sonraki run'ı başlatır."""
        return self.start_run(timestamp)

    def should_transition(self, current_time: float) -> bool:
        """Geçerli aşama süresi dolup dolmadığını kontrol eder."""
        if not self.is_run_active:
            return False
        return (current_time - self.stage_start_time) >= self.stage_duration

    def peek_next_stage(self) -> Tuple[CalibrationStage, List[str]]:
        """Bir sonraki aşama ve tetiklenecek marker'ları durumu değiştirmeden inceler."""
        if not self.is_run_active:
            return self.stage, []

        cls = self.current_class or "rest"

        if self.stage == CalibrationStage.FIXATION:
            return CalibrationStage.CUE, [f"cue_{cls}"]
        elif self.stage == CalibrationStage.CUE:
            return CalibrationStage.IMAGERY, ["imagery_start"]
        elif self.stage == CalibrationStage.IMAGERY:
            return CalibrationStage.REST, ["imagery_end", "rest_start"]
        elif self.stage == CalibrationStage.REST:
            markers = ["trial_end"]
            is_last_trial = (self.current_trial_in_run + 1) >= self.trials_per_run
            if not is_last_trial:
                return CalibrationStage.FIXATION, ["trial_end", "trial_start", "fixation_start"]
            else:
                is_last_run = (self.current_run + 1) >= self.n_runs
                if not is_last_run:
                    return CalibrationStage.INTER_RUN_PAUSE, ["trial_end", "run_end", "pause_start"]
                else:
                    return CalibrationStage.SESSION_END, ["trial_end", "run_end", "session_end"]

        return self.stage, []

    def commit_transition(self, timestamp: float) -> Tuple[CalibrationStage, List[str]]:
        """Aşama geçişini onaylar, zaman damgalarını kaydeder ve marker'ları döner."""
        if not self.is_run_active:
            return self.stage, []

        cls = self.current_class or "rest"
        markers: List[str] = []

        if self.stage == CalibrationStage.FIXATION:
            self.stage = CalibrationStage.CUE
            self.stage_start_time = timestamp
            self.stage_duration = self.timing.cue_sec
            marker = f"cue_{cls}"
            self.current_trial_timestamps["cue"] = timestamp
            markers.append(marker)

        elif self.stage == CalibrationStage.CUE:
            self.stage = CalibrationStage.IMAGERY
            self.stage_start_time = timestamp
            self.stage_duration = self.timing.imagery_sec
            marker = "imagery_start"
            self.current_trial_timestamps["imagery_start"] = timestamp
            markers.append(marker)

        elif self.stage == CalibrationStage.IMAGERY:
            self.stage = CalibrationStage.REST
            self.stage_start_time = timestamp
            self.stage_duration = self.current_rest_duration
            self.current_trial_timestamps["imagery_end"] = timestamp
            self.current_trial_timestamps["rest_start"] = timestamp
            markers.extend(["imagery_end", "rest_start"])

        elif self.stage == CalibrationStage.REST:
            self.current_trial_timestamps["trial_end"] = timestamp
            markers.append("trial_end")

            # Tamamlanan denemeyi kaydet
            trial_record = {
                "run": self.current_run,
                "trial_in_run": self.current_trial_in_run,
                "global_trial": self.global_trial_index,
                "class": cls,
                "rest_duration": self.current_rest_duration,
                "timestamps": dict(self.current_trial_timestamps),
            }
            self.trials_history.append(trial_record)

            is_last_trial = (self.current_trial_in_run + 1) >= self.trials_per_run
            if not is_last_trial:
                # Sonraki denemeye geç
                self.current_trial_in_run += 1
                self.global_trial_index += 1
                self.current_rest_duration = self._sample_rest_duration()
                self.current_trial_timestamps = {
                    "trial_start": timestamp,
                    "fixation_start": timestamp,
                }
                self.stage = CalibrationStage.FIXATION
                self.stage_start_time = timestamp
                self.stage_duration = self.timing.fixation_sec
                markers.extend(["trial_start", "fixation_start"])
            else:
                # Run bitti
                markers.append("run_end")
                self.is_run_active = False
                is_last_run = (self.current_run + 1) >= self.n_runs

                if not is_last_run:
                    # Mola aşaması
                    self.stage = CalibrationStage.INTER_RUN_PAUSE
                    self.is_paused = True
                    self.stage_start_time = timestamp
                    self.stage_duration = self.timing.inter_run_pause_sec
                    markers.append("pause_start")
                    self.current_run += 1
                else:
                    # Oturum bitti
                    self.stage = CalibrationStage.SESSION_END
                    self.is_session_active = False
                    self.is_completed = True
                    self.session_end_time = timestamp
                    markers.append("session_end")

        for m in markers:
            self._validate_marker(m)

        return self.stage, markers

    def update(self, current_time: float) -> List[str]:
        """Süresi dolan aşamaları adım adım ilerletir ve üretilen tüm marker'ları döner.

        Headless simülasyon ve testler için idealdir.
        """
        all_markers: List[str] = []
        while self.is_run_active and self.should_transition(current_time):
            trans_ts = (
                self.stage_start_time + self.stage_duration
                if self.stage_duration > 0
                else current_time
            )
            _, markers = self.commit_transition(trans_ts)
            all_markers.extend(markers)
        return all_markers

    def abort(self, timestamp: float) -> List[str]:
        """Oturumu güvenli bir biçimde yarıda keser."""
        markers: List[str] = []
        if self.is_session_active or self.is_run_active or self.is_paused:
            self.aborted = True
            self.is_session_active = False
            self.is_run_active = False
            self.is_paused = False
            self.session_end_time = timestamp
            self.stage = CalibrationStage.SESSION_END
            marker = "session_end"
            self._validate_marker(marker)
            markers.append(marker)
        return markers

    def stage_time_remaining(self, current_time: float) -> float:
        """Geçerli aşamada kalan süreyi (sn) döner."""
        if self.stage_duration <= 0.0:
            return 0.0
        elapsed = current_time - self.stage_start_time
        return max(0.0, self.stage_duration - elapsed)

    def stage_progress(self, current_time: float) -> float:
        """Geçerli aşamanın ilerleme oranını döner (0.0 - 1.0)."""
        if self.stage_duration <= 0.0:
            return 1.0
        elapsed = current_time - self.stage_start_time
        return min(1.0, max(0.0, elapsed / self.stage_duration))

    def _validate_marker(self, marker_name: str) -> None:
        if not marker_name.isascii():
            raise ValueError(f"Marker ismi ASCII dışı karakter içeremez: '{marker_name}'")

    def get_session_summary(self) -> Dict[str, Any]:
        """Oturum logu için özet sözlük oluşturur."""
        return {
            "profile": self.profile_name,
            "seed": self.seed,
            "classes": list(self.classes),
            "total_runs": self.n_runs,
            "runs_completed": self.current_run + (1 if self.is_completed else 0),
            "trials_completed": len(self.trials_history),
            "total_planned_trials": self.total_trials,
            "aborted": self.aborted,
            "is_completed": self.is_completed,
            "session_start_time": self.session_start_time,
            "session_end_time": self.session_end_time,
            "trials": list(self.trials_history),
            "timing_config": {
                "fixation_sec": self.timing.fixation_sec,
                "cue_sec": self.timing.cue_sec,
                "imagery_sec": self.timing.imagery_sec,
                "rest_min_sec": self.timing.rest_min_sec,
                "rest_max_sec": self.timing.rest_max_sec,
                "inter_run_pause_sec": self.timing.inter_run_pause_sec,
            },
        }
