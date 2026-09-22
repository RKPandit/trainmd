"""Dedup (one trial per cell) + the H8 neutral-vs-descriptive identification metric."""
from __future__ import annotations

from harness import sweep_stats as ss


# --------------------------------------------------------------------------- #
# dedup_one_per_cell
# --------------------------------------------------------------------------- #

def _rec(case, agent, anchor, rep, provider, status, ts, rid, id_correct=True):
    return {
        "case_id": case, "run_id": rid, "status": status,
        "environment": {"timestamp_utc": ts},
        "conditions": {"sweep_name": "s", "agent_type": agent, "anchor": anchor,
                       "repeat_index": rep, "provider": provider},
        "submission": {"diagnosis": {"detected": True}},
        "scores": {"identification": {"correct": id_correct},
                   "detection": {"correct": True}, "evidence": {"f1": 0.5},
                   "recovery": {"verdict": "recovered"}},
    }


def test_dedup_keeps_latest_completed_excludes_crashed():
    recs = [
        _rec("c1", "static", "off", 0, "openai", "crashed", "2026-01-01T00:00:00Z", "a"),
        _rec("c1", "static", "off", 0, "openai", "completed", "2026-01-01T00:05:00Z", "b"),
        _rec("c2", "static", "off", 0, "openai", "crashed", "2026-01-01T00:00:00Z", "x"),
        _rec("c2", "static", "off", 0, "openai", "crashed", "2026-01-01T00:01:00Z", "y"),
    ]
    kept = ss.dedup_one_per_cell(recs)
    # c1: the completed retry is kept; c2 (all crashed) is dropped entirely.
    assert [r["run_id"] for r in kept] == ["b"]


def test_dedup_latest_of_two_completed():
    recs = [
        _rec("c1", "react", "rule", 1, "anthropic", "completed", "2026-01-01T00:00:00Z", "old"),
        _rec("c1", "react", "rule", 1, "anthropic", "completed", "2026-01-01T09:00:00Z", "new"),
    ]
    assert [r["run_id"] for r in ss.dedup_one_per_cell(recs)] == ["new"]


def test_dedup_noop_on_clean_one_per_cell():
    # A record with no status field (legacy/fixture) is not crashed -> kept; distinct
    # cells stay 1:1 and in order (frozen-report byte-identity relies on this).
    recs = [
        {"case_id": "c1", "run_id": "1", "conditions": {"agent_type": "react", "anchor": "off",
                                                        "repeat_index": 0, "provider": None}},
        {"case_id": "c2", "run_id": "2", "conditions": {"agent_type": "react", "anchor": "off",
                                                        "repeat_index": 0, "provider": None}},
    ]
    kept = ss.dedup_one_per_cell(recs)
    assert [r["run_id"] for r in kept] == ["1", "2"]


def test_dedup_audit_reports_multi_and_excluded():
    recs = [
        _rec("c1", "static", "off", 0, "openai", "completed", "t2", "b"),
        _rec("c1", "static", "off", 0, "openai", "crashed", "t1", "a"),
        _rec("c2", "static", "off", 0, "openai", "crashed", "t1", "x"),
    ]
    aud = ss.dedup_audit(recs)
    assert aud["n_cells_out"] == 1               # only c1 survives
    assert aud["n_cells_multi_record"] == 1      # only c1 had >1 record
    assert aud["n_excluded_records"] == 2
    assert aud["excluded_status_counts"] == {"crashed": 2}


# --------------------------------------------------------------------------- #
# H8 identification contrast + verdict
# --------------------------------------------------------------------------- #

def _pair_recs(neutral_id_rate, descriptive_id_rate, n_cases=6, arm="off", provider="openai"):
    """Build id-scored trials for both variants at a target per-variant id rate."""
    recs = []
    for op, rate in (("silent.data_leakage.v1", descriptive_id_rate),
                     ("silent.data_leakage_neutral.v1", neutral_id_rate)):
        for i in range(n_cases):
            correct = i < round(rate * n_cases)
            r = _rec(f"case_{op[-4:]}_{i}", "static", arm, 0, provider, "completed",
                     f"t{i}", f"{op}-{i}", id_correct=correct)
            r["_op"] = op
            r["_anchor"] = arm
            r["_provider"] = provider
            r["_tier"] = "dynamics"
            recs.append(r)
    return recs


def test_h8_confirming_when_gap_small():
    recs = _pair_recs(neutral_id_rate=0.83, descriptive_id_rate=0.83)
    out = ss.h8_identification_contrast(recs)
    assert out["available"]
    row = out["rows"][0]
    assert abs(row["point"]) <= 0.15
    assert row["verdict"] == "confirming (no substantial gap)"


def test_h8_refuting_when_neutral_far_below_and_ci_excludes_zero():
    # neutral much lower than descriptive -> Δ < -0.30; with 6 clean cases per side
    # and a large separation the CI excludes 0.
    recs = _pair_recs(neutral_id_rate=0.0, descriptive_id_rate=1.0)
    out = ss.h8_identification_contrast(recs)
    row = out["rows"][0]
    assert row["point"] < -0.30 and row["hi"] < 0
    assert row["verdict"] == "refuting (name-reading)"


def test_h8_unavailable_without_both_variants():
    recs = _pair_recs(0.8, 0.8)
    recs = [r for r in recs if r["_op"] == "silent.data_leakage.v1"]  # drop neutral
    assert ss.h8_identification_contrast(recs)["available"] is False


def test_h8_verdict_thresholds():
    assert ss._h8_verdict(0.10, -0.05, 0.25) == "confirming (no substantial gap)"
    assert ss._h8_verdict(-0.40, -0.55, -0.20) == "refuting (name-reading)"
    assert ss._h8_verdict(-0.40, -0.55, 0.10) == "inconclusive"   # CI includes 0
    assert ss._h8_verdict(-0.20, -0.30, -0.05) == "inconclusive"  # between bounds
