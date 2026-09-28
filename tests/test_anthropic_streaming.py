"""AnthropicClient STREAMS every request (DECISIONS 2026-09-28).

The Sonnet 5 probe failed before any API call: the SDK refuses a NON-streaming request whose max_tokens could
take > 10 minutes ("Streaming is required ..."), and the output cap must not be lowered. These tests drive the
REAL anthropic SDK (only HTTP is mocked, answering with the real event stream) and prove: a 32,768-token cap
goes out as a streamed request; the final accumulated message keeps thinking text + signature and
redacted_thinking byte-for-byte for replay; usage comes from the FINAL message (not message_start's
provisional output count); a transient failure mid-request retries the whole request; create() is never used.
"""
from __future__ import annotations

import json

import anthropic
import httpx
import pytest

from harness.llm.anthropic_client import AnthropicClient
from anthropic_sse import sse_response  # tests/anthropic_sse.py

THINKING = {"type": "thinking", "thinking": "The val curve rises while hidden falls; check the config.",
            "signature": "EqQBCkYIBxgCKkBsig+/==" * 4}
REDACTED = {"type": "redacted_thinking", "data": "EmwKAhgBEgy3va3pzix/LafPsn4aDFIT"}
TOOL = {"type": "tool_use", "id": "tu1", "name": "submit",
        "input": {"diagnosis": {"detected": True, "operator_class": "x"}, "evidence_refs": []}}
MSG = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
       "content": [THINKING, REDACTED, {"type": "text", "text": "Submitting."}, TOOL],
       "stop_reason": "tool_use", "stop_sequence": None,
       "usage": {"input_tokens": 100, "output_tokens": 2345,
                 "cache_read_input_tokens": 40, "cache_creation_input_tokens": 10}}


def _client(handler, **kw):
    c = AnthropicClient(model="claude-sonnet-5", effort="high", **kw)
    c._client = anthropic.Anthropic(api_key="test", max_retries=0,
                                   http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return c


def test_high_output_cap_is_sent_as_a_streamed_request():
    sent = []

    def handler(req):
        sent.append(json.loads(req.content))
        return sse_response(MSG)
    r = _client(handler).complete([{"role": "user", "content": "hi"}], [], max_tokens=32768)
    assert sent[0]["stream"] is True and sent[0]["max_tokens"] == 32768      # the cap is NOT lowered
    assert r.stop_reason == "tool_use"


def test_final_message_keeps_every_block_verbatim_for_replay():
    r = _client(lambda req: sse_response(MSG)).complete([{"role": "user", "content": "hi"}], [], max_tokens=32768)
    blocks = r.assistant_blocks
    assert [b["type"] for b in blocks] == ["thinking", "redacted_thinking", "text", "tool_use"]
    assert blocks[0]["thinking"] == THINKING["thinking"] and blocks[0]["signature"] == THINKING["signature"]
    assert blocks[1]["data"] == REDACTED["data"]
    assert r.reasoning_blocks == 2
    assert r.tool_calls[0].arguments == TOOL["input"] and r.text == "Submitting."


def test_usage_is_taken_from_the_final_message():
    r = _client(lambda req: sse_response(MSG)).complete([{"role": "user", "content": "hi"}], [], max_tokens=32768)
    assert r.usage.output_tokens == 2345                      # not message_start's provisional 1
    assert r.usage.input_tokens == 100 + 40 + 10              # total prompt, as before
    assert r.usage.cached_tokens == 40 and r.usage.cache_write_tokens == 10
    assert r.raw["completion"] == {"stop_reason": "tool_use"}


def test_transient_failure_retries_the_whole_request(monkeypatch):
    monkeypatch.setattr("harness.llm.anthropic_client.time.sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "boom"}})
        return sse_response(MSG)
    r = _client(handler).complete([{"role": "user", "content": "hi"}], [], max_tokens=32768)
    assert len(calls) == 2 and r.usage.output_tokens == 2345


def test_create_is_never_called_and_non_streaming_would_have_refused(monkeypatch):
    c = _client(lambda req: sse_response(MSG))
    with pytest.raises(Exception, match="Streaming is required"):   # why streaming is needed at this cap
        c._client.messages.create(**c.request_kwargs([{"role": "user", "content": "hi"}], [], 32768))

    def boom(*a, **k):
        raise AssertionError("messages.create must not be used")
    monkeypatch.setattr(c._client.messages, "create", boom)
    c.complete([{"role": "user", "content": "hi"}], [], max_tokens=32768)


def test_describe_records_the_transport():
    assert AnthropicClient(model="claude-sonnet-5", effort="high").describe()["transport"].startswith("streaming")
