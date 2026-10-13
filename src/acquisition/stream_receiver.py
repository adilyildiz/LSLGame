"""X.on EEG LSL Alıcı ve Halka Tampon (Ring Buffer) Modülü.

X.on akışını config/device_xon.yaml kuralına göre keşfeder,
son ~5 saniyelik veriyi kesintisiz döngüsel tamponda saklar,
ve akış meta verisinden kanal, impedans ve filtre bilgilerini ayrıştırır.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pylsl
import yaml

logger = logging.getLogger(__name__)


def load_xon_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Cihaz yapılandırma dosyasını yükler."""
    if config_path is None:
        # Default path relative to project root
        project_root = Path(__file__).resolve().parent.parent.parent
        config_path = project_root / "config" / "device_xon.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Konfigürasyon dosyası bulunamadı: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_xon_stream(
    config: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
    name_prefix: Optional[str] = None,
    stream_type: Optional[str] = None,
) -> pylsl.StreamInfo:
    """Ağdaki LSL akışları arasından X.on EEG akışını bulur.

    Eşleme kuralı: type == 'EEG' ve adı 'X.on' ile başlayan ilk akış.
    """
    if config is None:
        try:
            config = load_xon_config()
        except Exception:
            config = {}

    expected_type = stream_type or config.get("stream", {}).get("type", "EEG")
    expected_prefix = name_prefix or config.get("stream", {}).get("name_prefix", "X.on")

    start_time = time.time()
    logger.info(
        f"X.on akışı aranıyor (type='{expected_type}', name_prefix='{expected_prefix}', timeout={timeout}s)..."
    )

    while (time.time() - start_time) < timeout:
        streams = pylsl.resolve_byprop("type", expected_type, timeout=min(1.0, timeout))
        for info in streams:
            if info.name().startswith(expected_prefix):
                logger.info(
                    f"X.on akışı bulundu: {info.name()} ({info.nominal_srate()} Hz, {info.channel_count()} kanal)"
                )
                return info

    raise TimeoutError(
        f"X.on akışı bulunamadı (type='{expected_type}', prefix='{expected_prefix}'). "
        f"Zaman aşımı ({timeout} sn)."
    )


def parse_xon_metadata(info_or_inlet: Union[pylsl.StreamInfo, pylsl.StreamInlet, Any]) -> Dict[str, Any]:
    """Akış bilgisinden kanal, filtre ve impedans meta verilerini okur.

    Döndürülen yapı:
    {
        'name': str,
        'type': str,
        'channel_count': int,
        'nominal_srate': float,
        'source_id': str,
        'channels': [{'label': str, 'type': str, 'unit': str}, ...],
        'filters': [{'label': str, 'unit': str, 'value': float}, ...],
        'impedances': {channel_label: {'value': float, 'unit': str}, ...}
    }
    """
    if isinstance(info_or_inlet, pylsl.StreamInlet):
        info = info_or_inlet.info()
    else:
        info = info_or_inlet

    metadata: Dict[str, Any] = {
        "name": info.name() if hasattr(info, "name") else "",
        "type": info.type() if hasattr(info, "type") else "",
        "channel_count": info.channel_count() if hasattr(info, "channel_count") else 0,
        "nominal_srate": info.nominal_srate() if hasattr(info, "nominal_srate") else 0.0,
        "source_id": info.source_id() if hasattr(info, "source_id") else "",
        "channels": [],
        "filters": [],
        "impedances": {},
    }

    if not hasattr(info, "desc"):
        return metadata

    desc = info.desc()
    if desc.empty():
        return metadata

    # 1. Kanallar
    chans_node = desc.child("channels")
    if not chans_node.empty():
        ch_node = chans_node.child("channel")
        while not ch_node.empty():
            ch_data = {
                "label": ch_node.child_value("label"),
                "type": ch_node.child_value("type"),
                "unit": ch_node.child_value("unit"),
            }
            metadata["channels"].append(ch_data)
            ch_node = ch_node.next_sibling("channel")

    # 2. Filtreler
    filters_node = desc.child("filters")
    if not filters_node.empty():
        f_node = filters_node.child("filter")
        while not f_node.empty():
            val_str = f_node.child_value("value")
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                val = val_str
            metadata["filters"].append({
                "label": f_node.child_value("label"),
                "unit": f_node.child_value("unit"),
                "value": val,
            })
            f_node = f_node.next_sibling("filter")

    # 3. İmpedanslar
    imp_node = desc.child("impedances")
    if not imp_node.empty():
        i_node = imp_node.child("impedance")
        while not i_node.empty():
            lbl = i_node.child_value("label")
            val_str = i_node.child_value("value")
            unit_str = i_node.child_value("unit")
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                val = val_str
            metadata["impedances"][lbl] = {
                "value": val,
                "unit": unit_str,
            }
            i_node = i_node.next_sibling("impedance")

    return metadata


