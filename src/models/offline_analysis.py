"""Çevrimdışı Analiz, Model Seçimi ve Raporlama Komut Satırı Aracı.

PLAN.md Faz 4 (4.1-4.5), Faz 5.1 ve agy_tasks/06_faz4_offline_analiz.md uyarınca:
Kullanım:
python -m src.models.offline_analysis --xdf data/sub-01/ses-*/...xdf [...] --out results/sub-01 [--models M1,M2,M3,M4,M5] [--synthetic --erd 0.4 --runs 4 --profile mi2 --seed 1]

Çıktılar:
- out/erd_c3_cz_c4.png
- out/r2_map.png
- out/time_resolved_accuracy.png
- out/confusion_matrices.png
- out/results.json
- out/report.md
- models/<subject>/<tarih>_<model>.joblib ve _meta.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence

import joblib
import numpy as np

from src.models.evaluation import (
    compute_time_resolved_accuracy,
    evaluate_class_selection,
    evaluate_session_cv,
    plot_confusion_matrices,
    plot_time_resolved_accuracy,
)
from src.models.pipelines import build_pipelines
from src.processing.artifacts import reject_artifacts
from src.processing.epochs import extract_epochs
from src.processing.erd_analysis import (
    check_emg_confound,
    compute_erd_time_frequency,
    compute_r2_map,
    plot_erd_time_frequency,
    plot_r2_map,
)
from src.processing.recording import Recording, load_xdf
from src.simulation.offline_dataset import generate_offline_dataset

logger = logging.getLogger(__name__)


def generate_markdown_report(
    results_dict: Dict[str, Any],
    subject: str,
    output_path: Path,
) -> str:
    """İnsan tarafından okunabilir kapsamlı Markdown analiz raporu üretir."""
    models_res = results_dict.get("models", {})
    best_model = results_dict.get("best_model", "N/A")
    best_acc = results_dict.get("best_accuracy", 0.0)
    perm_test = results_dict.get("permutation_test", {})
    emg_res = results_dict.get("emg_check", {})
    art_res = results_dict.get("artifacts", {}).get("summary", {})
    class_sel = results_dict.get("class_selection", {})
    saved_meta = results_dict.get("saved_model_meta", {})

    lines: List[str] = [
        f"# BCI Çevrimdışı Analiz ve Model Seçimi Raporu",
        f"",
        f"- **Katılımcı / Denek:** `{subject}`",
        f"- **Analiz Tarihi:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Veri Kaynağı:** {results_dict.get('data_source', 'Sentetik')}",
        f"- **Sınıflar:** `{', '.join(results_dict.get('classes', []))}`",
        f"- **Toplam Epok Sayısı:** {art_res.get('total_epochs', results_dict.get('n_epochs', 0))}",
        f"",
        f"---",
        f"",
        f"## 1. Model Karşılaştırma Tablosu (Run-Bloklu CV)",
        f"",
        f"| Model | Açıklama | Doğruluk (Mean ± Std) | Dengeli Doğruluk | Cohen's κ | ITR (bit/dk) |",
        f"|---|---|---|---|---|---|",
    ]

    model_descriptions = {
        "M1": "Log-Bant Gücü (C3, Cz, C4; μ, β) + LDA",
        "M2": "CSP (8-30 Hz) + LDA",
        "M3": "FBCSP + MI Öznitelik Seçimi + LDA",
        "M4": "Riemann: Kovaryans → Tanjant Uzayı + Lojistik Regresyon",
        "M5": "Riemann MDM",
    }

    for name, r in models_res.items():
        desc = model_descriptions.get(name, "Standart Model")
        acc = r["accuracy"]
        acc_std = r.get("accuracy_std", 0.0)
        bal_acc = r["balanced_accuracy"]
        kappa = r["cohen_kappa"]
        itr = r["itr_bpm"]
        is_best = " ⭐ (En İyi)" if name == best_model else ""
        lines.append(
            f"| **{name}**{is_best} | {desc} | %{acc*100:.1f} ± %{acc_std*100:.1f} | %{bal_acc*100:.1f} | {kappa:.3f} | {itr:.2f} |"
        )

    lines.extend([
        f"",
        f"> **En İyi Model:** `{best_model}` (Doğruluk: **%{best_acc*100:.1f}**)",
        f"",
        f"---",
        f"",
        f"## 2. Şans Seviyesi ve İstatistiki Anlamlılık",
        f"",
        f"- **Teorik Şans Seviyesi:** %{results_dict.get('chance_level_theory', 0.5)*100:.1f}",
        f"- **Ampirik %95 Şans Eşiği (Permütasyon):** %{perm_test.get('chance_level_95', 0.5)*100:.1f}",
        f"- **Permütasyon Testi p-değeri:** `{perm_test.get('p_value', 1.0):.4f}` "
        f"({'✅ İstatistiksel olarak anlamlı (p < 0.05)' if perm_test.get('p_value', 1.0) < 0.05 else '❌ Anlamlı değil (şans seviyesinde)'})",
        f"",
        f"---",
        f"",
        f"## 3. Nörofizyolojik Doğrulama ve EMG Kontrolü",
        f"",
    ])

    if emg_res.get("has_warning", False):
        lines.extend([
            f"> [!WARNING]",
            f"> **KAS ARTEFAKTI (EMG) UYARISI:**",
            f"> {emg_res.get('warning_msg', '30-45 Hz bandında anlamlı fark var.')}",
            f"> Modelin başarısı beyin ritimlerinden değil, kas kasılmasından kaynaklanıyor olabilir!",
            f"",
        ])
    else:
        lines.extend([
            f"> [!NOTE]",
            f"> **EMG Kontrolü Başarılı:** {emg_res.get('warning_msg', '30-45 Hz bandında kas ayrışması tespit edilmedi.')}",
            f"",
        ])

    lines.extend([
        f"- **ERD/ERS Zaman-Frekans Haritası:** `erd_c3_cz_c4.png`",
        f"- **Kanal × Frekans r² Ayırt Edicilik Haritası:** `r2_map.png`",
        f"",
        f"---",
        f"",
        f"## 4. Artefakt Reddi İstatistikleri",
        f"",
        f"- **Reddedilen Epok Oranı:** %{art_res.get('rejection_ratio', 0.0)*100:.1f} ({art_res.get('rejected_epochs', 0)} / {art_res.get('total_epochs', 0)})",
        f"- **Temiz Kalan Epok Sayısı:** {art_res.get('clean_epochs', 0)}",
        f"- **Reddetme Nedenleri Dağılımı:**",
    ])

    for reason, cnt in art_res.get("reasons_breakdown", {}).items():
        lines.append(f"  - `{reason}`: {cnt} adet")

    if class_sel and class_sel.get("recommendation") != "N/A":
        lines.extend([
            f"",
            f"---",
            f"",
            f"## 5. Sınıf Seçimi Önerisi (PLAN 4.5)",
            f"",
            f"- **'Yukarı' Sınıfı Değerlendirmesi:**",
            f"  {class_sel.get('recommendation', '')}",
        ])

    if saved_meta:
        lines.extend([
            f"",
            f"---",
            f"",
            f"## 6. Kaydedilen Model ve Meta Veri",
            f"",
            f"- **Model Dosyası:** `{saved_meta.get('model_file', '')}`",
            f"- **Meta Veri:** `{saved_meta.get('meta_file', '')}`",
            f"- **Filtre Modu:** `{saved_meta.get('filter_mode', 'causal')}`",
            f"- **Pencere Aralığı:** `{saved_meta.get('window_sec', 3.0)} sn`",
        ])

    report_content = "\n".join(lines)
    output_path.write_text(report_content, encoding="utf-8")
    return report_content


def run_offline_analysis(
    xdf_paths: Optional[Sequence[Union[str, Path]]] = None,
    out_dir: Union[str, Path] = "results/sub-01",
    models: Optional[Sequence[str]] = None,
    synthetic: bool = False,
    erd: float = 0.4,
    runs: int = 4,
    trials_per_run: int = 20,
    profile: str = "mi2",
    classes: Optional[Sequence[str]] = None,
    seed: int = 42,
    emg_confound: bool = False,
    subject: str = "sub-01",
    filter_mode: str = "causal",
    n_permutations: int = 100,
    save_model_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Çevrimdışı analiz hattını uçtan uca yürütür."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Veri yükleme veya sentetik üretim
    if synthetic or not xdf_paths:
        logger.info("Sentetik kalibrasyon verisi üretiliyor...")
        recording = generate_offline_dataset(
            erd_power_drop=erd,
            n_runs=runs,
            trials_per_run=trials_per_run,
            profile=profile,
            classes=classes,
            seed=seed,
            emg_confound=emg_confound,
        )
        data_source_desc = f"Sentetik (erd={erd}, runs={runs}, profile={profile}, seed={seed})"
    else:
        logger.info(f"XDF dosyası yükleniyor: {xdf_paths[0]}")
        recording = load_xdf(xdf_paths[0])
        data_source_desc = str(xdf_paths[0])
        if "subject" in recording.meta and recording.meta["subject"] != "unknown":
            subject = recording.meta["subject"]

    # 2. Epoklama
    logger.info("İmgeleme epokları çıkarılıyor...")
    epochs_raw = extract_epochs(
        recording=recording,
        tmin=0.5,
        tmax=3.5,
        filter_mode=filter_mode,
        f_low=8.0,
        f_high=30.0,
    )

    # 3. Artefakt tespiti ve reddi
    logger.info("Artefakt kontrolü yapılıyor...")
    clean_epochs, art_report = reject_artifacts(epochs_raw)
    if len(clean_epochs) < 10:
        logger.warning("Artefakt reddi sonrası çok az epok kaldı, tüm epoklar kullanılıyor.")
        clean_epochs = epochs_raw

    # 4. Nörofizyolojik doğrulama
    logger.info("Nörofizyolojik doğrulama (ERD ve r²) yapılıyor...")
    erd_data = compute_erd_time_frequency(clean_epochs)
    plot_erd_time_frequency(erd_data, out_path / "erd_c3_cz_c4.png")

    r2_mat, freqs, ch_names = compute_r2_map(clean_epochs)
    plot_r2_map(r2_mat, freqs, ch_names, out_path / "r2_map.png")
    np.save(out_path / "r2_matrix.npy", r2_mat)

    # EMG Kontrolü
    logger.info("EMG kontrolü yapılıyor...")
    emg_p, emg_warn, emg_msg, emg_details = check_emg_confound(
        clean_epochs,
        n_permutations=min(200, n_permutations),
        seed=seed,
    )

    # 5. Model oluşturma ve değerlendirme
    selected_models = list(models) if models else ["M1", "M2", "M3", "M4", "M5"]
    pipelines = build_pipelines(
        srate=clean_epochs.srate,
        ch_names=clean_epochs.ch_names,
        model_names=selected_models,
    )

    logger.info(f"Modeller değerlendiriliyor: {list(pipelines.keys())}")
    eval_results = evaluate_session_cv(
        pipelines=pipelines,
        epochs=clean_epochs,
        n_permutations=n_permutations,
        seed=seed,
    )

    # Zaman çözünürlüklü doğruluk
    logger.info("Zaman çözünürlüklü doğruluk profili çıkarılıyor...")
    best_model_name = eval_results.get("best_model", "M1")
    time_results = {}
    if best_model_name in pipelines:
        t_centers, t_accs = compute_time_resolved_accuracy(pipelines[best_model_name], clean_epochs)
        time_results[best_model_name] = (t_centers, t_accs)
        plot_time_resolved_accuracy(
            time_results,
            chance_level=eval_results["chance_level_theory"],
            output_png=out_path / "time_resolved_accuracy.png",
        )

    # Karışıklık matrisleri grafiği
    cm_dict = {m: res["confusion_matrix"] for m, res in eval_results["models"].items()}
    plot_confusion_matrices(cm_dict, eval_results["classes"], out_path / "confusion_matrices.png")

    # Sınıf seçimi değerlendirmesi
    class_sel_results = {}
    if len(eval_results["classes"]) > 2:
        logger.info("Sınıf seçimi analizi yapılıyor...")
        class_sel_results = evaluate_class_selection(pipelines[best_model_name], clean_epochs)

    # 6. En iyi modeli eğit ve kaydet
    if save_model_dir is None:
        save_model_path = Path("models") / subject
    else:
        save_model_path = Path(save_model_dir)
    save_model_path.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_filename = f"{timestamp_str}_{best_model_name}.joblib"
    meta_filename = f"{timestamp_str}_{best_model_name}_meta.json"

    # En iyi modeli tüm temiz veri üzerinde fit et
    final_model = pipelines[best_model_name]
    final_model.fit(clean_epochs.data, clean_epochs.labels)
    joblib.dump(final_model, save_model_path / model_filename)

    model_metadata = {
        "model_name": best_model_name,
        "model_file": str(save_model_path / model_filename),
        "meta_file": str(save_model_path / meta_filename),
        "subject": subject,
        "training_date": datetime.now().isoformat(),
        "cv_accuracy": eval_results["best_accuracy"],
        "classes": eval_results["classes"],
        "channel_names": clean_epochs.ch_names,
        "srate": clean_epochs.srate,
        "filter_mode": filter_mode,
        "bandpass_hz": [8.0, 30.0],
        "notch_hz": [50.0, 100.0],
        "filter_order": 4,
        "window_tmin": 0.5,
        "window_tmax": 3.5,
        "window_sec": 3.0,
        "spatial_filter": "csp" if "CSP" in best_model_name else "none",
        "data_sources": [data_source_desc],
    }

    with open(save_model_path / meta_filename, "w", encoding="utf-8") as f:
        json.dump(model_metadata, f, indent=2, ensure_ascii=False)

    # 7. Sonuç JSON ve Raporu Yaz
    full_results: Dict[str, Any] = {
        "subject": subject,
        "data_source": data_source_desc,
        "classes": eval_results["classes"],
        "n_epochs": len(clean_epochs),
        "chance_level_theory": eval_results["chance_level_theory"],
        "best_model": best_model_name,
        "best_accuracy": eval_results["best_accuracy"],
        "models": eval_results["models"],
        "permutation_test": eval_results.get("permutation_test", {}),
        "emg_check": {
            "p_value": emg_p,
            "has_warning": emg_warn,
            "warning_msg": emg_msg,
            "details": emg_details,
        },
        "artifacts": art_report,
        "class_selection": class_sel_results,
        "saved_model_meta": model_metadata,
    }

    with open(out_path / "results.json", "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2, ensure_ascii=False)

    generate_markdown_report(full_results, subject, out_path / "report.md")
    logger.info(f"Analiz tamamlandı. Rapor: {out_path / 'report.md'}")

    return full_results


def main() -> None:
    parser = argparse.ArgumentParser(description="BCI Çevrimdışı Analiz ve Model Seçimi")
    parser.add_argument("--xdf", nargs="*", help="Analiz edilecek XDF dosya yolları")
    parser.add_argument("--out", default="results/sub-01", help="Çıktı klasörü")
    parser.add_argument("--models", help="Virgülle ayrılmış model listesi (M1,M2,M3,M4,M5)")
    parser.add_argument("--synthetic", action="store_true", help="Sentetik veri üretecini kullan")
    parser.add_argument("--erd", type=float, default=0.4, help="Sentetik ERD güç düşüş oranı")
    parser.add_argument("--runs", type=int, default=4, help="Run sayısı")
    parser.add_argument("--profile", default="mi2", help="Kalibrasyon profili (mi2, mi3, mi5)")
    parser.add_argument("--seed", type=int, default=42, help="Rastgele tohum")
    parser.add_argument("--emg-confound", action="store_true", help="EMG karıştırıcı senaryosu")
    parser.add_argument("--subject", default="sub-01", help="Katılımcı / Denek ID")
    parser.add_argument("--filter-mode", default="causal", choices=["causal", "zero_phase"])
    parser.add_argument("--n-permutations", type=int, default=100, help="Permütasyon sayısı")
    parser.add_argument("--save-model-dir", help="Model kayıt klasörü")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    model_list = [m.strip() for m in args.models.split(",")] if args.models else None

    run_offline_analysis(
        xdf_paths=args.xdf,
        out_dir=args.out,
        models=model_list,
        synthetic=args.synthetic,
        erd=args.erd,
        runs=args.runs,
        profile=args.profile,
        seed=args.seed,
        emg_confound=args.emg_confound,
        subject=args.subject,
        filter_mode=args.filter_mode,
        n_permutations=args.n_permutations,
        save_model_dir=args.save_model_dir,
    )


if __name__ == "__main__":
    main()
