"""Static full-context baseline agent — the H6 control condition (spec §8).

The control for tool-mediated investigation: it assembles the ENTIRE run (config,
code, metrics, logs) into one prompt and makes ONE LLM call, versus the ReAct
agent's tool loop.  The two agents share system-prompt text, submit schema,
reference band, and healthy-runs guidance VERBATIM (imported from
``agents.llm_agent``) and differ ONLY in investigation mode — so any score
difference is attributable to tools, not wording.

Context is read ONLY through the sealed ``ToolContext`` (the same read tools the
ReAct agent uses), never off the filesystem, so the wall applies identically.
The public card reaches both agents through the shared system prompt (it lives
outside the sealed workspace).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import yaml

from agents.llm_agent import (
    HEALTHY_RUNS_TEXT,
    SUBMIT_FORMAT_TEXT,
    SUBMIT_SCHEMA,
    build_case_info,
)
from harness.llm.client import LLMClient
from harness.tools.tool_context import ToolContext

# Prompt version — bump whenever the static prompt template text changes (the
# drift guard in test_prompt_versioning asserts the template hash matches).
STATIC_PROMPT_VERSION = "static-1"

# Static intro — the ONLY textual difference from the ReAct prompt (investigation
# mode). Everything after it (case info, healthy runs, submit format) is shared.
_STATIC_INTRO = (
    "You are a machine learning diagnostics agent. You are analyzing a "
    "possibly-faulty training run. You are given the COMPLETE contents of the "
    "run below — config, code, metrics, and logs — in a single view. Analyze "
    "them in one pass, then call the submit tool EXACTLY ONCE with your diagnosis."
)

_METRIC_SERIES = ["train_loss", "val_loss", "metric_visible_val_acc", "lr"]


class _BudgetExhausted(Exception):
    """Raised when a context-assembly read is refused for budget — a hard error."""


class StaticContextAgent:
    """One-shot full-context baseline (H6 control)."""

    def __init__(
        self,
        client: LLMClient,
        model_id: str = "unknown",
        temperature: float = 1.0,
        max_response_tokens: int = 8192,
        max_log_chars: int = 20000,
        provider: str = "anthropic",
        anchor: str = "on",
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._temperature = temperature
        self._max_response_tokens = max_response_tokens
        self._max_log_chars = max_log_chars
        self._provider = provider
        self._anchor = anchor  # "on" includes the reference band; "off" omits it
        self._record: dict | None = None

    @property
    def name(self) -> str:
        return f"static_{self._model_id}"

    def set_record(self, record: dict) -> None:
        self._record = record

    # -- sealed-layer readers ----------------------------------------------

    @staticmethod
    def _check_budget(result: dict) -> dict:
        if result.get("status") == "error" and result.get("error") == "BUDGET_EXHAUSTED":
            raise _BudgetExhausted(result.get("detail", "budget exhausted"))
        return result

    def _read_code_full(self, tools: ToolContext, path: str) -> str:
        """Read a full workspace file via read_code's 100-line pages."""
        out: list[str] = []
        start = 1
        while True:
            res = self._check_budget(
                tools.call("read_code", path=path, start_line=start, end_line=start + 99)
            )
            if res.get("status") != "ok":
                return f"(unavailable: {res.get('error')})"
            out.extend(res["lines"])
            if res["end_line"] >= res["total_lines"] or not res["lines"]:
                break
            start = res["end_line"] + 1
        return "\n".join(out)

    def _read_log_full(self, tools: ToolContext) -> tuple[str, bool]:
        """Read the full stdout.log via read_log's 50-line pages; apply the cap."""
        out: list[str] = []
        start = 1
        while True:
            res = self._check_budget(
                tools.call("read_log", artifact_id="logs/stdout.log",
                           start_line=start, end_line=start + 49)
            )
            if res.get("status") != "ok":
                return f"(unavailable: {res.get('error')})", False
            out.extend(res["lines"])
            if res["end_line"] >= res["total_lines"] or not res["lines"]:
                break
            start = res["end_line"] + 1
        text = "\n".join(out)
        if len(text) > self._max_log_chars:
            half = self._max_log_chars // 2
            dropped = len(text) - self._max_log_chars
            text = text[:half] + f"\n…[truncated {dropped} chars]…\n" + text[-half:]
            return text, True
        return text, False

    def _read_metrics_table(self, tools: ToolContext) -> str:
        """End-of-epoch rows via query_metrics, zipped into a compact table."""
        by_series: dict[str, dict] = {}
        for series in _METRIC_SERIES:
            res = self._check_budget(tools.call("query_metrics", series=series))
            if res.get("status") != "ok":
                continue
            by_series[series] = {v["epoch"]: v["value"] for v in res.get("values", [])}
        if not by_series:
            return "(no end-of-epoch metrics — the run did not produce them)"
        epochs = sorted({e for m in by_series.values() for e in m})
        header = "epoch | " + " | ".join(_METRIC_SERIES)
        rows = [header, "-" * len(header)]
        for e in epochs:
            cells = [str(e)] + [
                (f"{by_series.get(s, {}).get(e):.6f}"
                 if isinstance(by_series.get(s, {}).get(e), float)
                 else str(by_series.get(s, {}).get(e, "")))
                for s in _METRIC_SERIES
            ]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

    # -- prompt assembly ----------------------------------------------------

    def _system_prompt(self, case_dir: Path) -> str:
        with open(case_dir / "card.public.yaml") as f:
            card = yaml.safe_load(f)
        return (
            _STATIC_INTRO
            + "\n\n## Case information\n\n"
            + build_case_info(card, include_band=self._anchor == "on")
            + "\n\n"
            + HEALTHY_RUNS_TEXT
            + "\n\n"
            + SUBMIT_FORMAT_TEXT
        )

    def _assemble_user_message(self, tools: ToolContext) -> tuple[str, list[str]]:
        """Read every artifact through the sealed layer; return (message, truncated)."""
        config_yaml = self._read_code_full(tools, "config.yaml")
        config_resolved = self._read_code_full(tools, "run_output/config.resolved.yaml")
        train_py = self._read_code_full(tools, "train.py")
        datautil_py = self._read_code_full(tools, "datautil.py")
        metrics = self._read_metrics_table(tools)
        log_text, log_truncated = self._read_log_full(tools)

        truncated = ["logs/stdout.log"] if log_truncated else []
        sections = [
            ("config.yaml", config_yaml),
            ("config.resolved.yaml", config_resolved),
            ("train.py", train_py),
            ("datautil.py", datautil_py),
            ("metrics.jsonl (end-of-epoch)", metrics),
            ("logs/stdout.log", log_text),
        ]
        body = "\n\n".join(f"### {name}\n\n```\n{content}\n```" for name, content in sections)
        return "# Run artifacts\n\n" + body, truncated

    # -- run ----------------------------------------------------------------

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        case_dir = Path(case_dir)
        if self._record is not None:
            self._record["model"].update({
                "model_id": self._model_id,
                "provider": self._provider,
                "temperature": self._temperature,
                "max_tokens": self._max_response_tokens,
            })
            self._record.setdefault("static_context", {})

        # 1. Assemble context via the sealed tool layer (tagged, budget hard-fail).
        n_before = len(tools.transcript)
        tools.set_phase("context_assembly")
        try:
            user_message, truncated = self._assemble_user_message(tools)
        except _BudgetExhausted as e:
            tools.set_phase(None)
            if self._record is not None:
                self._record["static_context"].update({
                    "assembly_failed": f"budget exhausted during context assembly: {e}",
                    "assembly_tool_calls": len(tools.transcript) - n_before,
                })
                self._record["termination_reason"] = "assembly_failed"
            return  # HARD FAIL — never diagnose on partial context; submission stays None
        finally:
            tools.set_phase(None)

        assembly_calls = len(tools.transcript) - n_before
        if self._record is not None:
            self._record["static_context"].update({
                "assembly_tool_calls": assembly_calls,
                "any_truncated": bool(truncated),
                "truncated_artifacts": truncated,
                "assembly_failed": None,
            })

        # 2. Single message = shared instructions + the assembled artifacts.
        system_prompt = self._system_prompt(case_dir)
        if self._record is not None:
            self._record["prompt"] = {
                "system_prompt_text": system_prompt,
                "prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest(),
                "prompt_version": STATIC_PROMPT_VERSION + (
                    "" if self._anchor == "on" else "-noanchor"),
            }
        full = system_prompt + "\n\n" + user_message
        messages: list[dict] = [{"role": "user", "content": full}]

        # 3. One LLM call (+ at most one bounded follow-up), submit exactly once.
        first_input_tokens: int | None = None
        termination = "no_submit_after_followup"  # default if neither call submits
        for attempt in range(2):
            _t0 = time.monotonic()
            response = self._client.complete(
                messages, [SUBMIT_SCHEMA], max_tokens=self._max_response_tokens,
            )
            _latency = time.monotonic() - _t0
            if first_input_tokens is None:
                first_input_tokens = response.usage.input_tokens
            self._capture(response, attempt, _latency)

            submit_calls = [tc for tc in response.tool_calls if tc.name == "submit"]
            if submit_calls:
                tc = submit_calls[0]
                if isinstance(tc.arguments, dict):
                    tools.call("submit", **tc.arguments)
                termination = "submitted"
                break

            # No submit yet. One bounded follow-up (also the max_tokens continuation).
            if attempt == 0:
                assistant_content: list[dict] = []
                if response.text:
                    assistant_content.append({"type": "text", "text": response.text})
                for tcall in response.tool_calls:
                    assistant_content.append({
                        "type": "tool_use", "id": tcall.id,
                        "name": tcall.name, "input": tcall.arguments,
                    })
                if assistant_content:
                    messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": "You must call submit now."})
            # attempt == 1 with no submit → submission stays None.

        if self._record is not None:
            self._record["static_context"]["context_tokens_sent"] = first_input_tokens
            self._record["termination_reason"] = termination

    def _capture(self, response, turn: int, latency_sec: float = 0.0) -> None:
        if self._record is None:
            return
        u = self._record["usage"]
        u["llm_calls"] += 1
        u["input_tokens"] += response.usage.input_tokens
        u["output_tokens"] += response.usage.output_tokens
        u["cached_tokens"] += response.usage.cached_tokens
        entry = {
            "turn": turn,
            "response_text": response.text,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ],
            "stop_reason": response.stop_reason,
            "api_model": (response.raw or {}).get("model"),
            "latency_sec": round(latency_sec, 4),
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
        self._record["llm_transcript"].append(entry)
        if response.stop_reason == "max_tokens":
            u["max_tokens_truncations"] += 1
            entry["truncated"] = True
