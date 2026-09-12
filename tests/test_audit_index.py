"""Planted-violation tests for the impossible-combination audit (spec §8).

For each rule, synthesize a record that violates exactly that rule and assert
it fires while no OTHER FAIL rule does.  A clean record fires nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.audit_index import assert_clean_for_aggregation, run_audit


def _base(**over):
    rec = {
        "case_id": "case_0001", "run_id": "t", "status": "completed",
        "model": {"model_id": None},
        "usage": {"input_tokens": 100, "output_tokens": 10,
                  "estimated_cost_usd": None, "cost_is_estimate": True},
        "submission": {"diagnosis": {"detected": True}, "evidence_refs": [], "repair_spec": None},
        "scores": {
            "detection": {"correct": True}, "identification": {"correct": True},
            "evidence": {"f1": 0.0, "recall": 0.0},
            "recovery": {"verdict": "recovered", "per_seed_hidden_metrics": []},
        },
        "card_superseded": False,
    }
    rec.update(over)
    return rec


def _write_and_audit(tmp: Path, rec: dict):
    trials = tmp / "results" / "case_0001" / "trials"
    trials.mkdir(parents=True)
    (trials / "t.yaml").write_text(yaml.dump(rec))
    rows, fail_count = run_audit(tmp)
    return {r["rule"]: r for r in rows}, fail_count


def _fail_rules_fired(by_name):
    return {name for name, r in by_name.items() if r["severity"] == "FAIL" and r["count"] > 0}


def test_clean_record_fires_nothing(tmp_path):
    by_name, fail_count = _write_and_audit(tmp_path, _base())
    assert fail_count == 0


def test_r1_recovered_not_detected(tmp_path):
    rec = _base()
    rec["submission"]["diagnosis"]["detected"] = False
    rec["scores"]["identification"]["correct"] = False  # avoid R6 (INFO)
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R1_recovered_not_detected"}


def test_r2_no_submission_scored(tmp_path):
    rec = _base(submission=None)  # but detection scored correct
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R2_no_submission_scored"}


def test_r3_crash_recovered_incomplete(tmp_path):
    rec = _base()
    rec["scores"]["recovery"]["per_seed_hidden_metrics"] = [{"exitcode": 1}]
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R3_crash_recovered_incomplete"}


def test_r4_control_patch_no_intervention(tmp_path):
    rec = _base()
    rec["submission"]["repair_spec"] = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
    rec["scores"]["recovery"] = {"verdict": "no_unnecessary_repair", "no_unnecessary_repair": True}
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R4_control_patch_no_intervention"}


def test_r5_not_detected_with_evidence(tmp_path):
    rec = _base()
    rec["submission"]["diagnosis"]["detected"] = False
    rec["submission"]["evidence_refs"] = [{"kind": "config_key"}]
    rec["scores"]["identification"]["correct"] = False  # avoid R6
    rec["scores"]["recovery"] = {"verdict": "not_recovered"}  # avoid R1
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R5_not_detected_with_evidence"}


def test_r7_completed_zero_input_tokens(tmp_path):
    rec = _base()
    rec["model"]["model_id"] = "some-llm"
    rec["usage"]["input_tokens"] = 0
    rec["scores"]["recovery"] = {"verdict": "not_recovered"}
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R7_completed_zero_input_tokens"}


def test_r8_cost_price_mismatch(tmp_path):
    from harness.pricing import estimate_cost
    est = estimate_cost("claude-haiku-4-5-20251001", 1000, 1000, 0)
    if est is None or est.cost_usd == 0:
        pytest.skip("haiku not in price table")
    rec = _base()
    rec["model"]["model_id"] = "claude-haiku-4-5-20251001"
    rec["usage"].update({
        "input_tokens": 1000, "output_tokens": 1000, "cached_tokens": 0,
        "estimated_cost_usd": est.cost_usd * 5,  # 400% off
        "cost_is_estimate": False,
    })
    rec["scores"]["recovery"] = {"verdict": "not_recovered"}
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert _fail_rules_fired(by_name) == {"R8_cost_price_mismatch"}


def test_r11_confidence_out_of_range(tmp_path):
    """Out-of-range confidence fires R11 (INFO); in-range does not."""
    rec = _base()
    rec["submission"]["confidence"] = 1.5  # stored raw, un-clamped
    by_name, fail_count = _write_and_audit(tmp_path, rec)
    assert by_name["R11_confidence_out_of_range"]["count"] == 1
    assert by_name["R11_confidence_out_of_range"]["severity"] == "INFO"
    assert fail_count == 0  # INFO does not fail


def test_r11_in_range_confidence_ok(tmp_path):
    rec = _base()
    rec["submission"]["confidence"] = 0.8
    by_name, _ = _write_and_audit(tmp_path, rec)
    assert by_name["R11_confidence_out_of_range"]["count"] == 0


def test_assert_clean_refuses_on_fail(tmp_path):
    rec = _base(submission=None)  # fires R2 (FAIL)
    _write_and_audit(tmp_path, rec)
    with pytest.raises(RuntimeError, match="refusing to aggregate"):
        assert_clean_for_aggregation(tmp_path, force=False)
    # force=True does not raise.
    assert_clean_for_aggregation(tmp_path, force=True)
