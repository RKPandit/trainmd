"""Calibration sweep for silent.lr_warmup.v1 — find a SPANNING, STABLE ladder.

The current ladder saturates: lr 0.2 and 0.5 both collapse to the majority-class
baseline (~0.756), and lr 0.1 is unstable across seeds. We need three DISTINCT,
STABLE rungs spanning the effect-size range, all above the collapse baseline and
all clearing tolerance by ≥2σ + the ~1e-3 cross-microarch bound on AMD (so the
guard holds on Intel by construction; DECISIONS 2026-09-14 / L18).

For each candidate lr × seed: train via the real train.py, evaluate hidden acc,
report per-seed accs, spread, mean σ-distance from the healthy reference, and
whether the rung clears the 2σ+1e-3 bar on EVERY seed. In-container, thread-pinned.
No paid trial.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
WL = ROOT / "workloads" / "tabular_adult"
sys.path.insert(0, str(ROOT))
from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint  # noqa: E402

LR_GRID = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.20]
SEEDS = [0, 1, 2, 42, 43]

REF = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
H = REF["metric_hidden_test_acc"]
H_MEAN, H_STD, TOL = H["mean"], H["std"], H["tolerance_lower"]
BAR = round(TOL - 2 * H_STD - 1e-3, 6)   # clear 2σ on AMD with +1e-3 so Intel holds
BASELINE = 0.756008                       # majority-class collapse point (avoid)


def _hidden_acc(lr: float, seed: int) -> float:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "workspace"; ws.mkdir()
        for f in ["train.py", "config.yaml", "datautil.py"]:
            shutil.copy2(WL / f, ws / f)
        cfg = yaml.safe_load((ws / "config.yaml").read_text())
        cfg["training"]["lr"] = lr
        (ws / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
        out = ws / "out"
        subprocess.run(
            [sys.executable, str(ws / "train.py"), "--config", str(ws / "config.yaml"),
             "--data-dir", str(WL / ".data"), "--output-dir", str(out), "--seed", str(seed)],
            capture_output=True, text=True, check=False,
        )
        ckpt = out / "checkpoints" / "ckpt_final.pt"
        if not ckpt.exists():
            return float("nan")
        return evaluate_checkpoint(ckpt, WL / ".hidden_data", cfg)["metric_hidden_test_acc"]


def main() -> int:
    print(f"reference: healthy_mean={H_MEAN:.6f} std={H_STD:.6f} tol={TOL:.6f} "
          f"| 2σ+1e-3 bar={BAR:.6f} | collapse baseline≈{BASELINE:.6f}")
    print(f"{'lr':>6} " + " ".join(f"s{sd:<7}" for sd in SEEDS)
          + f"{'min':>9}{'max':>9}{'spread':>9}{'meanσ':>8}{'clears2σ+':>10}{'collapsed?':>11}")
    for lr in LR_GRID:
        accs = [_hidden_acc(lr, sd) for sd in SEEDS]
        mn, mx = min(accs), max(accs)
        spread = mx - mn
        mean_sigma = (H_MEAN - float(np.mean(accs))) / H_STD
        clears = all(a <= BAR for a in accs)
        collapsed = all(abs(a - BASELINE) < 1e-4 for a in accs)
        print(f"{lr:>6.2f} " + " ".join(f"{a:<8.5f}" for a in accs)
              + f"{mn:>9.5f}{mx:>9.5f}{spread:>9.5f}{mean_sigma:>8.2f}"
              + f"{str(clears):>10}{str(collapsed):>11}")
    print()
    print("Pick 3 rungs: DISTINCT, low spread, monotone (mild>mod>sev acc), all clears2σ+=True,")
    print("all collapsed?=False, mild NEAR the bar (weakest valid case). Report σ per rung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
