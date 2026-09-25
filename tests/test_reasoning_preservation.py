"""Reasoning preservation across tool calls (STAGE4; LIMITATIONS L32).

Both providers require the model's prior reasoning to be passed back with tool results and silently
continue WITHOUT it otherwise:
- Anthropic: thinking blocks must be passed back "complete and unmodified" (else the API "silently
  disables thinking" for the continuation) — Sonnet 5 / Opus 5.5 think by default;
- OpenAI: "any reasoning items returned in model responses with tool calls must also be passed back
  with tool call outputs" — H8's Luna ReAct ran with them dropped.

These tests drive the REAL agents against mocked HTTP APIs and inspect the SERIALIZED second request:
the first response's thinking block (with its signature) / reasoning item (with encrypted_content)
must reappear in it byte-for-byte. Plus the adapter request shapes (temperature / effort / thinking),
the live ``reasoning_check``, and the price entries.
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic
import httpx
import openai
import pytest

from agents.llm_agent import LLMAgent, count_reasoning_blocks
from agents.static_agent import StaticContextAgent
from harness.llm.anthropic_client import AnthropicClient, model_caps
from harness.llm.openai_client import OpenAIClient, to_responses_input
from harness.tools.tool_context import ToolContext
from harness.tools.tools import register_all_tools

CASE = Path(__file__).resolve().parent / "fixtures" / "cases_public" / "case_0001"


@pytest.fixture(autouse=True)
def _offline_keys(monkeypatch):
    """SDK clients construct offline from placeholder keys; every request hits a MockTransport."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")


SIG = "EqoBCkgIARABGAIiQGr9xU0signature-must-survive"
THINKING = {"type": "thinking", "thinking": "", "signature": SIG}
ENC = "gAAAAABencrypted-reasoning-must-survive"


def _blank_record():
    return {"model": {}, "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                                   "cached_tokens": 0, "cache_write_tokens": 0,
                                   "max_tokens_truncations": 0},
            "llm_transcript": []}


def _tools():
    t = ToolContext(CASE)
    register_all_tools(t)
    return t


# ---- Anthropic ------------------------------------------------------------------------------------

def _anthropic_responses():
    usage = {"input_tokens": 10, "output_tokens": 5}
    first = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
             "content": [THINKING, {"type": "text", "text": "Checking the config."},
                         {"type": "tool_use", "id": "tu1", "name": "read_config", "input": {}}],
             "stop_reason": "tool_use", "stop_sequence": None, "usage": usage}
    second = {"id": "m2", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
              "content": [{"type": "thinking", "thinking": "", "signature": SIG + "-2"},
                          {"type": "tool_use", "id": "tu2", "name": "submit",
                           "input": {"diagnosis": {"detected": True, "operator_class": "x"},
                                     "evidence_refs": []}}],
              "stop_reason": "tool_use", "stop_sequence": None, "usage": usage}
    return [first, second]


def _anthropic_client(model, sent, responses, **kw):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=queue.pop(0))
    c = AnthropicClient(model=model, **kw)
    c._client = anthropic.Anthropic(api_key="test",
                                   http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return c


def test_react_passes_thinking_block_back_unchanged():
    sent = []
    client = _anthropic_client("claude-sonnet-5", sent, _anthropic_responses(), effort="medium")
    agent = LLMAgent(client, model_id="claude-sonnet-5", anchor="off")
    rec = _blank_record()
    agent.set_record(rec)
    agent.run(CASE, _tools())
    assert len(sent) == 2
    assistant = [m for m in sent[1]["messages"] if m["role"] == "assistant"][0]
    assert assistant["content"][0] == THINKING            # first block, byte-for-byte, signature intact
    assert [b["type"] for b in assistant["content"]] == ["thinking", "text", "tool_use"]
    calls = rec["llm_transcript"]
    assert calls[0]["reasoning_blocks"] == 1 and calls[0]["replayed_reasoning_blocks"] == 0
    assert calls[1]["reasoning_blocks"] == 1 and calls[1]["replayed_reasoning_blocks"] == 1
    assert rec["model"]["effort"] == "medium"
    assert rec["model"]["temperature"] == "model default (not settable)"


def test_static_followup_passes_thinking_block_back_unchanged():
    sent = []
    first = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
             "content": [THINKING, {"type": "text", "text": "Let me think."}],
             "stop_reason": "end_turn", "stop_sequence": None,
             "usage": {"input_tokens": 10, "output_tokens": 5}}
    second = _anthropic_responses()[1]
    client = _anthropic_client("claude-opus-5-5", sent, [first, second])
    agent = StaticContextAgent(client, model_id="claude-opus-5-5", anchor="off")
    agent.set_record(_blank_record())
    agent.run(CASE, _tools())
    assistant = [m for m in sent[1]["messages"] if m["role"] == "assistant"][0]
    assert assistant["content"][0] == THINKING


@pytest.mark.parametrize("model,temp_sent", [("claude-haiku-4-5-20251001", True),
                                              ("claude-sonnet-5", False), ("claude-opus-5-5", False)])
def test_temperature_only_where_accepted(model, temp_sent):
    kw = AnthropicClient(model=model).request_kwargs([], [], 100)
    assert ("temperature" in kw) is temp_sent


def test_effort_and_thinking_request_shape_and_validation():
    kw = AnthropicClient(model="claude-sonnet-5", effort="medium", thinking="disabled").request_kwargs([], [], 100)
    assert kw["output_config"] == {"effort": "medium"} and kw["thinking"] == {"type": "disabled"}
    assert "output_config" not in AnthropicClient(model="claude-sonnet-5").request_kwargs([], [], 100)
    with pytest.raises(ValueError):
        AnthropicClient(model="claude-opus-5-5", thinking="disabled")      # always on → 400 upstream
    with pytest.raises(ValueError):
        AnthropicClient(model="claude-haiku-4-5-20251001", effort="low")   # no effort on Haiku 4.5
    assert model_caps("claude-opus-5-5")["default_effort"] == "medium"


