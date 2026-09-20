"""Subset-gate selection + coverage assertion (pure; no builds, no training)."""
from __future__ import annotations

from harness.gate_known_answer import subset_by_operator_strength


def test_picks_one_case_per_operator_strength():
    # two seeds for the same (op, strength) -> exactly one representative (smallest name)
    cases = [
        ("case_0002", "silent.lr_warmup.v1", "mild"),
        ("case_0001", "silent.lr_warmup.v1", "mild"),
        ("case_0003", "silent.lr_warmup.v1", "moderate"),
    ]
    sel, ok, info = subset_by_operator_strength(cases)
    assert sel == {"case_0001", "case_0003"}      # one per group, smallest id
    assert ok is True
    assert info["n_selected"] == 2


def test_coverage_passes_when_all_expected_groups_present():
    cases = [
        ("case_0001", "opA", "mild"),
        ("case_0002", "opA", "severe"),
        ("case_0003", "opB", "mild"),
    ]
    expected = {("opA", "mild"), ("opA", "severe"), ("opB", "mild")}
    sel, ok, info = subset_by_operator_strength(cases, expected)
    assert ok is True
    assert info["missing"] == []
    assert info["covered_groups"] == 3


def test_coverage_fails_when_a_design_group_is_missing_from_the_build():
    # The build is missing opB/mild -> coverage must FAIL (not silently pass).
    cases = [
        ("case_0001", "opA", "mild"),
        ("case_0002", "opA", "severe"),
    ]
    expected = {("opA", "mild"), ("opA", "severe"), ("opB", "mild")}
    sel, ok, info = subset_by_operator_strength(cases, expected)
    assert ok is False
    assert info["missing"] == [("opB", "mild")]
