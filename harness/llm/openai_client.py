"""OpenAI API client implementing :class:`LLMClient` (second provider).

Uses the ``openai`` SDK (optional dependency, install with
``uv pip install -e '.[llm]'``).  Reads ``OPENAI_API_KEY`` from the environment
— never logs or prints it.

Uses the **Responses API** (``/v1/responses``), not chat/completions: GPT-5.6
Luna rejects function tools together with a non-``none`` ``reasoning_effort`` on
chat/completions, so keeping reasoning at the pinned effort WITH tools requires
this endpoint (docs/DECISIONS.md 2026-09-19).

The harness speaks ONE message dialect internally: the Anthropic content-block
shape that :mod:`agents.llm_agent` builds (a first user-role string prompt, then
assistant turns carrying ``text``/``tool_use`` blocks and user turns carrying
``tool_result`` blocks) plus the Anthropic tool schema
(``{name, description, input_schema}``).  This adapter TRANSLATES that dialect to
and from the OpenAI Responses shape (``function_call`` / ``function_call_output``
items paired by ``call_id``) and NEVER alters any prompt text — the translation
functions are pure and unit-tested so byte-identity across providers is provable
(``tests/test_openai_client.py``).

Includes bounded retry (max 2 retries) on transient errors only: rate-limit, 5xx,
timeout, connection.  No retry on auth or 400 errors.
"""
from __future__ import annotations

import json
import time

from harness.llm.client import LLMResponse, ToolCallRequest, Usage

_MODELS_DOC_URL = "https://developers.openai.com/api/docs/models"

_MAX_RETRIES = 2
_BASE_DELAY = 1.0  # seconds

# reasoning.effort tiers Luna (and the GPT-5.6 family) expose; "medium" is the
# provider default. We PIN it explicitly (never leave it implicit) so a
# cross-provider comparison is not silently confounded — Haiku has no such knob,
# so an unpinned effort would be an unstated difference (docs/DECISIONS.md).
_EFFORT_TIERS = ("none", "low", "medium", "high", "xhigh", "max")

# Per-model provider metadata (verified from OpenAI's model docs, 2026-09-19).
# knowledge_cutoff is recorded because it bears on the "does the model already
# know Adult's achievable accuracy" prior confound flagged for the frontier arm.
_GPT6_COMMON = {"context_window_tokens": 1_050_000, "max_output_tokens": 128_000,
                "long_context_threshold_tokens": 272_000}
_MODEL_METADATA: dict[str, dict] = {
    # Verified 2026-09-24 (developers.openai.com model pages, raw): alias-only (no dated snapshot).
    "gpt-6-luna": {"knowledge_cutoff": "2026-05-18", **_GPT6_COMMON},
    "gpt-6-sol": {"knowledge_cutoff": "2026-04-20", **_GPT6_COMMON},
    "gpt-5.6-luna": {
        "knowledge_cutoff": "2026-02-16",
        "context_window_tokens": 1_050_000,
        "max_output_tokens": 128_000,
        # Long-context meter: above this input-token threshold OpenAI bills input
        # (and cached input / cache writes) at 2x and output at 1.5x. Our prompts
        # are far below it; recorded so a future large-context workload is not
        # silently double-billed. See harness/pricing.py.
        "long_context_threshold_tokens": 272_000,
        # Tier-1 account rate limits. NOT a constraint for sequential runs at
        # ~30K tokens/trial, but recorded in the model block (-> the sweep
        # manifest) so a future PARALLELIZED runner does not hit them blind.
        "rate_limits_tier1": {
            "rpm": 500,
            "tpm": 500_000,
            "batch_queue_tokens": 5_000_000,
        },
    },
}

# --------------------------------------------------------------------------- #
# Pure translation (no SDK, no network) — unit-tested directly.
# --------------------------------------------------------------------------- #

def check_effort(effort: str) -> str:
    """Validate a reasoning.effort tier (fail loud) and return it."""
    if effort not in _EFFORT_TIERS:
        raise ValueError(f"reasoning_effort {effort!r} not in {_EFFORT_TIERS}")
    return effort


def describe_model(model: str, temperature: float, reasoning_effort: str) -> dict:
    """Provider metadata for the trial's model block (pure; no SDK/network).

    Merges the pinned ``reasoning_effort`` and the per-model ``knowledge_cutoff`` /
    context window / long-context threshold from :data:`_MODEL_METADATA`.
    """
    return {
        "provider": "openai",
        "model_id": model,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        **dict(_MODEL_METADATA.get(model, {})),
    }


def to_responses_tools(tools_schema: list[dict]) -> list[dict]:
    """Anthropic tool schema -> OpenAI Responses ``tools`` (function) schema.

    Responses function tools are FLAT (no nested ``function`` key). ``input_schema``
    (a JSON Schema) is carried through verbatim as ``parameters`` — the tool
    contract the model sees is unchanged.
    """
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["input_schema"],
        }
        for t in tools_schema
    ]


