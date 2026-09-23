"""Part-A tests (STAGE3_PLAN §0.3): the analysis pipeline is plan-driven and legacy-map-consistent.

- one legacy map (`on`->`rule`) applied at load; no downstream metric sees a legacy value;
- a synthetic 2-operator / 4-arm design reports correctly with no code change;
- the ratio-gap-closed statistic matches a hand-computed value on a fixture.
"""
from __future__ import annotations

from harness import sweep_stats as ss
from harness.anchors import normalize_anchor


def _rec(cid, op, symptom, agent, anchor, detected, tier="dynamics", ev_f1=1.0, pv=None):
    r = {"case_id": cid,
         "conditions": {"agent_type": agent, "anchor": anchor},
         "prompt": {"prompt_version": pv},
         "scores": {"detection": {"correct": detected, "detected_predicted": detected},
                    "identification": {"correct": detected},
                    "evidence": {"f1": ev_f1},
                    "recovery": {"verdict": "recovered" if detected else "not_recovered"}},
         "submission": {"diagnosis": {"detected": detected}}}
    return ss.attach_meta(r, {"operator_id": op, "tier": tier, "symptom_direction": symptom,
                              "visible_sigma_distance": 1.0, "hidden_sigma_distance": 1.0})


# --------------------------------------------------------------------------- #
# One legacy map, applied at load; no downstream code sees "on"
# --------------------------------------------------------------------------- #

def test_normalize_anchor_is_the_single_map():
    assert normalize_anchor("on") == "rule"
    assert normalize_anchor("off") == "off"
    assert normalize_anchor("numbers") == "numbers"
    assert normalize_anchor(None) is None
    # v1 labels are unchanged whether the version is explicit or absent (frozen reports).
    for pv in (None, "react-1", "react-1-noanchor", "static-1-rule"):
        assert normalize_anchor("rule", pv) == "rule"


def test_arm_identity_includes_prompt_version():
    import pytest
    assert normalize_anchor("rule", "react-2-rule") == "rule.v2"
    assert normalize_anchor("stats", "static-2-stats") == "stats.v2"
    assert normalize_anchor("off", "react-2-off") == "off.v2"
    assert normalize_anchor("rule", "react-1-rule") != normalize_anchor("rule", "react-2-rule")
    # Nothing maps across versions: legacy "on" and "numbers" cannot reach a v2 arm; "stats"
    # does not exist in v1; an unrecognized version string is an error, not a default.
    for anchor, pv in (("on", "react-2-rule"), ("numbers", "react-2-numbers"),
                       ("stats", "react-1-stats"), ("stats", None), ("rule", "mystery-9")):
        with pytest.raises(ValueError):
            normalize_anchor(anchor, pv)


def test_report_with_both_versions_keeps_them_separate():
    """A report over v1 AND v2 records never merges H8's rule (v1) with Stage 4's rule (v2)."""
    from harness import report_gen
    recs = []
    for cid in ("A", "B"):
        for arm, v1_hit, v2_hit in (("off", False, False), ("rule", True, False)):
            recs.append(_rec(cid, "op.a.v1", "positive", "react", arm, v1_hit, pv=f"react-1-{arm}"))
            recs.append(_rec(cid, "op.a.v1", "positive", "react", arm, v2_hit, pv=f"react-2-{arm}"))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "numbers", True, pv="react-1-numbers"))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "stats", False, pv="react-2-stats"))
        for arm, pv in (("rule", "static-1-rule"), ("rule", "static-2-rule")):
            recs.append(_rec(f"ctl{cid}", "control.healthy.v1", "none", "static", arm,
                             detected=False, tier="control", pv=pv))
    s = ss.compute_all(recs)
    assert s["arms"] == ["numbers", "off", "off.v2", "rule", "rule.v2", "stats.v2"]
    d = s["detection_by_operator_arm"]["op.a.v1"]
    assert d["rule"]["point"] == 1.0 and d["rule.v2"]["point"] == 0.0      # not pooled (0.5)
    assert set(s["control_fpr"]["per_arm"]) == {"rule", "rule.v2"}
    # contrasts across arms are never computed over mixed versions
    assert s["ratio_gap_closed"]["available"] is False
    assert "mix prompt versions" in s["ratio_gap_closed"]["reason"]
    md = report_gen.generate(recs, {"name": "mixed", "date": "", "model": None, "models": None,
                                    "plan_arms": None, "n_cells": None,
                                    "excluded": {"trusted": 0, "superseded": 0}})
    assert "| rule.v2 |" in md and "| rule |" in md


