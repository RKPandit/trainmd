"""LLM client protocol, response types, and fake client for testing.

Defines the provider-agnostic :class:`LLMClient` protocol and the
:class:`FakeLLMClient` that replays scripted responses for zero-cost testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCallRequest:
    """One tool-use block from the model's response."""

    id: str           # tool_use block id (needed for result pairing)
    name: str         # tool name
    arguments: dict   # parsed kwargs


@dataclass(frozen=True)
class Usage:
    """Token counts for one LLM call."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    """Parsed model response."""

    text: str | None                     # assistant text (may be None if only tool calls)
    tool_calls: list[ToolCallRequest]    # zero or more
    stop_reason: str                     # "end_turn", "tool_use", "max_tokens"
    usage: Usage
    raw: dict | None = None              # provider-specific raw response for llm_transcript


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    """Provider-agnostic LLM client interface."""

    def complete(
        self,
        messages: list[dict],
        tools_schema: list[dict],
        *,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Fake client for testing
# ---------------------------------------------------------------------------

class FakeLLMClient:
    """Replays a fixed list of scripted responses.

    Each response carries fake :class:`Usage` tokens so tests can verify
    incremental accumulation.  If the response list is exhausted, returns
    an ``end_turn`` with no text (simulates model going silent).
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    def complete(
        self,
        messages: list[dict],
        tools_schema: list[dict],
        *,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self._call_index >= len(self._responses):
            return LLMResponse(
                text=None,
                tool_calls=[],
                stop_reason="end_turn",
                usage=Usage(input_tokens=0, output_tokens=0),
            )
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp
