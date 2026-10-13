"""Model Başarımı, Sanity ve EMG Karıştırıcı Testleri.

PLAN.md Faz 4.3, 4.4, Faz 17.3 ve Görev 06 Madde 8 (4, 5, 6, 7) uyarınca:
4. Sinyal varken: erd_power_drop=0.4, mi2 (left/right), 4 run -> en az bir model CV >= %75, perm p < 0.05.
5. Sinyal yokken (Sanity, PLAN 17.3): erd_power_drop=0.0 -> tüm modeller %35-%65 arası şans seviyesinde, perm p > 0.05.
6. Etiket karıştırma: etiketler karıştırılınca doğruluk şans seviyesine düşmeli.
7. EMG karıştırıcı: emg_confound senaryosunda EMG uyarısı üretilmeli, normal senaryoda üretilmemeli.
"""

import numpy as np
import pytest
from scipy import stats

from src.models.evaluation import evaluate_session_cv
from src.models.pipelines import FilterBankCSP, build_pipelines
from src.processing.epochs import extract_epochs
from src.processing.erd_analysis import check_emg_confound
from src.simulation.offline_dataset import generate_offline_dataset


def test_signal_present_accuracy_and_permutation():
    """Sinyal varken (erd=0.4, 2 sınıf, 4 run) en az bir model >= %75 olmalı ve p < 0.05."""
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)
    models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)

    results = evaluate_session_cv(models, epochs, n_permutations=25, seed=42)

    best_acc = results["best_accuracy"]
    perm_p = results["permutation_test"]["p_value"]

    assert best_acc >= 0.75, f"En iyi model doğruluğu <%75: {best_acc:.2%}"
    assert perm_p < 0.05, f"Permütasyon testi p-değeri >= 0.05: {perm_p:.4f}"


def test_no_signal_c3_cz_c4_band_power_difference():
    """D1 Testi: erd=0 ile üretilen veride sınıflar arası C3/Cz/C4 bant gücü farkı istatistiksel olarak yok olmalı."""
    rec = generate_offline_dataset(
        erd_power_drop=0.0,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)
    left_mask = (epochs.labels == "left")
    right_mask = (epochs.labels == "right")

    for ch_name in ["C3", "Cz", "C4"]:
        ch_idx = epochs.ch_names.index(ch_name)
        power_left = np.var(epochs.data[left_mask, :, ch_idx], axis=1)
        power_right = np.var(epochs.data[right_mask, :, ch_idx], axis=1)

        t_stat, p_val = stats.ttest_ind(power_left, power_right)
        assert p_val > 0.05, f"{ch_name} kanalında erd=0 iken sınıflar arası güç farkı anlamlı çıktı: p={p_val:.4f}, t={t_stat:.3f}"


def test_no_signal_sanity_leakage_check():
    """Sanity Testi (D1 & D4, Test 5): 5 tohumla, 2 sınıfla ortalama doğruluk %40-%60 arasında ve perm p < 0.05 sayısı <= 1 olmalı."""
    seeds = [1, 2, 3, 4, 5]
    sig_count = 0

    for s in seeds:
        rec = generate_offline_dataset(
            erd_power_drop=0.0,
            n_runs=4,
            trials_per_run=20,
            classes=["left", "right"],
            seed=s,
        )
        epochs = extract_epochs(rec)
        models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)

        results = evaluate_session_cv(models, epochs, n_permutations=20, seed=s)
        accs = [m["accuracy"] for m in results["models"].values()]
        mean_acc = float(np.mean(accs))

        assert 0.40 - 1e-4 <= mean_acc <= 0.60 + 1e-4, f"Tohum {s}: Modellerin ortalama doğruluğu (%40-%60) aralığı dışında: {mean_acc:.2%}"

        sel_p = results["permutation_test"]["selection_corrected_p_value"]
        if sel_p < 0.05:
            sig_count += 1

    assert sig_count <= 1, f"5 tohum içinde p < 0.05 olan tohum sayısı > 1: {sig_count}/5"


