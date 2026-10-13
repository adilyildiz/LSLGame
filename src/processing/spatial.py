"""Uzamsal Filtreleme Modülü.

PLAN.md Faz 4.1 uyarınca:
- Ham (kulak referansı)
- Küçük Laplace: C3' = C3 - ortalama(F3, P3, Cz); C4' = C4 - ortalama(F4, P4, Cz)
- CAR (Ortak Ortalama Referans)
- scikit-learn uyumlu SpatialFilterTransformer.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Union

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

DEFAULT_CH_NAMES = ["F3", "F4", "C3", "Cz", "C4", "P3", "P4"]


def apply_laplacian(
    data: np.ndarray,
    ch_names: Optional[Sequence[str]] = None,
) -> np.ndarray:
    """Küçük Laplace filtresi uygular.

    C3' = C3 - ortalama(F3, P3, Cz)
    C4' = C4 - ortalama(F4, P4, Cz)

    data: (n_samples, n_channels) veya (n_epochs, n_samples, n_channels)
    """
    if ch_names is None:
        ch_names = DEFAULT_CH_NAMES
    ch_list = list(ch_names)

    c3_idx = ch_list.index("C3")
    cz_idx = ch_list.index("Cz")
    c4_idx = ch_list.index("C4")
    f3_idx = ch_list.index("F3")
    f4_idx = ch_list.index("F4")
    p3_idx = ch_list.index("P3")
    p4_idx = ch_list.index("P4")

    out = np.array(data, dtype=np.float64, copy=True)

    if out.ndim == 2:
        c3_lap = out[:, c3_idx] - (out[:, f3_idx] + out[:, p3_idx] + out[:, cz_idx]) / 3.0
        c4_lap = out[:, c4_idx] - (out[:, f4_idx] + out[:, p4_idx] + out[:, cz_idx]) / 3.0
        out[:, c3_idx] = c3_lap
        out[:, c4_idx] = c4_lap
    elif out.ndim == 3:
        c3_lap = out[:, :, c3_idx] - (out[:, :, f3_idx] + out[:, :, p3_idx] + out[:, :, cz_idx]) / 3.0
        c4_lap = out[:, :, c4_idx] - (out[:, :, f4_idx] + out[:, :, p4_idx] + out[:, :, cz_idx]) / 3.0
        out[:, :, c3_idx] = c3_lap
        out[:, :, c4_idx] = c4_lap
    else:
        raise ValueError(f"Desteklenmeyen veri boyutu: {out.shape}")

    return out


def apply_car(data: np.ndarray) -> np.ndarray:
    """Ortak Ortalama Referans (Common Average Reference - CAR) uygular.

    data: (n_samples, n_channels) veya (n_epochs, n_samples, n_channels)
    """
    out = np.array(data, dtype=np.float64, copy=True)
    # Kanal ekseni daima son eksendir
    car_mean = np.mean(out, axis=-1, keepdims=True)
    return out - car_mean


class SpatialFilterTransformer(BaseEstimator, TransformerMixin):
    """scikit-learn boru hatları için uzamsal filtre dönüştürücüsü."""

    def __init__(self, method: str = "raw", ch_names: Optional[Sequence[str]] = None):
        self.method = method
        self.ch_names = list(ch_names) if ch_names is not None else DEFAULT_CH_NAMES

    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> SpatialFilterTransformer:
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.method == "raw" or self.method == "none":
            return np.array(X, copy=True)
        elif self.method == "laplacian":
            return apply_laplacian(X, ch_names=self.ch_names)
        elif self.method == "car":
            return apply_car(X)
        else:
            raise ValueError(f"Bilinmeyen uzamsal filtre metodu: {self.method}")
