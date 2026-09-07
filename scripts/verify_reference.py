"""Verify that regenerated reference stats match the committed snapshot.

Compares only deterministic fields (metrics, per-epoch curves).
Non-deterministic fields (wall_time_sec, peak_memory_mb) are ignored.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


_NONDETERMINISTIC = {"wall_time_sec", "peak_memory_mb"}


def strip_nondeterministic(obj: object) -> object:
    """Recursively remove non-deterministic keys from a nested structure."""
    if isinstance(obj, dict):
        return {
            k: strip_nondeterministic(v)
            for k, v in obj.items()
            if k not in _NONDETERMINISTIC
        }
    if isinstance(obj, list):
        return [strip_nondeterministic(item) for item in obj]
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify reference stats match")
    parser.add_argument("committed", type=Path, help="Committed stats.yaml")
    parser.add_argument("generated", type=Path, help="Freshly generated stats.yaml")
    args = parser.parse_args()

    with open(args.committed) as f:
        committed = yaml.safe_load(f)
    with open(args.generated) as f:
        generated = yaml.safe_load(f)

    committed_clean = strip_nondeterministic(committed)
    generated_clean = strip_nondeterministic(generated)

    if committed_clean == generated_clean:
        print("PASS: reference stats match (deterministic fields identical).")
        return 0

    # Find first difference for a useful error message
    committed_yaml = yaml.dump(committed_clean, default_flow_style=False, sort_keys=False)
    generated_yaml = yaml.dump(generated_clean, default_flow_style=False, sort_keys=False)

    print("FAIL: reference stats do NOT match.", file=sys.stderr)
    print("", file=sys.stderr)
    for i, (a, b) in enumerate(
        zip(committed_yaml.splitlines(), generated_yaml.splitlines()), 1,
    ):
        if a != b:
            print(f"First difference at line {i}:", file=sys.stderr)
            print(f"  committed: {a}", file=sys.stderr)
            print(f"  generated: {b}", file=sys.stderr)
            break
    return 1


if __name__ == "__main__":
    sys.exit(main())
