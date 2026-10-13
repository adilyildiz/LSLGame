"""Denetim ölçümü: sinyalsiz (erd=0) ve sinyalli (erd=0.4) sentetik veride model doğrulukları.

Beklenen (Görev 07 sonrası):
- erd=0, 2 sınıf: tüm modeller ~%40-60, permütasyon p < 0.05 olan tohum sayısı <= 1/6.
- erd=0.4: en az bir model belirgin şekilde şansın üstünde.

Çalıştırma: .venv\\Scripts\\python tools\\audit\\olcum_sinyalsiz_veri.py
"""
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.evaluation import evaluate_session_cv
from src.models.pipelines import build_pipelines
from src.processing.artifacts import reject_artifacts
from src.processing.epochs import extract_epochs
from src.simulation.offline_dataset import generate_offline_dataset

t0 = time.time()
for erd in (0.0, 0.4):
    accs, pvals = {}, []
    for seed in range(201, 207):
        rec = generate_offline_dataset(erd_power_drop=erd, n_runs=4, seed=seed, classes=["left", "right"])
        ep, _ = reject_artifacts(extract_epochs(rec, tmin=0.5, tmax=3.5, filter_mode="causal"))
        res = evaluate_session_cv(build_pipelines(srate=ep.srate), ep, n_permutations=40 if erd == 0 else 0, seed=seed)
        for m, r in res["models"].items():
            accs.setdefault(m, []).append(r["accuracy"])
        if "permutation_test" in res:
            pvals.append(res["permutation_test"]["p_value"])
    line = " | ".join(f"{m} {np.mean(v) * 100:.0f}%" for m, v in accs.items())
    print(f"[erd={erd}, 2 sinif, 6 tohum] {line} | perm p: {np.round(pvals, 3).tolist()}")
print(f"[sure] {time.time() - t0:.0f} sn")
