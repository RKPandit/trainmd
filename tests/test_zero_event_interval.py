"""Correction #6 (2026-09-23, STAGE4 4.0.2): a zero-event rate must never render [0, 0].

The case-clustered bootstrap percentile CI returns [0, 0] for any stratum with zero observed
events (every resample is also zero) — asserting zero uncertainty from zero observations. Every
zero-event RATE now carries a one-sided 95% Clopper–Pearson upper bound, exact for k = 0:
p_upper = 1 − 0.05^(1/n). These tests pin the bound, the control-FPR wiring, and the renderer.
"""
from __future__ import annotations

import re

import pytest

from harness import report_gen
from harness import sweep_stats as ss


# --------------------------------------------------------------------------- #
# The bound itself
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("n,expected", [
    (12, 0.2209),   # stage2gate off-arm control FPR 0/12
    (18, 0.1533),   # sweep1 off-arm control FPR 0/18
    (20, 0.1391),   # the review's "0/20 permits roughly 14%"
    (40, 0.0722),
    (1, 0.9500),    # one observation says almost nothing
])
def test_zero_event_upper_matches_clopper_pearson(n, expected):
    assert ss.zero_event_upper(n) == pytest.approx(expected, abs=5e-5)


def test_zero_event_upper_is_exact_for_k0():
    # One-sided (1−α) CP upper for k=0 solves (1−p)^n = α exactly.
    for n in (2, 7, 19, 38, 100):
        p = ss.zero_event_upper(n)
        assert (1 - p) ** n == pytest.approx(0.05, rel=1e-9)


def test_zero_event_upper_shrinks_with_n_but_never_reaches_zero():
    bounds = [ss.zero_event_upper(n) for n in (1, 2, 5, 20, 100, 10_000)]
    assert bounds == sorted(bounds, reverse=True)
    assert all(b > 0 for b in bounds)


@pytest.mark.parametrize("n", [0, None, -3])
def test_zero_event_upper_undefined_without_trials(n):
    assert ss.zero_event_upper(n) is None


# --------------------------------------------------------------------------- #
# _mark_zero_event: rates with 0 events get the bound; everything else untouched
# --------------------------------------------------------------------------- #

def test_mark_zero_event_replaces_degenerate_interval():
    ci = {"point": 0.0, "lo": 0.0, "hi": 0.0, "n_fp": 0, "n_trials": 18, "n_cases": 3}
    ss._mark_zero_event(ci)
    assert ci["one_sided_upper"] is True
    assert ci["point"] == 0.0 and ci["lo"] == 0.0
    assert ci["hi"] == pytest.approx(0.1533, abs=5e-5)


def test_mark_zero_event_leaves_nonzero_rates_alone():
    ci = {"point": 0.1, "lo": 0.0, "hi": 0.225, "n_fp": 4, "n_trials": 40}
    before = dict(ci)
    ss._mark_zero_event(ci)
    assert ci == before  # no one_sided flag, interval untouched


# --------------------------------------------------------------------------- #
# Wiring through control_fpr (pooled per-arm AND §5.1 strata)
# --------------------------------------------------------------------------- #

def _ctrl(case, anchor, detected, band="in_band"):
    return {
        "_tier": "control", "case_id": case, "_anchor": anchor,
        "_band_vis": band, "_band_hid": band,
        "scores": {"detection": {"detected": detected}},
        "submission": {"diagnosis": {"detected": detected}},
    }


def _zero_event_records():
    # 'off' arm: 0 false positives across 10 control cases → zero-event pooled + strata.
    recs = [_ctrl(f"case_{i:04d}", "off", False) for i in range(10)]
    # 'rule' arm: 1 FP → the non-zero path stays a bootstrap CI.
    recs += [_ctrl(f"case_{i:04d}", "rule", i == 0) for i in range(10)]
    return recs


def test_control_fpr_zero_event_arm_is_bounded():
    out = ss.control_fpr(_zero_event_records())
    off = out["per_arm"]["off"]
    assert off["n_fp"] == 0
    assert off.get("one_sided_upper") is True
    assert off["hi"] > 0.0, "zero-event arm must not report hi == 0"
    assert off["hi"] == pytest.approx(ss.zero_event_upper(off["n_trials"]), abs=1e-6)
    # The arm with an event keeps its ordinary bootstrap interval.
    assert not out["per_arm"]["rule"].get("one_sided_upper")


def test_control_fpr_zero_event_strata_are_bounded():
    out = ss.control_fpr(_zero_event_records())
    assert out["stratified"] is True
    stratum = out["by_band"]["off"]["in_band"]
    assert stratum["n_fp"] == 0
    assert stratum.get("one_sided_upper") is True and stratum["hi"] > 0.0


# --------------------------------------------------------------------------- #
# The renderer: the property the review asked for
# --------------------------------------------------------------------------- #

_ZERO_ZERO = re.compile(r"\[0(?:\.0+)?, 0(?:\.0+)?\]")


def test_zero_event_rate_never_renders_zero_zero():
    for n in (1, 2, 4, 12, 18, 19, 20, 38, 40):
        ci = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0,
                                  "n_fp": 0, "n_trials": n})
        text = report_gen._ci(ci)
        assert not _ZERO_ZERO.search(text), f"0/{n} rendered {text!r}"
        assert text.startswith("0.000 [0, ") and text.endswith("]†"), text


def test_render_matches_published_correction_values():
    # The before/after values disclosed as correction #6.
    for n, shown in ((18, "0.000 [0, 0.153]†"), (12, "0.000 [0, 0.221]†")):
        ci = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0,
                                  "n_fp": 0, "n_trials": n})
        assert report_gen._ci(ci) == shown


def test_nonzero_render_unchanged():
    assert report_gen._ci({"point": 0.1, "lo": 0.0, "hi": 0.225}) == "0.100 [0.000, 0.225]"


def test_legend_only_when_a_bound_is_present():
    bounded = {"per_arm": {"off": {"one_sided_upper": True}}}
    plain = {"per_arm": {"off": {"point": 0.1, "lo": 0.0, "hi": 0.2}}}
    assert report_gen._has_one_sided(bounded) is True
    assert report_gen._has_one_sided(plain) is False
