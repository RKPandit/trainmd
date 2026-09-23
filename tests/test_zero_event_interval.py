"""Correction #6 (2026-09-23, STAGE4 4.0.2): a zero-event rate must never render [0, 0].

The case-clustered bootstrap percentile CI returns [0, 0] for any stratum with zero observed
events (every resample is also zero) — asserting zero uncertainty from zero observations. In the
tables every zero-event RATE now carries the EXACT two-sided 95% Clopper–Pearson interval over the
number of UNIQUE CASES (the bootstrap's own cluster unit), [0, 1 − 0.025^(1/n_cases)]; the one-sided
form appears only as a labelled prose ceiling. Rows with 1–2 events are flagged: the percentile
bootstrap understates uncertainty at that count.
"""
from __future__ import annotations

import re

import pytest

from harness import report_gen
from harness import sweep_stats as ss


# --------------------------------------------------------------------------- #
# Exact Clopper–Pearson
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("n,two_sided,one_sided", [
    (3, 0.7076, 0.6316),    # sweep1 / stage2gate off arm: 3 unique control cases
    (19, 0.1765, 0.1459),   # h8 in-band stratum: 19 unique cases
    (20, 0.1684, 0.1391),   # the review's "0/20 permits roughly 14%" is the one-sided ceiling
    (1, 0.9750, 0.9500),
])
def test_zero_event_upper_values(n, two_sided, one_sided):
    assert ss.zero_event_upper(n) == pytest.approx(two_sided, abs=5e-5)           # tables
    assert ss.zero_event_upper(n, two_sided=False) == pytest.approx(one_sided, abs=5e-5)  # prose


@pytest.mark.parametrize("n", [0, None, -3])
def test_zero_event_upper_undefined_without_units(n):
    assert ss.zero_event_upper(n) is None


def test_closed_form_matches_exact_clopper_pearson_at_k0():
    for n in (1, 2, 3, 7, 19, 20, 38, 100):
        lo, hi = ss.clopper_pearson(0, n)
        assert lo == 0.0
        assert hi == pytest.approx(ss.zero_event_upper(n), abs=1e-9)


def test_clopper_pearson_known_value():
    lo, hi = ss.clopper_pearson(1, 19)          # the review's worked example
    assert lo == pytest.approx(0.0013, abs=5e-5)
    assert hi == pytest.approx(0.2603, abs=5e-4)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 12, 19, 20, 40])
def test_exact_bounds_monotone_non_decreasing_in_event_count(n):
    """At a fixed cluster count, exact bounds never decrease as events increase — so a zero-event
    bound is (correctly) the tightest, and one more event can only widen the upper edge."""
    bounds = [ss.clopper_pearson(k, n) for k in range(n + 1)]
    los, his = [b[0] for b in bounds], [b[1] for b in bounds]
    assert all(a <= b + 1e-12 for a, b in zip(los, los[1:])), f"lower bound not monotone at n={n}"
    assert all(a <= b + 1e-12 for a, b in zip(his, his[1:])), f"upper bound not monotone at n={n}"
    assert his[0] == pytest.approx(ss.zero_event_upper(n), abs=1e-9)


# --------------------------------------------------------------------------- #
# _mark_zero_event: cluster count, not trial count; 1–2 events flagged
# --------------------------------------------------------------------------- #

def test_bound_uses_unique_cases_not_trials():
    a = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0, "n_fp": 0, "n_trials": 18, "n_cases": 3})
    b = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0, "n_fp": 0, "n_trials": 600, "n_cases": 3})
    assert a["zero_event_cp"] is True and a["lo"] == 0.0 and a["point"] == 0.0
    assert a["hi"] == pytest.approx(0.7076, abs=5e-5)     # not 0.185 (18 trials) / 0.153
    assert a["hi"] == b["hi"], "more correlated trials in the same cases must not tighten the bound"


@pytest.mark.parametrize("n_fp,flagged", [(0, False), (1, True), (2, True), (3, False), (6, False)])
def test_low_count_flag(n_fp, flagged):
    ci = ss._mark_zero_event({"point": 0.1, "lo": 0.0, "hi": 0.3, "n_fp": n_fp,
                              "n_trials": 40, "n_cases": 20})
    assert bool(ci.get("low_count")) is flagged