# ---- OpenAI ---------------------------------------------------------------------------------------

def _openai_responses():
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "input_tokens_details": {"cached_tokens": 0},
             "output_tokens_details": {"reasoning_tokens": 3}}
    base = {"object": "response", "created_at": 0, "model": "gpt-5.6-luna", "status": "completed",
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [], "usage": usage}
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": ENC}
    first = {**base, "id": "resp_1", "output": [
        reasoning,
        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "read_config",
         "arguments": "{}", "status": "completed"}]}
    second = {**base, "id": "resp_2", "output": [
        {"type": "reasoning", "id": "rs_2", "summary": [], "encrypted_content": ENC + "-2"},
        {"type": "function_call", "id": "fc_2", "call_id": "call_2", "name": "submit",
         "arguments": json.dumps({"diagnosis": {"detected": True, "operator_class": "x"},
                                  "evidence_refs": []}), "status": "completed"}]}
    return [first, second], reasoning


def test_openai_react_replays_reasoning_items_and_is_stateless():
    (r1, r2), reasoning = _openai_responses()
    queue, sent = [r1, r2], []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=queue.pop(0))
    client = OpenAIClient(model="gpt-5.6-luna", reasoning_effort="medium")
    client._client = openai.OpenAI(api_key="test",
                                   http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    agent = LLMAgent(client, model_id="gpt-5.6-luna", provider="openai", anchor="off")
    rec = _blank_record()
    agent.set_record(rec)
    agent.run(CASE, _tools())
    assert len(sent) == 2
    assert sent[0]["store"] is False and "reasoning.encrypted_content" in sent[0]["include"]
    replayed = [i for i in sent[1]["input"] if i.get("type") == "reasoning"]
    assert replayed == [reasoning]                                  # verbatim, encrypted_content intact
    calls = [i for i in sent[1]["input"] if i.get("type") == "function_call"]
    assert [c["call_id"] for c in calls] == ["call_1"]              # not duplicated by a rebuild
    outputs = [i for i in sent[1]["input"] if i.get("type") == "function_call_output"]
    assert [o["call_id"] for o in outputs] == ["call_1"]
    assert rec["llm_transcript"][1]["replayed_reasoning_blocks"] == 1
    assert rec["llm_transcript"][0]["usage"]["reasoning_tokens"] == 3


def test_rebuilt_turns_still_translate_for_clients_without_native_blocks():
    msgs = [{"role": "user", "content": "p"},
            {"role": "assistant", "content": [{"type": "text", "text": "t"},
                                              {"type": "tool_use", "id": "c1", "name": "f", "input": {}}]}]
    items = to_responses_input(msgs)
    assert [i.get("type", i.get("role")) for i in items] == ["user", "assistant", "function_call"]


def test_count_reasoning_blocks():
    msgs = [{"role": "user", "content": "p"},
            {"role": "assistant", "content": [THINKING, {"type": "redacted_thinking", "data": "x"}]},
            {"role": "assistant", "content": [{"type": "openai_output_items",
                                               "items": [{"type": "reasoning"}, {"type": "message"}]}]}]
    assert count_reasoning_blocks(msgs) == 3


# ---- live reasoning check -------------------------------------------------------------------------

def _trial(run_id, calls):
    return {"run_id": run_id, "llm_transcript": [
        {"reasoning_blocks": rb, "replayed_reasoning_blocks": rp} for rb, rp in calls]}


def test_reasoning_check_statuses():
    from harness.sweep import REASONING_CHECK_TRIALS, reasoning_check
    good = [_trial(f"g{i}", [(1, 0), (1, 1), (0, 2)]) for i in range(REASONING_CHECK_TRIALS)]
    assert reasoning_check(good)["status"] == "passed"
    dropped = good[:2] + [_trial("bad", [(1, 0), (1, 0)])]           # the H8 bug shape
    r = reasoning_check(dropped)
    assert r["status"] == "failed" and r["dropped_run_ids"] == ["bad"]
    never_again = [_trial(f"n{i}", [(1, 0), (0, 1), (0, 1)]) for i in range(REASONING_CHECK_TRIALS)]
    assert reasoning_check(never_again)["status"] == "failed"         # thinking never recurs
    assert reasoning_check(good[:2])["status"] == "pending"
    assert reasoning_check([_trial("h", [(0, 0), (0, 0)])])["status"] == "not_applicable"  # Haiku, no thinking


# ---- sweep factory + price table ------------------------------------------------------------------

def test_sweep_passes_cell_reasoning_settings():
    from harness.sweep import _make_client
    c = _make_client("anthropic", "claude-sonnet-5", effort="medium", thinking="disabled")
    assert c.effort == "medium" and c.thinking == "disabled"
    assert _make_client("anthropic", "claude-haiku-4-5-20251001").effort is None     # Part 1 unchanged
    assert _make_client("openai", "gpt-5.6-luna", effort="none")._reasoning_effort == "none"
    assert _make_client("openai", "gpt-5.6-luna")._reasoning_effort == "medium"    # Part 1 unchanged
    with pytest.raises(ValueError):
        _make_client("openai", "gpt-6-sol", thinking="disabled")


def test_price_entries_for_part2_models():
    from harness.pricing import _PRICE_TABLE
    assert _PRICE_TABLE["claude-opus-5-5"] == {"input": 4.0, "output": 20.0, "cached_input": 0.20, "cache_write": 5.0}
    assert _PRICE_TABLE["gpt-6-luna"]["output"] == 0.50 and _PRICE_TABLE["gpt-6-sol"]["input"] == 2.0