def to_responses_input(messages: list[dict]) -> list[dict]:
    """Anthropic content-block messages -> OpenAI Responses ``input`` items.

    Prompt text is passed through byte-for-byte:
    - user with a string ``content`` (the instruction prompt) -> ``{"role":
      "user", "content": <same string>}``.
    - user with ``tool_result`` blocks -> one ``{"type": "function_call_output",
      "call_id", "output"}`` per block (content string unchanged).
    - assistant turns carrying an ``openai_output_items`` block (the provider-NATIVE turn,
      from :func:`parse_responses`) -> those output items VERBATIM, reasoning items (with
      ``encrypted_content``) included. OpenAI: "any reasoning items returned in model responses
      with tool calls must also be passed back with tool call outputs" — rebuilding the turn from
      text + calls drops them (H8's Luna ReAct ran that way; LIMITATIONS L32).
    - other assistant blocks (fake/test clients) -> a ``{"role": "assistant", "content": <joined
      text>}`` item (when there is text) plus one ``{"type": "function_call", "call_id",
      "name", "arguments"}`` per ``tool_use`` (arguments = ``json.dumps(input)``).
      Pairing is by ``call_id`` (== our tool_use id), symmetric with the
      ``function_call_output`` above.
    """
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "user":
            if isinstance(content, str):
                # L13 (docs/LIMITATIONS.md): the instruction prompt is delivered
                # as the INITIAL USER-ROLE message, NOT the provider system/
                # developer role. Keep role + position exactly; NEVER remap to
                # role="system"/"developer" — that would be a cross-provider
                # confound. (No system message is injected anywhere here.)
                out.append({"role": "user", "content": content})
            else:
                for block in content:
                    if block.get("type") == "tool_result":
                        out.append({
                            "type": "function_call_output",
                            "call_id": block["tool_use_id"],
                            "output": block["content"],
                        })
                    elif block.get("type") == "text":
                        out.append({"role": "user", "content": block["text"]})
        elif role == "assistant":
            native = [b for b in content if b.get("type") == "openai_output_items"]
            if native:
                for b in native:
                    out.extend(b["items"])
                continue
            text_parts: list[str] = []
            calls: list[dict] = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    calls.append({
                        "type": "function_call",
                        "call_id": block["id"],
                        "name": block["name"],
                        "arguments": json.dumps(block["input"]),
                    })
            if text_parts:
                out.append({"role": "assistant",
                            "content": "\n".join(text_parts)})
            out.extend(calls)
        else:  # pragma: no cover - the agent never emits other roles
            out.append({"role": role, "content": content})
    return out


def parse_responses(response) -> LLMResponse:
    """Parse an OpenAI Responses API response into :class:`LLMResponse`.

    Walks ``response.output``: ``message`` items contribute assistant text
    (``output_text``), ``function_call`` items become tool calls (paired by
    ``call_id``), ``reasoning`` items are ignored (never surfaced). A function
    call's ``arguments`` string is ``json.loads``-ed; a malformed string is kept
    RAW (not coerced to ``{}``) so the agent's ``isinstance(dict)`` check surfaces
    it as a faithful tool error. Reasoning tokens are already counted in
    ``usage.output_tokens`` (billed as output).
    """
    text_parts: list[str] = []
    tool_calls: list[ToolCallRequest] = []
    native_items = [_item_dict(i) for i in (getattr(response, "output", None) or [])]
    n_reasoning = sum(1 for i in native_items if i.get("type") == "reasoning")
    for item in (getattr(response, "output", None) or []):
        itype = getattr(item, "type", None)
        if itype == "message":
            for c in (getattr(item, "content", None) or []):
                if getattr(c, "type", None) == "output_text":
                    text_parts.append(c.text)
        elif itype == "function_call":
            raw_args = item.arguments
            if isinstance(raw_args, str):
                try:
                    args: object = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = raw_args  # keep raw; agent treats non-dict as error
            else:
                args = raw_args
            tool_calls.append(
                ToolCallRequest(id=item.call_id, name=item.name, arguments=args)
            )

    # stop_reason from the response status, not a per-choice finish_reason.
    status = getattr(response, "status", None)
    if status == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        stop_reason = "max_tokens" if reason == "max_output_tokens" else (reason or "incomplete")
    else:
        stop_reason = "tool_use" if tool_calls else "end_turn"

    usage = response.usage
    in_details = getattr(usage, "input_tokens_details", None)
    cached = (getattr(in_details, "cached_tokens", 0) or 0) if in_details is not None else 0
    # GPT-5.6+ bills automatic-cache WRITES at 1.25x input; the Responses API reports them in
    # usage.input_tokens_details.cache_write_tokens (verified 2026-09-23, OpenAI prompt-caching
    # guide). Not captured before this change, so Luna costs through Sweep 3 omit the premium.
    cache_write = (getattr(in_details, "cache_write_tokens", 0) or 0) if in_details is not None else 0
    # Reasoning tokens are billed as output and ALREADY included in output_tokens;
    # the Responses API also breaks them out. Surface the breakout in `raw` (not a
    # new Usage field) so cost accounting stays correct while reasoning volume is
    # still visible per call.
    out_details = getattr(usage, "output_tokens_details", None)
    reasoning = (getattr(out_details, "reasoning_tokens", 0) or 0) if out_details is not None else 0

    return LLMResponse(
        text="\n".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=usage.input_tokens,   # already the total (includes cached/written)
            output_tokens=usage.output_tokens,
            cached_tokens=cached,
            cache_write_tokens=cache_write,
        ),
        raw={"model": response.model, "id": response.id,
             "reasoning_tokens": reasoning},
        assistant_blocks=[{"type": "openai_output_items", "items": native_items}],
        reasoning_blocks=n_reasoning,
    )


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


