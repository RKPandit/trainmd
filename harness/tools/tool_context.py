"""Tool execution context for agent trials (spec §6).

Manages budget tracking, path confinement, call logging, and tool dispatch
for one agent trial on one case.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    """Record of one tool invocation."""

    index: int
    tool_name: str
    arguments: dict
    result: dict
    timestamp: float
    phase: str | None = None  # e.g. "context_assembly" — metadata, not counting


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _error(code: str, detail: str) -> dict:
    """Build a standard error result."""
    return {"status": "error", "error": code, "detail": detail}


# ---------------------------------------------------------------------------
# ToolContext
# ---------------------------------------------------------------------------

class ToolContext:
    """Manages tool execution for one agent trial on one case."""

    def __init__(self, case_dir: Path) -> None:
        self._case_dir = Path(case_dir).resolve()
        self._workspace_root = (self._case_dir / "workspace").resolve()

        with open(self._case_dir / "card.public.yaml") as f:
            card = yaml.safe_load(f)

        self._permitted_tools: set[str] = set(card["permitted_tools"])
        budget = card["agent_budget"]
        self._max_tool_calls: int = budget["max_tool_calls"]
        self._max_submissions: int = budget["max_submissions"]

        self._call_log: list[ToolCall] = []
        self._call_count: int = 0
        self._submission_count: int = 0
        self._submission: dict | None = None
        self._phase: str | None = None  # tags subsequent calls; does not affect counting

        # Tool function registry — populated by register_tool()
        self._tool_fns: dict[str, Callable] = {}

    # -- registration -------------------------------------------------------

    def register_tool(self, name: str, fn: Callable) -> None:
        """Register a tool function.  ``fn(ctx, **kwargs) -> dict``."""
        self._tool_fns[name] = fn

    def set_phase(self, phase: str | None) -> None:
        """Tag subsequent tool calls with a phase label (metadata only).

        Used by the static-context agent to mark its context-assembly reads
        (``"context_assembly"``) so analysis can net them out of
        investigation-effort comparisons.  Does NOT change budget/counting.
        """
        self._phase = phase

    # -- public API ---------------------------------------------------------

    def call(self, tool_name: str, **kwargs: Any) -> dict:
        """Execute a tool call with budget and permission checks."""
        # Budget check (counts ALL calls, including rejected ones)
        if self._call_count >= self._max_tool_calls:
            result = _error(
                "BUDGET_EXHAUSTED",
                f"Tool call budget exhausted ({self._max_tool_calls} calls)",
            )
            self._log_call(tool_name, kwargs, result)
            return result

        # Permission check
        if tool_name not in self._permitted_tools:
            result = _error(
                "TOOL_NOT_PERMITTED",
                f"Tool {tool_name!r} is not in permitted_tools for this case",
            )
            self._log_call(tool_name, kwargs, result)
            return result

        # Dispatch
        fn = self._tool_fns.get(tool_name)
        if fn is None:
            result = _error(
                "TOOL_NOT_AVAILABLE",
                f"Tool {tool_name!r} is not implemented",
            )
            self._log_call(tool_name, kwargs, result)
            return result

        result = fn(self, **kwargs)
        self._log_call(tool_name, kwargs, result)
        return result

    def resolve_path(self, path: str) -> Path:
        """Resolve a relative path within the workspace.

        Uses Path.resolve() + is_relative_to() as the sole confinement
        mechanism.  No string-based name blocking.

        Raises:
            ValueError: If the path is absolute or resolves outside workspace.
        """
        if Path(path).is_absolute():
            raise ValueError(
                f"Absolute paths are not allowed: {path!r}"
            )

        resolved = (self._workspace_root / path).resolve()

        if not resolved.is_relative_to(self._workspace_root):
            raise ValueError(
                f"Path escapes workspace: {path!r}"
            )

        return resolved

    # -- properties ---------------------------------------------------------

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def case_dir(self) -> Path:
        return self._case_dir

    @property
    def transcript(self) -> list[dict]:
        """Serializable list of all tool calls."""
        return [asdict(tc) for tc in self._call_log]

    @property
    def budget_remaining(self) -> int:
        return max(0, self._max_tool_calls - self._call_count)

    @property
    def budget_total(self) -> int:
        return self._max_tool_calls

    @property
    def submission(self) -> dict | None:
        return self._submission

    @property
    def submission_count(self) -> int:
        return self._submission_count

    @property
    def max_submissions(self) -> int:
        return self._max_submissions

    # -- submission ---------------------------------------------------------

    def record_submission(self, submission: dict) -> None:
        """Record a submission (called by the submit tool)."""
        self._submission_count += 1
        self._submission = submission

    # -- internals ----------------------------------------------------------

    def _log_call(self, tool_name: str, arguments: dict, result: dict) -> None:
        """Log a tool call and increment the counter."""
        tc = ToolCall(
            index=self._call_count,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            timestamp=time.monotonic(),
            phase=self._phase,
        )
        self._call_log.append(tc)
        self._call_count += 1
