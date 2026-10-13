"""BCI_Control Arayüz Sözleşmesi ve İletişim Altyapısı.

PLAN.md Bölüm 4.3 ve agy_tasks/01_faz0_faz2.md uyarınca:
BCI_Control LSL akışı, oyun/uygulama ile zihinsel veya simüle edilmiş kontrol kaynakları
arasındaki tak-çıkar köprüdür.

İki mod desteklenir:
1. Ayrık Mod (Discrete):
   5 kanal: ['p_left', 'p_right', 'p_up', 'p_down', 'p_rest']
   Değerler: [0.0, 1.0] aralığında sınıf olasılıkları.
2. Sürekli Mod (Continuous):
   2 kanal: ['vx', 'vy']
   Değerler: [-1.0, 1.0] aralığında normalize hızlar.
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pylsl

logger = logging.getLogger(__name__)

STREAM_NAME = "BCI_Control"
STREAM_TYPE = "Control"
DEFAULT_SRATE = 20.0  # Hz

DISCRETE_CHANNELS = ["p_left", "p_right", "p_up", "p_down", "p_rest"]
CONTINUOUS_CHANNELS = ["vx", "vy"]


class ControlMode(str, enum.Enum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


class Direction(str, enum.Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    REST = "rest"


def create_control_stream_info(
    mode: Union[ControlMode, str] = ControlMode.DISCRETE,
    srate: float = DEFAULT_SRATE,
    source_id: str = "BCI_Control_Source",
) -> pylsl.StreamInfo:
    """Belirtilen mod için BCI_Control StreamInfo nesnesi oluşturur."""
    mode_val = ControlMode(mode)
    if mode_val == ControlMode.DISCRETE:
        ch_labels = DISCRETE_CHANNELS
    else:
        ch_labels = CONTINUOUS_CHANNELS

    info = pylsl.StreamInfo(
        name=STREAM_NAME,
        type=STREAM_TYPE,
        channel_count=len(ch_labels),
        nominal_srate=srate,
        channel_format=pylsl.cf_float32,
        source_id=source_id,
    )

    desc = info.desc()
    desc.append_child_value("mode", mode_val.value)
    chans = desc.append_child("channels")
    for lbl in ch_labels:
        ch = chans.append_child("channel")
        ch.append_child_value("label", lbl)
        ch.append_child_value("type", "Control")
        ch.append_child_value("unit", "probability" if mode_val == ControlMode.DISCRETE else "norm_vel")

    return info


def identify_control_mode(info_or_channel_count: Union[pylsl.StreamInfo, int]) -> ControlMode:
    """Kanal sayısı veya XML meta verisinden kontrol modunu belirler."""
    if isinstance(info_or_channel_count, pylsl.StreamInfo):
        ch_count = info_or_channel_count.channel_count()
        mode_val = info_or_channel_count.desc().child_value("mode")
        if mode_val in (ControlMode.DISCRETE.value, ControlMode.CONTINUOUS.value):
            return ControlMode(mode_val)
    else:
        ch_count = int(info_or_channel_count)

    if ch_count == len(DISCRETE_CHANNELS):
        return ControlMode.DISCRETE
    elif ch_count == len(CONTINUOUS_CHANNELS):
        return ControlMode.CONTINUOUS
    else:
        raise ValueError(f"Bilinmeyen BCI_Control kanal sayısı: {ch_count}")


class ControlSender:
    """BCI_Control akışını yayınlayan sınıf."""

    def __init__(
        self,
        mode: Union[ControlMode, str] = ControlMode.DISCRETE,
        srate: float = DEFAULT_SRATE,
        source_id: str = "BCI_Control_Sender",
    ):
        self.mode = ControlMode(mode)
        self.srate = float(srate)
        self.stream_info = create_control_stream_info(self.mode, srate=self.srate, source_id=source_id)
        self.outlet = pylsl.StreamOutlet(self.stream_info)

    def send_discrete(
        self,
        p_left: float,
        p_right: float,
        p_up: float = 0.0,
        p_down: float = 0.0,
        p_rest: float = 0.0,
    ) -> None:
        """Ayrık sınıf olasılıklarını yayınlar."""
        if self.mode != ControlMode.DISCRETE:
            raise RuntimeError("ControlSender sürekli (continuous) modda yapılandırılmış.")
        sample = [float(p_left), float(p_right), float(p_up), float(p_down), float(p_rest)]
        self.outlet.push_sample(sample)

    def send_continuous(self, vx: float, vy: float) -> None:
        """Sürekli hız vektörünü (vx, vy) yayınlar."""
        if self.mode != ControlMode.CONTINUOUS:
            raise RuntimeError("ControlSender ayrık (discrete) modda yapılandırılmış.")
        vx_c = float(np.clip(vx, -1.0, 1.0))
        vy_c = float(np.clip(vy, -1.0, 1.0))
        self.outlet.push_sample([vx_c, vy_c])


class ControlReceiver:
    """BCI_Control akışını okuyan ve oyuna/uygulamaya sunan sınıf."""

    def __init__(
        self,
        stream_info: Optional[pylsl.StreamInfo] = None,
        timeout: float = 5.0,
        threshold: float = 0.5,
        stale_after: float = 0.3,
        source_id: Optional[str] = None,
    ):
        self.threshold = float(threshold)
        self.stale_after = float(stale_after)
        self._last_sample: Optional[List[float]] = None
        self._last_sample_time: float = 0.0

        if stream_info is None:
            if source_id is not None:
                streams = pylsl.resolve_byprop("source_id", source_id, timeout=timeout)
            else:
                streams = pylsl.resolve_byprop("name", STREAM_NAME, timeout=timeout)
                if not streams:
                    # Type ile arama alternatifi
                    streams = pylsl.resolve_byprop("type", STREAM_TYPE, timeout=timeout)
            if not streams:
                target_desc = f"source_id='{source_id}'" if source_id else f"name='{STREAM_NAME}'"
                raise TimeoutError(f"'{STREAM_NAME}' LSL akışı bulunamadı ({target_desc}, zaman aşımı {timeout} sn).")
            stream_info = streams[0]

        self.stream_info = stream_info
        self.inlet = pylsl.StreamInlet(self.stream_info, max_buflen=10)
        try:
            self.inlet.open_stream(timeout=timeout)
        except (pylsl.util.TimeoutError, pylsl.util.LostError, TimeoutError) as e:
            raise TimeoutError(f"BCI_Control akışına bağlanılamadı (zaman aşımı {timeout} sn): {e}") from e

        self.mode = identify_control_mode(self.stream_info)
        name_str = self.stream_info.name() if hasattr(self.stream_info, "name") else ""
        src_str = self.stream_info.source_id() if hasattr(self.stream_info, "source_id") else ""
        self.is_simulator = bool(
            "-SIM-" in name_str
            or "-SIM-" in src_str
            or "SIM" in src_str.upper()
            or "KEYBOARD" in src_str.upper()
        )
        logger.info(f"BCI_Control akışına bağlandı. Mod: {self.mode.value}, Simülatör: {self.is_simulator}")

    def pull_latest(self, timeout: float = 0.0) -> Tuple[Optional[List[float]], Optional[float]]:
        """LSL'den son örneği ve zaman damgasını çeker (varsa)."""
        chunks, timestamps = self.inlet.pull_chunk(timeout=timeout)
        if chunks:
            ts = timestamps[-1] if (timestamps and len(timestamps) > 0) else None
            return chunks[-1], ts
        return None, None

    def get_command(
        self,
        timeout: float = 0.0,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """En son kontrol sinyalini yorumlanmış komut formatında döner."""
        th = threshold if threshold is not None else self.threshold
        sample, sample_ts = self.pull_latest(timeout=timeout)

        if sample is None and timeout > 0.0:
            start_t = time.perf_counter()
            while (time.perf_counter() - start_t) < timeout:
                sample, sample_ts = self.pull_latest(timeout=min(0.05, timeout))
                if sample is not None:
                    break
                time.sleep(0.01)

        now = pylsl.local_clock()
        if sample is not None:
            ts = sample_ts if (sample_ts is not None and sample_ts > 0.0) else now
            self._last_sample = sample
            self._last_sample_time = ts
            if (now - ts) <= self.stale_after:
                active_sample = sample
                is_stale = False
            else:
                active_sample = None
                is_stale = True
        else:
            if self._last_sample is not None and (now - self._last_sample_time) <= self.stale_after:
                active_sample = self._last_sample
                is_stale = False
            else:
                active_sample = None
                is_stale = True

        result: Dict[str, Any] = {
            "mode": self.mode.value,
            "has_signal": (not is_stale) and (active_sample is not None),
            "raw": active_sample,
            "direction": Direction.REST.value,
            "confidence": 0.0,
            "vx": 0.0,
            "vy": 0.0,
            "is_simulator": self.is_simulator,
        }

        if active_sample is None or is_stale:
            return result

        if self.mode == ControlMode.DISCRETE:
            # sample: [p_left, p_right, p_up, p_down, p_rest]
            probs = np.array(active_sample, dtype=np.float32)
            max_idx = int(np.argmax(probs))
            max_p = float(probs[max_idx])
            dirs = [
                Direction.LEFT.value,
                Direction.RIGHT.value,
                Direction.UP.value,
                Direction.DOWN.value,
                Direction.REST.value,
            ]
            chosen_dir = dirs[max_idx]

            # Eşik kontrolü
            if chosen_dir != Direction.REST.value and max_p >= th:
                result["direction"] = chosen_dir
                result["confidence"] = max_p
                # Ayrık modu sanal vx/vy'ye de çevir
                if chosen_dir == Direction.LEFT.value:
                    result["vx"] = -max_p
                elif chosen_dir == Direction.RIGHT.value:
                    result["vx"] = max_p
                elif chosen_dir == Direction.UP.value:
                    result["vy"] = max_p
                elif chosen_dir == Direction.DOWN.value:
                    result["vy"] = -max_p
            else:
                result["direction"] = Direction.REST.value
                result["confidence"] = float(probs[4]) if len(probs) > 4 else (1.0 - max_p)

        else:
            # Sürekli mod: sample = [vx, vy]
            vx = float(active_sample[0])
            vy = float(active_sample[1]) if len(active_sample) > 1 else 0.0
            result["vx"] = vx
            result["vy"] = vy
            mag = float(np.hypot(vx, vy))
            result["confidence"] = mag

            # Hız vektörünü yön kararına çevir
            if mag >= th:
                if abs(vx) > abs(vy):
                    result["direction"] = Direction.RIGHT.value if vx > 0 else Direction.LEFT.value
                else:
                    result["direction"] = Direction.UP.value if vy > 0 else Direction.DOWN.value
            else:
                result["direction"] = Direction.REST.value

        return result

    def close(self) -> None:
        if hasattr(self, "inlet") and self.inlet:
            self.inlet.close_stream()
