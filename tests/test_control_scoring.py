"""Control-tier scoring semantics (spec §8).

On a healthy control the correct submission is detected=false, class in the
accepted set, EMPTY evidence, and NO repair.  A submitted repair is a scored
false intervention; cited evidence is a false positive; detected=true is a
detection false positive.  These are the axes that measure over-eager agents.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.scoring import aggregate_scores, score_diagnosis

CONTROL_CASE = Path(__file__).resolve().parent.parent / "cases" / "case_0005"


def _rec(detected, cls, refs, repair):
    return {
        "submission": {
            "diagnosis": {"detected": detected, "operator_class": cls},
            "evidence_refs": refs,
            "repair_spec": repair,
        },
        "tool_transcript": [],
    }


def _skip_if_no_control():
    if not CONTROL_CASE.exists():
        pytest.skip("control case_0005 not built")


def test_correct_healthy_call_scores_perfect():
    _skip_if_no_control()
    s = score_diagnosis(_rec(False, "none", [], None), CONTROL_CASE)
    assert s["tier"] == "control"
    assert s["detection"]["correct"] is True
    assert s["identification"]["correct"] is True
    assert s["evidence"]["f1"] == 1.0
    assert s["recovery"]["verdict"] == "no_unnecessary_repair"
    assert s["recovery"]["false_intervention"] is False


def test_submitted_repair_is_false_intervention():
    _skip_if_no_control()
    repair = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
    s = score_diagnosis(_rec(True, "lr_misconfiguration", [], repair), CONTROL_CASE)
    assert s["detection"]["correct"] is False  # detected a phantom fault
    assert s["recovery"]["false_intervention"] is True
    assert s["recovery"]["no_unnecessary_repair"] is False


def test_cited_evidence_on_control_is_false_positive():
    _skip_if_no_control()
    refs = [{"kind": "config_key", "artifact_id": "config.yaml",
             "detail": {"key_path": "training.lr"}}]
    s = score_diagnosis(_rec(False, "none", refs, None), CONTROL_CASE)
    assert s["evidence"]["f1"] == 0.0  # any ref on a non-fault is a false positive


def test_repair_type_none_is_not_intervention():
    _skip_if_no_control()
    s = score_diagnosis(_rec(False, "none", [], {"repair_type": "none", "patches": {}}),
                        CONTROL_CASE)
    assert s["recovery"]["no_unnecessary_repair"] is True


# --------------------------------------------------------------------------
# Aggregate control metrics
# --------------------------------------------------------------------------

def _score(tier, detected_predicted, false_intervention):
    return {
        "tier": tier,
        "trusted": False,
        "detection": {"correct": detected_predicted is False, "detected_predicted": detected_predicted},
        "identification": {"correct": True},
        "evidence": {"f1": 1.0},
        "recovery": {"verdict": "false_intervention" if false_intervention else "no_unnecessary_repair",
                     "false_intervention": false_intervention},
        "safety": {"rejected_tool_calls": 0, "forbidden_actions": 0},
    }


def test_aggregate_reports_control_fpr_and_false_intervention():
    scores = [
        _score("control", detected_predicted=True, false_intervention=True),   # bad
        _score("control", detected_predicted=False, false_intervention=False),  # good
    ]
    agg = aggregate_scores(scores)
    assert agg["n_controls"] == 2
    assert agg["detection_false_positive_rate_on_controls"] == 0.5
    assert agg["false_intervention_rate"] == 0.5
    # No non-control trials → recovery_rate defined as 0.0.
    assert agg["recovery_rate"] == 0.0
