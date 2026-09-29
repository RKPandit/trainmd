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
from harness.seed_sets import (
    CONFIRMATORY_BENIGN,
    CONFIRMATORY_BENIGN_IMAGE,
    CONFIRMATORY_CONTROL,
    CONFIRMATORY_FAULTY,
)
from operators.control.benign import BENIGN_OPERATORS
from operators.control.benign import benign_design as _benign_design
from operators.image.controls import IMAGE_BENIGN_OPERATORS, ImageHealthyControlOperator
from operators.registry import DEFAULT_GROUP, all_operator_ids, get_operator

WORKLOAD = os.environ.get("WORKLOAD", "tabular_adult")
CONTROL = "control.healthy.v1"
STRENGTHS = ["mild", "moderate", "severe"]
# §5.2: confirmatory seeds from the single source of truth (harness/seed_sets.py),
# disjoint from the reference band (200–229). Controls moved {0,1,2} → 50–69 (≥20).
FAULTY_SEEDS = sorted(CONFIRMATORY_FAULTY)      # [42, 43]
CONTROL_SEEDS = sorted(CONFIRMATORY_CONTROL)    # [50..69]
BENIGN_SEEDS = sorted(CONFIRMATORY_BENIGN)      # 70–93 ∪ 110–157: 3 blocks of 6 types × 4 seeds


def benign_design() -> list[tuple[str, str, int]]:
    """(operator_id, "mild", seed) for the benign-configuration controls — paired block by block (the
    pairing lives in benign.benign_design; the first block, 70–93, is unchanged)."""
    return _benign_design(BENIGN_SEEDS)


# Part 3 image workload (design docs/PART3_DESIGN_DRAFT.md §3–4): same faulty and control seeds; benign
# 70–93 ∪ 110–169 in blocks of 7 types × 4. 7 faulty × 3 × 6 + 20 + 84 = 230 cases.
IMAGE_GROUP = "image_fmnist"
IMAGE_CONTROL = ImageHealthyControlOperator.id
IMAGE_BENIGN_SEEDS = sorted(CONFIRMATORY_BENIGN_IMAGE)


def _faulty_ops(group: str = DEFAULT_GROUP) -> list[str]:
    return sorted(op for op in all_operator_ids(group) if get_operator(op).layer != "control")


def case_design_tuples(group: str = DEFAULT_GROUP) -> list[tuple[str, str, int]]:
    """The full case design as (operator_id, strength, seed) tuples, sourced from operators/registry.py
    (CODE), not the generated cases/registry.hidden.yaml. This is the single source of truth for the
    case COUNT — so a check can derive it from a fresh checkout, before any case is built. Keep this
    the one place the design is enumerated (main() and scripts/check_current_state.py both use it).

    ``group`` selects the workload (operators/registry.py workload groups); the default is workload 1, whose
    design, order and count are unchanged by the image workload's."""
    if group == IMAGE_GROUP:
        tuples = [(op, st, sd) for op in _faulty_ops(group) for st in STRENGTHS for sd in FAULTY_SEEDS]
        tuples += [(IMAGE_CONTROL, "mild", sd) for sd in CONTROL_SEEDS]
        return tuples + _benign_design(IMAGE_BENIGN_SEEDS, IMAGE_BENIGN_OPERATORS)
    if group != DEFAULT_GROUP:
        raise ValueError(f"no case design for workload group {group!r}")
    tuples = [(op, st, sd) for op in _faulty_ops() for st in STRENGTHS for sd in FAULTY_SEEDS]
    tuples += [(CONTROL, "mild", sd) for sd in CONTROL_SEEDS]
    # Appended LAST so the existing case numbering (case_0001–0128) is unchanged.
    tuples += benign_design()
    return tuples


def main() -> int:
    root = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
    # WORKLOAD_GROUP=image_fmnist builds the Part 3 image design (appended after workload 1's cases).
    group = os.environ.get("WORKLOAD_GROUP", DEFAULT_GROUP)
    tuples = case_design_tuples(group)
    faulty = _faulty_ops(group)
    benign = IMAGE_BENIGN_OPERATORS if group == IMAGE_GROUP else BENIGN_OPERATORS
    n_benign = len(IMAGE_BENIGN_SEEDS if group == IMAGE_GROUP else BENIGN_SEEDS)
    print(f"Building {len(tuples)} {group} cases "
          f"({len(faulty)} faulty x {len(STRENGTHS)} x {len(FAULTY_SEEDS)} "
          f"+ control x {len(CONTROL_SEEDS)} + benign {len(benign)} x "
          f"{n_benign // len(benign)}) against the current reference.")
    built = 0
    for op, st, sd in tuples:
        # Each operator declares the workload family whose train.py reads its keys
        # (default tabular_adult); the neutral-key variant runs on tabular_adult_neutral.
        wl = getattr(get_operator(op), "WORKLOAD_FAMILY", WORKLOAD)
        case_dir = build_case(wl, op, st, sd, project_root=root, force=True)
        built += 1
        print(f"  [{built:2}/{len(tuples)}] {op} {st} seed={sd} -> {Path(case_dir).name}")
    print(f"Built {built} cases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
