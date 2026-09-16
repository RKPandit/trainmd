"""The four seed sets are disjoint and match the committed config (STAGE3_PLAN §5.2).

§5.2 moves the reference band OFF the control/calibration seeds to cure the
seed-collision circularity (control FPR biased LOW — L3). These tests pin the
invariant a validator (W3b) and the build design rely on.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from harness import seed_sets

REPO = Path(__file__).resolve().parent.parent


def test_all_seed_sets_pairwise_disjoint():
    assert seed_sets.disjointness_violations() == []
    seed_sets.assert_disjoint()  # does not raise


def test_reference_moved_off_control_seeds():
    # The whole point of §5.2: reference shares no seed with the cases it judges.
    assert seed_sets.REFERENCE & seed_sets.CONFIRMATORY == frozenset()
    assert {0, 1, 2} & seed_sets.REFERENCE == frozenset()   # old control seeds are gone
    assert seed_sets.REFERENCE == frozenset(range(200, 230))


def test_at_least_20_control_seeds():
    assert len(seed_sets.CONFIRMATORY_CONTROL) >= 20


def test_config_reference_seeds_match_seed_sets():
    cfg = yaml.safe_load((REPO / "workloads" / "tabular_adult" / "config.yaml").read_text())
    assert set(cfg["reference"]["seeds"]) == set(seed_sets.REFERENCE), (
        "config.yaml reference.seeds must equal seed_sets.REFERENCE (single source of truth)"
    )


def test_build_design_uses_confirmatory_seeds():
    from scripts.build_all_cases import CONTROL_SEEDS, FAULTY_SEEDS
    assert set(FAULTY_SEEDS) == set(seed_sets.CONFIRMATORY_FAULTY)
    assert set(CONTROL_SEEDS) == set(seed_sets.CONFIRMATORY_CONTROL)
    # none of the case seeds fall in the reference/development/hidden-eval sets
    for s in set(FAULTY_SEEDS) | set(CONTROL_SEEDS):
        assert s not in seed_sets.REFERENCE
        assert s not in seed_sets.DEVELOPMENT
        assert s not in seed_sets.HIDDEN_EVAL
