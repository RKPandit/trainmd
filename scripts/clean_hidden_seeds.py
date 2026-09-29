#!/usr/bin/env python3
"""The CLEAN config's result on the hidden-eval seeds (100–102) against the workload's recovery tolerance —
the margin a correct repair has at best (author's request 2026-09-28, before any image case exists).

Runs `harness.evaluator.verify_repair.run_hidden_seeds` — the ONE training path recovery verification uses — on the
workload's clean config, and reports each seed's hidden metric minus `tolerance_lower` and the 3-seed mean (the
pre-registered mean-of-3 recovery rule). Native amd64 only (the numbers are platform-sensitive).

    python scripts/clean_hidden_seeds.py --workload image_fmnist [--out result.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workload", required=True)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    from harness.evaluator.verify_repair import run_hidden_seeds
    from harness.platform_guard import cpu_provenance, require_native_amd64
    from harness.seed_sets import HIDDEN_EVAL
    require_native_amd64(context="measure the clean hidden-seed margin")
    wd = ROOT / "workloads" / a.workload
    cfg = yaml.safe_load((wd / "config.yaml").read_text())
    tol = yaml.safe_load((wd / "reference" / "stats.yaml").read_text())["metric_hidden_test_acc"]["tolerance_lower"]
    res = run_hidden_seeds(cfg, wd, sorted(HIDDEN_EVAL))
    bad = [r for r in res if r["exitcode"] != 0 or r["metric_hidden_test_acc"] is None]
    if bad:
        print(json.dumps(bad, indent=2))
        return 1
    rows = [{"seed": r["seed"], "hidden": r["metric_hidden_test_acc"],
             "margin": round(r["metric_hidden_test_acc"] - tol, 6)} for r in res]
    mean = sum(r["hidden"] for r in rows) / len(rows)
    out = {"workload": a.workload, "cpu": cpu_provenance(), "tolerance_lower": tol, "per_seed": rows,
           "mean_hidden": round(mean, 6), "mean_margin": round(mean - tol, 6),
           "seeds_below_tolerance": [r["seed"] for r in rows if r["margin"] < 0]}
    print(f"{a.workload}  CPU {out['cpu']}  tolerance_lower {tol}")
    for r in rows:
        print(f"  seed {r['seed']}: hidden {r['hidden']:.6f}  margin {r['margin']:+.6f}")
    print(f"  3-seed mean {out['mean_hidden']:.6f}  margin {out['mean_margin']:+.6f}  "
          f"seeds below tolerance: {out['seeds_below_tolerance'] or 'none'}")
    if a.out:
        a.out.write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
