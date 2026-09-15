"""Part-B tests (STAGE3_PLAN §0.3): the records release is a WALL, not a hope.

- a planted hidden value in a record -> export fails naming it;
- a trusted probe record -> excluded from the primary release;
- the allowlist rejects an unknown top-level field rather than passing it through.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("export_release", ROOT / "scripts" / "export_release.py")
exp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp)

_FAULTY_VALUE = 0.812345  # a "hidden" number for the fixture


def _mk_root(tmp: Path, *, trusted=False, extra_field=False, leak=False) -> Path:
    cid = "case_0001"
    (tmp / "cases" / cid / "hidden").mkdir(parents=True)
    (tmp / "results" / cid / "trials").mkdir(parents=True)
    (tmp / "sweeps").mkdir(parents=True)
    (tmp / "cases" / cid / "hidden" / "verify.yaml").write_text(yaml.dump({
        "faulty_value": _FAULTY_VALUE, "tolerance_lower": 0.80,
        "reference_metric_mean": 0.85, "reference_metric_std": 0.01,
        "hidden_eval_seeds": [100, 101, 102]}))
    (tmp / "cases" / cid / "hidden" / "card.hidden.yaml").write_text(yaml.dump({
        "operator_id": "silent.data_leakage.v1", "layer": "dynamics", "strength": "moderate",
        "seed": 42, "case_build_id": "bid", "symptom_direction": "positive",
        "visible_sigma_distance": -5.0, "hidden_sigma_distance": -3.0,
        "accepted_classes": ["data_leakage"], "faulty_visible_value": 0.90}))
    (tmp / "cases" / cid / "card.public.yaml").write_text(yaml.dump({"case_id": cid}))
    rec = {
        "case_id": cid, "run_id": "r1", "trusted": trusted, "card_superseded": False,
        "conditions": {"sweep_name": "s", "agent_type": "react", "anchor": "off", "repeat_index": 0},
        "submission": {"diagnosis": {"detected": True}},
        "scores": {"detection": {"correct": True}, "identification": {"correct": True},
                   "evidence": {"f1": 1.0},
                   "recovery": {"verdict": "recovered", "compute_sec": 1.0,
                                "per_seed_hidden_metrics": [{"metric_hidden_test_acc": _FAULTY_VALUE}]}},
        "tool_transcript": [], "llm_transcript": [], "usage": {"estimated_cost_usd": 0.01},
        "model": {"model_id": "m"}, "environment": {}, "prompt": {"text": "p"},
    }
    if leak:  # plant the hidden faulty_value into an agent-visible field
        rec["tool_transcript"] = [{"result": f"observed {_FAULTY_VALUE:.6f} somewhere"}]
    if extra_field:
        rec["secret_field"] = "surprise"
    (tmp / "results" / cid / "trials" / "t1.yaml").write_text(yaml.dump(rec))
    return tmp


def test_clean_export_succeeds_and_strips_hidden_metrics(tmp_path):
    _mk_root(tmp_path)
    r = exp.export(tmp_path, "s")
    assert r["n_trials"] == 1
    import json
    trial = json.loads(next((r["out_dir"] / "trials").glob("*.json")).read_text())
    # per_seed_hidden_metrics (hidden values) stripped from the exported recovery block
    assert "per_seed_hidden_metrics" not in trial["scores"]["recovery"]
    assert trial["scores"]["recovery"]["verdict"] == "recovered"


def test_planted_hidden_value_fails_export(tmp_path):
    _mk_root(tmp_path, leak=True)
    with pytest.raises(SystemExit) as e:
        exp.export(tmp_path, "s")
    assert "faulty_value" in str(e.value) and f"{_FAULTY_VALUE:.6f}" in str(e.value)


def test_trusted_record_excluded_by_default(tmp_path):
    _mk_root(tmp_path, trusted=True)
    r = exp.export(tmp_path, "s")
    assert r["n_trials"] == 0
    assert r["n_probes_excluded_or_segregated"] == 1
    assert not list((r["out_dir"] / "trials").glob("*.json"))


def test_allowlist_rejects_unknown_field(tmp_path):
    _mk_root(tmp_path, extra_field=True)
    with pytest.raises(SystemExit) as e:
        exp.export(tmp_path, "s")
    assert "secret_field" in str(e.value)
