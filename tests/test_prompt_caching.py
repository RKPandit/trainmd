"""Prompt caching is TRANSPORT-ONLY (Stage 4 Part 1 cost optimization).

Pins: (1) the real serialized Anthropic request is byte-identical with caching on or off except for
the single top-level ``cache_control`` key — no prompt text changes; (2) usage is normalized so
``input_tokens`` stays the TOTAL prompt (as in Sweeps 1–3) with cache reads/writes as subsets, on
both providers; (3) writes are priced (Anthropic 5-minute write 1.25x; Luna 1.25x) and the
uncached-equivalent cost is recorded beside the billed cost; (4) only the multi-turn ReAct agent
enables caching; (5) R8 prices cache writes.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from harness.llm.anthropic_client import AnthropicClient
from harness.llm.openai_client import parse_responses
from harness.pricing import estimate_cost, uncached_equivalent_cost

HAIKU = "claude-haiku-4-5-20251001"
LUNA = "gpt-5.6-luna"

MESSAGES = [
    {"role": "user", "content": "You are a diagnostics agent. Investigate the run."},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Reading the config."},
        {"type": "tool_use", "id": "t1", "name": "read_config", "input": {"path": "config.yaml"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "lr: 0.01"}]},
]
TOOLS = [{"name": "read_config", "description": "Read a config file.",
          "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                           "required": ["path"]}}]


def _client(prompt_caching: bool, sent: list, usage: dict | None = None) -> AnthropicClient:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content)
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": HAIKU,
            "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": usage or {"input_tokens": 3, "output_tokens": 2}})
    c = AnthropicClient(model=HAIKU, temperature=1.0, prompt_caching=prompt_caching)
    c._client = anthropic.Anthropic(
        api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return c


# --------------------------------------------------------------------------- #
# (1) Byte-identical prompt on the wire
# --------------------------------------------------------------------------- #

def test_serialized_request_identical_except_top_level_cache_control():
    off, on = [], []
    _client(False, off).complete(messages=MESSAGES, tools_schema=TOOLS)
    _client(True, on).complete(messages=MESSAGES, tools_schema=TOOLS)
    body_off, body_on = json.loads(off[0]), json.loads(on[0])
    assert body_on.pop("cache_control") == {"type": "ephemeral"}   # 5-minute TTL, top level only
    assert "cache_control" not in body_off
    assert body_on == body_off                                     # everything else identical
    # And the prompt itself — messages + tools — is byte-identical as serialized.
    for key in ("messages", "tools"):
        assert json.dumps(body_on[key], sort_keys=True) == json.dumps(body_off[key], sort_keys=True)
    assert "cache_control" not in json.dumps(body_on["messages"])  # no per-block markers injected


def test_caching_does_not_mutate_the_callers_messages():
    snapshot = json.dumps(MESSAGES, sort_keys=True)
    _client(True, []).complete(messages=MESSAGES, tools_schema=TOOLS)
    assert json.dumps(MESSAGES, sort_keys=True) == snapshot


def test_default_is_off():
    assert AnthropicClient(model=HAIKU).prompt_caching is False


# --------------------------------------------------------------------------- #
# (2) Usage normalization — input_tokens is the TOTAL prompt on both providers
# --------------------------------------------------------------------------- #

def test_anthropic_usage_normalized_to_total_prompt():
    # With caching, Anthropic's usage.input_tokens is only the uncached remainder.
    resp = _client(True, [], usage={"input_tokens": 50, "output_tokens": 100,
                                    "cache_creation_input_tokens": 2000,
                                    "cache_read_input_tokens": 6000}
                   ).complete(messages=MESSAGES, tools_schema=TOOLS)
    u = resp.usage
    assert (u.input_tokens, u.cached_tokens, u.cache_write_tokens) == (8050, 6000, 2000)
    assert u.output_tokens == 100


def test_anthropic_usage_without_cache_fields_is_unchanged():
    u = _client(False, []).complete(messages=MESSAGES, tools_schema=TOOLS).usage
    assert (u.input_tokens, u.cached_tokens, u.cache_write_tokens) == (3, 0, 0)


def test_openai_cache_writes_captured():
    resp = SimpleNamespace(
        output=[], status="completed", model=LUNA, id="r1",
        usage=SimpleNamespace(
            input_tokens=5000, output_tokens=80,
            input_tokens_details=SimpleNamespace(cached_tokens=3000, cache_write_tokens=1500),
            output_tokens_details=SimpleNamespace(reasoning_tokens=10)))
    u = parse_responses(resp).usage
    assert (u.input_tokens, u.cached_tokens, u.cache_write_tokens) == (5000, 3000, 1500)


# --------------------------------------------------------------------------- #
# (3) Pricing: writes priced, uncached-equivalent reported
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model,inp,read,write,out", [
    (HAIKU, 1.00, 0.10, 1.25, 5.00),   # verified 2026-09-23, platform.claude.com pricing
    (LUNA, 0.20, 0.02, 0.25, 1.20),    # verified 2026-09-23, developers.openai.com pricing
])
def test_billed_cost_prices_reads_and_writes(model, inp, read, write, out):
    total, cached, written, output = 10_000, 6_000, 2_000, 500
    expected = ((total - cached - written) * inp + cached * read + written * write + output * out) / 1e6
    assert estimate_cost(model, total, output, cached, written).cost_usd == pytest.approx(expected)
    assert uncached_equivalent_cost(model, total, output).cost_usd == pytest.approx(
        (total * inp + output * out) / 1e6)


def test_no_cache_tokens_prices_exactly_as_before():
    # Sweeps 1–3 records carry no cache writes: their cost must be unchanged.
    assert estimate_cost(HAIKU, 88713, 1591).cost_usd == pytest.approx((88713 * 1 + 1591 * 5) / 1e6)


def test_unverified_write_price_falls_back_to_premium_not_discount(monkeypatch):
    from harness import pricing
    monkeypatch.setitem(pricing._PRICE_TABLE, "x-model",
                        {"input": 1.0, "output": 1.0, "cached_input": 0.1})
    assert estimate_cost("x-model", 1000, 0, 0, 1000).cost_usd == pytest.approx(1.25 * 1000 / 1e6)


# --------------------------------------------------------------------------- #
# (4) Only ReAct turns caching on; provenance + index record it
# --------------------------------------------------------------------------- #

def test_factory_enables_caching_for_react_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from harness.sweep import _default_agent_factory
    react = _default_agent_factory({"provider": "anthropic", "model": HAIKU,
                                    "agent": "react", "anchor": "off"}, HAIKU)
    static = _default_agent_factory({"provider": "anthropic", "model": HAIKU,
                                     "agent": "static", "anchor": "off"}, HAIKU)
    assert react._client.prompt_caching is True
    assert static._client.prompt_caching is False


def test_provenance_records_billed_and_uncached_cost_and_index_fields():
    from harness.provenance import _index_line, finalize_record
    record = {"case_id": "case_0001", "agent_name": "react-1", "run_id": "r1",
              "environment": {}, "model": {"model_id": HAIKU}, "status": "ok",
              "usage": {"llm_calls": 3, "input_tokens": 20000, "output_tokens": 900,
                        "cached_tokens": 12000, "cache_write_tokens": 5000,
                        "total_tokens": 0, "max_tokens_truncations": 0},
              "scores": {}, "budget": {}}
    tools = SimpleNamespace(submission=None, transcript=[], budget_total=10, budget_remaining=5)
    finalize_record(record, tools, scores=None, wall_clock_sec=1.0)
    u = record["usage"]
    billed = (3000 * 1 + 12000 * 0.10 + 5000 * 1.25 + 900 * 5) / 1e6
    assert u["estimated_cost_usd"] == pytest.approx(billed)
    assert u["uncached_equivalent_cost_usd"] == pytest.approx((20000 * 1 + 900 * 5) / 1e6)
    row = _index_line(record)
    assert (row["cached_tokens"], row["cache_write_tokens"]) == (12000, 5000)
    assert row["uncached_equivalent_cost_usd"] == pytest.approx((20000 + 4500) / 1e6)


# --------------------------------------------------------------------------- #
# (5) R8 prices cache writes
# --------------------------------------------------------------------------- #

def _r8_record(cost):
    return {"model": {"model_id": HAIKU},
            "usage": {"input_tokens": 20000, "output_tokens": 900, "cached_tokens": 12000,
                      "cache_write_tokens": 5000, "estimated_cost_usd": cost,
                      "cost_is_estimate": False}}


def test_r8_passes_when_cost_includes_write_pricing():
    from harness.audit_index import _r8
    billed = estimate_cost(HAIKU, 20000, 900, 12000, 5000).cost_usd
    assert _r8(_r8_record(billed)) is False


def test_r8_flags_cost_that_ignores_cache_writes():
    from harness.audit_index import _r8
    writes_as_plain_input = estimate_cost(HAIKU, 20000, 900, 12000).cost_usd
    assert _r8(_r8_record(writes_as_plain_input)) is True
