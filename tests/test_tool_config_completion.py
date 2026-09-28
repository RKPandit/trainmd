"""Effective tool configuration + completion status per trial (reviewer fix 2, 2026-09-27; record schema 1.3).

Part 1's strict-mode claim rests on OBSERVED behaviour (unparseable / truncated submit calls), not on a
missing flag; these fields make both the configuration actually sent and the observed completion explicit.
"""
from __future__ import annotations

from types import SimpleNamespace

from agents.llm_agent import SUBMIT_SCHEMA, TOOLS_SCHEMA
from harness.llm.openai_client import OpenAIClient, parse_responses
from harness.provenance import completion_summary


def _oa(strict, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    return OpenAIClient(model="gpt-5.6-luna", reasoning_effort="medium", strict_tools=strict)


def test_openai_tool_config_states_strict_and_hashes_the_payload_sent(monkeypatch):
    s, o = _oa(True, monkeypatch).tool_config(TOOLS_SCHEMA), _oa(False, monkeypatch).tool_config(TOOLS_SCHEMA)
    assert s["api"] == o["api"] == "openai.responses"
    assert s["strict"] is True and o["strict"] is False            # recorded either way, never omitted
    assert s["schema_form"].startswith("closed") and o["schema_form"].startswith("canonical")
    assert s["tools_sha256"] != o["tools_sha256"]
    assert _oa(True, monkeypatch).tool_config(TOOLS_SCHEMA) == s   # deterministic
    assert _oa(True, monkeypatch).tool_config([SUBMIT_SCHEMA])["tools_sha256"] != s["tools_sha256"]


def test_anthropic_tool_config_is_never_strict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    from harness.llm.anthropic_client import AnthropicClient
    c = AnthropicClient(model="claude-haiku-4-5-20251001").tool_config(TOOLS_SCHEMA)
    assert c["api"] == "anthropic.messages" and c["strict"] is False and c["tools_sha256"].startswith("sha256:")


def _resp(status, reason=None, arguments='{"diagnosis": {"detected": true}}'):
    item = SimpleNamespace(type="function_call", call_id="c1", name="submit", arguments=arguments,
                           model_dump=lambda exclude_none=True: {"type": "function_call"})
    usage = SimpleNamespace(input_tokens=5, output_tokens=2, input_tokens_details=None, output_tokens_details=None)
    return SimpleNamespace(output=[item], status=status, usage=usage, model="m", id="r",
                           incomplete_details=SimpleNamespace(reason=reason) if reason else None)


def test_openai_parse_keeps_the_provider_completion_status_verbatim():
    ok = parse_responses(_resp("completed"))
    assert ok.raw["completion"] == {"status": "completed", "incomplete_reason": None}
    cut = parse_responses(_resp("incomplete", "max_output_tokens", arguments='{"diagnosis": {"det'))
    assert cut.stop_reason == "max_tokens"
    assert cut.raw["completion"] == {"status": "incomplete", "incomplete_reason": "max_output_tokens"}


def test_completion_summary_from_observed_transcript():
    rec = {"llm_transcript": [
        {"stop_reason": "tool_use", "tool_calls": [{"name": "read_log", "arguments": {}}]},
        {"stop_reason": "max_tokens", "completion": {"status": "incomplete"},
         "tool_calls": [{"name": "submit", "arguments": '{"diagnosis": {"det'}]}]}
    assert completion_summary(rec) == {"llm_calls": 2, "incomplete_calls": 1, "final_stop_reason": "max_tokens",
                                       "submit_called": True, "submit_parsed": False}
    rec["llm_transcript"][1] = {"stop_reason": "tool_use",
                                "tool_calls": [{"name": "submit", "arguments": {"diagnosis": {}}}]}
    assert completion_summary(rec)["submit_parsed"] is True and completion_summary(rec)["incomplete_calls"] == 0
    assert completion_summary({}) == {"llm_calls": 0, "incomplete_calls": 0, "final_stop_reason": None,
                                      "submit_called": False, "submit_parsed": False}
