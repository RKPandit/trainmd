"""LLM-powered diagnostic agent with ReAct loop.

Uses the :class:`LLMClient` protocol to call any LLM provider.  Incrementally
captures usage tokens on every call so that the provenance record survives
crashes.  All agent logic is testable at zero cost via :class:`FakeLLMClient`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from harness.llm.client import LLMClient, LLMResponse, Usage
from harness.tools.tool_context import ToolContext


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic message format)
# ---------------------------------------------------------------------------

TOOLS_SCHEMA: list[dict] = [
    {
        "name": "read_log",
        "description": (
            "Read lines from a log file in the training run output. "
            "Returns lines between start_line and end_line (max 50 per page)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "Log file name relative to run_output/, e.g. 'logs/stdout.log'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-indexed, default 1)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (default 50, max page size 50)",
                },
            },
            "required": ["artifact_id"],
        },
    },
    {
        "name": "query_metrics",
        "description": (
            "Query epoch-level metrics from metrics.jsonl. "
            "Returns the full series or a windowed/aggregated view."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series": {
                    "type": "string",
                    "description": "Metric series name, e.g. 'train_loss', 'metric_visible_val_acc'",
                },
                "start_epoch": {
                    "type": "integer",
                    "description": "First epoch (inclusive). Omit for full series.",
                },
                "end_epoch": {
                    "type": "integer",
                    "description": "Last epoch (inclusive). Omit for full series.",
                },
                "agg": {
                    "type": "string",
                    "enum": ["mean", "min", "max", "last"],
                    "description": "Aggregation over the window. Omit for raw values.",
                },
            },
            "required": ["series"],
        },
    },
    {
        "name": "read_config",
        "description": (
            "Read the resolved training config (config.resolved.yaml). "
            "Returns the full config or a specific key path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key_path": {
                    "type": "string",
                    "description": (
                        "Dot-separated key path, e.g. 'training.lr'. "
                        "Omit for the full config."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_code",
        "description": (
            "Read source code from the workspace. "
            "Returns lines between start_line and end_line (max 100 per page)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file in the workspace, e.g. 'train.py'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-indexed, default 1)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (default 100, max page size 100)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (default '**/*')",
                },
            },
            "required": [],
        },
    },
    {
        "name": "submit",
        "description": (
            "Submit your final diagnosis, evidence, and repair. "
            "Call EXACTLY ONCE as your last action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "diagnosis": {
                    "type": "object",
                    "description": "Detection and classification of the incident.",
                    "properties": {
                        "detected": {
                            "type": "boolean",
                            "description": "true if you believe an incident occurred",
                        },
                        "operator_class": {
                            "type": "string",
                            "description": (
                                "Category of the fault, e.g. 'lr_misconfiguration', "
                                "'data_corruption', 'none'"
                            ),
                        },
                    },
                    "required": ["detected", "operator_class"],
                },
                "evidence_refs": {
                    "type": "array",
                    "description": "Evidence references supporting your diagnosis.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["config_key", "metric_window", "line_range", "code_span"],
                            },
                            "artifact_id": {
                                "type": "string",
                                "description": (
                                    "Artifact name, e.g. 'config.yaml', 'metrics.jsonl', "
                                    "'logs/stdout.log', 'train.py'"
                                ),
                            },
                            "detail": {
                                "type": "object",
                                "description": (
                                    "Kind-specific fields. "
                                    "config_key: {key_path: str}. "
                                    "metric_window: {series: str, start_epoch: int, end_epoch: int}. "
                                    "line_range: {start_line: int, end_line: int}. "
                                    "code_span: {start_line: int, end_line: int}."
                                ),
                            },
                        },
                        "required": ["kind", "artifact_id", "detail"],
                    },
                },
                "repair_spec": {
                    "type": "object",
                    "description": "Proposed config repair.",
                    "properties": {
                        "repair_type": {
                            "type": "string",
                            "description": "Always 'config_patch' for now.",
                        },
                        "patches": {
                            "type": "object",
                            "description": "Mapping of dotted key paths to corrected values.",
                        },
                    },
                    "required": ["repair_type", "patches"],
                },
            },
            "required": ["diagnosis", "evidence_refs", "repair_spec"],
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are a machine learning diagnostics agent. You are investigating a \
possibly-faulty training run. Your job:

1. Investigate using the available tools to determine if there is an \
incident, what kind of incident it is, and gather evidence.
2. Propose a repair if an incident is detected.
3. Call the submit tool EXACTLY ONCE as your final action.

## Case information

{case_info}

## Investigation strategy

- Start by listing files and reading the config.
- Query metrics to spot anomalies (compare training loss, validation accuracy \
across epochs).
- Read training code if config values seem suspicious.
- Focus on learning rate, batch size, and optimizer settings as common silent \
fault vectors.
- Look for values that differ significantly from reasonable defaults.
- If you detect an incident, gather evidence appropriate to the fault: \
a config_key ref pointing to the faulty parameter, plus whichever fits the \
symptom — a metric_window for anomalous training curves, or a line_range \
for an error/traceback in a log file (e.g. logs/stdout.log).

## Submit format

When ready, call submit with:
- diagnosis.detected: true/false
- diagnosis.operator_class: category string (e.g. "lr_misconfiguration", \
"data_corruption", "none")
- evidence_refs: list of evidence references
- repair_spec.repair_type: "config_patch"
- repair_spec.patches: dict mapping dotted key paths to corrected values
"""


