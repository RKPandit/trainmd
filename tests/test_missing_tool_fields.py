"""STAGE4_PLAN 4.0.6 / Stage 3 mandate: a submit is ALWAYS ACCEPTED; missing fields score EMPTY.

Contract (author's review of #35):
- a submit missing a schema-required field is accepted with that field EMPTY — never rejected as a
  non-submission — and the axes are scored INDEPENDENTLY (no evidence ⇒ evidence F1 = 0, while a
  correct diagnosis keeps its detection and identification credit);
- unknown extra arguments are IGNORED;
- the tool result is identical either way (no error to retry), so the SAME slip costs a ReAct agent
  and a static agent exactly the same — both agents are tested on the same slips;
- the trial records a compliance flag (``compliance.missing_fields`` / ``ignored_fields``) so
  compliance is reported separately from diagnosis.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.scoring import score_detection, score_evidence, score_identification
from harness.tools.tool_context import ToolContext
from harness.tools.tools import register_all_tools

FAULTY = {"layer": "dynamics", "operator_id": "silent.lr_warmup.v1",
          "accepted_classes": ["lr_warmup", "learning_rate"]}
CONTROL = {"layer": "control", "operator_id": "control.healthy.v1",
           "accepted_classes": ["none", "healthy", "no_incident", "no_fault", "nothing_wrong"]}
OK = {"status": "ok", "submitted": True}


@pytest.fixture
def ctx(tmp_path):
    """A minimal case: just the public card the ToolContext reads (no build needed)."""
    (tmp_path / "workspace").mkdir()
    (tmp_path / "card.public.yaml").write_text(yaml.safe_dump({
        "permitted_tools": ["submit", "list_files"],
        "agent_budget": {"max_tool_calls": 10, "max_submissions": 1},
    }))
    tc = ToolContext(tmp_path)
    register_all_tools(tc)
    return tc


# ---- tool layer: always accepted, identical result, compliance recorded ------------------------

@pytest.mark.parametrize("args,missing", [
    ({"evidence_refs": []}, ["diagnosis", "diagnosis.detected", "diagnosis.operator_class"]),
    ({"diagnosis": {"detected": True, "operator_class": "lr"}}, ["evidence_refs"]),
    ({"diagnosis": {"operator_class": "lr"}, "evidence_refs": []}, ["diagnosis.detected"]),
    ({"diagnosis": {"detected": True}, "evidence_refs": []}, ["diagnosis.operator_class"]),
    ({"diagnosis": {"detected": False, "operator_class": None}, "evidence_refs": []},
     ["diagnosis.operator_class"]),
    ({"diagnosis": "garbage", "evidence_refs": "also garbage"},
     ["diagnosis", "evidence_refs", "diagnosis.detected", "diagnosis.operator_class"]),
    ({}, ["diagnosis", "evidence_refs", "diagnosis.detected", "diagnosis.operator_class"]),
])
def test_missing_fields_accepted_empty_and_recorded(ctx, args, missing):
    assert ctx.call("submit", **args) == OK                  # identical result: nothing to retry
    sub = ctx.submission
    assert sub["missing_fields"] == missing and "ignored_fields" not in sub
    assert isinstance(sub["diagnosis"], dict) and isinstance(sub["evidence_refs"], list)


def test_unknown_extra_arguments_are_ignored_and_recorded(ctx):
    assert ctx.call("submit", diagnosis={"detected": True, "operator_class": "x"},
                    evidence_refs=[], severity="high", bogus=1) == OK
    sub = ctx.submission
    assert sub["ignored_fields"] == ["bogus", "severity"] and "missing_fields" not in sub
    assert "bogus" not in sub and sub["diagnosis"]["operator_class"] == "x"


def test_complete_submission_has_no_compliance_flags(ctx):
    assert ctx.call("submit", diagnosis={"detected": False, "operator_class": "none"},
                    evidence_refs=[]) == OK
    assert "missing_fields" not in ctx.submission and "ignored_fields" not in ctx.submission


def test_non_submit_tool_with_bad_arguments_is_a_logged_error(ctx):
    """Other tools keep the argument check: a logged, counted tool error, never an exception."""
    result = ctx.call("list_files", not_an_argument="x")
    assert result["error"] == "INVALID_ARGUMENTS"
    assert ctx.transcript[-1]["result"]["error"] == "INVALID_ARGUMENTS"
    assert ctx.budget_remaining == 9


def test_compliance_lands_on_the_trial_record(ctx):
    from harness.provenance import build_empty_record, finalize_record
    rec = build_empty_record("case_x", "a", "r1", {})
    assert rec["compliance"] is None
    ctx.call("submit", diagnosis={"detected": True, "operator_class": "x"}, extra=1)
    rec = finalize_record(rec, ctx, None, 0.0)
    assert rec["compliance"] == {"missing_fields": ["evidence_refs"], "ignored_fields": ["extra"]}


def test_compliance_is_exported():
    from scripts.export_release import _TRIAL_ALLOW
    assert "compliance" in _TRIAL_ALLOW


# ---- scoring: axes independent; empty fields score empty ---------------------------------------

def test_correct_diagnosis_without_evidence_keeps_detection_and_identification():
    sub = {"diagnosis": {"detected": True, "operator_class": "lr_warmup"}, "evidence_refs": []}
    assert score_detection(sub, FAULTY)["correct"] is True
    assert score_identification(sub, FAULTY)["correct"] is True
    ref = [{"kind": "config_key", "artifact_id": "config.yaml", "detail": {"key_path": "training.lr"}}]
    assert score_evidence([], ref)["f1"] == 0.0


@pytest.mark.parametrize("card", [FAULTY, CONTROL], ids=["faulty", "control"])
@pytest.mark.parametrize("diagnosis", [None, {}, {"operator_class": "lr"}, {"detected": None}, "garbage"])
def test_empty_detected_scores_detection_incorrect_on_every_tier(card, diagnosis):
    sub = {"evidence_refs": []} if diagnosis is None else {"diagnosis": diagnosis, "evidence_refs": []}
    det = score_detection(sub, card)
    assert det["correct"] is False and det["detected_predicted"] is None and det["missing_field"]


def test_empty_detected_does_not_cost_identification():
    sub = {"diagnosis": {"operator_class": "lr_warmup"}, "evidence_refs": []}
    assert score_detection(sub, FAULTY)["correct"] is False
    assert score_identification(sub, FAULTY)["correct"] is True


@pytest.mark.parametrize("card", [FAULTY, CONTROL], ids=["faulty", "control"])
@pytest.mark.parametrize("cls", ["<absent>", None, "", "   ", 7])
def test_empty_operator_class_scores_identification_empty(card, cls):
    diag = {"detected": True} if cls == "<absent>" else {"detected": True, "operator_class": cls}
    ident = score_identification({"diagnosis": diag, "evidence_refs": []}, card)
    assert ident["correct"] is False and ident["predicted_class"] == ""
    assert ident["missing_field"] and ident["matched_operators"] == []


def test_present_fields_score_exactly_as_before():
    sub = {"diagnosis": {"detected": False, "operator_class": "no_fault"}, "evidence_refs": []}
    assert score_detection(sub, CONTROL) == {"detected_predicted": False, "detected_actual": False,
                                             "correct": True}
    ident = score_identification(sub, CONTROL)
    assert ident["correct"] is True and "missing_field" not in ident


# ---- agents: the SAME slip is handled IDENTICALLY by ReAct and static ---------------------------

CASES = Path(__file__).resolve().parent.parent / "cases"
SLIPS = {
    "missing_evidence": ({"diagnosis": {"detected": True, "operator_class": "lr"}},
                         ["evidence_refs"], []),
    "unknown_extra": ({"diagnosis": {"detected": True, "operator_class": "lr"}, "evidence_refs": [],
                       "severity": "high"}, [], ["severity"]),
    "malformed_payload": ("not a dict",
                          ["diagnosis", "evidence_refs", "diagnosis.detected", "diagnosis.operator_class"], []),
}


def _built(case_name="case_0001"):
    case_dir = CASES / case_name
    if not (case_dir / "card.public.yaml").exists():
        pytest.skip(f"{case_name} not built")
    tools = ToolContext(case_dir)
    register_all_tools(tools)
    return case_dir, tools


def _response(arguments):
    from harness.llm.client import LLMResponse, ToolCallRequest, Usage
    return LLMResponse(text="", tool_calls=[ToolCallRequest(id="s1", name="submit", arguments=arguments)],
                       stop_reason="tool_use", usage=Usage(input_tokens=10, output_tokens=5))


class _Client:
    def __init__(self, responses):
        self._r = list(responses)

    def complete(self, messages, tools_schema, *, max_tokens=4096):
        return self._r.pop(0)


def _blank_record():
    return {"model": {}, "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                                   "cached_tokens": 0, "max_tokens_truncations": 0},
            "llm_transcript": []}


def _run(agent_cls, arguments):
    case_dir, tools = _built()
    agent = agent_cls(_Client([_response(arguments)]), model_id="fake")
    rec = _blank_record()
    agent.set_record(rec)
    agent.run(case_dir, tools)
    return tools, rec


@pytest.mark.parametrize("slip", sorted(SLIPS))
def test_react_and_static_treat_the_same_slip_identically(slip):
    from agents.llm_agent import LLMAgent
    from agents.static_agent import StaticContextAgent
    arguments, missing, ignored = SLIPS[slip]
    outcomes = []
    for cls in (LLMAgent, StaticContextAgent):
        tools, rec = _run(cls, arguments)
        sub = tools.submission
        assert sub is not None, f"{cls.__name__}: the submit was not accepted"
        assert rec["termination_reason"] == "submitted"
        outcomes.append((sub.get("missing_fields", []), sub.get("ignored_fields", []),
                         sub["diagnosis"], sub["evidence_refs"]))
    assert outcomes[0] == outcomes[1] and outcomes[0][:2] == (missing, ignored)
