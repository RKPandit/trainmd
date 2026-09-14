"""Measure the diagnostically-sharp metric_window per operator (evidence v2).

For each operator that cites a metric_window, the anomaly's "sharp" window is the
contiguous set of epochs where the faulty reported metric_visible_val_acc is
clearly OUTSIDE the healthy band the agent actually sees (the card's
reference_visible_metric mean ± 2σ) on EVERY measured seed. This is the
"measure, don't assume" basis for the alternative metric_window GT (full-run +
sharp). Positive-symptom operators exit ABOVE the band; negative-symptom BELOW.

In-container, thread-pinned. No paid trial.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
WL = ROOT / "workloads" / "tabular_adult"
sys.path.insert(0, str(ROOT))
from operators.registry import get_operator  # noqa: E402
from random import Random  # noqa: E402

OPERATORS = [
    "silent.lr_warmup.v1",
    "silent.label_corruption.v1",
    "silent.data_leakage.v1",
    "silent.metric_inflation.v1",
]
STRENGTH = "moderate"
SEEDS = [0, 1, 2]

REF = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
V = REF["metric_visible_val_acc"]
LO, HI = V["mean"] - 2 * V["std"], V["mean"] + 2 * V["std"]


def _per_epoch_val_acc(workspace: Path, cfg_path: Path, seed: int) -> list[float]:
    out = workspace / f"out_{seed}"
    subprocess.run(
        [sys.executable, str(workspace / "train.py"), "--config", str(cfg_path),
         "--data-dir", str(WL / ".data"), "--output-dir", str(out), "--seed", str(seed)],
        capture_output=True, text=True, check=False,
    )
    accs = []
    for line in (out / "metrics.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("end_of_epoch"):
            accs.append(r["metric_visible_val_acc"])
    return accs


def main() -> int:
    print(f"healthy band [{LO:.6f}, {HI:.6f}] (visible mean {V['mean']:.6f} ± 2σ)")
    print()
    for op_id in OPERATORS:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            ws.mkdir()
            for f in ["train.py", "config.yaml", "datautil.py"]:
                shutil.copy2(WL / f, ws / f)
            get_operator(op_id).apply(ws, Random(0), STRENGTH)
            cfg_path = ws / "config.yaml"
            curves = [_per_epoch_val_acc(ws, cfg_path, s) for s in SEEDS]
        n_ep = min(len(c) for c in curves)
        # per epoch: outside the band (same side) on ALL seeds?
        outside = []
        for e in range(n_ep):
            vals = [c[e] for c in curves]
            if all(v > HI for v in vals):
                outside.append((e, "above"))
            elif all(v < LO for v in vals):
                outside.append((e, "below"))
        eps = [e for e, _ in outside]
        side = outside[0][1] if outside else "n/a"
        print(f"=== {op_id} (moderate) — direction: {side} ===")
        print("  per-epoch min val_acc across seeds:",
              " ".join(f"{min(c[e] for c in curves):.3f}" for e in range(n_ep)))
        if eps:
            print(f"  SHARP window (outside band all seeds): epochs [{min(eps)}, {max(eps)}] "
                  f"({len(eps)} epochs; contiguous={eps == list(range(min(eps), max(eps)+1))})")
        else:
            print("  SHARP window: NONE (never clearly outside band on all seeds)")
        print(f"  full-run window: [0, {n_ep-1}]")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
