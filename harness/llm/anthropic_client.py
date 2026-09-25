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


# Per-model request capabilities, verified 2026-09-24 against platform.claude.com (models overview,
# effort, thinking, model-deprecations). temperature: Claude 4.7+ return 400 on a non-default value.
# effort: output_config.effort levels. thinking: explicit thinking.type values accepted.
_MODEL_CAPS = {
    "claude-haiku-4-5-20251001": {"temperature": True, "effort": (), "thinking": (),
                                  "default_effort": "not supported", "default_thinking": "off"},
    "claude-sonnet-5": {"temperature": False, "effort": ("low", "medium", "high", "xhigh", "max"),
                        "thinking": ("adaptive", "disabled"),
                        "default_effort": "high", "default_thinking": "adaptive, on"},
    "claude-opus-5-5": {"temperature": False, "effort": ("low", "medium", "high", "xhigh", "max"),
                        "thinking": ("adaptive",),          # disabled -> 400: always on
                        "default_effort": "medium", "default_thinking": "adaptive, always on"},
}
_LEGACY_CAPS = {"temperature": True, "effort": (), "thinking": (),
                "default_effort": "not supported", "default_thinking": "off"}


def model_caps(model: str) -> dict:
    """Request capabilities for ``model`` (unknown models keep the legacy request shape)."""
    return _MODEL_CAPS.get(model, _LEGACY_CAPS)


def _to_plain(x):
    """SDK model / namespace / container -> plain JSON-able structure, unchanged (None fields dropped)."""
    if hasattr(x, "model_dump"):
        return x.model_dump(exclude_none=True)
    if isinstance(x, dict):
        return {k: _to_plain(v) for k, v in x.items() if v is not None}
    if isinstance(x, (list, tuple)):
        return [_to_plain(v) for v in x]
    if hasattr(x, "__dict__"):
        return {k: _to_plain(v) for k, v in vars(x).items() if v is not None and not k.startswith("_")}
    return x


def _block_dict(block) -> dict:
    """A response content block as a plain dict, unchanged."""
    return _to_plain(block)


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
                 prompt_caching: bool = False, effort: str | None = None,
                 thinking: str | None = None) -> None:
        import anthropic

        caps = model_caps(model)
        if effort is not None and effort not in caps["effort"]:
            raise ValueError(f"{model}: effort {effort!r} not supported (allowed: {caps['effort'] or 'none'})")
        if thinking is not None and thinking not in caps["thinking"]:
            raise ValueError(f"{model}: thinking {thinking!r} not supported (allowed: {caps['thinking']})")
        self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
        self._model = model
        self._temperature = temperature
        self._caps = caps
        self.effort = effort
        self.thinking = thinking
        self.prompt_caching = prompt_caching

    def request_kwargs(self, messages: list[dict], tools_schema: list[dict],
                       max_tokens: int) -> dict:
        """The exact ``messages.create`` kwargs. Caching adds ONLY the top-level
        ``cache_control`` key; ``messages``/``tools`` are passed through untouched.

        ``temperature`` is sent only to models that accept it (Claude 4.7+ return 400 on a
        non-default value); ``output_config.effort`` / ``thinking`` only when set explicitly."""
        kwargs = dict(model=self._model, max_tokens=max_tokens, messages=messages,
                      tools=tools_schema)
        if self._caps["temperature"]:
            kwargs["temperature"] = self._temperature
        if self.effort is not None:
            kwargs["output_config"] = {"effort": self.effort}
        if self.thinking is not None:
            kwargs["thinking"] = {"type": self.thinking}
        if self.prompt_caching:
            kwargs["cache_control"] = dict(self._CACHE_CONTROL)
        return kwargs

    def describe(self) -> dict:
        """Merged into the trial's model block by the agents: the generation settings actually
        requested (temperature is 'model default (not settable)' on Claude 4.7+ models)."""
        return {"provider": "anthropic", **self.generation_settings()}

    def generation_settings(self) -> dict:
        """What was actually requested — recorded in the trial's model block (provenance)."""
        return {"temperature": self._temperature if self._caps["temperature"] else "model default (not settable)",
                "effort": self.effort or f"model default ({self._caps['default_effort']})",
                "thinking": self.thinking or f"model default ({self._caps['default_thinking']})"}

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
        """Parse an Anthropic Messages API response into LLMResponse.

        ``assistant_blocks`` carries EVERY content block exactly as returned (thinking +
        signature, redacted_thinking, text, tool_use): with tool use the API requires the
        assistant's thinking blocks back "complete and unmodified", and silently drops thinking
        for the continuation if they are missing."""
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        blocks = [_block_dict(b) for b in response.content]
        n_thinking = sum(1 for b in blocks if b.get("type") in ("thinking", "redacted_thinking"))

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
            assistant_blocks=blocks,
            reasoning_blocks=n_thinking,
        )
