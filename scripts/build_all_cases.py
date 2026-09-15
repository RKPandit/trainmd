"""Build the full case design from a FRESH checkout (Stage 1b, item 5).

Sources the faulty operator set from operators/registry.py (code), NOT the case
registry — so it bootstraps from an empty checkout (the bug that made
`sweep plan --build-missing` build only controls). Builds each case with
force=True (idempotent) against the CURRENT reference. Does NOT validate — CI
runs validate-all + gate + margins as separate, individually-reportable steps.

Design: faulty operators x {mild,moderate,severe} x seeds[42,43]
        + control x seeds[0,1,2] (strength mild). Registry-driven: the count follows the
        faulty-operator set in operators/registry.py (5 faulty operators -> 33 cases as of
        2026-09-15; was 27 with 4 operators pre-metric_inflation). See docs/CURRENT_STATE.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Run as a bare script (python scripts/build_all_cases.py): only scripts/ is on
# sys.path, so add the repo root before importing harness/operators.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.build_case import build_case
from operators.registry import all_operator_ids

WORKLOAD = os.environ.get("WORKLOAD", "tabular_adult")
CONTROL = "control.healthy.v1"
STRENGTHS = ["mild", "moderate", "severe"]
FAULTY_SEEDS = [42, 43]
CONTROL_SEEDS = [0, 1, 2]


def main() -> int:
    root = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
    faulty = sorted(op for op in all_operator_ids() if op != CONTROL)
    tuples = [(op, st, sd) for op in faulty for st in STRENGTHS for sd in FAULTY_SEEDS]
    tuples += [(CONTROL, "mild", sd) for sd in CONTROL_SEEDS]
    print(f"Building {len(tuples)} cases "
          f"({len(faulty)} faulty x {len(STRENGTHS)} x {len(FAULTY_SEEDS)} "
          f"+ control x {len(CONTROL_SEEDS)}) against the current reference.")
    built = 0
    for op, st, sd in tuples:
        case_dir = build_case(WORKLOAD, op, st, sd, project_root=root, force=True)
        built += 1
        print(f"  [{built:2}/{len(tuples)}] {op} {st} seed={sd} -> {Path(case_dir).name}")
    print(f"Built {built} cases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
