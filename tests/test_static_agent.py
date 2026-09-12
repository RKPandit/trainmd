"""StaticContextAgent — the H6 control baseline (spec §8).

Zero API cost (FakeLLMClient / a capturing stub).  Proves: one call + one submit;
bounded no-submit follow-up then None; full context assembled through the SEALED
tool layer (tagged context_assembly) with the size cap; budget exhaustion is a
HARD FAIL (never diagnose on partial context); and the shared prompt sections are
byte-identical to the ReAct prompt (differ ONLY in investigation mode).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agents.llm_agent import (
    HEALTHY_RUNS_TEXT,
    SUBMIT_FORMAT_TEXT,
    _build_system_prompt,
    reference_band_line,
)
from agents.static_agent import StaticContextAgent
from harness.llm.client import LLMResponse, ToolCallRequest, Usage
from harness.tools.tool_context import ToolContext
from harness.tools.tools import register_all_tools

CASES = Path(__file__).resolve().parent.parent / "cases"


class CapturingClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self._i = 0
        self.calls = []

    def complete(self, messages, tools_schema, *, max_tokens=4096):
        self.calls.append({"messages": messages, "tools": tools_schema})
        resp = self._responses[self._i]
        self._i += 1
        return resp


def _submit_response(*, detected=True, cls="lr_misconfiguration",
                     refs=None, repair=None, stop_reason="tool_use"):
    return LLMResponse(
        text="Here is my diagnosis.",
        tool_calls=[ToolCallRequest(id="s1", name="submit", arguments={
            "diagnosis": {"detected": detected, "operator_class": cls},
            "evidence_refs": refs or [],
            "repair_spec": repair,
        })],
        stop_reason=stop_reason,
        usage=Usage(input_tokens=1500, output_tokens=80),
    )


def _no_submit(stop_reason="end_turn"):
    return LLMResponse(text="thinking...", tool_calls=[], stop_reason=stop_reason,
                       usage=Usage(input_tokens=1500, output_tokens=20))


def _blank_record():
    return {
        "model": {},
        "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                  "cached_tokens": 0, "max_tokens_truncations": 0},
        "llm_transcript": [],
    }


def _tools(case_name):
    case_dir = CASES / case_name
    if not case_dir.exists():
        pytest.skip(f"{case_name} not built")
    tools = ToolContext(case_dir)
    register_all_tools(tools)
    return case_dir, tools


def _run(case_name, client, *, max_log_chars=20000):
    case_dir, tools = _tools(case_name)
    agent = StaticContextAgent(client, model_id="fake", max_log_chars=max_log_chars)
    rec = _blank_record()
    agent.set_record(rec)
    agent.run(case_dir, tools)
    return case_dir, tools, rec, agent


class TestSubmitOnce:

    def test_single_call_single_submit(self):
        client = CapturingClient([_submit_response()])
        _, tools, rec, _ = _run("case_0001", client)
        assert tools.submission is not None
        assert rec["usage"]["llm_calls"] == 1
        assert len(client.calls) == 1
        # The model was given only the submit tool.
        assert [t["name"] for t in client.calls[0]["tools"]] == ["submit"]


class TestNoSubmitFollowup:

    def test_followup_then_none(self):
        client = CapturingClient([_no_submit(), _no_submit()])
        _, tools, rec, _ = _run("case_0001", client)
        assert tools.submission is None
        assert rec["usage"]["llm_calls"] == 2
        # The second call carries the bounded follow-up.
        second = client.calls[1]["messages"]
        assert any("You must call submit now." in m.get("content", "")
                   for m in second if isinstance(m.get("content"), str))


class TestContextAssembly:

    def test_all_artifacts_and_headers(self):
        client = CapturingClient([_submit_response()])
        _, _, _, _ = _run("case_0001", client)
        content = client.calls[0]["messages"][0]["content"]
        for header in ["### config.yaml", "### config.resolved.yaml", "### train.py",
                       "### datautil.py", "### metrics.jsonl", "### logs/stdout.log"]:
            assert header in content, f"missing section {header}"
        # train.py delivered in full (a late-file marker is present).
        assert "SageMaker-compatible" in content or "def main" in content

    def test_log_cap_applied(self):
        client = CapturingClient([_submit_response()])
        _, _, rec, _ = _run("case_0001", client, max_log_chars=200)
        assert rec["static_context"]["any_truncated"] is True
        assert "logs/stdout.log" in rec["static_context"]["truncated_artifacts"]
        content = client.calls[0]["messages"][0]["content"]
        assert "…[truncated" in content


class TestSealedReads:

    def test_reads_are_tool_calls_tagged_assembly(self):
        client = CapturingClient([_submit_response()])
        _, tools, rec, _ = _run("case_0001", client)
        transcript = tools.transcript
        read_calls = [t for t in transcript if t["tool_name"] in
                      ("read_code", "read_log", "query_metrics")]
        assert read_calls, "no sealed read tool calls"
        assert all(t["phase"] == "context_assembly" for t in read_calls)
        assert rec["static_context"]["assembly_tool_calls"] == \
            sum(1 for t in transcript if t["phase"] == "context_assembly")

    def test_outside_workspace_refused(self):
        _, tools = _tools("case_0001")
        res = tools.call("read_code", path="../../hidden/verify.yaml")
        assert res["status"] == "error"
        assert res["error"] == "INVALID_PATH"


class TestBudgetHardFail:

    def test_budget_exhaustion_aborts_without_model_call(self):
        """Planted tiny budget → assembly runs out → abort, no partial-context call."""
        case_dir, tools = _tools("case_0001")
        tools._max_tool_calls = 3  # exhaust mid-assembly
        client = CapturingClient([_submit_response()])  # must NOT be consumed
        agent = StaticContextAgent(client, model_id="fake")
        rec = _blank_record()
        agent.set_record(rec)
        agent.run(case_dir, tools)

        assert tools.submission is None
        assert len(client.calls) == 0, "made a model call on partial context"
        assert rec["static_context"]["assembly_failed"]
        assert rec["usage"]["llm_calls"] == 0


class TestVerbatimSharedSections:

    def test_shared_sections_identical_to_react(self):
        case_dir, _ = _tools("case_0001")
        react_prompt = _build_system_prompt(case_dir)
        agent = StaticContextAgent(CapturingClient([]), model_id="fake")
        static_prompt = agent._system_prompt(case_dir)
        card = yaml.safe_load((case_dir / "card.public.yaml").read_text())
        band = reference_band_line(card)

        for text in (HEALTHY_RUNS_TEXT, SUBMIT_FORMAT_TEXT, band):
            assert text in react_prompt
            assert text in static_prompt


class TestCaptureFields:

    def test_termination_submitted(self):
        _, _, rec, _ = _run("case_0001", CapturingClient([_submit_response()]))
        assert rec["termination_reason"] == "submitted"

    def test_termination_no_submit_after_followup(self):
        _, _, rec, _ = _run("case_0001", CapturingClient([_no_submit(), _no_submit()]))
        assert rec["termination_reason"] == "no_submit_after_followup"

    def test_termination_assembly_failed(self):
        case_dir, tools = _tools("case_0001")
        tools._max_tool_calls = 3
        rec = _blank_record()
        agent = StaticContextAgent(CapturingClient([_submit_response()]), model_id="fake")
        agent.set_record(rec)
        agent.run(case_dir, tools)
        assert rec["termination_reason"] == "assembly_failed"

    def test_prompt_block_recorded(self):
        _, _, rec, _ = _run("case_0001", CapturingClient([_submit_response()]))
        assert rec["prompt"]["prompt_version"] == "static-1"
        assert rec["prompt"]["system_prompt_text"]
        assert len(rec["prompt"]["prompt_hash"]) == 64

    def test_transcript_has_api_model_and_latency(self):
        _, _, rec, _ = _run("case_0001", CapturingClient([_submit_response()]))
        entry = rec["llm_transcript"][0]
        assert "api_model" in entry           # None for the fake client
        assert isinstance(entry["latency_sec"], float)

    def test_confidence_rationale_stored_raw(self):
        resp = LLMResponse(
            text="done",
            tool_calls=[ToolCallRequest(id="s1", name="submit", arguments={
                "diagnosis": {"detected": True, "operator_class": "lr_misconfiguration"},
                "evidence_refs": [],
                "repair_spec": None,
                "confidence": 1.5,          # deliberately out of range — stored raw
                "rationale": "high lr",
            })],
            stop_reason="tool_use",
            usage=Usage(input_tokens=1500, output_tokens=40),
        )
        _, tools, _, _ = _run("case_0001", CapturingClient([resp]))
        assert tools.submission["confidence"] == 1.5  # not clamped
        assert tools.submission["rationale"] == "high lr"


class TestControlCase:

    def test_no_repair_submission_on_control(self):
        client = CapturingClient([
            _submit_response(detected=False, cls="none", refs=[], repair=None),
        ])
        _, tools, _, _ = _run("case_0005", client)
        assert tools.submission is not None
        assert tools.submission["diagnosis"]["detected"] is False
        assert tools.submission["repair_spec"] is None
