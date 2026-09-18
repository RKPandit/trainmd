"""Calibration sweep for silent.data_leakage.v1 — pick mild's p under the margin rule.

The mutated feature is aux = |label - Bernoulli(p)|, so correlation = 1 - 2p:
LOWER p = STRONGER leak = higher visible inflation AND deeper hidden degradation.

mild must clear BOTH halves of the silent-tier contract with >= 2σ + 1e-3 margin
on EVERY calibration seed, against the band it is judged by (operators/margins.py):
  - symptom half:      visible val_acc >= mean_v + 4σ_v + 1e-3   (positive_symptom_bar)
  - degradation half:  hidden  acc     <= tol   - 2σ_h - 1e-3    (degradation_bar)
Pick the LARGEST p (weakest leak) that clears both on all seeds, keeping the ladder
monotone (p_mild > p_moderate). Each p is a full retrain (the leak changes the data),
so this trains once per (p, seed). In-container, thread-pinned. No paid trial.

Run (native amd64, in the canonical container):
    python scripts/calibrate_data_leakage.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from random import Random

import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
sys.path.insert(0, str(ROOT))
WL = ROOT / "workloads" / "tabular_adult"

from operators.silent.data_leakage import DataLeakageOperator, _STRENGTH_P  # noqa: E402
from operators.margins import positive_symptom_bar, degradation_bar  # noqa: E402
from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint  # noqa: E402

SEEDS = [0, 1, 2]
# Descending p (weakest leak first); the first that clears both halves on all seeds
# is the pick (largest p = mildest). Stops above moderate's p to keep monotonicity.
P_GRID = [0.30, 0.28, 0.26, 0.25, 0.24, 0.22, 0.21]


def _train(workspace: Path, config: dict, seed: int, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cfg_path = out / "config.yaml"
    cfg_path.write_text(yaml.dump(config))
    r = subprocess.run(
        [sys.executable, str(workspace / "train.py"),
         "--config", str(cfg_path), "--data-dir", str(WL / ".data"),
         "--output-dir", str(out), "--seed", str(seed)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"train.py failed (seed={seed}):\n{r.stderr[-800:]}")


def _visible(out: Path) -> float:
    lines = [json.loads(l) for l in (out / "metrics.jsonl").read_text().splitlines() if l.strip()]
    return [l for l in lines if l.get("end_of_epoch")][-1]["metric_visible_val_acc"]


def main() -> int:
    stats = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
    sym_bar = positive_symptom_bar(stats)
    deg_bar = degradation_bar(stats)
    moderate_p = _STRENGTH_P["moderate"]
    print(f"band: seeds {sorted(SEEDS)} | symptom_bar(mean+4σ+1e-3)={sym_bar:.6f} "
          f"| degradation_bar(tol-2σ-1e-3)={deg_bar:.6f} | moderate p={moderate_p}")
    print(f"{'p':>6} {'corr':>5} | {'vis s0':>8} {'vis s1':>8} {'vis s2':>8} {'visMin':>8} {'symOK':>6} "
          f"| {'hid s0':>8} {'hid s1':>8} {'hid s2':>8} {'hidMax':>8} {'degOK':>6} | {'clears':>7}")
    pick = None
    for p in P_GRID:
        if p <= moderate_p:
            print(f"{p:>6.2f}  (<= moderate p={moderate_p}; skip to keep ladder monotone)")
            continue
        vis, hid = {}, {}
        for seed in SEEDS:
            base = Path(tempfile.mkdtemp())
            ws = base / "ws"; ws.mkdir(parents=True)
            for f in ("train.py", "config.yaml", "datautil.py"):
                shutil.copy2(WL / f, ws / f)
            _STRENGTH_P["mild"] = p
            DataLeakageOperator().apply(ws, Random(seed), "mild")
            cfg = yaml.safe_load((ws / "config.yaml").read_text())
            out = base / "out"
            _train(ws, cfg, seed, out)
            vis[seed] = _visible(out)
            hid[seed] = evaluate_checkpoint(
                out / "checkpoints" / "ckpt_final.pt", WL / ".hidden_data", cfg
            )["metric_hidden_test_acc"]
            shutil.rmtree(base, ignore_errors=True)
        vmin = min(vis[s] for s in SEEDS)
        hmax = max(hid[s] for s in SEEDS)
        sym_ok = all(vis[s] >= sym_bar for s in SEEDS)
        deg_ok = all(hid[s] <= deg_bar for s in SEEDS)
        clears = sym_ok and deg_ok
        print(f"{p:>6.2f} {1-2*p:>5.2f} | {vis[0]:>8.5f} {vis[1]:>8.5f} {vis[2]:>8.5f} "
              f"{vmin:>8.5f} {str(sym_ok):>6} | {hid[0]:>8.5f} {hid[1]:>8.5f} {hid[2]:>8.5f} "
              f"{hmax:>8.5f} {str(deg_ok):>6} | {str(clears):>7}")
        if clears and pick is None:
            pick = p  # first (largest) p that clears both halves
    print()
    if pick is None:
        print("SELECT: no p in the grid clears both halves above moderate — LADDER SQUEEZE. "
              "Report before setting; do not compress the ladder silently.")
        return 1
    print(f"SELECT: mild p = {pick}  (largest p clearing both halves with >= 2σ+1e-3 on all seeds). "
          f"Set _STRENGTH_P['mild'] = {pick} if it differs from the committed value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
