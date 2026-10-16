"""Çevrimiçi Kod Çözücü (Faz 5): X.on EEG -> model -> 'BCI_Control' LSL akışı.

Eğitim hattıyla (src.processing.epochs / src.models.offline_analysis) aynı ön işlemeyi kullanır:
- Sürekli akışa nedensel 50/100 Hz çentik + 8-30 Hz bant geçiren (StatefulFilter).
- Son `window_sec` (varsayılan 3 sn) saniyelik pencere, kaydırma adımı `step_sec`.
- Model: models/<denek>/*.joblib (+ _meta.json), predict_proba ile sınıf olasılıkları.

Çıktı: ayrık 5 kanallı BCI_Control (p_left, p_right, p_up, p_down, p_rest).
Güven eşiğin altındaysa p_rest = 1 yayınlanır (oyun yanlışlıkla hareket etmesin).

Kullanım:
    python -m src.online.decoder --subject sub-01
    python -m src.online.decoder --model models/sub-01/XXXX.joblib --allow-simulator
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence

import joblib
import numpy as np

from src.control.contract import DISCRETE_CHANNELS, ControlMode, ControlSender
from src.processing.filters import StatefulFilter

logger = logging.getLogger(__name__)

# Model sınıf etiketi -> BCI_Control kanal adı
_LABEL_TO_CHANNEL = {
    "left": "p_left",
    "right": "p_right",
    "up": "p_up",
    "down": "p_down",
    "rest": "p_rest",
}


class OnlineDecoder:
    """Akıştan gelen blokları filtreleyip kayan pencerede sınıflandıran çekirdek (LSL'siz test edilebilir)."""

    def __init__(
        self,
        model: Any,
        srate: float = 250.0,
        n_channels: int = 7,
        window_sec: float = 3.0,
        f_low: float = 8.0,
        f_high: float = 30.0,
        notch_freqs: Sequence[float] = (50.0, 100.0),
        smoothing: float = 0.5,
        conf_threshold: float = 0.6,
    ):
        self.model = model
        self.srate = float(srate)
        self.n_channels = int(n_channels)
        self.window_samples = int(round(window_sec * self.srate))
        self.smoothing = float(smoothing)
        self.conf_threshold = float(conf_threshold)

        self.filter = StatefulFilter(
            srate=self.srate,
            n_channels=self.n_channels,
            f_low=f_low,
            f_high=f_high,
            notch_freqs=notch_freqs,
        )
        # Filtrelenmiş verinin kayan tamponu (n, n_channels)
        self._buf = np.zeros((0, self.n_channels), dtype=np.float64)
        # Filtre geçici rejimi (transient) için atlanacak örnek sayısı
        self._warmup_samples = int(round(1.0 * self.srate))
        self._seen = 0

        classes = getattr(model, "classes_", None)
        if classes is None:
            raise ValueError("Modelde classes_ yok; predict_proba sırası belirlenemiyor.")
        self.classes: List[str] = [str(c) for c in classes]
        self._smoothed: Optional[np.ndarray] = None

    @property
    def ready(self) -> bool:
        return len(self._buf) >= self.window_samples and self._seen >= self.window_samples + self._warmup_samples

    def push(self, chunk: np.ndarray) -> None:
        """Ham (uV) EEG bloğunu (n, n_channels) ekler."""
        chunk = np.asarray(chunk, dtype=np.float64)
        if chunk.size == 0:
            return
        filt = self.filter.filter_block(chunk)
        self._seen += len(filt)
        self._buf = np.vstack([self._buf, filt])[-self.window_samples :]

    def predict_probs(self) -> Optional[Dict[str, float]]:
        """Son pencere için BCI_Control kanal olasılıklarını döner (hazır değilse None)."""
        if not self.ready:
            return None

        window = self._buf[-self.window_samples :][None, :, :]  # (1, n_times, n_channels)
        p = np.asarray(self.model.predict_proba(window)[0], dtype=np.float64)

        if self._smoothed is None:
            self._smoothed = p
        else:
            a = self.smoothing
            self._smoothed = a * self._smoothed + (1.0 - a) * p
        p = self._smoothed

        out = {ch: 0.0 for ch in DISCRETE_CHANNELS}
        for cls, prob in zip(self.classes, p):
            ch = _LABEL_TO_CHANNEL.get(cls)
            if ch is not None:
                out[ch] = float(prob)

        # Güven düşükse dinlenme
        move_probs = [out[c] for c in DISCRETE_CHANNELS if c != "p_rest"]
        if max(move_probs) < self.conf_threshold:
            out = {ch: 0.0 for ch in DISCRETE_CHANNELS}
            out["p_rest"] = 1.0
        elif out["p_rest"] == 0.0:
            out["p_rest"] = float(max(0.0, 1.0 - max(move_probs)))
        return out


def find_latest_model(subject: str, models_dir: Path = Path("models")) -> Path:
    """models/<denek>/ altındaki en yeni .joblib dosyasını döner."""
    files = sorted((models_dir / subject).glob("*.joblib"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"{models_dir / subject} altında .joblib model bulunamadı.")
    return files[-1]


def run_online(
    model_path: Path,
    allow_simulator: bool = False,
    step_sec: float = 0.1,
    window_sec: Optional[float] = None,
    smoothing: float = 0.5,
    conf_threshold: float = 0.6,
    timeout: float = 10.0,
) -> None:
    from src.acquisition.stream_receiver import XonStreamReceiver, load_xon_config

    model = joblib.load(model_path)
    meta_path = model_path.with_name(model_path.stem + "_meta.json")
    meta: Dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    win = window_sec or float(meta.get("window_sec", 3.0))
    bp = meta.get("bandpass_hz", [8.0, 30.0])
    notch = meta.get("notch_hz", [50.0, 100.0])

    cfg = load_xon_config()
    eeg_idx = cfg.get("channels", {}).get("indices", {}).get("eeg", [0, 1, 2, 3, 4, 5, 6])

    print(f"Model: {model_path.name}  (sınıflar: {getattr(model, 'classes_', '?')})")
    print("X.on akışı aranıyor...")
    receiver = XonStreamReceiver(config=cfg, timeout=timeout, allow_simulator=allow_simulator)
    srate = float(receiver.metadata["nominal_srate"] or 250.0)
    print(f"Bağlandı: {receiver.stream_info.name()} ({srate} Hz)")

    decoder = OnlineDecoder(
        model,
        srate=srate,
        n_channels=len(eeg_idx),
        window_sec=win,
        f_low=bp[0],
        f_high=bp[1],
        notch_freqs=notch,
        smoothing=smoothing,
        conf_threshold=conf_threshold,
    )
    sender = ControlSender(mode=ControlMode.DISCRETE, srate=1.0 / step_sec, source_id="BCI_Online_Decoder")
    print(f"BCI_Control yayını başladı (pencere {win} sn, adım {step_sec} sn). Durdurmak için Ctrl+C.")

    last = 0.0
    try:
        while True:
            samples, _ = receiver.pull_new_data(timeout=0.0)
            if samples:
                arr = np.asarray(samples, dtype=np.float64)[:, eeg_idx]
                decoder.push(arr)

            now = time.perf_counter()
            if now - last >= step_sec:
                last = now
                probs = decoder.predict_probs()
                if probs is None:
                    sender.send_discrete(0.0, 0.0, 0.0, 0.0, 1.0)  # ısınma: dinlenme
                else:
                    sender.send_discrete(
                        probs["p_left"], probs["p_right"], probs["p_up"], probs["p_down"], probs["p_rest"]
                    )
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.close()
        print("Kod çözücü durduruldu.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Çevrimiçi BCI kod çözücü (X.on -> BCI_Control)")
    parser.add_argument("--subject", default="sub-01")
    parser.add_argument("--model", help="Model .joblib yolu (verilmezse denek için en yenisi)")
    parser.add_argument("--allow-simulator", action="store_true")
    parser.add_argument("--step", type=float, default=0.1, help="Tahmin adımı (sn)")
    parser.add_argument("--window", type=float, default=None, help="Pencere uzunluğu (sn)")
    parser.add_argument("--smoothing", type=float, default=0.5, help="EMA katsayısı (0=yok)")
    parser.add_argument("--conf", type=float, default=0.6, help="Hareket için en düşük olasılık")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    model_path = Path(args.model) if args.model else find_latest_model(args.subject)
    run_online(
        model_path,
        allow_simulator=args.allow_simulator,
        step_sec=args.step,
        window_sec=args.window,
        smoothing=args.smoothing,
        conf_threshold=args.conf,
    )


if __name__ == "__main__":
    main()