def test_rows_with_three_or_more_events_are_untouched():
    ci = {"point": 0.1, "lo": 0.0, "hi": 0.225, "n_fp": 4, "n_trials": 40, "n_cases": 20}
    before = dict(ci)
    assert ss._mark_zero_event(ci) == before


# --------------------------------------------------------------------------- #
# Wiring through control_fpr (pooled per-arm AND §5.1 strata)
# --------------------------------------------------------------------------- #

def _ctrl(case, anchor, detected, band="in_band"):
    return {"_tier": "control", "case_id": case, "_anchor": anchor,
            "_band_vis": band, "_band_hid": band,
            "submission": {"diagnosis": {"detected": detected}}}


def _records():
    # 'off': 0 FP over 10 cases × 3 trials; 'rule': exactly 1 FP trial (low-count).
    recs = [_ctrl(f"case_{i:04d}", "off", False) for i in range(10) for _ in range(3)]
    recs += [_ctrl(f"case_{i:04d}", "rule", i == 0 and t == 0) for i in range(10) for t in range(3)]
    return recs


def test_control_fpr_zero_event_arm_uses_cluster_count():
    out = ss.control_fpr(_records())
    off = out["per_arm"]["off"]
    assert off["n_fp"] == 0 and off["n_cases"] == 10 and off["n_trials"] == 30
    assert off["zero_event_cp"] is True
    assert off["hi"] == pytest.approx(ss.zero_event_upper(10), abs=1e-6)
    assert out["per_arm"]["rule"].get("low_count") is True
    assert not out["per_arm"]["rule"].get("zero_event_cp")


def test_control_fpr_zero_event_strata_use_cluster_count():
    out = ss.control_fpr(_records())
    stratum = out["by_band"]["off"]["in_band"]
    assert stratum["zero_event_cp"] is True
    assert stratum["hi"] == pytest.approx(ss.zero_event_upper(stratum["n_cases"]), abs=1e-6)


# --------------------------------------------------------------------------- #
# The renderer
# --------------------------------------------------------------------------- #

_ZERO_ZERO = re.compile(r"\[0(?:\.0+)?, 0(?:\.0+)?\]")


def test_zero_event_rate_never_renders_zero_zero():
    for n_cases in (1, 2, 3, 18, 19, 20):
        ci = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0, "n_fp": 0,
                                  "n_trials": 2 * n_cases, "n_cases": n_cases})
        text = report_gen._ci(ci)
        assert not _ZERO_ZERO.search(text), text
        assert text.startswith("0.000 [0, ") and text.endswith("]†"), text


def test_render_matches_published_correction_values():
    # sweep1 off 0/18 and stage2gate off 0/12 are both over 3 unique control cases.
    for n_trials in (18, 12):
        ci = ss._mark_zero_event({"point": 0.0, "lo": 0.0, "hi": 0.0, "n_fp": 0,
                                  "n_trials": n_trials, "n_cases": 3})
        assert report_gen._ci(ci) == "0.000 [0, 0.708]†"


def test_low_count_row_is_flagged_in_render():
    ci = ss._mark_zero_event({"point": 0.053, "lo": 0.0, "hi": 0.158, "n_fp": 1,
                              "n_trials": 19, "n_cases": 19})
    assert report_gen._ci(ci) == "0.053 [0.000, 0.158]‡"


def test_ordinary_render_unchanged():
    assert report_gen._ci({"point": 0.1, "lo": 0.0, "hi": 0.225}) == "0.100 [0.000, 0.225]"


def test_legend_flags():
    assert report_gen._has_flag({"per_arm": {"off": {"zero_event_cp": True}}}, "zero_event_cp")
    assert report_gen._has_flag({"x": [{"low_count": True}]}, "low_count")
    assert not report_gen._has_flag({"per_arm": {"off": {"point": 0.1}}}, "zero_event_cp")