def test_label_shuffling_drops_to_chance():
    """Gerçek veride etiketler karıştırılınca doğruluk şans seviyesine düşmeli."""
    rec = generate_offline_dataset(
        erd_power_drop=0.4,
        n_runs=4,
        trials_per_run=20,
        classes=["left", "right"],
        seed=42,
    )
    epochs = extract_epochs(rec)

    # Etiketleri karıştır
    rng = np.random.default_rng(999)
    shuffled_labels = rng.permutation(epochs.labels)
    epochs_shuffled = extract_epochs(rec)
    epochs_shuffled.labels = shuffled_labels

    models = build_pipelines(srate=rec.srate, ch_names=rec.ch_names)
    results = evaluate_session_cv(models, epochs_shuffled, n_permutations=0, seed=42)

    for m_name, m_res in results["models"].items():
        acc = m_res["accuracy"]
        assert 0.35 <= acc <= 0.65, f"Karıştırılmış etiketlerde {m_name} şans seviyesine düşmedi: {acc:.2%}"


def test_emg_confound_detection():
    """D2 Testi: 1/4 EMG genliğinde uyarı üretilmeli, erd=0.4 normal senaryoda 5 tohumda uyarı oranı <= 1/5 olmalı."""
    # 1. 1/4 genlikte EMG Confound senaryosu (65.0 / 4 = 16.25 uV)
    rec_emg = generate_offline_dataset(
        erd_power_drop=0.0,
        emg_confound=True,
        emg_amplitude=65.0 / 4.0,
        seed=42,
    )
    ep_emg = extract_epochs(rec_emg)
    p_emg, warn_emg, msg_emg, _ = check_emg_confound(ep_emg, n_permutations=50, seed=42)

    assert warn_emg, f"1/4 genlikli EMG confound senaryosunda uyarı üretilmedi: p={p_emg:.4f}"
    assert p_emg < 0.05
    assert "UYARI" in msg_emg

    # 2. erd=0.4 normal senaryo en az 5 tohumda uyarı oranı <= 1/5 olmalı
    normal_warn_count = 0
    seeds = [42, 101, 202, 303, 404]
    for s in seeds:
        rec_norm = generate_offline_dataset(erd_power_drop=0.4, emg_confound=False, seed=s)
        ep_norm = extract_epochs(rec_norm)
        _, warn_norm, _, _ = check_emg_confound(ep_norm, n_permutations=50, seed=s)
        if warn_norm:
            normal_warn_count += 1

    assert normal_warn_count <= 1, f"Normal senaryoda sahte uyarı oranı > 1/5: {normal_warn_count}/5"

    # 3. raw_data yoksa açık bir hata vermeli
    ep_no_raw = extract_epochs(rec_emg)
    ep_no_raw.raw_data = None
    with pytest.raises(ValueError, match="raw_data"):
        check_emg_confound(ep_no_raw)


def test_fbcsp_subbands_and_prefilter_warning(caplog):
    """D3 Testi: FBCSP alt bantları 8-30 Hz içinde olmalı ve dışındaki bantlar uyarı loglamalı."""
    # 1. Varsayılan bantlar 8-30 Hz arasında olmalı
    for f_low, f_high in FilterBankCSP.DEFAULT_BANDS:
        assert 8.0 <= f_low, f"Alt bant başlangıcı < 8 Hz: {f_low}"
        assert f_high <= 30.0, f"Alt bant bitişi > 30 Hz: {f_high}"

    # 2. Ön filtre dışı bant tanımlandığında uyarı loglanmalı
    fbcsp = FilterBankCSP(bands=[(4.0, 8.0), (8.0, 12.0)], pre_filter_range=(8.0, 30.0))
    dummy_X = np.random.randn(10, 7, 250)
    dummy_y = np.array(["left", "right"] * 5)
    with caplog.at_level("WARNING"):
        fbcsp.fit(dummy_X, dummy_y)
    assert any("ön filtre aralığı" in record.message for record in caplog.records)
