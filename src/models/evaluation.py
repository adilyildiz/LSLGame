"""BCI Model Değerlendirme ve Karşılaştırma Modülü.

PLAN.md Faz 4.4, Faz 4.5 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
- Oturum içi: run'a göre bloklu çapraz doğrulama (GroupKFold, grup = run). Rastgele karıştırma YOK.
- Oturumlar arası: önceki oturumlarla eğit, son oturumla test.
- Metrikler: doğruluk, dengelenmiş doğruluk, Cohen's κ, karışıklık matrisi, ITR (bit/dk; Wolpaw formülü).
- Şans seviyesi: etiket permütasyon testi -> p-değeri ve %95 şans eşiği.
- Zaman çözünürlüklü doğruluk: deneme içinde kayan pencere -> grafik.
- Sınıf seçimi (PLAN 4.5): tüm sınıf çiftleri için ikili doğruluk matrisi. "Yukarı" için
  both_hands vs arithmetic karşılaştırması ve önerisi.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from src.processing.epochs import Epochs

logger = logging.getLogger(__name__)


def compute_itr(accuracy: float, n_classes: int, trial_duration_sec: float = 7.0) -> float:
    """Wolpaw formülüne göre Bilgi Transfer Hızını (ITR, bit/dk) hesaplar.

    B = log2(N) + P*log2(P) + (1-P)*log2((1-P)/(N-1))
    ITR = B * (60 / T)
    """
    if n_classes <= 1:
        return 0.0
    if accuracy <= (1.0 / n_classes):
        return 0.0
    if accuracy >= 1.0:
        b = np.log2(n_classes)
    else:
        b = (
            np.log2(n_classes)
            + accuracy * np.log2(accuracy)
            + (1.0 - accuracy) * np.log2((1.0 - accuracy) / (n_classes - 1))
        )
    return max(0.0, float(b * (60.0 / trial_duration_sec)))


def evaluate_session_cv(
    pipelines: Dict[str, Pipeline],
    epochs: Epochs,
    n_splits: Optional[int] = None,
    n_permutations: int = 100,
    trial_duration_sec: float = 7.0,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """Run-bloklu çapraz doğrulama ile modelleri değerlendirir.

    GroupKFold kullanılır (grup = run_indices).
    Her model için doğruluk, dengeli doğruluk, kappa, karışıklık matrisi ve ITR hesaplanır.
    Permütasyon testiyle şans seviyesi doğrulanır.
    """
    X = epochs.data  # (n_epochs, n_times, n_channels)
    y = epochs.labels
    groups = epochs.run_indices
    unique_runs = np.unique(groups)
    unique_classes = sorted(list(set(y)))
    n_classes = len(unique_classes)

    if n_splits is None:
        n_splits = len(unique_runs)
    n_splits = min(n_splits, len(unique_runs))

    if n_splits < 2:
        raise ValueError(f"En az 2 farklı run gereklidir, bulunan: {len(unique_runs)}")

    gkf = GroupKFold(n_splits=n_splits)

    results: Dict[str, Any] = {
        "models": {},
        "classes": unique_classes,
        "n_splits": n_splits,
        "n_epochs": len(epochs),
        "chance_level_theory": 1.0 / n_classes,
    }

    best_model_name = ""
    best_acc = -1.0

    for name, pipe in pipelines.items():
        oof_preds = np.empty_like(y)
        fold_accuracies = []

        for train_idx, test_idx in gkf.split(X, y, groups=groups):
            fold_pipe = clone(pipe)
            fold_pipe.fit(X[train_idx], y[train_idx])
            preds = fold_pipe.predict(X[test_idx])
            oof_preds[test_idx] = preds
            fold_accuracies.append(float(accuracy_score(y[test_idx], preds)))

        acc = float(accuracy_score(y, oof_preds))
        bal_acc = float(balanced_accuracy_score(y, oof_preds))
        kappa = float(cohen_kappa_score(y, oof_preds))
        cm = confusion_matrix(y, oof_preds, labels=unique_classes).tolist()
        itr_val = compute_itr(acc, n_classes, trial_duration_sec=trial_duration_sec)

        results["models"][name] = {
            "accuracy": acc,
            "accuracy_std": float(np.std(fold_accuracies)),
            "fold_accuracies": fold_accuracies,
            "balanced_accuracy": bal_acc,
            "cohen_kappa": kappa,
            "confusion_matrix": cm,
            "itr_bpm": itr_val,
            "oof_preds": oof_preds.tolist(),
        }

        if acc > best_acc:
            best_acc = acc
            best_model_name = name

    results["best_model"] = best_model_name
    results["best_accuracy"] = best_acc

    # Permütasyon Testi (Şans seviyesi ve p-değeri)
    if n_permutations > 0 and best_model_name in pipelines:
        target_pipe = pipelines[best_model_name]
        rng = np.random.default_rng(seed)
        perm_accs = np.zeros(n_permutations, dtype=np.float64)

        for b in range(n_permutations):
            y_perm = rng.permutation(y)
            perm_preds = np.empty_like(y)
            for train_idx, test_idx in gkf.split(X, y_perm, groups=groups):
                fold_p = clone(target_pipe)
                fold_p.fit(X[train_idx], y_perm[train_idx])
                perm_preds[test_idx] = fold_p.predict(X[test_idx])
            perm_accs[b] = accuracy_score(y_perm, perm_preds)

        p_value = float(np.sum(perm_accs >= best_acc) + 1) / float(n_permutations + 1)
        chance_95 = float(np.percentile(perm_accs, 95))

        results["permutation_test"] = {
            "model": best_model_name,
            "p_value": p_value,
            "chance_level_95": chance_95,
            "perm_mean": float(np.mean(perm_accs)),
            "perm_std": float(np.std(perm_accs)),
            "n_permutations": n_permutations,
        }

    return results


def evaluate_across_sessions(
    pipelines: Dict[str, Pipeline],
    epochs_train: Epochs,
    epochs_test: Epochs,
    trial_duration_sec: float = 7.0,
) -> Dict[str, Any]:
    """Oturumlar arası değerlendirme (önceki oturumlarla eğit, son oturumla test)."""
    X_train, y_train = epochs_train.data, epochs_train.labels
    X_test, y_test = epochs_test.data, epochs_test.labels
    unique_classes = sorted(list(set(y_train)))
    n_classes = len(unique_classes)

    results: Dict[str, Any] = {"models": {}, "classes": unique_classes}

    for name, pipe in pipelines.items():
        p = clone(pipe)
        p.fit(X_train, y_train)
        preds = p.predict(X_test)

        acc = float(accuracy_score(y_test, preds))
        bal_acc = float(balanced_accuracy_score(y_test, preds))
        kappa = float(cohen_kappa_score(y_test, preds))
        cm = confusion_matrix(y_test, preds, labels=unique_classes).tolist()
        itr_val = compute_itr(acc, n_classes, trial_duration_sec=trial_duration_sec)

        results["models"][name] = {
            "accuracy": acc,
            "balanced_accuracy": bal_acc,
            "cohen_kappa": kappa,
            "confusion_matrix": cm,
            "itr_bpm": itr_val,
        }

    return results


def compute_time_resolved_accuracy(
    pipeline: Pipeline,
    epochs: Epochs,
    window_sec: float = 1.0,
    step_sec: float = 0.25,
    n_splits: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Deneme içinde kayan pencere ile zaman çözünürlüklü doğruluk profili çıkarır.

    Dönüş:
    - center_times: Kayan pencerelerin merkez zamanları (sn)
    - accuracies: Zaman pencerelerindeki CV doğrulukları
    """
    data = epochs.data  # (n_epochs, n_times, n_channels)
    labels = epochs.labels
    groups = epochs.run_indices
    srate = epochs.srate
    times = epochs.times

    win_samples = int(round(window_sec * srate))
    step_samples = int(round(step_sec * srate))
    n_total_times = data.shape[1]

    if win_samples >= n_total_times:
        return np.array([times[n_total_times // 2]]), np.array([1.0 / len(set(labels))])

    if n_splits is None:
        n_splits = len(np.unique(groups))
    n_splits = min(n_splits, len(np.unique(groups)))
    gkf = GroupKFold(n_splits=n_splits)

    center_times = []
    accuracies = []

    for start_idx in range(0, n_total_times - win_samples + 1, step_samples):
        end_idx = start_idx + win_samples
        mid_idx = (start_idx + end_idx) // 2
        center_times.append(times[mid_idx])

        # Zaman penceresi alt kümesi (n_epochs, win_samples, n_channels)
        X_sub = data[:, start_idx:end_idx, :]
        oof_preds = np.empty_like(labels)

        for train_idx, test_idx in gkf.split(X_sub, labels, groups=groups):
            p = clone(pipeline)
            p.fit(X_sub[train_idx], labels[train_idx])
            oof_preds[test_idx] = p.predict(X_sub[test_idx])

        acc = accuracy_score(labels, oof_preds)
        accuracies.append(float(acc))

    return np.array(center_times), np.array(accuracies)


def plot_time_resolved_accuracy(
    time_results: Dict[str, Tuple[np.ndarray, np.ndarray]],
    chance_level: float,
    output_png: Union[str, Path],
) -> None:
    """Zaman çözünürlüklü doğruluk grafiğini PNG olarak çizer."""
    fig, ax = plt.subplots(figsize=(8, 4.5))

    for model_name, (center_times, accs) in time_results.items():
        ax.plot(center_times, accs * 100.0, label=f"{model_name}", lw=2)

    ax.axhline(chance_level * 100.0, color="gray", linestyle="--", label=f"Şans ({chance_level*100:.0f}%)")
    ax.set_xlabel("İmgeleme Başlangıcına Göre Zaman (sn)")
    ax.set_ylabel("CV Doğruluk (%)")
    ax.set_title("Zaman Çözünürlüklü Kod Çözme Başarısı")
    ax.set_ylim(max(0.0, (chance_level - 0.2) * 100.0), 105.0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    out_path = Path(output_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_confusion_matrices(
    confusion_dict: Dict[str, List[List[int]]],
    classes: List[str],
    output_png: Union[str, Path],
) -> None:
    """Modellerin karışıklık matrislerini grid olarak kaydeder."""
    n_models = len(confusion_dict)
    n_cols = min(3, n_models)
    n_rows = int(np.ceil(n_models / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.5 * n_cols, 4 * n_rows), squeeze=False)

    for idx, (m_name, cm_list) in enumerate(confusion_dict.items()):
        r = idx // n_cols
        c = idx % n_cols
        ax = axes[r, c]
        cm = np.array(cm_list)

        im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
        ax.set_title(f"Karışıklık Matrisi: {m_name}")
        tick_marks = np.arange(len(classes))
        ax.set_xticks(tick_marks)
        ax.set_yticks(tick_marks)
        ax.set_xticklabels(classes, rotation=45)
        ax.set_yticklabels(classes)

        # Rakamları hücrelere yaz
        thresh = cm.max() / 2.0 if cm.max() > 0 else 1.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(
                    j,
                    i,
                    format(cm[i, j], "d"),
                    ha="center",
                    va="center",
                    color="white" if cm[i, j] > thresh else "black",
                )

        ax.set_ylabel("Gerçek Sınıf")
        ax.set_xlabel("Tahmin Edilen Sınıf")

    # Boş kalan subplotları kapat
    for idx in range(n_models, n_rows * n_cols):
        r = idx // n_cols
        c = idx % n_cols
        axes[r, c].axis("off")

    fig.tight_layout()
    out_path = Path(output_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def evaluate_class_selection(
    pipeline: Pipeline,
    epochs: Epochs,
) -> Dict[str, Any]:
    """Tüm sınıf çiftleri için ikili doğruluk matrisi çıkarır (PLAN 4.5).

    'Yukarı' yönü için 'both_hands' ile 'arithmetic' sınıflarını karşılaştırır.
    """
    unique_classes = sorted(list(set(epochs.labels)))
    n_classes = len(unique_classes)
    pairwise_matrix: Dict[str, Dict[str, float]] = {c: {} for c in unique_classes}

    groups = epochs.run_indices

    for i, c1 in enumerate(unique_classes):
        for j, c2 in enumerate(unique_classes):
            if i >= j:
                continue
            pair_mask = np.isin(epochs.labels, [c1, c2])
            sub_ep = epochs.subset(np.where(pair_mask)[0])

            n_runs = len(np.unique(sub_ep.run_indices))
            if n_runs < 2:
                pairwise_matrix[c1][c2] = 0.5
                pairwise_matrix[c2][c1] = 0.5
                continue

            gkf = GroupKFold(n_splits=n_runs)
            oof = np.empty_like(sub_ep.labels)
            for tr_idx, te_idx in gkf.split(sub_ep.data, sub_ep.labels, groups=sub_ep.run_indices):
                p = clone(pipeline)
                p.fit(sub_ep.data[tr_idx], sub_ep.labels[tr_idx])
                oof[te_idx] = p.predict(sub_ep.data[te_idx])

            acc = float(accuracy_score(sub_ep.labels, oof))
            pairwise_matrix[c1][c2] = acc
            pairwise_matrix[c2][c1] = acc

    # 'Yukarı' sınıf adayları karşılaştırması
    candidates = ["both_hands", "arithmetic"]
    other_classes = [c for c in unique_classes if c not in candidates]
    candidate_scores: Dict[str, float] = {}

    for cand in candidates:
        if cand in unique_classes and other_classes:
            accs = [pairwise_matrix[cand].get(other, 0.5) for other in other_classes]
            candidate_scores[cand] = float(np.mean(accs))

    recommendation = "N/A"
    if "both_hands" in candidate_scores and "arithmetic" in candidate_scores:
        if candidate_scores["both_hands"] >= candidate_scores["arithmetic"]:
            recommendation = (
                f"'both_hands' ({candidate_scores['both_hands']:.2%}) diğer sınıflardan "
                f"'arithmetic' ({candidate_scores['arithmetic']:.2%}) sınıfına göre daha iyi ayrışıyor. "
                f"'both_hands' önerilir."
            )
        else:
            recommendation = (
                f"'arithmetic' ({candidate_scores['arithmetic']:.2%}) diğer sınıflardan "
                f"'both_hands' ({candidate_scores['both_hands']:.2%}) sınıfına göre daha iyi ayrışıyor. "
                f"'arithmetic' önerilir."
            )
    elif "both_hands" in candidate_scores:
        recommendation = f"'both_hands' ({candidate_scores['both_hands']:.2%}) ayrışma skoru ile kullanılabilir."
    elif "arithmetic" in candidate_scores:
        recommendation = f"'arithmetic' ({candidate_scores['arithmetic']:.2%}) ayrışma skoru ile kullanılabilir."

    return {
        "classes": unique_classes,
        "pairwise_accuracy": pairwise_matrix,
        "candidate_scores": candidate_scores,
        "recommendation": recommendation,
    }
