"""Sentetik X.on EEG LSL Yayınlayıcı.

X.on başlığı takılı olmadan geliştirme ve test yapabilmek için:
- X.on ile birebir aynı akış adı (X.on-SIM-0000), tip (EEG), kanal sayısı (11),
  örnekleme hızı (250 Hz) ve meta verileri (kanal etiketleri, filtreler, impedanslar) yayınlar.
- Pembe gürültü (1/f) + 10 Hz μ (mu) ritmi üretir.
- Motor imgeleme (MI) ERD modülasyonu:
  - 'left' (sol): C4 elektrodunun 8–30 Hz gücünü ~%40 düşürür (kontralateral ERD).
  - 'right' (sağ): C3 elektrodunun 8–30 Hz gücünü ~%40 düşürür.
  - 'down' (aşağı): Cz elektrodunun 8–30 Hz gücünü ~%40 düşürür.
  - 'up' (yukarı): C3 ve C4 elektrotlarının gücünü birlikte düşürür.
  - 'rest' (dinlenme): Normal temel seviye.
- İvmeölçer kanallarında (accX, accY, accZ) ~1 g yerçekimi bileşenleri ve gürültü.
- F3 ve F4 kanallarına opsiyonel göz kırpma (blink) artefaktı enjeksiyonu.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Set

import numpy as np
import pylsl

logger = logging.getLogger(__name__)

CHANNEL_LABELS = [
    ("F3", "EEG", "μV"),
    ("F4", "EEG", "μV"),
    ("C3", "EEG", "μV"),
    ("Cz", "EEG", "μV"),
    ("C4", "EEG", "μV"),
    ("P3", "EEG", "μV"),
    ("P4", "EEG", "μV"),
    ("BIP", "EEG", "μV"),
    ("accX", "AUX", "mg₀"),
    ("accY", "AUX", "mg₀"),
    ("accZ", "AUX", "mg₀"),
]

FILTERS = [
    ("HighPass", "Hz", "0.500000"),
    ("LowPass", "Hz", "65.000000"),
]

IMPEDANCES = [
    ("P4", "kilo-Ohm", "83200.000000"),
    ("P3", "kilo-Ohm", "32600.000000"),
    ("C4", "kilo-Ohm", "67600.000000"),
    ("Cz", "kilo-Ohm", "16300.000000"),
    ("C3", "kilo-Ohm", "66900.000000"),
    ("F4", "kilo-Ohm", "53300.000000"),
    ("F3", "kilo-Ohm", "62800.000000"),
    ("Ref", "kilo-Ohm", "25000.000000"),
    ("Gnd", "kilo-Ohm", "10500.000000"),
]


class PinkNoiseGenerator:
    """Kellet filtresi kullanan gerçek zamanlı pembe gürültü (1/f) üreteci."""

    def __init__(self, n_channels: int = 11, rng: Optional[np.random.Generator] = None):
        self.n_channels = n_channels
        self.b = np.zeros((n_channels, 7), dtype=np.float64)
        self.rng = rng if rng is not None else np.random.default_rng()

    def generate(self, n_samples: int) -> np.ndarray:
        out = np.zeros((n_samples, self.n_channels), dtype=np.float64)
        for i in range(n_samples):
            white = self.rng.standard_normal(self.n_channels)
            self.b[:, 0] = 0.99886 * self.b[:, 0] + white * 0.0555179
            self.b[:, 1] = 0.99332 * self.b[:, 1] + white * 0.0750759
            self.b[:, 2] = 0.96900 * self.b[:, 2] + white * 0.1538520
            self.b[:, 3] = 0.86650 * self.b[:, 3] + white * 0.3104856
            self.b[:, 4] = 0.55000 * self.b[:, 4] + white * 0.5329522
            self.b[:, 5] = -0.7616 * self.b[:, 5] - white * 0.0168980
            pink = (
                self.b[:, 0]
                + self.b[:, 1]
                + self.b[:, 2]
                + self.b[:, 3]
                + self.b[:, 4]
                + self.b[:, 5]
                + self.b[:, 6]
                + white * 0.5362
            )
            self.b[:, 6] = white * 0.115926
            out[i, :] = pink
        return out


def create_xon_stream_info(
    name: str = "X.on-SIM-0000",
    srate: float = 250.0,
    source_id: str = "SIM-0000 250",
) -> pylsl.StreamInfo:
    """X.on başlığının birebir LSL StreamInfo nesnesini ve XML meta verisini oluşturur."""
    info = pylsl.StreamInfo(
        name=name,
        type="EEG",
        channel_count=len(CHANNEL_LABELS),
        nominal_srate=srate,
        channel_format=pylsl.cf_float32,
        source_id=source_id,
    )

    desc = info.desc()

    # Kanallar
    chans_node = desc.append_child("channels")
    for label, ch_type, unit in CHANNEL_LABELS:
        ch = chans_node.append_child("channel")
        ch.append_child_value("label", label)
        ch.append_child_value("type", ch_type)
        ch.append_child_value("unit", unit)

    # Filtreler
    filters_node = desc.append_child("filters")
    for label, unit, val in FILTERS:
        f = filters_node.append_child("filter")
        f.append_child_value("label", label)
        f.append_child_value("unit", unit)
        f.append_child_value("value", val)

    # İmpedanslar
    imp_node = desc.append_child("impedances")
    for label, unit, val in IMPEDANCES:
        imp = imp_node.append_child("impedance")
        imp.append_child_value("label", label)
        imp.append_child_value("unit", unit)
        imp.append_child_value("value", val)

    return info


class SyntheticEEGSource:
    """Sentetik X.on EEG LSL Yayınlayıcı sınıfı."""

    def __init__(
        self,
        name: str = "X.on-SIM-0000",
        srate: float = 250.0,
        chunk_size: int = 10,
        erd_power_drop: float = 0.40,
        random_seed: Optional[int] = None,
        source_id: Optional[str] = None,
    ):
        self.name = name
        self.srate = float(srate)
        self.chunk_size = chunk_size
        self.erd_power_drop = float(erd_power_drop)
        self.erd_attenuation = float(np.sqrt(max(0.0, 1.0 - self.erd_power_drop)))
        self.random_seed = random_seed
        self.rng = np.random.default_rng(random_seed)
        self.source_id = source_id or "SIM-0000 250"
        self.n_channels = len(CHANNEL_LABELS)

        self.stream_info = create_xon_stream_info(name=self.name, srate=self.srate, source_id=self.source_id)
        self.outlet = pylsl.StreamOutlet(self.stream_info, chunk_size=self.chunk_size)

        self.pink_noise = PinkNoiseGenerator(self.n_channels, rng=self.rng)

        # Durum değişkenleri
        self._class: str = "rest"
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Faz takipçileri
        self._phase_mu = self.rng.uniform(0, 2 * np.pi, self.n_channels)
        self._phase_beta = self.rng.uniform(0, 2 * np.pi, self.n_channels)
        self._phase_50hz = self.rng.uniform(0, 2 * np.pi, self.n_channels)

        # Göz kırpma artefaktı durumu
        self._blink_samples_left = 0
        self._blink_total_samples = 0
        self._blink_amplitude = 0.0

    def set_class(self, class_name: str) -> None:
        """Aktif zihinsel durumu değiştirir ('left', 'right', 'up', 'down', 'rest')."""
        class_name = class_name.lower().strip()
        valid = {"left", "right", "up", "down", "rest"}
        if class_name not in valid:
            raise ValueError(f"Geçersiz sınıf: {class_name}. Geçerli olanlar: {valid}")
        with self._lock:
            self._class = class_name
            logger.info(f"Sentetik EEG sınıfı güncellendi: {class_name}")

    @property
    def current_class(self) -> str:
        with self._lock:
            return self._class

    def inject_blink(self, amplitude: float = 150.0, duration_sec: float = 0.3) -> None:
        """F3 ve F4 kanallarına göz kırpma darbesi enjekte eder."""
        with self._lock:
            self._blink_amplitude = float(amplitude)
            self._blink_total_samples = max(1, int(round(duration_sec * self.srate)))
            self._blink_samples_left = self._blink_total_samples

    def generate_chunk(self, n_samples: int) -> np.ndarray:
        """n_samples adet sentetik EEG/AUX verisi üretir."""
        # 1. Pembe gürültü (taban EEG: ~5-15 µV RMS)
        pink = self.pink_noise.generate(n_samples) * 3.5

        # 2. Sinüzoidal ritimler (mu ~10 Hz, beta ~20 Hz, sebeke 50 Hz)
        t = np.arange(n_samples) / self.srate
        dt_mu = 2.0 * np.pi * 10.0 / self.srate
        dt_beta = 2.0 * np.pi * 20.0 / self.srate
        dt_50 = 2.0 * np.pi * 50.0 / self.srate

        # Kanal indeksleri:
        # 0: F3, 1: F4, 2: C3, 3: Cz, 4: C4, 5: P3, 6: P4, 7: BIP, 8: accX, 9: accY, 10: accZ
        data = np.zeros((n_samples, self.n_channels), dtype=np.float32)

        with self._lock:
            active_class = self._class
            blink_left = self._blink_samples_left
            blink_total = self._blink_total_samples
            blink_amp = self._blink_amplitude

        # Temel ritim genlikleri (µV)
        base_mu_amp = {
            0: 5.0,   # F3
            1: 5.0,   # F4
            2: 20.0,  # C3 (motor)
            3: 18.0,  # Cz (motor)
            4: 20.0,  # C4 (motor)
            5: 12.0,  # P3
            6: 12.0,  # P4
            7: 0.0,   # BIP (pilot kayıtta 0)
        }

        # ERD kuralı: ~%40 güç düşüşü -> Genlik çarpanı sqrt(1 - erd_power_drop) ≈ 0.7746
        erd_attenuation = self.erd_attenuation

        mu_scales = np.ones(self.n_channels, dtype=np.float32)
        if active_class == "left":
            # Sol el hayali -> kontralateral C4 düşer
            mu_scales[4] = erd_attenuation
        elif active_class == "right":
            # Sağ el hayali -> kontralateral C3 düşer
            mu_scales[2] = erd_attenuation
        elif active_class == "down":
            # Ayak hayali -> Cz düşer
            mu_scales[3] = erd_attenuation
        elif active_class == "up":
            # İki el hayali -> C3 ve C4 birlikte düşer
            mu_scales[2] = erd_attenuation
            mu_scales[4] = erd_attenuation

        for ch in range(7):
            # Faz ilerlemesi
            phases_mu = self._phase_mu[ch] + np.cumsum(
                np.full(n_samples, dt_mu) + self.rng.standard_normal(n_samples) * 0.02
            )
            self._phase_mu[ch] = phases_mu[-1] % (2 * np.pi)

            phases_beta = self._phase_beta[ch] + np.cumsum(
                np.full(n_samples, dt_beta) + self.rng.standard_normal(n_samples) * 0.03
            )
            self._phase_beta[ch] = phases_beta[-1] % (2 * np.pi)

            phases_50 = self._phase_50hz[ch] + np.cumsum(np.full(n_samples, dt_50))
            self._phase_50hz[ch] = phases_50[-1] % (2 * np.pi)

            # 50 Hz şebeke gürültüsü (Cz hariç diğerlerinde biraz daha yüksek)
            amp_50 = 2.0 if ch == 3 else 8.0

            b_mu = base_mu_amp.get(ch, 10.0)
            amp_mu = b_mu * mu_scales[ch]
            amp_beta = (b_mu * 0.4) * mu_scales[ch]

            data[:, ch] = (
                pink[:, ch]
                + amp_mu * np.sin(phases_mu)
                + amp_beta * np.sin(phases_beta)
                + amp_50 * np.sin(phases_50)
            )

        # BIP (Kanal 7): Boş / sıfır
        data[:, 7] = 0.0

        # İvmeölçer kanalları (8, 9, 10): Pilot ortalaması ~(-105, 806, -494) mg -> |g| ≈ 950 mg
        data[:, 8] = -105.0 + self.rng.standard_normal(n_samples) * 2.0
        data[:, 9] = 806.0 + self.rng.standard_normal(n_samples) * 2.0
        data[:, 10] = -494.0 + self.rng.standard_normal(n_samples) * 2.0

        # Göz kırpma enjeksiyonu (F3 ve F4)
        if blink_left > 0:
            for s in range(n_samples):
                with self._lock:
                    if self._blink_samples_left > 0:
                        prog = 1.0 - (self._blink_samples_left / self._blink_total_samples)
                        # Yarım sinüs darbesi
                        pulse = float(np.sin(np.pi * prog) * self._blink_amplitude)
                        data[s, 0] += pulse  # F3
                        data[s, 1] += pulse  # F4
                        self._blink_samples_left -= 1
                    else:
                        break

        return data

    def step(self) -> None:
        """Tek bir chunk üretir ve LSL outlet'ine basar."""
        chunk = self.generate_chunk(self.chunk_size)
        self.outlet.push_chunk(chunk.tolist())

    def _run_loop(self) -> None:
        interval = self.chunk_size / self.srate
        next_time = time.perf_counter()
        while self._running:
            self.step()
            next_time += interval
            sleep_dur = next_time - time.perf_counter()
            if sleep_dur > 0:
                time.sleep(sleep_dur)
            else:
                next_time = time.perf_counter()

    def start(self) -> None:
        """Arka plan yayınını başlatır."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"SyntheticEEGSource '{self.name}' yayını başlatıldı (250 Hz).")

    def stop(self) -> None:
        """Arka plan yayınını durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info(f"SyntheticEEGSource '{self.name}' durduruldu.")

    def __enter__(self) -> SyntheticEEGSource:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