def drop_reasoning_items(resp: LLMResponse) -> LLMResponse:
    """The exploratory no-passback arm: remove reasoning items from the assistant turn the agent
    appends (message and function_call items kept unchanged), so the NEXT request carries no prior
    reasoning. ``reasoning_blocks`` still counts what the model PRODUCED on this call."""
    import dataclasses
    blocks = [{**b, "items": [i for i in b.get("items", []) if i.get("type") != "reasoning"]}
              if b.get("type") == "openai_output_items" else b
              for b in (resp.assistant_blocks or [])]
    return dataclasses.replace(resp, assistant_blocks=blocks)


def _item_dict(item) -> dict:
    """An output item as a plain dict, unchanged."""
    return _to_plain(item)


class OpenAIClient:
    """LLMClient implementation backed by the OpenAI **Responses** API.

    We use ``/v1/responses`` (not ``/v1/chat/completions``) because GPT-5.6 Luna
    refuses function tools together with ``reasoning_effort`` on chat/completions
    ("...use /v1/responses or set reasoning_effort to 'none'"); the Responses API
    keeps reasoning at the pinned effort AND supports function tools. Reasoning
    models do not accept ``temperature``, so it is NOT sent (recorded as null in
    the model block); the study's temperature=1.0 default only applies to the
    Anthropic arm. See docs/DECISIONS.md 2026-09-19.

    Args:
        model: Exact API model ID string (e.g. ``"gpt-5.6-luna"``).  No default —
            the caller must provide a verified ID.
        reasoning_effort: One of ``none/low/medium/high/xhigh/max``.  Pinned
            explicitly (default ``"medium"``, the provider default) and recorded
            in the trial's model block via :meth:`describe`.
        temperature: Accepted for interface symmetry but NOT sent to a reasoning
            model; recorded as ``None`` in :meth:`describe`.
        reasoning_passback: ``True`` (always, for every scheduled arm) replays prior reasoning
            items. ``False`` exists ONLY for the exploratory H8-defect arm (STAGE4 Part 1
            pre-registration; LIMITATIONS L32): reasoning items are dropped from the returned
            assistant turn, so no later request carries them — reproducing H8's Luna ReAct
            condition to quantify its handicap. Recorded in :meth:`describe` when off.
    """

    def __init__(
        self,
        model: str,
        temperature: float = 1.0,
        reasoning_effort: str = "medium",
        reasoning_passback: bool = True,
    ) -> None:
        import openai

        self._reasoning_effort = check_effort(reasoning_effort)
        self._reasoning_passback = bool(reasoning_passback)
        self._client = openai.OpenAI()  # OPENAI_API_KEY from env
        self._model = model
        # Reasoning models sample internally; temperature is not a supported
        # Responses param for them, so we do not send it (recorded as None).
        self._temperature = None

    def describe(self) -> dict:
        """Provider metadata merged into the trial's model block.

        Records the explicitly-pinned ``reasoning_effort`` (Haiku has no such
        knob — recording it makes the cross-provider difference stated, not
        hidden) and the model's ``knowledge_cutoff`` / context window.
        """
        d = describe_model(self._model, self._temperature, self._reasoning_effort)
        if not self._reasoning_passback:
            d["reasoning_passback"] = False
        return d

    def complete(
        self,
        messages: list[dict],
        tools_schema: list[dict],
        *,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Call the OpenAI Responses API with bounded retry."""
        import openai

        transient = (
            openai.RateLimitError,
            openai.InternalServerError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        )

        req_input = to_responses_input(messages)
        req_tools = to_responses_tools(tools_schema)

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.responses.create(
                    model=self._model,
                    input=req_input,
                    tools=req_tools,
                    # Effort pinned explicitly (never left implicit) — the reason
                    # we are on /v1/responses at all (see class docstring).
                    reasoning={"effort": self._reasoning_effort},
                    max_output_tokens=max_tokens,
                    # Stateless: nothing is stored server-side; reasoning items come back with
                    # encrypted_content and are REPLAYED verbatim in the next request's input
                    # (to_responses_input), so reasoning survives across tool calls.
                    store=False,
                    include=["reasoning.encrypted_content"],
                )
                parsed = parse_responses(response)
                return parsed if self._reasoning_passback else drop_reasoning_items(parsed)

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
