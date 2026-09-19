"""OpenAI adapter tests — pure translation + parsing, zero API cost.

The adapter targets the **Responses API** (``/v1/responses``) because GPT-5.6 Luna
rejects function tools with a non-``none`` ``reasoning_effort`` on chat/completions.
The ``openai`` SDK is NOT required: every test exercises the pure translation
functions (``to_responses_input``, ``to_responses_tools``, ``parse_responses``)
with hand-built fakes.  The property these must pin: the adapter NEVER alters
prompt text and never remaps the instruction prompt off the user role — so a
second provider receives byte-identical text at the same role/position as Anthropic.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.llm_agent import SUBMIT_FORMAT_TEXT, TOOLS_SCHEMA
from harness.llm.openai_client import (
    _EFFORT_TIERS,
    check_effort,
    describe_model,
    parse_responses,
    to_responses_input,
    to_responses_tools,
)
from harness.submission_repair import recover_folded_repair_spec


# --------------------------------------------------------------------------- #
# Fake Responses object builder (mirrors the SDK's attribute shape)
# --------------------------------------------------------------------------- #

def _msg_item(text):
    return SimpleNamespace(type="message", role="assistant",
                           content=[SimpleNamespace(type="output_text", text=text)])


def _call_item(call_id, name, arguments):
    return SimpleNamespace(type="function_call", call_id=call_id, name=name,
                           arguments=arguments)


def _fake_response(*, output, status="completed", incomplete_reason=None,
                   input_tokens=11, output_tokens=7, cached_tokens=0,
                   reasoning_tokens=0, model="gpt-5.6-luna", rid="resp_abc"):
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )
    incomplete = (SimpleNamespace(reason=incomplete_reason)
                  if incomplete_reason else None)
    return SimpleNamespace(output=output, usage=usage, status=status,
                           incomplete_details=incomplete, model=model, id=rid)


# --------------------------------------------------------------------------- #
# Tool-schema translation (flat Responses shape)
# --------------------------------------------------------------------------- #

def test_tools_translation_is_flat_and_preserves_contract():
    oa = to_responses_tools(TOOLS_SCHEMA)
    assert len(oa) == len(TOOLS_SCHEMA)
    for src, dst in zip(TOOLS_SCHEMA, oa):
        assert dst["type"] == "function"
        assert dst["name"] == src["name"]          # flat, not nested under "function"
        assert dst["description"] == src["description"]
        assert dst["parameters"] == src["input_schema"]  # JSON schema verbatim
        assert "function" not in dst


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

def test_parse_text_only_end_turn():
    r = parse_responses(_fake_response(output=[_msg_item("all done")]))
    assert r.text == "all done"
    assert r.tool_calls == []
    assert r.stop_reason == "end_turn"
    assert r.usage.input_tokens == 11
    assert r.usage.output_tokens == 7


def test_parse_tool_call_arguments_are_parsed_dict():
    r = parse_responses(_fake_response(output=[
        _call_item("call_1", "read_config", json.dumps({"key_path": "training.lr"}))]))
    assert r.text is None
    assert r.stop_reason == "tool_use"
    assert len(r.tool_calls) == 1
    tc = r.tool_calls[0]
    assert tc.id == "call_1"          # paired by call_id
    assert tc.name == "read_config"
    assert tc.arguments == {"key_path": "training.lr"}


def test_parse_malformed_arguments_kept_raw_not_coerced():
    r = parse_responses(_fake_response(output=[
        _call_item("c", "read_config", "{not json")]))
    assert r.tool_calls[0].arguments == "{not json"
    assert not isinstance(r.tool_calls[0].arguments, dict)


def test_parse_incomplete_maps_to_max_tokens_and_cached():
    r = parse_responses(_fake_response(
        output=[_msg_item("cut off")], status="incomplete",
        incomplete_reason="max_output_tokens", cached_tokens=4))
    assert r.stop_reason == "max_tokens"
    assert r.usage.cached_tokens == 4


def test_parse_captures_api_model_string():
    r = parse_responses(_fake_response(output=[_msg_item("x")], model="gpt-5.6-luna"))
    assert r.raw["model"] == "gpt-5.6-luna"   # API-reported model string (provenance)


def test_parse_exposes_reasoning_tokens_in_raw():
    # Reasoning tokens are billed as output (kept in usage.output_tokens) but the
    # Responses API breaks them out; surface the breakout in raw for reporting.
    r = parse_responses(_fake_response(
        output=[_msg_item("answer")], output_tokens=50, reasoning_tokens=42))
    assert r.usage.output_tokens == 50          # reasoning already counted here
    assert r.raw["reasoning_tokens"] == 42      # ...and visible separately


# --------------------------------------------------------------------------- #
# reasoning.effort pinning + provider metadata (Luna)
# --------------------------------------------------------------------------- #

def test_effort_tiers_and_validation():
    assert _EFFORT_TIERS == ("none", "low", "medium", "high", "xhigh", "max")
    assert check_effort("medium") == "medium"
    with pytest.raises(ValueError):
        check_effort("reasonable")


def test_describe_records_effort_and_luna_metadata():
    # The client sends no temperature to a reasoning model -> recorded as None.
    d = describe_model("gpt-5.6-luna", None, "medium")
    assert d["provider"] == "openai"
    assert d["model_id"] == "gpt-5.6-luna"
    assert d["temperature"] is None
    assert d["reasoning_effort"] == "medium"
    assert d["knowledge_cutoff"] == "2026-02-16"
    assert d["context_window_tokens"] == 1_050_000
    assert d["max_output_tokens"] == 128_000
    assert d["long_context_threshold_tokens"] == 272_000
    assert d["rate_limits_tier1"] == {
        "rpm": 500, "tpm": 500_000, "batch_queue_tokens": 5_000_000}


def test_no_verbosity_param_is_pinned():
    import inspect

    import harness.llm.openai_client as oc
    assert "verbosity" not in inspect.getsource(oc.OpenAIClient.complete)
    assert "verbosity" not in describe_model("gpt-5.6-luna", None, "medium")


# --------------------------------------------------------------------------- #
# Message translation (Responses input items)
# --------------------------------------------------------------------------- #

def test_message_translation_shapes():
    messages = [
        {"role": "user", "content": "INSTRUCTION PROMPT"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "id": "t1", "name": "read_config",
             "input": {"key_path": "training.lr"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": json.dumps({"status": "ok", "value": 0.01})},
        ]},
    ]
    oa = to_responses_input(messages)
    assert oa[0] == {"role": "user", "content": "INSTRUCTION PROMPT"}
    # assistant text -> message item, then a function_call item
    assert oa[1] == {"role": "assistant", "content": "let me check"}
    assert oa[2]["type"] == "function_call"
    assert oa[2]["call_id"] == "t1"
    assert oa[2]["name"] == "read_config"
    assert json.loads(oa[2]["arguments"]) == {"key_path": "training.lr"}
    # tool result -> function_call_output paired by call_id
    assert oa[3]["type"] == "function_call_output"
    assert oa[3]["call_id"] == "t1"
    assert json.loads(oa[3]["output"]) == {"status": "ok", "value": 0.01}


# --------------------------------------------------------------------------- #
# L13: instruction stays user-role; no system/developer remap
# --------------------------------------------------------------------------- #

def test_instruction_prompt_stays_user_role_no_system_remap():
    messages = [
        {"role": "user", "content": "INSTRUCTION PROMPT (user role, position 0)"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "read_config", "input": {}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]},
    ]
    oa = to_responses_input(messages)
    assert oa[0] == {"role": "user",
                     "content": "INSTRUCTION PROMPT (user role, position 0)"}
    roles = {m.get("role") for m in oa if "role" in m}
    # Never system/developer/instructions — the prompt is a user message.
    assert not (roles & {"system", "developer", "instructions"})
    assert roles <= {"user", "assistant"}


def test_adapter_never_uses_responses_instructions_field():
    # The Responses API has a top-level `instructions` field; we must NOT use it
    # (L13 — the prompt is delivered as a user input message, not as system-level
    # instructions). Pin that complete() sends no `instructions=` argument.
    import inspect

    import harness.llm.openai_client as oc
    src = inspect.getsource(oc.OpenAIClient.complete)
    assert "instructions" not in src
    # And no translated input item is an `instructions`-typed item.
    items = to_responses_input([{"role": "user", "content": "P"}])
    assert all(m.get("type") != "instructions" for m in items)


# --------------------------------------------------------------------------- #
# Byte-identical prompt text across providers (the literal-slice guarantee)
# --------------------------------------------------------------------------- #

def _anthropic_texts(messages: list[dict]) -> list[str]:
    out: list[str] = []
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            out.append(c)
        else:
            for b in c:
                if b.get("type") == "text":
                    out.append(b["text"])
                elif b.get("type") == "tool_result":
                    out.append(b["content"])
    return out


def _responses_texts(items: list[dict]) -> list[str]:
    out: list[str] = []
    for m in items:
        if m.get("type") == "function_call_output":
            out.append(m["output"])
        elif "content" in m and isinstance(m["content"], str):
            out.append(m["content"])
    return out


def test_prompt_text_byte_identical_across_providers():
    messages = [
        {"role": "user", "content": SUBMIT_FORMAT_TEXT},
        {"role": "assistant", "content": [
            {"type": "text", "text": "reasoning with unicode σ and 2σ band"},
            {"type": "tool_use", "id": "t1", "name": "query_metrics",
             "input": {"series": "train_loss"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": json.dumps({"status": "ok", "series": [0.1, 0.2]})},
        ]},
    ]
    assert _responses_texts(to_responses_input(messages)) == _anthropic_texts(messages)
    assert to_responses_input(messages)[0]["content"] == SUBMIT_FORMAT_TEXT


# --------------------------------------------------------------------------- #
# Folding rate is measurable on the parsed output (structured vs folded submit)
# --------------------------------------------------------------------------- #

def test_folding_measurable_from_parsed_submit():
    good = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
    structured = parse_responses(_fake_response(output=[_call_item("s", "submit",
        json.dumps({"diagnosis": "lr too high", "repair_spec": good,
                    "rationale": "ok"}))]))
    assert recover_folded_repair_spec(structured.tool_calls[0].arguments).reason == \
        "already_structured"
    folded = parse_responses(_fake_response(output=[_call_item("s", "submit",
        json.dumps({"diagnosis": "lr too high", "repair_spec": None,
                    "rationale": "repair: " + json.dumps(good)}))]))
    fold = recover_folded_repair_spec(folded.tool_calls[0].arguments)
    assert fold.warning is True
    assert fold.reason == "recovered"
