"""XDF Kaydından LSL Akışını Yeniden Oynatıcı (Replay).

Gerçek bir XDF kaydındaki X.on EEG akışını, orijinal meta verileri ve zamanlamasıyla
LSL üzerinden yeniden yayınlar.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pylsl
import pyxdf

logger = logging.getLogger(__name__)


def _copy_desc_dict_to_lsl_xml(desc_dict: Dict[str, Any], xml_node: pylsl.xml_element) -> None:
    """pyxdf tarafından üretilen desc sözlüğünü pylsl XML ağacına aktarır."""
    for key, val_list in desc_dict.items():
        if not val_list:
            continue
        val = val_list[0] if isinstance(val_list, list) else val_list

        if isinstance(val, dict):
            # Alt grup (örn. channels, filters, impedances)
            child = xml_node.append_child(key)
            for sub_key, sub_items in val.items():
                if isinstance(sub_items, list):
                    for item in sub_items:
                        item_node = child.append_child(sub_key)
                        if isinstance(item, dict):
                            for prop_k, prop_v in item.items():
                                prop_val = prop_v[0] if isinstance(prop_v, list) else prop_v
                                item_node.append_child_value(prop_k, str(prop_val))
                        else:
                            item_node.append_child_value("val", str(item))
                elif isinstance(sub_items, dict):
                    sub_child = child.append_child(sub_key)
                    for prop_k, prop_v in sub_items.items():
                        prop_val = prop_v[0] if isinstance(prop_v, list) else prop_v
                        sub_child.append_child_value(prop_k, str(prop_val))
                else:
                    child.append_child_value(sub_key, str(sub_items))
        elif isinstance(val, str):
            xml_node.append_child_value(key, val)


class XDFReplay:
    """XDF dosyasından X.on EEG akışını okuyup LSL üzerinde yeniden yayınlayan sınıf."""

    def __init__(
        self,
        xdf_path: Union[str, Path] = "data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf",
        stream_name_prefix: str = "X.on",
        speed_factor: float = 1.0,
        loop: bool = False,
        chunk_size: int = 10,
    ):
        self.xdf_path = Path(xdf_path)
        if not self.xdf_path.exists():
            raise FileNotFoundError(f"XDF dosyası bulunamadı: {self.xdf_path}")

        self.stream_name_prefix = stream_name_prefix
        self.speed_factor = float(speed_factor)
        self.loop = loop
        self.chunk_size = chunk_size

        logger.info(f"XDF yükleniyor: {self.xdf_path}")
        streams, header = pyxdf.load_xdf(str(self.xdf_path))

        target_stream = None
        for s in streams:
            name = s["info"]["name"][0]
            stype = s["info"]["type"][0]
            if name.startswith(self.stream_name_prefix) and stype == "EEG":
                target_stream = s
                break

        if target_stream is None:
            raise ValueError(
                f"XDF dosyasında adı '{self.stream_name_prefix}' ile başlayan EEG akışı bulunamadı."
            )

        self.stream_info_dict = target_stream["info"]
        self.time_series = np.asarray(target_stream["time_series"], dtype=np.float32)
        self.time_stamps = np.asarray(target_stream["time_stamps"], dtype=np.float64)
        self.n_samples, self.n_channels = self.time_series.shape

        self.name = self.stream_info_dict["name"][0]
        self.type = self.stream_info_dict["type"][0]
        self.nominal_srate = float(self.stream_info_dict["nominal_srate"][0])
        self.source_id = (
            self.stream_info_dict["source_id"][0]
            if "source_id" in self.stream_info_dict
            else "REPLAY-SOURCE"
        )

        logger.info(
            f"Seçilen akış: {self.name} | {self.n_channels} kanal | "
            f"{self.nominal_srate} Hz | {self.n_samples} örnek"
        )

        # LSL Outlet oluştur
        self.lsl_info = pylsl.StreamInfo(
            name=self.name,
            type=self.type,
            channel_count=self.n_channels,
            nominal_srate=self.nominal_srate,
            channel_format=pylsl.cf_float32,
            source_id=self.source_id,
        )

        if "desc" in self.stream_info_dict and self.stream_info_dict["desc"]:
            desc_dict = self.stream_info_dict["desc"][0]
            _copy_desc_dict_to_lsl_xml(desc_dict, self.lsl_info.desc())

        self.outlet = pylsl.StreamOutlet(self.lsl_info, chunk_size=self.chunk_size)

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _replay_loop(self) -> None:
        idx = 0
        dt = (self.chunk_size / self.nominal_srate) / self.speed_factor
        next_time = time.perf_counter()

        while self._running:
            end_idx = min(idx + self.chunk_size, self.n_samples)
            chunk = self.time_series[idx:end_idx].tolist()
            if chunk:
                self.outlet.push_chunk(chunk)
            idx = end_idx

            if idx >= self.n_samples:
                if self.loop:
                    idx = 0
                    logger.info("XDF Replay başa sardı (loop).")
                else:
                    logger.info("XDF Replay tamamlandı.")
                    self._running = False
                    break

            next_time += dt
            sleep_dur = next_time - time.perf_counter()
            if sleep_dur > 0:
                time.sleep(sleep_dur)
            else:
                next_time = time.perf_counter()

    def start(self) -> None:
        """Yeniden oynatmayı başlatır."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._replay_loop, daemon=True)
        self._thread.start()
        logger.info(f"XDF Replay başlatıldı: {self.name}")

    def stop(self) -> None:
        """Yeniden oynatmayı durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("XDF Replay durduruldu.")

    def __enter__(self) -> XDFReplay:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="X.on XDF Replay Aracı")
    parser.add_argument(
        "--xdf",
        type=str,
        default="data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf",
        help="Oynatılacak XDF dosyası",
    )
    parser.add_argument("--loop", action="store_true", help="Sürekli başa sar")
    parser.add_argument("--speed", type=float, default=1.0, help="Oynatma hızı çarpanı")
    args = parser.parse_args()

    replay = XDFReplay(xdf_path=args.xdf, speed_factor=args.speed, loop=args.loop)
    replay.start()
    print("Replay çalışıyor. Çıkmak için Enter'a basın...")
    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        replay.stop()
