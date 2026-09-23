"""Anthropic API client implementing :class:`LLMClient`.

Uses the ``anthropic`` SDK (optional dependency, install with
``uv pip install -e '.[llm]'``).  Reads ``ANTHROPIC_API_KEY`` from the
environment — never logs or prints it.

Includes bounded retry (max 2 retries) on transient errors only:
rate-limit, 5xx, timeout, connection.  No retry on auth or 400 errors.
"""
from __future__ import annotations

import time

from harness.llm.client import LLMResponse, ToolCallRequest, Usage

_MODELS_DOC_URL = "https://docs.anthropic.com/en/docs/about-claude/models"

_MAX_RETRIES = 2
_BASE_DELAY = 1.0  # seconds


class AnthropicClient:
    """LLMClient implementation backed by the Anthropic Messages API.

    Args:
        model: Exact API model ID string (e.g. ``"claude-haiku-4-5-20251001"``).
            No default — caller must provide a verified ID.
        temperature: Sampling temperature (0.0–1.0).
        prompt_caching: Enable Anthropic prompt caching (TRANSPORT-ONLY). Adds a single
            top-level ``cache_control={"type": "ephemeral"}`` (5-minute TTL): the API places the
            breakpoint on the last cacheable block and moves it forward as a multi-turn
            conversation grows, so each call reads the prior prefix and writes only the new
            turn. It changes NO message content — prompt text is byte-identical with caching
            on or off. Worth it only for multi-turn agents (ReAct); a single-call agent would
            pay the 1.25x write with nothing to read. Haiku 4.5 caches only prefixes of
            >= 4,096 tokens (shorter ones silently don't cache). Default off.
    """

    # 5-minute TTL: ReAct calls within a trial start seconds apart (H8: max call latency
    # 65 s), so the default ephemeral entry stays warm; the 1-hour TTL would double the
    # write price for nothing. Verified 2026-09-23 (platform.claude.com prompt-caching).
    _CACHE_CONTROL = {"type": "ephemeral"}

    def __init__(self, model: str, temperature: float = 1.0, *,
                 prompt_caching: bool = False) -> None:
        import anthropic

        self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
        self._model = model
        self._temperature = temperature
        self.prompt_caching = prompt_caching

    def request_kwargs(self, messages: list[dict], tools_schema: list[dict],
                       max_tokens: int) -> dict:
        """The exact ``messages.create`` kwargs. Caching adds ONLY the top-level
        ``cache_control`` key; ``messages``/``tools`` are passed through untouched."""
        kwargs = dict(model=self._model, max_tokens=max_tokens, messages=messages,
                      tools=tools_schema, temperature=self._temperature)
        if self.prompt_caching:
            kwargs["cache_control"] = dict(self._CACHE_CONTROL)
        return kwargs

    def complete(
        self,
        messages: list[dict],
        tools_schema: list[dict],
        *,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Call the Anthropic Messages API with bounded retry."""
        import anthropic

        # Transient errors worth retrying
        transient = (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        )

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    **self.request_kwargs(messages, tools_schema, max_tokens))
                return self._parse_response(response)

            except transient as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_BASE_DELAY * (2 ** attempt))
                    continue
                raise

            except anthropic.NotFoundError as e:
                raise ValueError(
                    f"Model {self._model!r} not found. "
                    f"Set --model to a valid Anthropic model ID. "
                    f"See {_MODELS_DOC_URL}"
                ) from e

            except anthropic.APIStatusError:
                # Auth errors (401/403), bad request (400), etc. — no retry
                raise

        # Should not reach here, but satisfy type checker
        assert last_error is not None
        raise last_error

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Parse an Anthropic Messages API response into LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        u = response.usage
        read = getattr(u, "cache_read_input_tokens", 0) or 0
        write = getattr(u, "cache_creation_input_tokens", 0) or 0
        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage=Usage(
                # With caching on, Anthropic's usage.input_tokens is only the uncached
                # remainder AFTER the last breakpoint; the total prompt is
                # input + cache_creation + cache_read. Normalize to the TOTAL (see Usage).
                input_tokens=u.input_tokens + write + read,
                output_tokens=u.output_tokens,
                cached_tokens=read,
                cache_write_tokens=write,
            ),
            raw={"model": response.model, "id": response.id},
        )
