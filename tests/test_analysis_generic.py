"""Part-A tests (STAGE3_PLAN §0.3): the analysis pipeline is plan-driven and legacy-map-consistent.

- one legacy map (`on`->`rule`) applied at load; no downstream metric sees a legacy value;
- a synthetic 2-operator / 4-arm design reports correctly with no code change;
- the ratio-gap-closed statistic matches a hand-computed value on a fixture.
"""
from __future__ import annotations

from harness import sweep_stats as ss
from harness.anchors import normalize_anchor


def _rec(cid, op, symptom, agent, anchor, detected, tier="dynamics", ev_f1=1.0):
    r = {"case_id": cid,
         "conditions": {"agent_type": agent, "anchor": anchor},
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

def test_two_operator_four_arm_design():
    arms = ["off", "numbers", "rule", "extra"]
    recs = []
    for op in ("op.x.v1", "op.y.v1"):
        for i, cid in enumerate((f"{op}-c1", f"{op}-c2")):
            for arm in arms:
                recs.append(_rec(cid, op, "positive", "react", arm, detected=(arm != "off")))
    s = ss.compute_all(recs)
    assert s["operators_faulty"] == ["op.x.v1", "op.y.v1"]
    assert s["arms"] == ["extra", "numbers", "off", "rule"]
    # every operator×arm present has a detection cell
    for op in s["operators_faulty"]:
        assert set(s["detection_by_operator_arm"][op]) == set(arms)


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