def test_v2_contrasts_use_v2_arms():
    recs = []
    for cid, hit in (("A", True), ("B", False)):
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "off", False, pv="react-2-off"))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "stats", hit, pv="react-2-stats"))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "rule", True, pv="react-2-rule"))
    r = ss.ratio_gap_closed(recs)
    assert r["available"] and (r["low_arm"], r["mid_arm"], r["high_arm"]) == ("off.v2", "stats.v2", "rule.v2")
    assert abs(r["operators"]["op.a.v1"]["fraction_closed_by_mid"]["point"] - 0.5) < 1e-9


def test_legacy_on_record_is_rule_everywhere():
    # A planted legacy-"on" record must be treated as "rule" by every metric.
    recs = [_rec("c1", "op.a.v1", "positive", "react", "on", True),
            _rec("c1", "op.a.v1", "positive", "react", "off", False)]
    assert all(r["_anchor"] in ("rule", "off") for r in recs)  # never "on"
    assert ss.arms_present(recs) == ["off", "rule"]
    dba = ss.detection_by_operator_arm(recs)
    assert "rule" in dba["op.a.v1"] and "on" not in dba["op.a.v1"]


# --------------------------------------------------------------------------- #
# Generic: a 2-operator / 4-arm design reports with no code change
# --------------------------------------------------------------------------- #

def test_two_operator_four_arm_design(monkeypatch):
    # A hypothetical future prompt version declaring FOUR arms: declaring the arm set in
    # harness/anchors.py is the only change needed — the analysis itself is generic.
    from harness import anchors
    arms = ["off", "stats", "rule", "extra"]
    monkeypatch.setitem(anchors.ARMS_BY_PROMPT_MAJOR, 9, tuple(arms))
    recs = []
    for op in ("op.x.v1", "op.y.v1"):
        for i, cid in enumerate((f"{op}-c1", f"{op}-c2")):
            for arm in arms:
                recs.append(_rec(cid, op, "positive", "react", arm, detected=(arm != "off"),
                                 pv=f"react-9-{arm}"))
    s = ss.compute_all(recs)
    assert s["operators_faulty"] == ["op.x.v1", "op.y.v1"]
    assert s["arms"] == ["extra.v9", "off.v9", "rule.v9", "stats.v9"]
    # every operator×arm present has a detection cell
    for op in s["operators_faulty"]:
        assert set(s["detection_by_operator_arm"][op]) == {f"{a}.v9" for a in arms}


def test_metrics_registry_rejects_unknown_and_selects():
    recs = [_rec("c1", "op.a.v1", "positive", "react", "off", True)]
    only = ss.compute_all(recs, metrics=["recovery_endpoints"])
    assert "recovery_endpoints" in only and "control_fpr" not in only
    import pytest
    with pytest.raises(KeyError):
        ss.compute_all(recs, metrics=["not_a_metric"])


# --------------------------------------------------------------------------- #
# Ratio gap closed — hand-computed fixture
# --------------------------------------------------------------------------- #

def test_ratio_gap_closed_matches_hand_value():
    # 2 cases; off=0/2, numbers=1/2, rule=2/2  ->  (0.5-0)/(1-0) = 0.5 exactly.
    recs = []
    for cid, num_hit in (("A", True), ("B", False)):
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "off", False))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "numbers", num_hit))
        recs.append(_rec(cid, "op.a.v1", "positive", "react", "rule", True))
    r = ss.ratio_gap_closed(recs)
    assert r["available"]
    d = r["operators"]["op.a.v1"]
    assert d["detect_off"] == 0.0 and d["detect_numbers"] == 0.5 and d["detect_rule"] == 1.0
    assert abs(d["fraction_closed_by_mid"]["point"] - 0.5) < 1e-9
    lo, hi = d["fraction_closed_by_mid"]["lo"], d["fraction_closed_by_mid"]["hi"]
    assert 0.0 <= lo <= 0.5 <= hi <= 1.0


def test_ratio_unavailable_without_three_arms():
    recs = [_rec("c1", "op.a.v1", "positive", "react", "off", False),
            _rec("c1", "op.a.v1", "positive", "react", "rule", True)]
    assert ss.ratio_gap_closed(recs)["available"] is False