class XonRingBuffer:
    """Sabit boyutlu dairesel (halka) veri tamponu.

    Gerçek zamanlı olarak son N saniyelik EEG verisini ve zaman damgalarını tutar.
    Thread-safe okuma/yazma desteği sunar.
    """

    def __init__(
        self,
        capacity_seconds: float = 5.0,
        srate: float = 250.0,
        n_channels: int = 11,
    ):
        self.capacity_seconds = float(capacity_seconds)
        self.srate = float(srate)
        self.n_channels = int(n_channels)
        self.capacity_samples = int(np.ceil(self.capacity_seconds * self.srate))

        self._data = np.zeros((self.capacity_samples, self.n_channels), dtype=np.float32)
        self._timestamps = np.zeros(self.capacity_samples, dtype=np.float64)

        self._write_pos = 0
        self._total_samples = 0
        self._lock = threading.Lock()

    @property
    def sample_count(self) -> int:
        """Tampondaki geçerli örnek sayısı."""
        with self._lock:
            return min(self._total_samples, self.capacity_samples)

    @property
    def total_samples(self) -> int:
        """Tampona bugüne kadar yazılan toplam örnek sayısı."""
        with self._lock:
            return self._total_samples

    def clear(self) -> None:
        """Tamponu sıfırlar."""
        with self._lock:
            self._write_pos = 0
            self._total_samples = 0
            self._data.fill(0.0)
            self._timestamps.fill(0.0)

    def append(self, chunk: Union[np.ndarray, List[List[float]]], timestamps: Union[np.ndarray, List[float]]) -> None:
        """Tampona yeni örnek blokları ekler."""
        chunk_arr = np.asarray(chunk, dtype=np.float32)
        ts_arr = np.asarray(timestamps, dtype=np.float64)

        if len(chunk_arr) == 0:
            return

        n = len(chunk_arr)
        if chunk_arr.shape[1] != self.n_channels:
            raise ValueError(
                f"Kanal sayısı uyuşmazlığı: beklenen {self.n_channels}, gelen {chunk_arr.shape[1]}"
            )

        with self._lock:
            if n >= self.capacity_samples:
                # Gelen blok tampondan büyükse sadece son capacity_samples kadarını al
                chunk_arr = chunk_arr[-self.capacity_samples :]
                ts_arr = ts_arr[-self.capacity_samples :]
                self._data[:] = chunk_arr
                self._timestamps[:] = ts_arr
                self._write_pos = 0
                self._total_samples += n
                return

            end_pos = self._write_pos + n
            if end_pos <= self.capacity_samples:
                self._data[self._write_pos : end_pos] = chunk_arr
                self._timestamps[self._write_pos : end_pos] = ts_arr
                self._write_pos = end_pos % self.capacity_samples
            else:
                first_part = self.capacity_samples - self._write_pos
                self._data[self._write_pos :] = chunk_arr[:first_part]
                self._timestamps[self._write_pos :] = ts_arr[:first_part]

                second_part = n - first_part
                self._data[:second_part] = chunk_arr[first_part:]
                self._timestamps[:second_part] = ts_arr[first_part:]
                self._write_pos = second_part

            self._total_samples += n

    def get_latest_samples(self, n_samples: int) -> Tuple[np.ndarray, np.ndarray]:
        """Tampondaki en son n_samples adet örneği ve zaman damgalarını kronolojik sırayla döner."""
        with self._lock:
            avail = min(self._total_samples, self.capacity_samples)
            if n_samples > avail:
                raise ValueError(
                    f"İstenen örnek sayısı ({n_samples}) tampondaki mevcut sayıdan ({avail}) fazla."
                )
            if n_samples <= 0:
                return (
                    np.empty((0, self.n_channels), dtype=np.float32),
                    np.empty(0, dtype=np.float64),
                )

            start_idx = (self._write_pos - n_samples) % self.capacity_samples
            end_idx = self._write_pos

            if start_idx < end_idx:
                data = self._data[start_idx:end_idx].copy()
                ts = self._timestamps[start_idx:end_idx].copy()
            else:
                data = np.vstack((self._data[start_idx:], self._data[:end_idx]))
                ts = np.concatenate((self._timestamps[start_idx:], self._timestamps[:end_idx]))

            return data, ts

    def get_latest_window(self, duration_sec: float) -> Tuple[np.ndarray, np.ndarray]:
        """Belirtilen süre (saniye) kadar en son veriyi döner."""
        n_samples = int(round(duration_sec * self.srate))
        return self.get_latest_samples(n_samples)

    def is_ready(self, min_duration_sec: float) -> bool:
        """Tamponda en az min_duration_sec kadar veri birikip birikmediğini kontrol eder."""
        needed_samples = int(round(min_duration_sec * self.srate))
        return self.sample_count >= needed_samples