if __name__ == "__main__":
    import sys

    print("=== Sentetik X.on EEG Yayınlayıcı Başlatılıyor ===")
    print("Akış Adı: X.on-SIM-0000 (11 kanal, 250 Hz)")
    print("Komutlar:")
    print("  l : Sol el (C4 ERD ~%40)")
    print("  r : Sağ el (C3 ERD ~%40)")
    print("  d : Ayak / Aşağı (Cz ERD ~%40)")
    print("  u : İki el / Yukarı (C3+C4 ERD ~%40)")
    print("  s : Dinlenme / Nötr (Rest)")
    print("  b : Göz kırpma artefaktı enjekte et")
    print("  q : Çıkış")
    print("-------------------------------------------------")

    source = SyntheticEEGSource()
    source.start()

    try:
        while True:
            cmd = input("Komut [l/r/d/u/s/b/q]: ").strip().lower()
            if cmd == "q":
                break
            elif cmd == "l":
                source.set_class("left")
            elif cmd == "r":
                source.set_class("right")
            elif cmd == "d":
                source.set_class("down")
            elif cmd == "u":
                source.set_class("up")
            elif cmd == "s":
                source.set_class("rest")
            elif cmd == "b":
                source.inject_blink(amplitude=160.0)
                print("Göz kırpma enjekte edildi.")
    except KeyboardInterrupt:
        pass
    finally:
        source.stop()
        print("Yayın durduruldu.")
