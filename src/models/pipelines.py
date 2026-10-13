"""BCI Sınıflandırma Boru Hatları (Pipelines) Modülü.

PLAN.md Faz 4.3 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- M1: Log-bant gücü (C3, Cz, C4; μ ve β) + LDA (shrinkage).
- M2: CSP (8-30 Hz) + LDA (shrinkage).
- M3: FBCSP (4-8, 8-12, ..., 26-30 Hz) + MI tabanlı öznitelik seçimi + LDA.
- M4: Kovaryans -> Tanjant Uzayı + Lojistik Regresyon (pyriemann).
- M5: Kovaryans -> MDM (pyriemann).
- M6 (EEGNet) yapılmayacak.

Veri Sızıntısı Kuralı:
CSP, öznitelik seçimi, kovaryans referansı ve normalleştirici gibi tüm veri-güdümlü
adımlar pipeline içinde yer alır ve yalnızca eğitim katında (fit) eğitilir.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from scipy import linalg, signal
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from pyriemann.classification import MDM
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace

from src.processing.recording import DEFAULT_EEG_CH_NAMES

logger = logging.getLogger(__name__)


class EnsureChannelsFirst(BaseEstimator, TransformerMixin):
    """Girdi boyutunu (n_epochs, n_channels, n_times) olarak garanti eder."""

    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> EnsureChannelsFirst:
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        arr = np.asarray(X, dtype=np.float64)
        if arr.ndim != 3:
            raise ValueError(f"3 boyutlu epok matrisi bekleniyordu, gelen: {arr.shape}")
        # Eğer shape[1] > shape[2] ise tipik olarak (epochs, times, channels)'dir
        if arr.shape[1] > arr.shape[2]:
            return np.transpose(arr, (0, 2, 1))
        return arr


class LogBandPower(BaseEstimator, TransformerMixin):
    """Seçilen kanallardan μ ve β bantlarında log güç öznitelikleri çıkarır."""

    def __init__(
        self,
        srate: float = 250.0,
        ch_names: Optional[Sequence[str]] = None,
        selected_channels: Optional[Sequence[str]] = None,
        bands: Optional[Sequence[Tuple[float, float]]] = None,
    ):
        self.srate = srate
        self.ch_names = ch_names
        self.selected_channels = selected_channels
        self.bands = bands

    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> LogBandPower:
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        # X: (n_epochs, n_channels, n_times)
        X = np.asarray(X, dtype=np.float64)
        n_epochs, n_channels, n_times = X.shape

        ch_list = list(self.ch_names) if self.ch_names is not None else DEFAULT_EEG_CH_NAMES
        sel_channels = list(self.selected_channels) if self.selected_channels is not None else ["C3", "Cz", "C4"]
        band_list = list(self.bands) if self.bands is not None else [(8.0, 12.0), (16.0, 28.0)]

        sel_indices = [
            ch_list.index(ch) for ch in sel_channels if ch in ch_list
        ]
        if not sel_indices:
            sel_indices = list(range(n_channels))

        features = []
        nyq = 0.5 * self.srate

        for f_low, f_high in band_list:
            low = max(0.1, f_low) / nyq
            high = min(nyq - 0.1, f_high) / nyq
            sos = signal.butter(3, [low, high], btype="bandpass", output="sos")

            for ch_idx in sel_indices:
                filtered = signal.sosfilt(sos, X[:, ch_idx, :], axis=-1)
                power = np.var(filtered, axis=-1)
                log_power = np.log(np.maximum(power, 1e-12))
                features.append(log_power)

        return np.column_stack(features)


class CSP(BaseEstimator, TransformerMixin):
    """Ortak Uzamsal Örüntüler (Common Spatial Patterns - CSP).

    İkili ve çok sınıflı (One-vs-Rest) motor imgeleme için uzamsal filtreler öğrenir.
    Veri sızıntısını önlemek için yalnızca eğitim kümesinde fit edilir.
    """

    def __init__(self, n_components: int = 4, log: bool = True):
        self.n_components = n_components
        self.log = log
        self.filters_: Optional[np.ndarray] = None
        self.classes_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> CSP:
        # X: (n_epochs, n_channels, n_times)
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        self.classes_ = np.unique(y)
        n_classes = len(self.classes_)
        n_channels = X.shape[1]

        if n_classes < 2:
            raise ValueError("CSP için en az 2 sınıf gereklidir.")

        if n_classes == 2:
            # 2-sınıf klasik CSP
            c1_mask = (y == self.classes_[0])
            c2_mask = (y == self.classes_[1])

            cov1 = self._compute_mean_cov(X[c1_mask])
            cov2 = self._compute_mean_cov(X[c2_mask])

            cov_total = cov1 + cov2
            # Düzenlileştirme (sayısal kararlılık için)
            cov_total += np.eye(n_channels) * 1e-6 * np.trace(cov_total) / n_channels

            eigvals, U = linalg.eigh(cov_total)
            idx = np.argsort(eigvals)[::-1]
            eigvals, U = eigvals[idx], U[:, idx]

            # Beyazlatma (Whitening) matrisi
            P = np.diag(1.0 / np.sqrt(np.maximum(eigvals, 1e-9))) @ U.T
            S1 = P @ cov1 @ P.T

            eigvals1, B = linalg.eigh(S1)
            idx1 = np.argsort(eigvals1)[::-1]
            B = B[:, idx1]

            W = B.T @ P
            m = max(1, self.n_components // 2)
            m = min(m, n_channels // 2) if n_channels >= 2 else 1
            if 2 * m <= n_channels:
                self.filters_ = np.vstack([W[:m], W[-m:]])
            else:
                self.filters_ = W[:min(self.n_components, n_channels)]

        else:
            # Çok sınıflı One-vs-Rest CSP
            all_filters = []
            m = max(1, self.n_components // n_classes)
            for cls in self.classes_:
                pos_mask = (y == cls)
                neg_mask = (y != cls)

                cov_pos = self._compute_mean_cov(X[pos_mask])
                cov_neg = self._compute_mean_cov(X[neg_mask])

                cov_total = cov_pos + cov_neg
                cov_total += np.eye(n_channels) * 1e-6 * np.trace(cov_total) / n_channels

                eigvals, U = linalg.eigh(cov_total)
                idx = np.argsort(eigvals)[::-1]
                eigvals, U = eigvals[idx], U[:, idx]

                P = np.diag(1.0 / np.sqrt(np.maximum(eigvals, 1e-9))) @ U.T
                S_pos = P @ cov_pos @ P.T

                eigvals_pos, B = linalg.eigh(S_pos)
                idx_pos = np.argsort(eigvals_pos)[::-1]
                B = B[:, idx_pos]

                W = B.T @ P
                all_filters.append(W[:min(m, n_channels)])

            self.filters_ = np.vstack(all_filters)

        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.filters_ is None:
            raise RuntimeError("CSP henüz fit edilmedi.")

        X = np.asarray(X, dtype=np.float64)
        n_epochs = X.shape[0]

        # Her epoku filtrelerle projekte et: Z = W @ X -> (n_filters, n_times)
        # Öznitelik: log-varyans
        features = np.zeros((n_epochs, len(self.filters_)), dtype=np.float64)
        for i in range(n_epochs):
            proj = self.filters_ @ X[i]  # (n_filters, n_times)
            var = np.var(proj, axis=-1)
            if self.log:
                norm_var = var / np.maximum(np.sum(var), 1e-12)
                features[i] = np.log(np.maximum(norm_var, 1e-12))
            else:
                features[i] = var

        return features

    @staticmethod
    def _compute_mean_cov(epochs_subset: np.ndarray) -> np.ndarray:
        covs = []
        for ep in epochs_subset:
            c = np.cov(ep)
            # Normalize et
            c /= np.maximum(np.trace(c), 1e-12)
            covs.append(c)
        return np.mean(covs, axis=0)


class FilterBankCSP(BaseEstimator, TransformerMixin):
    """Filtre Bankası CSP (FBCSP).

    Alt bantlar: 4-8, 8-12, 12-16, 16-20, 20-24, 24-28, 26-30 Hz.
    Her bant için ayrı CSP modeller ve öznitelikleri birleştirir.
    """

    DEFAULT_BANDS = [
        (4.0, 8.0),
        (8.0, 12.0),
        (12.0, 16.0),
        (16.0, 20.0),
        (20.0, 24.0),
        (24.0, 28.0),
        (26.0, 30.0),
    ]

    def __init__(
        self,
        srate: float = 250.0,
        n_components: int = 4,
        bands: Optional[Sequence[Tuple[float, float]]] = None,
    ):
        self.srate = srate
        self.n_components = n_components
        self.bands = bands

    def fit(self, X: np.ndarray, y: np.ndarray) -> FilterBankCSP:
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        self.csp_models_ = []
        band_list = list(self.bands) if self.bands is not None else self.DEFAULT_BANDS
        nyq = 0.5 * self.srate

        for f_low, f_high in band_list:
            low = max(0.1, f_low) / nyq
            high = min(nyq - 0.1, f_high) / nyq
            sos = signal.butter(3, [low, high], btype="bandpass", output="sos")

            # Bant geçiren filtrele
            filtered_X = np.zeros_like(X)
            for i in range(len(X)):
                filtered_X[i] = signal.sosfilt(sos, X[i], axis=-1)

            csp = CSP(n_components=self.n_components, log=True)
            csp.fit(filtered_X, y)
            self.csp_models_.append(csp)

        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        band_list = list(self.bands) if self.bands is not None else self.DEFAULT_BANDS
        nyq = 0.5 * self.srate
        all_features = []

        for (f_low, f_high), csp in zip(band_list, self.csp_models_):
            low = max(0.1, f_low) / nyq
            high = min(nyq - 0.1, f_high) / nyq
            sos = signal.butter(3, [low, high], btype="bandpass", output="sos")

            filtered_X = np.zeros_like(X)
            for i in range(len(X)):
                filtered_X[i] = signal.sosfilt(sos, X[i], axis=-1)

            feats = csp.transform(filtered_X)
            all_features.append(feats)

        return np.column_stack(all_features)


# Pipeline Fabrika Fonksiyonları


def build_m1_log_bandpower(
    srate: float = 250.0,
    ch_names: Optional[Sequence[str]] = None,
    selected_channels: Sequence[str] = ("C3", "Cz", "C4"),
) -> Pipeline:
    """M1: Log-bant gücü + LDA (shrinkage='auto')."""
    return Pipeline([
        ("ensure_shape", EnsureChannelsFirst()),
        (
            "features",
            LogBandPower(
                srate=srate,
                ch_names=ch_names,
                selected_channels=selected_channels,
                bands=((8.0, 12.0), (16.0, 28.0)),
            ),
        ),
        ("clf", LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
    ])


def build_m2_csp(n_components: int = 4) -> Pipeline:
    """M2: CSP (8-30 Hz) + LDA (shrinkage='auto')."""
    return Pipeline([
        ("ensure_shape", EnsureChannelsFirst()),
        ("csp", CSP(n_components=n_components, log=True)),
        ("clf", LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
    ])


def build_m3_fbcsp(srate: float = 250.0, n_components: int = 4, k_features: int = 8) -> Pipeline:
    """M3: FBCSP + MI tabanlı öznitelik seçimi + LDA."""
    return Pipeline([
        ("ensure_shape", EnsureChannelsFirst()),
        ("fbcsp", FilterBankCSP(srate=srate, n_components=n_components)),
        ("select_k", SelectKBest(score_func=mutual_info_classif, k=k_features)),
        ("clf", LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
    ])


def build_m4_tangentspace() -> Pipeline:
    """M4: Riemann: Kovaryans -> Tanjant Uzayı + Lojistik Regresyon."""
    return Pipeline([
        ("ensure_shape", EnsureChannelsFirst()),
        ("cov", Covariances(estimator="lwf")),
        ("ts", TangentSpace(metric="riemann")),
        ("clf", LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")),
    ])


def build_m5_mdm() -> Pipeline:
    """M5: Riemann MDM (Minimum Distance to Mean)."""
    return Pipeline([
        ("ensure_shape", EnsureChannelsFirst()),
        ("cov", Covariances(estimator="lwf")),
        ("clf", MDM(metric=dict(mean="riemann", distance="riemann"))),
    ])


def build_pipelines(
    srate: float = 250.0,
    ch_names: Optional[Sequence[str]] = None,
    model_names: Optional[Sequence[str]] = None,
) -> Dict[str, Pipeline]:
    """İstenen modeller için Pipeline sözlüğü oluşturur."""
    all_models: Dict[str, Pipeline] = {
        "M1": build_m1_log_bandpower(srate=srate, ch_names=ch_names),
        "M2": build_m2_csp(n_components=4),
        "M3": build_m3_fbcsp(srate=srate, n_components=4, k_features=8),
        "M4": build_m4_tangentspace(),
        "M5": build_m5_mdm(),
    }

    if model_names is not None:
        return {name: all_models[name] for name in model_names if name in all_models}
    return all_models