def _build_system_prompt(case_dir: Path) -> str:
    """Build the system prompt from the public case card."""
    card_path = case_dir / "card.public.yaml"
    with open(card_path) as f:
        card = yaml.safe_load(f)

    case_info_parts = [
        f"Case ID: {card.get('case_id', 'unknown')}",
        f"Workload: {card.get('workload_name', 'unknown')}",
    ]

    if "description" in card:
        case_info_parts.append(f"Description: {card['description']}")

    ref = card.get("reference_visible_metric")
    if ref:
        case_info_parts.append(
            f"Healthy runs on this workload achieve {ref['series']} "
            f"≈ {ref['mean']:.4f} ± {ref['std']:.4f}; treat values "
            f"well outside this band (above OR below) as anomalous."
        )

    return _SYSTEM_PROMPT_TEMPLATE.format(case_info="\n".join(case_info_parts))


# ---------------------------------------------------------------------------
# LLM Agent
# ---------------------------------------------------------------------------

class LLMAgent:
    """ReAct agent powered by an LLM via the :class:`LLMClient` protocol.

    Incrementally captures usage tokens after every ``client.complete()``
    call so that the provenance record survives crashes.
    """

    def __init__(
        self,
        client: LLMClient,
        model_id: str = "unknown",
        temperature: float = 1.0,
        max_turns: int = 15,
        max_total_tokens: int = 200_000,
        max_response_tokens: int = 8192,
        provider: str = "anthropic",
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._temperature = temperature
        self._max_turns = max_turns
        self._max_total_tokens = max_total_tokens
        self._max_response_tokens = max_response_tokens
        self._provider = provider
        self._record: dict | None = None

    @property
    def name(self) -> str:
        return f"llm_{self._model_id}"

    def set_record(self, record: dict) -> None:
        """Called by run_trial before agent.run() to provide the mutable record."""
        self._record = record

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        """Execute the ReAct investigation loop."""
        # 1. Populate model block in record
        if self._record is not None:
            self._record["model"].update({
                "model_id": self._model_id,
                "provider": self._provider,
                "temperature": self._temperature,
                "max_tokens": self._max_response_tokens,
            })

        # 2. Build system prompt
        system_prompt = _build_system_prompt(case_dir)

        # 3. Initialize messages
        messages: list[dict] = [{"role": "user", "content": system_prompt}]

        # 4. ReAct loop
        submitted = False
        consecutive_continuations = 0
        for turn in range(self._max_turns):
            # Token budget check
            if self._record is not None:
                total = (
                    self._record["usage"]["input_tokens"]
                    + self._record["usage"]["output_tokens"]
                )
                if total >= self._max_total_tokens:
                    break

            # Call LLM
            response = self._client.complete(
                messages, TOOLS_SCHEMA, max_tokens=self._max_response_tokens,
            )

            # Incremental usage capture (CRITICAL — crash safety)
            if self._record is not None:
                self._record["usage"]["llm_calls"] += 1
                self._record["usage"]["input_tokens"] += response.usage.input_tokens
                self._record["usage"]["output_tokens"] += response.usage.output_tokens
                self._record["usage"]["cached_tokens"] += response.usage.cached_tokens

            # Append to llm_transcript
            if self._record is not None:
                self._record["llm_transcript"].append({
                    "turn": turn,
                    "response_text": response.text,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    "stop_reason": response.stop_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                })
                # Truncation is a per-model behavior worth reporting: count it
                # and flag the affected entry, whether or not tool calls came
                # back with the truncated response.
                if response.stop_reason == "max_tokens":
                    self._record["usage"]["max_tokens_truncations"] += 1
                    self._record["llm_transcript"][-1]["truncated"] = True

            # Build assistant message for conversation history
            assistant_content: list[dict] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            if not assistant_content:
                break  # model returned nothing
            messages.append({"role": "assistant", "content": assistant_content})

            # If no tool calls, the model is either done thinking (end_turn)
            # or was silenced mid-sentence by the output limit (max_tokens).
            # Truncation must not end the trial: prompt a continuation so a
            # verbose model is not penalized by the plumbing.  The partial
            # assistant text is already appended to `messages` above.
            if not response.tool_calls:
                if response.stop_reason == "max_tokens":
                    if consecutive_continuations >= 3:
                        # Cap exceeded — end cleanly with no submission.
                        if self._record is not None:
                            self._record["llm_transcript"][-1][
                                "continuation_capped"
                            ] = True
                        break
                    consecutive_continuations += 1
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was cut off by the output "
                            "limit. Continue from where you stopped. You must "
                            "finish by calling a tool (for example, submit)."
                        ),
                    })
                    continue  # consumes a turn via the for-loop bound
                break

            # Tool calls came back — the model made progress; reset the counter.
            consecutive_continuations = 0

            # Execute tool calls
            tool_results: list[dict] = []
            for tc in response.tool_calls:
                try:
                    if not isinstance(tc.arguments, dict):
                        raise TypeError(
                            f"Expected dict arguments, got {type(tc.arguments).__name__}"
                        )
                    result = tools.call(tc.name, **tc.arguments)
                except Exception as e:
                    result = {
                        "status": "error",
                        "error": "TOOL_EXECUTION_ERROR",
                        "detail": str(e),
                    }

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(result),
                })

                if tc.name == "submit" and result.get("status") == "ok":
                    submitted = True

            messages.append({"role": "user", "content": tool_results})

            if submitted:
                break
