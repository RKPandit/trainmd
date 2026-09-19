"""OpenAI API client implementing :class:`LLMClient` (second provider).

Uses the ``openai`` SDK (optional dependency, install with
``uv pip install -e '.[llm]'``).  Reads ``OPENAI_API_KEY`` from the environment
— never logs or prints it.

The harness speaks ONE message dialect internally: the Anthropic content-block
shape that :mod:`agents.llm_agent` builds (a first user-role string prompt, then
assistant turns carrying ``text``/``tool_use`` blocks and user turns carrying
``tool_result`` blocks) plus the Anthropic tool schema
(``{name, description, input_schema}``).  This adapter TRANSLATES that dialect to
and from the OpenAI Chat Completions shape and NEVER alters any prompt text — the
translation functions are pure and unit-tested so byte-identity across providers
is provable (``tests/test_openai_client.py``).

Includes bounded retry (max 2 retries) on transient errors only: rate-limit, 5xx,
timeout, connection.  No retry on auth or 400 errors.
"""
from __future__ import annotations

import json
import time

from harness.llm.client import LLMResponse, ToolCallRequest, Usage

_MODELS_DOC_URL = "https://platform.openai.com/docs/models"

_MAX_RETRIES = 2
_BASE_DELAY = 1.0  # seconds

# OpenAI finish_reason -> our provider-agnostic stop_reason vocabulary.
_STOP_REASON = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",  # legacy
    "length": "max_tokens",
}


# --------------------------------------------------------------------------- #
# Pure translation (no SDK, no network) — unit-tested directly.
# --------------------------------------------------------------------------- #

def to_openai_tools(tools_schema: list[dict]) -> list[dict]:
    """Anthropic tool schema -> OpenAI ``tools`` (function) schema.

    ``input_schema`` (a JSON Schema) is carried through verbatim as
    ``function.parameters`` — the tool contract the model sees is unchanged.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools_schema
    ]


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Anthropic content-block messages -> OpenAI Chat Completions messages.

    Prompt text is passed through byte-for-byte:
    - user with a string ``content`` (the instruction prompt) -> ``{"role":
      "user", "content": <same string>}``.
    - user with ``tool_result`` blocks -> one ``{"role": "tool",
      "tool_call_id", "content"}`` per block (content string unchanged).
    - assistant blocks -> ``{"role": "assistant", "content": <joined text or
      None>, "tool_calls": [...]}`` where each ``tool_use`` becomes a function
      call whose ``arguments`` is ``json.dumps(input)``.
    """
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "user":
            if isinstance(content, str):
                # L13 (docs/LIMITATIONS.md): the instruction prompt is delivered
                # as the INITIAL USER-ROLE message, NOT the provider system role.
                # Keep role + position exactly; NEVER remap to role="system" — that
                # would be a cross-provider confound. (No system message is injected
                # anywhere in this adapter.)
                out.append({"role": "user", "content": content})
            else:
                for block in content:
                    if block.get("type") == "tool_result":
                        out.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block["content"],
                        })
                    elif block.get("type") == "text":
                        out.append({"role": "user", "content": block["text"]})
        elif role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"]),
                        },
                    })
            msg: dict = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:  # pragma: no cover - the agent never emits other roles
            out.append({"role": role, "content": content})
    return out


def parse_openai_response(response) -> LLMResponse:
    """Parse an OpenAI Chat Completions response into :class:`LLMResponse`.

    A tool call's ``arguments`` string is ``json.loads``-ed into a dict.  If the
    model emits a malformed arguments string, the RAW string is kept (not
    silently coerced to ``{}``) so the agent's ``isinstance(dict)`` check surfaces
    it as a faithful tool error rather than hiding a bad call.
    """
    choice = response.choices[0]
    msg = choice.message

    tool_calls: list[ToolCallRequest] = []
    for tc in (getattr(msg, "tool_calls", None) or []):
        raw_args = tc.function.arguments
        if isinstance(raw_args, str):
            try:
                args: object = json.loads(raw_args)
            except json.JSONDecodeError:
                args = raw_args  # keep raw; agent treats non-dict as a tool error
        else:
            args = raw_args
        tool_calls.append(
            ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args)
        )

    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None)
    cached = (getattr(details, "cached_tokens", 0) or 0) if details is not None else 0

    return LLMResponse(
        text=(msg.content or None),
        tool_calls=tool_calls,
        stop_reason=_STOP_REASON.get(choice.finish_reason, choice.finish_reason),
        usage=Usage(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cached_tokens=cached,
        ),
        raw={"model": response.model, "id": response.id},
    )


class OpenAIClient:
    """LLMClient implementation backed by the OpenAI Chat Completions API.

    Args:
        model: Exact API model ID string (e.g. ``"gpt-5-mini"``).  No default —
            the caller must provide a verified ID.
        temperature: Sampling temperature (0.0–1.0).  The study runs at 1.0.
    """

    def __init__(self, model: str, temperature: float = 1.0) -> None:
        import openai

        self._client = openai.OpenAI()  # OPENAI_API_KEY from env
        self._model = model
        self._temperature = temperature

    def complete(
        self,
        messages: list[dict],
        tools_schema: list[dict],
        *,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Call the OpenAI Chat Completions API with bounded retry."""
        import openai

        transient = (
            openai.RateLimitError,
            openai.InternalServerError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        )

        oa_messages = to_openai_messages(messages)
        oa_tools = to_openai_tools(tools_schema)

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=oa_messages,
                    tools=oa_tools,
                    temperature=self._temperature,
                    # GPT-5-era models require max_completion_tokens (max_tokens
                    # is rejected); it caps the output budget as max_tokens did.
                    max_completion_tokens=max_tokens,
                )
                return parse_openai_response(response)

            except transient as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_BASE_DELAY * (2 ** attempt))
                    continue
                raise

            except openai.NotFoundError as e:
                raise ValueError(
                    f"Model {self._model!r} not found. "
                    f"Set --model to a valid OpenAI model ID. "
                    f"See {_MODELS_DOC_URL}"
                ) from e

            except openai.APIStatusError:
                # Auth (401/403), bad request (400), etc. — no retry
                raise

        assert last_error is not None  # pragma: no cover
        raise last_error
