"""Individual tool implementations (spec §6).

Each tool is a function ``(ctx: ToolContext, **kwargs) -> dict`` returning
a status dict.  Tools are registered on the ToolContext by
:func:`register_all_tools`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from harness.tools.tool_context import ToolContext, _error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_LOG_PAGE = 50
_MAX_CODE_PAGE = 100


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def read_log(ctx: ToolContext, *, artifact_id: str,
             start_line: int = 1, end_line: int = 50) -> dict:
    """Read lines from a log artifact in run_output/."""
    try:
        resolved = ctx.resolve_path(f"run_output/{artifact_id}")
    except ValueError as e:
        return _error("INVALID_PATH", str(e))

    if not resolved.exists():
        return _error("ARTIFACT_NOT_FOUND", f"Artifact not found: {artifact_id!r}")

    lines = resolved.read_text().splitlines()
    total_lines = len(lines)

    start_line = max(1, start_line)
    end_line = min(start_line + _MAX_LOG_PAGE - 1, end_line, total_lines)

    selected = lines[start_line - 1 : end_line]

    return {
        "status": "ok",
        "lines": selected,
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": total_lines,
    }


def query_metrics(ctx: ToolContext, *, series: str,
                  start_epoch: int | None = None,
                  end_epoch: int | None = None,
                  agg: str | None = None) -> dict:
    """Query metrics from run_output/metrics.jsonl."""
    try:
        resolved = ctx.resolve_path("run_output/metrics.jsonl")
    except ValueError as e:
        return _error("INVALID_PATH", str(e))

    if not resolved.exists():
        return _error("ARTIFACT_NOT_FOUND", "metrics.jsonl not found")

    records = []
    with open(resolved) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("end_of_epoch"):
                records.append(rec)

    # Check that the series exists in at least one record
    if not any(series in rec for rec in records):
        return _error(
            "INVALID_ARGUMENTS",
            f"Series {series!r} not found in metrics",
        )

    # Filter by epoch range
    values = []
    for rec in records:
        epoch = rec.get("epoch")
        if start_epoch is not None and epoch < start_epoch:
            continue
        if end_epoch is not None and epoch > end_epoch:
            continue
        if series in rec:
            values.append({"epoch": epoch, "value": rec[series]})

    # Aggregate if requested
    if agg is not None:
        if not values:
            return _error("INVALID_ARGUMENTS", "No values in range for aggregation")

        nums = [v["value"] for v in values]
        if agg == "mean":
            agg_value = sum(nums) / len(nums)
        elif agg == "min":
            agg_value = min(nums)
        elif agg == "max":
            agg_value = max(nums)
        elif agg == "last":
            agg_value = nums[-1]
        else:
            return _error(
                "INVALID_ARGUMENTS",
                f"Unknown aggregation {agg!r}; use mean/min/max/last",
            )

        return {
            "status": "ok",
            "series": series,
            "agg": agg,
            "value": agg_value,
        }

    return {
        "status": "ok",
        "series": series,
        "values": values,
    }


def read_config(ctx: ToolContext, *, key_path: str | None = None) -> dict:
    """Read config from run_output/config.resolved.yaml."""
    try:
        resolved = ctx.resolve_path("run_output/config.resolved.yaml")
    except ValueError as e:
        return _error("INVALID_PATH", str(e))

    if not resolved.exists():
        return _error("ARTIFACT_NOT_FOUND", "config.resolved.yaml not found")

    with open(resolved) as f:
        config = yaml.safe_load(f)

    if key_path is None:
        return {"status": "ok", "key_path": None, "value": config}

    # Navigate dot-separated key path
    current = config
    for key in key_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return _error(
                "INVALID_ARGUMENTS",
                f"Key path {key_path!r} not found in config",
            )
        current = current[key]

    return {"status": "ok", "key_path": key_path, "value": current}


def read_code(ctx: ToolContext, *, path: str,
              start_line: int = 1, end_line: int = 100) -> dict:
    """Read lines from a source file in the workspace."""
    try:
        resolved = ctx.resolve_path(path)
    except ValueError as e:
        return _error("INVALID_PATH", str(e))

    if not resolved.exists():
        return _error("ARTIFACT_NOT_FOUND", f"File not found: {path!r}")

    lines = resolved.read_text().splitlines()
    total_lines = len(lines)

    start_line = max(1, start_line)
    end_line = min(start_line + _MAX_CODE_PAGE - 1, end_line, total_lines)

    selected = lines[start_line - 1 : end_line]

    return {
        "status": "ok",
        "path": path,
        "lines": selected,
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": total_lines,
    }


def list_files(ctx: ToolContext, *, pattern: str = "**/*") -> dict:
    """List files in the workspace."""
    ws = ctx.workspace_root
    files = []

    # Show .data as a single entry if it exists
    data_dir = ws / ".data"
    has_data = data_dir.exists()

    for p in sorted(ws.rglob(pattern)):
        # Skip .data contents — just show .data as a directory entry
        if has_data:
            try:
                p.resolve().relative_to(data_dir.resolve())
                continue
            except ValueError:
                pass

        if p.is_file():
            files.append(str(p.relative_to(ws)))

    if has_data:
        files.append(".data/")
        files.sort()

    return {"status": "ok", "files": files}


def submit(ctx: ToolContext, *, diagnosis: dict,
           evidence_refs: list, repair_spec: dict | None = None) -> dict:
    """Record the agent's submission.

    ``repair_spec`` may be ``None`` (or ``{"repair_type": "none", "patches": {}}``)
    to submit NO repair — the correct action on a healthy run.  Any other case
    expects a ``config_patch`` repair.
    """
    if ctx.submission_count >= ctx.max_submissions:
        return _error(
            "SUBMISSION_LIMIT_REACHED",
            f"Maximum submissions ({ctx.max_submissions}) reached",
        )

    submission = {
        "diagnosis": diagnosis,
        "evidence_refs": evidence_refs,
        "repair_spec": repair_spec,
    }
    ctx.record_submission(submission)

    return {"status": "ok", "submitted": True}


def diff_config(ctx: ToolContext, **kwargs: Any) -> dict:
    """Deferred to M2.3."""
    return _error("TOOL_NOT_AVAILABLE", "diff_config is deferred to M2.3")


def run_training(ctx: ToolContext, **kwargs: Any) -> dict:
    """Deferred to M2.3."""
    return _error("TOOL_NOT_AVAILABLE", "run_training is deferred to M2.3")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_all_tools(ctx: ToolContext) -> None:
    """Register all tool functions on a ToolContext."""
    ctx.register_tool("read_log", read_log)
    ctx.register_tool("query_metrics", query_metrics)
    ctx.register_tool("read_config", read_config)
    ctx.register_tool("read_code", read_code)
    ctx.register_tool("list_files", list_files)
    ctx.register_tool("submit", submit)
    ctx.register_tool("diff_config", diff_config)
    ctx.register_tool("run_training", run_training)
