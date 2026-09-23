"""STAGE4_PLAN 4.0.6 / Stage 3 mandate: missing tool fields score as EMPTY, never crash.

Covers every schema-required submit field (``diagnosis``, ``evidence_refs``,
``diagnosis.detected``, ``diagnosis.operator_class``) on faulty AND control cases, the
tool-layer argument check (unknown / missing required arguments are a logged tool error for
every tool), and both agents' handling.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.scoring import score_detection, score_identification
from harness.tools.tool_context import ToolContext
from harness.tools.tools import register_all_tools

FAULTY = {"layer": "dynamics", "operator_id": "silent.lr_warmup.v1",
          "accepted_classes": ["lr_warmup", "learning_rate"]}
CONTROL = {"layer": "control", "operator_id": "control.healthy.v1",
           "accepted_classes": ["none", "healthy", "no_incident", "no_fault", "nothing_wrong"]}


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


# ---- tool layer ---------------------------------------------------------------------------------

@pytest.mark.parametrize("args,missing", [
    ({"evidence_refs": []}, ["diagnosis", "diagnosis.detected", "diagnosis.operator_class"]),
    ({"diagnosis": {"detected": True, "operator_class": "lr"}}, ["evidence_refs"]),
    ({"diagnosis": {"operator_class": "lr"}, "evidence_refs": []}, ["diagnosis.detected"]),
    ({"diagnosis": {"detected": True}, "evidence_refs": []}, ["diagnosis.operator_class"]),
    ({"diagnosis": {"detected": False, "operator_class": None}, "evidence_refs": []},
     ["diagnosis.operator_class"]),
    ({}, ["diagnosis", "evidence_refs", "diagnosis.detected", "diagnosis.operator_class"]),
])
def test_submit_accepts_missing_fields_and_records_them(ctx, args, missing):
    result = ctx.call("submit", **args)
    assert result["status"] == "ok" and result["missing_fields"] == missing
    sub = ctx.submission
    assert sub["missing_fields"] == missing
    assert isinstance(sub["diagnosis"], dict) and isinstance(sub["evidence_refs"], list)


def test_complete_submission_has_no_missing_fields(ctx):
    result = ctx.call("submit", diagnosis={"detected": False, "operator_class": "none"},
                      evidence_refs=[])
    assert result == {"status": "ok", "submitted": True}
    assert "missing_fields" not in ctx.submission


def test_unknown_argument_is_a_logged_tool_error_not_an_exception(ctx):
    result = ctx.call("submit", diagnosis={"detected": True, "operator_class": "x"},
                      evidence_refs=[], bogus=1)
    assert result["status"] == "error" and result["error"] == "INVALID_ARGUMENTS"
    assert ctx.submission is None
    last = ctx.transcript[-1]                # the failed call IS in the transcript
    assert last["tool_name"] == "submit" and last["result"]["error"] == "INVALID_ARGUMENTS"
    assert ctx.budget_remaining == 9         # a rejected call still counts against the budget


def test_argument_check_applies_to_every_tool(ctx):
    result = ctx.call("list_files", not_an_argument="x")
    assert result["error"] == "INVALID_ARGUMENTS"


# ---- scoring layer ------------------------------------------------------------------------------

@pytest.mark.parametrize("card", [FAULTY, CONTROL], ids=["faulty", "control"])
@pytest.mark.parametrize("diagnosis", [None, {}, {"operator_class": "lr"}, {"detected": None}, "garbage"])
def test_missing_detected_is_incorrect_on_every_tier(card, diagnosis):
    sub = {"evidence_refs": []} if diagnosis is None else {"diagnosis": diagnosis, "evidence_refs": []}
    det = score_detection(sub, card)
    assert det["correct"] is False and det["detected_predicted"] is None and det["missing_field"]


@pytest.mark.parametrize("card", [FAULTY, CONTROL], ids=["faulty", "control"])
@pytest.mark.parametrize("cls", ["<absent>", None, "", "   ", 7])
def test_missing_operator_class_scores_empty(card, cls):
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


def test_missing_evidence_and_repair_score_as_empty():
    from harness.scoring import _evidence_refs, _score_no_unnecessary_repair
    assert _evidence_refs({}) == [] and _evidence_refs({"evidence_refs": None}) == []
    # control: no repair submitted → no false intervention
    assert _score_no_unnecessary_repair({"diagnosis": {}})["false_intervention"] is False


# ---- agents (need a built case) -----------------------------------------------------------------

CASES = Path(__file__).resolve().parent.parent / "cases"


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


def _static(arguments):
    from agents.static_agent import StaticContextAgent
    case_dir, tools = _built()
    agent = StaticContextAgent(_Client([_response(arguments)]), model_id="fake")
    rec = {"model": {}, "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                                  "cached_tokens": 0, "max_tokens_truncations": 0},
           "llm_transcript": []}
    agent.set_record(rec)
    agent.run(case_dir, tools)
    return tools, rec


def test_static_agent_missing_evidence_refs_no_longer_crashes():
    tools, rec = _static({"diagnosis": {"detected": True, "operator_class": "lr"}})
    assert rec["termination_reason"] == "submitted"
    assert tools.submission["missing_fields"] == ["evidence_refs"]


def test_static_agent_unknown_argument_is_submit_rejected():
    tools, rec = _static({"diagnosis": {"detected": True, "operator_class": "lr"},
                          "evidence_refs": [], "extra": 1})
    assert rec["termination_reason"] == "submit_rejected" and tools.submission is None
