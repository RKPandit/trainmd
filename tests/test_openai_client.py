"""OpenAI adapter tests — pure translation + parsing, zero API cost.

The ``openai`` SDK is NOT required: every test exercises the pure translation
functions (``to_openai_messages``, ``to_openai_tools``, ``parse_openai_response``)
with hand-built fakes.  The one thing these tests must pin down is that the
adapter NEVER alters prompt text — so the text a second provider receives is
byte-identical to the text Anthropic receives (the study's cross-provider
comparison depends on it).
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
    parse_openai_response,
    to_openai_messages,
    to_openai_tools,
)
from harness.submission_repair import recover_folded_repair_spec


# --------------------------------------------------------------------------- #
# Fake OpenAI response builder (mirrors the SDK's attribute shape)
# --------------------------------------------------------------------------- #

def _fake_response(*, content, tool_calls, finish_reason,
                   prompt_tokens=11, completion_tokens=7, cached_tokens=0,
                   model="gpt-5-mini-2026", rid="chatcmpl-abc"):
    tcs = [
        SimpleNamespace(
            id=tc["id"],
            type="function",
            function=SimpleNamespace(name=tc["name"], arguments=tc["arguments"]),
        )
        for tc in tool_calls
    ]
    message = SimpleNamespace(content=content, tool_calls=tcs or None)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model, id=rid)


# --------------------------------------------------------------------------- #
# Tool-schema translation
# --------------------------------------------------------------------------- #

def test_tools_translation_preserves_contract():
    oa = to_openai_tools(TOOLS_SCHEMA)
    assert len(oa) == len(TOOLS_SCHEMA)
    for src, dst in zip(TOOLS_SCHEMA, oa):
        assert dst["type"] == "function"
        assert dst["function"]["name"] == src["name"]
        assert dst["function"]["description"] == src["description"]
        # input_schema is carried through verbatim (same object contract).
        assert dst["function"]["parameters"] == src["input_schema"]


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

def test_parse_text_only_end_turn():
    r = parse_openai_response(_fake_response(
        content="all done", tool_calls=[], finish_reason="stop"))
    assert r.text == "all done"
    assert r.tool_calls == []
    assert r.stop_reason == "end_turn"
    assert r.usage.input_tokens == 11
    assert r.usage.output_tokens == 7


def test_parse_tool_call_arguments_are_parsed_dict():
    r = parse_openai_response(_fake_response(
        content=None,
        tool_calls=[{"id": "call_1", "name": "read_config",
                     "arguments": json.dumps({"key_path": "training.lr"})}],
        finish_reason="tool_calls"))
    assert r.text is None
    assert r.stop_reason == "tool_use"
    assert len(r.tool_calls) == 1
    tc = r.tool_calls[0]
    assert tc.id == "call_1"
    assert tc.name == "read_config"
    assert tc.arguments == {"key_path": "training.lr"}  # parsed to a dict


def test_parse_malformed_arguments_kept_raw_not_coerced():
    # A malformed arguments string must NOT be silently turned into {}; keeping
    # it raw lets the agent's isinstance(dict) check surface a faithful error.
    r = parse_openai_response(_fake_response(
        content=None,
        tool_calls=[{"id": "c", "name": "read_config", "arguments": "{not json"}],
        finish_reason="tool_calls"))
    assert r.tool_calls[0].arguments == "{not json"
    assert not isinstance(r.tool_calls[0].arguments, dict)


def test_parse_length_maps_to_max_tokens_and_cached_tokens():
    r = parse_openai_response(_fake_response(
        content="cut off", tool_calls=[], finish_reason="length",
        cached_tokens=4))
    assert r.stop_reason == "max_tokens"
    assert r.usage.cached_tokens == 4


def test_parse_captures_api_model_string():
    r = parse_openai_response(_fake_response(
        content="x", tool_calls=[], finish_reason="stop", model="gpt-5.6-luna"))
    assert r.raw["model"] == "gpt-5.6-luna"  # API-reported model string


# --------------------------------------------------------------------------- #
# reasoning.effort pinning + provider metadata (Luna)
# --------------------------------------------------------------------------- #

def test_effort_tiers_and_validation():
    assert _EFFORT_TIERS == ("none", "low", "medium", "high", "xhigh", "max")
    assert check_effort("medium") == "medium"          # default, accepted
    with pytest.raises(ValueError):
        check_effort("reasonable")                     # bogus tier refused


def test_describe_records_effort_and_luna_metadata():
    d = describe_model("gpt-5.6-luna", 1.0, "medium")
    assert d["provider"] == "openai"
    assert d["model_id"] == "gpt-5.6-luna"
    assert d["reasoning_effort"] == "medium"           # pinned, recorded
    assert d["knowledge_cutoff"] == "2026-02-16"       # prior-confound metadata
    assert d["context_window_tokens"] == 1_050_000
    assert d["long_context_threshold_tokens"] == 272_000


# --------------------------------------------------------------------------- #
# Message translation
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
    oa = to_openai_messages(messages)
    assert oa[0] == {"role": "user", "content": "INSTRUCTION PROMPT"}
    assert oa[1]["role"] == "assistant"
    assert oa[1]["content"] == "let me check"
    assert oa[1]["tool_calls"][0]["id"] == "t1"
    assert oa[1]["tool_calls"][0]["function"]["name"] == "read_config"
    # arguments round-trips through JSON
    assert json.loads(oa[1]["tool_calls"][0]["function"]["arguments"]) == {
        "key_path": "training.lr"}
    assert oa[2]["role"] == "tool"
    assert oa[2]["tool_call_id"] == "t1"
    assert json.loads(oa[2]["content"]) == {"status": "ok", "value": 0.01}


# --------------------------------------------------------------------------- #
# Byte-identical prompt text across providers (the literal-slice guarantee)
# --------------------------------------------------------------------------- #

def _anthropic_texts(messages: list[dict]) -> list[str]:
    """Ordered text strings Anthropic receives (messages are sent as-is)."""
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


def _openai_texts(oa_messages: list[dict]) -> list[str]:
    """Ordered text strings OpenAI receives after translation."""
    out: list[str] = []
    for m in oa_messages:
        if m["role"] == "assistant":
            if m.get("content"):
                out.append(m["content"])
        elif isinstance(m.get("content"), str):
            out.append(m["content"])
    return out


def test_instruction_prompt_stays_user_role_no_system_remap():
    # L13 (docs/LIMITATIONS.md): instructions are the INITIAL USER-ROLE message,
    # never the provider system role. The OpenAI path must preserve role AND
    # position and emit no role="system" (remapping would be a cross-provider
    # confound that invalidates the comparison).
    messages = [
        {"role": "user", "content": "INSTRUCTION PROMPT (user role, position 0)"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "read_config", "input": {}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]},
    ]
    oa = to_openai_messages(messages)
    # Same role, same position: still first, still user.
    assert oa[0] == {"role": "user",
                     "content": "INSTRUCTION PROMPT (user role, position 0)"}
    # No message anywhere is remapped to the system role.
    assert all(m["role"] != "system" for m in oa)
    assert {m["role"] for m in oa} <= {"user", "assistant", "tool"}


def test_prompt_text_byte_identical_across_providers():
    # Use the real SUBMIT_FORMAT_TEXT literal slice as prompt content: whatever
    # the agent sends Anthropic must reach OpenAI byte-for-byte, unmodified.
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
    anthropic_texts = _anthropic_texts(messages)
    openai_texts = _openai_texts(to_openai_messages(messages))
    # Same text payloads, same order, byte-for-byte — no provider drift.
    assert openai_texts == anthropic_texts
    # And specifically the instruction prompt is untouched.
    assert to_openai_messages(messages)[0]["content"] == SUBMIT_FORMAT_TEXT
    assert SUBMIT_FORMAT_TEXT in openai_texts


# --------------------------------------------------------------------------- #
# Folding rate is measurable on the parsed output (structured vs folded submit)
# --------------------------------------------------------------------------- #

def test_folding_measurable_from_parsed_submit():
    good = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
    # Structured submit: repair_spec is a proper object -> NOT folded.
    structured = parse_openai_response(_fake_response(
        content=None,
        tool_calls=[{"id": "s", "name": "submit", "arguments": json.dumps({
            "diagnosis": "lr too high", "repair_spec": good, "rationale": "ok"})}],
        finish_reason="tool_calls"))
    assert recover_folded_repair_spec(structured.tool_calls[0].arguments).reason == \
        "already_structured"
    # Folded submit: the object is buried in the rationale string -> recovered+warned.
    folded = parse_openai_response(_fake_response(
        content=None,
        tool_calls=[{"id": "s", "name": "submit", "arguments": json.dumps({
            "diagnosis": "lr too high", "repair_spec": None,
            "rationale": "repair: " + json.dumps(good)})}],
        finish_reason="tool_calls"))
    fold = recover_folded_repair_spec(folded.tool_calls[0].arguments)
    assert fold.warning is True
    assert fold.reason == "recovered"
