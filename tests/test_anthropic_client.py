"""AnthropicClient tests that exercise the REAL anthropic SDK call — not a fake.

Regression guard for 2026-09-20: the committed uv.lock resolved anthropic 1.4.0
for python>=3.10 (CI + the canonical container are py3.11), and 1.4.0 removed
`temperature` from Messages.create(), so the paid sweep tripped its circuit
breaker on a client-side TypeError before any network call. A FakeLLMClient test
cannot catch that — the real SDK call signature has to be exercised. These tests
drive the actual anthropic.Anthropic client with only its HTTP transport mocked,
so the real messages.create() runs its full kwarg validation + serialization.
"""
from __future__ import annotations

import inspect

import anthropic
import httpx

from harness.llm.anthropic_client import AnthropicClient


def _canned_message(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "msg_1", "type": "message", "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 2},
    })


def _client_with_mocked_transport() -> AnthropicClient:
    c = AnthropicClient(model="claude-haiku-4-5-20251001", temperature=1.0)
    # Real SDK client; only the network layer is mocked. The real messages.create()
    # still validates every kwarg (incl. temperature) and serializes the request.
    c._client = anthropic.Anthropic(
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(_canned_message)),
    )
    return c


def test_real_create_accepts_temperature_and_round_trips():
    """AnthropicClient.complete() drives the REAL create() with temperature set.

    Fails with a TypeError if the installed SDK's Messages.create() no longer
    accepts `temperature` (the anthropic 1.x regression that broke the sweep)."""
    c = _client_with_mocked_transport()
    resp = c.complete(messages=[{"role": "user", "content": "hi"}], tools_schema=[])
    assert resp.text == "ok"
    assert resp.usage.input_tokens == 3 and resp.usage.output_tokens == 2
    assert resp.raw["model"] == "claude-haiku-4-5-20251001"


def test_installed_sdk_signature_matches_client_kwargs():
    """The kwargs AnthropicClient passes must all be accepted by the installed
    SDK's Messages.create — a direct signature check on the real dependency."""
    from anthropic.resources.messages import Messages
    sig = inspect.signature(Messages.create)
    # Mirrors harness/llm/anthropic_client.py::complete (keep in sync).
    client_kwargs = dict(model="m", max_tokens=16, messages=[], tools=[], temperature=1.0)
    # Raises TypeError if the installed SDK rejects any of these (e.g. temperature).
    sig.bind_partial(None, **client_kwargs)
    assert "temperature" in sig.parameters


def test_pinned_anthropic_major_is_the_tested_api():
    """The lock must resolve the 0.x Messages API the client is written for; a 1.x
    resolution (open upper bound) is what regressed. Cross-checks the pyproject cap."""
    major = int(anthropic.__version__.split(".")[0])
    assert major == 0, (
        f"anthropic {anthropic.__version__} resolved; the client targets the 0.x "
        f"Messages API (temperature is a top-level create kwarg). Check the "
        f"'anthropic>=0.40.0,<1' cap in pyproject.toml and re-lock."
    )
