#!/usr/bin/env python3
"""EXACT comparison of two reference stats.yaml files, ignoring only wall-clock / memory fields.

Used to prove a workload change leaves the CLEAN path unchanged (DECISIONS 2026-09-23,
grad_clip_norm): the reference is generated with the OLD and the NEW train.py on the SAME runner (same
microarchitecture — native training is byte-exact within a microarch, not across, see
scripts/verify_reference.py), and every learned value — per-seed metrics, per-epoch losses and
accuracies, and the aggregates — must be identical. Exit 1 on any difference.

    python scripts/compare_stats_exact.py OLD/stats.yaml NEW/stats.yaml [--report-only]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

IGNORED = {"wall_time_sec", "peak_memory_mb", "epoch_time_sec", "throughput_samples_per_sec"}


def diffs(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k in IGNORED:
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: present in only one file")
            else:
                out += diffs(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diffs(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--report-only", action="store_true", help="print differences, never fail")
    x = ap.parse_args()
    d = diffs(yaml.safe_load(x.a.read_text()), yaml.safe_load(x.b.read_text()))
    if d:
        print(f"compare_stats_exact: {len(d)} learned value(s) differ ({x.a} vs {x.b}); first 20:")
        print("  " + "\n  ".join(d[:20]))
        return 0 if x.report_only else 1
    print(f"compare_stats_exact: IDENTICAL — every learned value matches ({x.a} vs {x.b}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
