"""case_margins: the metric tier is REPORT-ONLY on band position (DECISIONS 2026-09-19).

The metric tier's "model untouched" guarantee is checkpoint bitwise identity
(build_case / validate_case C12), not hidden-band position — which varies by seed
and runner microarch (L24). So margin_flag must NEVER fail a metric case on band
position, only record where it sits. Dynamics gating is unchanged.
"""
from __future__ import annotations

from scripts.case_margins import margin_flag

_TOL = 0.844655
_TWO_STD = 0.003592  # 2σ (σ≈0.001796)


def test_metric_below_tolerance_is_report_only_not_a_failure():
    # seed 46 on an unlucky runner: 0.844355 < tol. Previously GUARD-FAIL; now OK.
    _margin, ok, flag = margin_flag("metric", 0.844355, _TOL, _TWO_STD)
    assert ok is True
    assert "OUT-OF-BAND below" in flag


def test_metric_above_band_is_report_only():
    # seed 46 on another runner: 0.853457 > mean+2σ. Report-only.
    _margin, ok, flag = margin_flag("metric", 0.853457, _TOL, _TWO_STD)
    assert ok is True
    assert "OUT-OF-BAND above" in flag


def test_metric_in_band_ok():
    _margin, ok, flag = margin_flag("metric", 0.848592, _TOL, _TWO_STD)
    assert ok is True


def test_dynamics_gating_unchanged():
    # dynamics faulty must be BELOW tol; above tol is a failure (not degraded).
    _m, ok_below, _f = margin_flag("dynamics", 0.800000, _TOL, _TWO_STD)
    assert ok_below is True
    _m, ok_above, _f = margin_flag("dynamics", 0.900000, _TOL, _TWO_STD)
    assert ok_above is False


def test_control_report_only_unchanged():
    _m, ok, _f = margin_flag("control", 0.800000, _TOL, _TWO_STD)  # below band
    assert ok is True
