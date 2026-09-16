"""Per-case margin flagging (STAGE3_PLAN §0.5 item 3): surface cases whose margin is sub-2σ.

A narrower band (from the 30-seed candidate) shrinks every case's margin; `margin_flag` must flag a
case that still HOLDS its tier guard but sits within 2× the reference std ("TIGHT — watch"), distinct
from a GUARD-FAIL (wrong side of tolerance). Tier direction is covered by test_tier_ripple; here we
pin the TIGHT-vs-clean boundary that the candidate margin table depends on.
"""
from __future__ import annotations

from scripts.case_margins import margin_flag

_TOL = 0.843719
_TWO_STD = 0.004274     # 2 × the committed 30-seed hidden std (§0.5)


def test_healthy_tight_when_margin_under_two_std():
    # Clears tolerance but only by less than 2σ → holds, but flagged TIGHT (watch under a narrower band).
    margin, ok, flag = margin_flag("control", _TOL + 0.001, _TOL, _TWO_STD)
    assert ok is True
    assert flag.startswith("TIGHT")
    assert 0 < margin < _TWO_STD


def test_healthy_clean_when_margin_at_least_two_std():
    margin, ok, flag = margin_flag("control", _TOL + _TWO_STD + 1e-6, _TOL, _TWO_STD)
    assert ok is True
    assert flag == ""
    assert margin >= _TWO_STD


def test_dynamics_tight_when_barely_below_tolerance():
    # Faulty run below tolerance by less than 2σ → correct side, but tight.
    margin, ok, flag = margin_flag("dynamics", _TOL - 0.001, _TOL, _TWO_STD)
    assert ok is True
    assert flag.startswith("TIGHT")


def test_metric_layer_uses_healthy_rule():
    # metric tier has a HEALTHY model → must clear tolerance; below it is a GUARD-FAIL, not TIGHT.
    _, ok, flag = margin_flag("metric", _TOL - 0.001, _TOL, _TWO_STD)
    assert ok is False
    assert "GUARD-FAIL" in flag
