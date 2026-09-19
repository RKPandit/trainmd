"""Smoke-harness safety tests — the off-design guard must be a POSITIVE check.

The provider smoke may only ever run against a throwaway case that is provably
NOT in the sweep design. These tests pin that guard: it rejects a real study
tuple and a reserved seed, and accepts a genuine throwaway. No network, no build.
"""
from __future__ import annotations

import pytest

from scripts.smoke_provider import (
    _all_reserved_seeds,
    _assert_off_design,
    _design_tuples,
)


def test_a_real_study_tuple_is_in_the_design():
    # data_leakage at a confirmatory seed is a study case — it MUST be flagged.
    design = _design_tuples()
    assert ("silent.data_leakage.v1", 42) in design
    with pytest.raises(SystemExit):
        _assert_off_design("silent.data_leakage.v1", 42)


def test_a_reserved_seed_is_refused_even_for_a_novel_operator():
    # Seed 200 is a reference-band seed; refuse it regardless of operator.
    assert 200 in _all_reserved_seeds()
    with pytest.raises(SystemExit):
        _assert_off_design("silent.lr_warmup.v1", 200)


def test_off_design_throwaway_is_accepted():
    # A faulty operator at a seed outside every set is a safe throwaway.
    seed = 90001
    assert ("silent.lr_warmup.v1", seed) not in _design_tuples()
    assert seed not in _all_reserved_seeds()
    _assert_off_design("silent.lr_warmup.v1", seed)  # does not raise
