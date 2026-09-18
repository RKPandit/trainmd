"""Per-seed margin table for ALL positive-symptom rungs, under the current band.

Prints, for data_leakage {mild,moderate,severe} and metric_inflation
{mild,moderate,severe}, each rung's per-seed clearance on both halves of its tier
contract against the structural bars (operators/margins.py):
  - symptom half (both operators):  visible >= mean_v + 4σ_v + 1e-3
  - degradation half (silent tier): hidden  <= tol - 2σ_h - 1e-3
  - healthy half (metric tier):     hidden within the ±2σ band (informational)

Run natively (amd64) in the canonical container as a CI step so the record carries
measured clearances for every rung — not just the ones that were recalibrated:
    python scripts/margin_report.py
Exit non-zero if any rung fails its contract halves (the CI step then fails loudly).
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

from operators.silent.data_leakage import DataLeakageOperator  # noqa: E402
from operators.metric.metric_inflation import MetricInflationOperator  # noqa: E402
from operators.margins import positive_symptom_bar, degradation_bar  # noqa: E402
from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint  # noqa: E402

from operators.silent.data_leakage_neutral import DataLeakageNeutralOperator  # noqa: E402

WL_NEUTRAL = ROOT / "workloads" / "tabular_adult_neutral"

SEEDS = [0, 1, 2]
STRENGTHS = ["mild", "moderate", "severe"]
# (label, operator, tier, workload_dir) — tier decides the second half:
# silent=degradation, metric=healthy. The neutral variant runs on its own family.
RUNGS = [
    ("data_leakage", DataLeakageOperator, "silent", WL),
    ("data_leakage_neutral", DataLeakageNeutralOperator, "silent", WL_NEUTRAL),
    ("metric_inflation", MetricInflationOperator, "metric", WL),
]


def _train(ws: Path, cfg: dict, seed: int, out: Path, data_dir: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cp = out / "config.yaml"
    cp.write_text(yaml.dump(cfg))
    r = subprocess.run(
        [sys.executable, str(ws / "train.py"), "--config", str(cp),
         "--data-dir", str(data_dir), "--output-dir", str(out), "--seed", str(seed)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"train.py failed ({ws}, seed={seed}):\n{r.stderr[-800:]}")


def _visible(out: Path) -> float:
    lines = [json.loads(l) for l in (out / "metrics.jsonl").read_text().splitlines() if l.strip()]
    return [l for l in lines if l.get("end_of_epoch")][-1]["metric_visible_val_acc"]


def main() -> int:
    stats = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
    sym_bar = positive_symptom_bar(stats)
    deg_bar = degradation_bar(stats)
    h = stats["metric_hidden_test_acc"]
    h_lo, h_hi = h["mean"] - 2 * h["std"], h["mean"] + 2 * h["std"]

    print("=== POSITIVE-SYMPTOM RUNG MARGIN TABLE (current band) ===")
    print(f"symptom_bar (mean+4σ+1e-3) = {sym_bar:.6f}   [visible must be >=]")
    print(f"degradation_bar (tol-2σ-1e-3) = {deg_bar:.6f}   [silent hidden must be <=]")
    print(f"healthy band [{h_lo:.6f}, {h_hi:.6f}]   [metric hidden must be within]")
    print()
    hdr = (f"{'rung':>28} | {'vis s0':>8} {'vis s1':>8} {'vis s2':>8} {'symMargin':>10} {'symOK':>6} "
           f"| {'2nd s0':>8} {'2nd s1':>8} {'2nd s2':>8} {'2ndOK':>6}")
    print(hdr)
    print("-" * len(hdr))
    all_ok = True
    for opname, opcls, tier, wl_dir in RUNGS:
        for strength in STRENGTHS:
            vis, sec = {}, {}
            for seed in SEEDS:
                base = Path(tempfile.mkdtemp())
                ws = base / "ws"; ws.mkdir(parents=True)
                for f in ("train.py", "config.yaml", "datautil.py"):
                    shutil.copy2(wl_dir / f, ws / f)
                opcls().apply(ws, Random(seed), strength)
                cfg = yaml.safe_load((ws / "config.yaml").read_text())
                out = base / "out"
                _train(ws, cfg, seed, out, wl_dir / ".data")
                vis[seed] = _visible(out)
                sec[seed] = evaluate_checkpoint(
                    out / "checkpoints" / "ckpt_final.pt", wl_dir / ".hidden_data", cfg
                )["metric_hidden_test_acc"]
                shutil.rmtree(base, ignore_errors=True)
            sym_ok = all(vis[s] >= sym_bar for s in SEEDS)
            sym_margin = min(vis[s] for s in SEEDS) - sym_bar
            if tier == "silent":
                second_ok = all(sec[s] <= deg_bar for s in SEEDS)
            else:  # metric: model healthy => hidden within band
                second_ok = all(h_lo <= sec[s] <= h_hi for s in SEEDS)
            all_ok = all_ok and sym_ok and second_ok
            print(f"{opname+'/'+strength:>28} | {vis[0]:>8.5f} {vis[1]:>8.5f} {vis[2]:>8.5f} "
                  f"{sym_margin:>+10.5f} {str(sym_ok):>6} | {sec[0]:>8.5f} {sec[1]:>8.5f} "
                  f"{sec[2]:>8.5f} {str(second_ok):>6}")
    print()
    print("ALL RUNGS CLEAR BOTH HALVES:", all_ok)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