class XonStreamReceiver:
    """X.on akışını bağlayıp halka tamponda tutan yönetici sınıf."""

    def __init__(
        self,
        stream_info: Optional[pylsl.StreamInfo] = None,
        config: Optional[Dict[str, Any]] = None,
        buffer_duration: float = 5.0,
        timeout: float = 5.0,
    ):
        self.config = config or load_xon_config()
        self.buffer_duration = buffer_duration

        if stream_info is None:
            stream_info = find_xon_stream(self.config, timeout=timeout)

        self.stream_info = stream_info
        self.inlet = pylsl.StreamInlet(self.stream_info, max_buflen=int(buffer_duration + 5))
        self.metadata = parse_xon_metadata(self.inlet)

        srate = self.metadata["nominal_srate"] or 250.0
        n_ch = self.metadata["channel_count"] or 11

        self.ring_buffer = XonRingBuffer(
            capacity_seconds=self.buffer_duration,
            srate=srate,
            n_channels=n_ch,
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def pull_new_data(self, timeout: float = 0.0) -> Tuple[List[List[float]], List[float]]:
        """LSL inlet'inden yeni veri bloğunu çeker ve tampona yazar."""
        samples, timestamps = self.inlet.pull_chunk(timeout=timeout)
        if timestamps:
            self.ring_buffer.append(samples, timestamps)
        return samples, timestamps

    def _pull_loop(self, poll_interval: float = 0.01) -> None:
        while self._running:
            self.pull_new_data(timeout=0.0)
            time.sleep(poll_interval)

    def start(self, poll_interval: float = 0.01) -> None:
        """Arka plan çekme iş parçacığını başlatır."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._pull_loop, args=(poll_interval,), daemon=True
        )
        self._thread.start()
        logger.info("XonStreamReceiver arka plan iş parçacığı başlatıldı.")

    def stop(self) -> None:
        """Arka plan çekme iş parçacığını durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("XonStreamReceiver durduruldu.")

    def close(self) -> None:
        self.stop()
        if hasattr(self, "inlet") and self.inlet:
            self.inlet.close_stream()

    def __enter__(self) -> XonStreamReceiver:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
