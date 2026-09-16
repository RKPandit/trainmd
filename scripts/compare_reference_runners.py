#!/usr/bin/env python3
"""Two-runner reproducibility gate for the 30-seed reference (STAGE3_PLAN §0.5).

Compares two independent CI runners' `stats.yaml`, reporting each runner's CPU model and the max
per-field delta over the DETERMINISTIC metric fields (visible/hidden mean, std, min, max,
tolerance_lower, and per-seed val/test acc) — timing fields (`wall_time_sec`, `peak_memory_mb`) are
excluded because they legitimately vary run-to-run.

Microarch-aware verdict (per DECISIONS 2026-09-14 / L18):
  * SAME CPU model  -> byte-exact required: ANY nonzero metric delta is a real bug -> STOP (exit 1).
  * DIFFERENT CPU   -> tolerance-based (means >2e-3, tolerance_lower >6e-3 = STOP), via
                       scripts/verify_reference.py.
Always prints the max per-field delta so the empirical cross-microarch distribution accumulates.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Timing/resource fields legitimately vary run-to-run; only deterministic METRIC fields are compared.
_EXCLUDE_KEYS = {"wall_time_sec", "peak_memory_mb", "epoch_time_sec"}


def _flatten_metrics(obj, prefix="") -> dict[str, float]:
    """Flatten numeric METRIC fields (timing excluded) to dotted paths."""
    out: dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _EXCLUDE_KEYS:
                continue
            out.update(_flatten_metrics(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten_metrics(v, f"{prefix}{i}."))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        key = prefix.rstrip(".")
        if not any(seg in _EXCLUDE_KEYS for seg in key.split(".")):
            out[key] = float(obj)
    return out


def compare(stats1: dict, stats2: dict) -> tuple[float, str, int]:
    """Return (max_abs_delta, field, n_compared) over shared metric fields."""
    a, b = _flatten_metrics(stats1), _flatten_metrics(stats2)
    shared = a.keys() & b.keys()
    max_d, max_f = 0.0, ""
    for k in shared:
        d = abs(a[k] - b[k])
        if d > max_d:
            max_d, max_f = d, k
    return max_d, max_f, len(shared)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats1", type=Path, required=True)
    ap.add_argument("--stats2", type=Path, required=True)
    ap.add_argument("--cpu1", default="", help="runner 1 CPU model string")
    ap.add_argument("--cpu2", default="", help="runner 2 CPU model string")
    a = ap.parse_args()

    s1 = yaml.safe_load(a.stats1.read_text())
    s2 = yaml.safe_load(a.stats2.read_text())
    max_d, field, n = compare(s1, s2)
    same_cpu = a.cpu1.strip() and (a.cpu1.strip() == a.cpu2.strip())

    print(f"runner-1 CPU: {a.cpu1.strip() or '(unknown)'}")
    print(f"runner-2 CPU: {a.cpu2.strip() or '(unknown)'}")
    print(f"metric fields compared: {n}")
    print(f"MAX per-field metric delta: {max_d:.3e} at '{field}'")

    if same_cpu:
        print("microarch: SAME -> byte-exact required (any nonzero metric delta is a real bug).")
        if max_d > 0:
            print(f"STOP: two same-microarch runners disagree by {max_d:.3e} at '{field}' — "
                  "a real reproducibility bug, not microarch noise.", file=sys.stderr)
            return 1
        print("VERDICT: byte-exact across two same-microarch runners. OK.")
        return 0

    print("microarch: DIFFERENT -> tolerance-based per L18 (DECISIONS 2026-09-14).")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_reference.py"),
                        str(a.stats1), str(a.stats2)], text=True)
    if r.returncode != 0:
        print("STOP: cross-microarch delta EXCEEDS the L18 thresholds — a real regression.", file=sys.stderr)
        return 1
    print("VERDICT: within L18 cross-microarch tolerance. OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
