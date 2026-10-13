"""Filtreleme ve Durumsal (Stateful) Filtre Modülü.

PLAN.md Faz 4.1, Faz 5.1 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- 50 Hz (+100 Hz harmonik) çentik filtresi.
- 8-30 Hz bant geçiren 4. derece Butterworth filtre.
- İki mod: 'zero_phase' (filtfilt - sadece görselleştirme ve ERD) ve 'causal' (sosfilt - model eğitimi).
- Model eğitimi varsayılan olarak 'causal' kullanmalıdır.
- StatefulFilter sınıfı: blok blok uygulandığında tek seferde uygulamayla aynı sonucu verir (hata < 1e-6).
  Faz 5 online döngüsünde bu sınıf kullanılacaktır.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


def create_bandpass_sos(
    srate: float,
    f_low: float = 8.0,
    f_high: float = 30.0,
    order: int = 4,
) -> np.ndarray:
    """Butterworth bant geçiren filtre için SOS (ikinci derece bölümler) matrisi üretir."""
    nyq = 0.5 * srate
    low = max(0.1, f_low) / nyq
    high = min(nyq - 0.1, f_high) / nyq
    if low >= high:
        raise ValueError(f"Geçersiz bant aralığı: f_low={f_low}, f_high={f_high}, Nyquist={nyq}")
    # scipy butter: N=order için 'bandpass' durumunda toplam filtre derecesi 2*order olur.
    # 4. derece Butterworth için N = order // 2 = 2 veya N = order.
    # Standart pratikte 4. derece b-p için N=order (4 SOS sekansı) kullanılır.
    return signal.butter(order, [low, high], btype="bandpass", output="sos")


def create_notch_sos(
    srate: float,
    freqs: Sequence[float] = (50.0, 100.0),
    q: float = 30.0,
) -> List[np.ndarray]:
    """Çentik (notch) filtreleri için SOS matrisleri listesi üretir."""
    nyq = 0.5 * srate
    sos_list: List[np.ndarray] = []
    for f in freqs:
        if 0 < f < nyq - 1.0:
            b, a = signal.iirnotch(f, q, fs=srate)
            sos = signal.tf2sos(b, a)
            sos_list.append(sos)
    return sos_list


def apply_notch(
    data: np.ndarray,
    srate: float,
    freqs: Sequence[float] = (50.0, 100.0),
    q: float = 30.0,
    mode: str = "causal",
) -> np.ndarray:
    """Çentik filtresi uygular.

    Parametreler:
    - data: (n_samples, n_channels) veya (n_samples,)
    - mode: 'causal' veya 'zero_phase'
    """
    sos_list = create_notch_sos(srate=srate, freqs=freqs, q=q)
    out = np.array(data, dtype=np.float64, copy=True)
    axis = 0

    for sos in sos_list:
        if mode == "causal":
            # Başlangıç durumu sıfır kabul edilir
            zi = signal.sosfilt_zi(sos)
            if out.ndim == 2:
                zi = zi[:, :, None] * np.zeros((1, 1, out.shape[1]))
            out, _ = signal.sosfilt(sos, out, axis=axis, zi=zi)
        elif mode == "zero_phase":
            out = signal.sosfiltfilt(sos, out, axis=axis)
        else:
            raise ValueError(f"Bilinmeyen filtre modu: {mode}")

    return out


def apply_bandpass(
    data: np.ndarray,
    srate: float,
    f_low: float = 8.0,
    f_high: float = 30.0,
    order: int = 4,
    mode: str = "causal",
) -> np.ndarray:
    """Bant geçiren filtre uygular.

    Parametreler:
    - data: (n_samples, n_channels) veya (n_samples,)
    - mode: 'causal' veya 'zero_phase'
    """
    sos = create_bandpass_sos(srate=srate, f_low=f_low, f_high=f_high, order=order)
    out = np.array(data, dtype=np.float64, copy=True)
    axis = 0

    if mode == "causal":
        zi = signal.sosfilt_zi(sos)
        if out.ndim == 2:
            zi = zi[:, :, None] * np.zeros((1, 1, out.shape[1]))
        out, _ = signal.sosfilt(sos, out, axis=axis, zi=zi)
    elif mode == "zero_phase":
        out = signal.sosfiltfilt(sos, out, axis=axis)
    else:
        raise ValueError(f"Bilinmeyen filtre modu: {mode}")

    return out


def filter_eeg(
    data: np.ndarray,
    srate: float,
    f_low: float = 8.0,
    f_high: float = 30.0,
    order: int = 4,
    notch_freqs: Sequence[float] = (50.0, 100.0),
    mode: str = "causal",
) -> np.ndarray:
    """Hem çentik hem bant geçiren filtreyi ardışık uygular."""
    notched = apply_notch(data, srate=srate, freqs=notch_freqs, mode=mode)
    bandpassed = apply_bandpass(notched, srate=srate, f_low=f_low, f_high=f_high, order=order, mode=mode)
    return bandpassed


class StatefulFilter:
    """Bloklar arası durum koruyan nedensel (causal) filtre.

    Faz 5 online döngüsünde sürekli gelen LSL bloklarını filtrelemek için kullanılır.
    Özellik: Blok blok uygulandığında, tüm veriye tek seferde uygulanan nedensel filtreyle
    birebir aynı sonucu verir (sayısal hata < 1e-6).
    """

    def __init__(
        self,
        srate: float = 250.0,
        n_channels: int = 7,
        f_low: float = 8.0,
        f_high: float = 30.0,
        order: int = 4,
        notch_freqs: Sequence[float] = (50.0, 100.0),
    ):
        self.srate = srate
        self.n_channels = n_channels
        self.f_low = f_low
        self.f_high = f_high
        self.order = order
        self.notch_freqs = tuple(notch_freqs)

        # SOS kaskadı oluştur
        self.notch_sos_list = create_notch_sos(srate=srate, freqs=self.notch_freqs)
        self.bp_sos = create_bandpass_sos(srate=srate, f_low=f_low, f_high=f_high, order=order)

        self.reset()

    def reset(self) -> None:
        """Filtre durumlarını (zi) sıfırlar."""
        # Her çentik filtresi için zi
        self.notch_zi = []
        for sos in self.notch_sos_list:
            zi = signal.sosfilt_zi(sos)[:, :, None] * np.zeros((1, 1, self.n_channels))
            self.notch_zi.append(zi)

        # Bant geçiren filtre için zi
        self.bp_zi = signal.sosfilt_zi(self.bp_sos)[:, :, None] * np.zeros((1, 1, self.n_channels))

    def filter_block(self, chunk: np.ndarray) -> np.ndarray:
        """Yeni bir veri bloğunu filtreler ve durumu günceller.

        chunk: (n_chunk_samples, n_channels)
        Dönüş: (n_chunk_samples, n_channels)
        """
        chunk = np.asarray(chunk, dtype=np.float64)
        if chunk.ndim != 2 or chunk.shape[1] != self.n_channels:
            raise ValueError(f"Beklenen veri boyutu: (n, {self.n_channels}), gelen: {chunk.shape}")

        if chunk.shape[0] == 0:
            return np.zeros((0, self.n_channels), dtype=np.float64)

        cur = chunk
        # 1. Çentik filtreleri
        new_notch_zi = []
        for sos, zi in zip(self.notch_sos_list, self.notch_zi):
            cur, next_zi = signal.sosfilt(sos, cur, axis=0, zi=zi)
            new_notch_zi.append(next_zi)
        self.notch_zi = new_notch_zi

        # 2. Bant geçiren filtre
        out, next_bp_zi = signal.sosfilt(self.bp_sos, cur, axis=0, zi=self.bp_zi)
        self.bp_zi = next_bp_zi

        return out

    def filter_full(self, data: np.ndarray) -> np.ndarray:
        """Tüm veriyi sıfır durumdan başlayarak tek seferde filtreler."""
        fresh = StatefulFilter(
            srate=self.srate,
            n_channels=self.n_channels,
            f_low=self.f_low,
            f_high=self.f_high,
            order=self.order,
            notch_freqs=self.notch_freqs,
        )
        return fresh.filter_block(data)
