"""Versioned trial-record schema, environment capture, and record I/O.

Every agent trial produces a self-contained provenance record that captures
the environment, model parameters, token usage, tool transcript, scores,
and submission.  Records are written to
``results/<case_id>/trials/<agent>_<run_id>.yaml`` and indexed in
``results/index.jsonl`` for DataFrame-level analysis.

Schema version: 1.0
"""
from __future__ import annotations

import hashlib
import json
import platform as platform_mod
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness.pricing import estimate_cost

SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    """SHA-256 hex digest of a file, or None if the file doesn't exist."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_info(project_root: Path) -> tuple[str, bool]:
    """Return (commit_hash, is_dirty).

    Falls back to (``"unknown"``, ``False``) if git is unavailable or the
    directory is not a repository.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=project_root,
        )
        commit_hash = commit.stdout.strip() if commit.returncode == 0 else "unknown"

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_root,
        )
        is_dirty = bool(status.stdout.strip()) if status.returncode == 0 else False
    except FileNotFoundError:
        commit_hash = "unknown"
        is_dirty = False

    return commit_hash, is_dirty


def capture_environment(project_root: Path, case_dir: Path) -> dict:
    """Capture environment block at run start."""
    commit_hash, is_dirty = _git_info(project_root)
    card_hash = _sha256_file(case_dir / "card.public.yaml") or "unknown"
    uv_lock_hash = _sha256_file(project_root / "uv.lock")

    return {
        "harness_git_commit": commit_hash,
        "git_dirty": is_dirty,
        "case_card_hash": card_hash,
        "python_version": sys.version,
        "platform": platform_mod.platform(),
        "uv_lock_hash": uv_lock_hash,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "wall_clock_sec": 0.0,  # filled by finalize_record
    }


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

def build_empty_record(
    case_id: str,
    agent_name: str,
    run_id: str,
    environment: dict,
) -> dict:
    """Create an empty schema-conformant record with all blocks initialized."""
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "agent_name": agent_name,
        "run_id": run_id,
        "status": "partial",

        "environment": dict(environment),

        "model": {
            "model_id": None,
            "model_version": None,
            "provider": None,
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "stop_reason": None,
            "request_seed": None,
        },

        "usage": {
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": None,
        },

        "submission": None,
        "tool_transcript": [],
        "llm_transcript": [],

        "scores": {
            "detection": None,
            "identification": None,
            "evidence": None,
            "recovery": None,
            "safety": None,
        },

        "budget": {
            "tool_calls_used": 0,
            "tool_calls_total": 0,
        },
    }


def finalize_record(
    record: dict,
    tools: Any,  # ToolContext — Any to avoid circular import
    scores: dict | None,
    wall_clock_sec: float,
) -> dict:
    """Fill in post-run fields: transcript, submission, scores, timing, cost."""
    record["environment"]["wall_clock_sec"] = wall_clock_sec
    record["submission"] = tools.submission
    record["tool_transcript"] = tools.transcript

    record["budget"]["tool_calls_used"] = tools.budget_total - tools.budget_remaining
    record["budget"]["tool_calls_total"] = tools.budget_total

    # Usage — stubs have zero tokens; real agents will populate these
    model_id = record["model"].get("model_id")
    input_tokens = record["usage"]["input_tokens"]
    output_tokens = record["usage"]["output_tokens"]
    cached_tokens = record["usage"]["cached_tokens"]
    record["usage"]["total_tokens"] = input_tokens + output_tokens

    cost_est = estimate_cost(model_id, input_tokens, output_tokens, cached_tokens)
    if cost_est is not None:
        record["usage"]["estimated_cost_usd"] = cost_est.cost_usd
        record["usage"]["cost_is_estimate"] = cost_est.is_estimate
    else:
        record["usage"]["estimated_cost_usd"] = None

    if scores is not None:
        record["scores"] = scores

    return record


# ---------------------------------------------------------------------------
# Record I/O
# ---------------------------------------------------------------------------

def _trials_dir(project_root: Path, case_id: str) -> Path:
    return project_root / "results" / case_id / "trials"


def write_record(
    project_root: Path,
    record: dict,
    overwrite_partial: bool = False,
) -> Path:
    """Write record to ``results/<case_id>/trials/<agent>_<run_id>.yaml``.

    If *overwrite_partial* is ``False`` (the default), raises
    :class:`FileExistsError` if the file already exists.

    If *overwrite_partial* is ``True``, only overwrites if the existing
    record has ``status: "partial"``.
    """
    trials = _trials_dir(project_root, record["case_id"])
    trials.mkdir(parents=True, exist_ok=True)
    path = trials / f"{record['agent_name']}_{record['run_id']}.yaml"

    if path.exists():
        if not overwrite_partial:
            raise FileExistsError(f"Trial record already exists: {path}")
        existing = yaml.safe_load(path.read_text())
        if existing.get("status") != "partial":
            raise FileExistsError(
                f"Refusing to overwrite non-partial record: {path}"
            )

    with open(path, "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False)

    return path


# ---------------------------------------------------------------------------
# Index (results/index.jsonl)
# ---------------------------------------------------------------------------

def _index_line(record: dict) -> dict:
    """Extract index-level fields from a full record."""
    scores = record.get("scores") or {}
    detection = scores.get("detection") or {}
    identification = scores.get("identification") or {}
    evidence = scores.get("evidence") or {}
    recovery = scores.get("recovery")

    if recovery is not None:
        recovery_verdict = recovery.get("verdict", "pending")
    else:
        recovery_verdict = "pending"

    usage = record.get("usage", {})
    cost_est = usage.get("estimated_cost_usd")

    return {
        "case_id": record["case_id"],
        "agent_name": record["agent_name"],
        "run_id": record["run_id"],
        "model_id": record.get("model", {}).get("model_id"),
        "detection_correct": detection.get("correct"),
        "identification_correct": identification.get("correct"),
        "evidence_f1": evidence.get("f1"),
        "recovery_verdict": recovery_verdict,
        "total_tokens": usage.get("total_tokens", 0),
        "estimated_cost_usd": cost_est,
        "cost_is_estimate": usage.get("cost_is_estimate", True),
        "harness_git_commit": record.get("environment", {}).get("harness_git_commit"),
        "status": record.get("status", "unknown"),
        "timestamp_utc": record.get("environment", {}).get("timestamp_utc"),
    }


def append_index(project_root: Path, record: dict) -> None:
    """Append one JSON line to ``results/index.jsonl``.

    Opens in append mode, writes one line, and flushes immediately.
    """
    index_path = project_root / "results" / "index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = _index_line(record)
    with open(index_path, "a") as f:
        f.write(json.dumps(line, separators=(",", ":")) + "\n")
        f.flush()


def update_index(project_root: Path, record: dict) -> None:
    """Rewrite the index line for *record*'s ``run_id`` from current state.

    The trial record is the single source of truth.  This function
    derives the index line via :func:`_index_line` and overwrites the
    existing entry in ``index.jsonl``.  Called after any (re)score —
    diagnosis or recovery — to keep the index in sync.

    If no matching ``run_id`` is found, the line is appended.
    """
    index_path = project_root / "results" / "index.jsonl"
    new_line = _index_line(record)
    run_id = record["run_id"]

    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "w") as f:
            f.write(json.dumps(new_line, separators=(",", ":")) + "\n")
            f.flush()
        return

    lines = index_path.read_text().splitlines()
    updated_lines: list[str] = []
    found = False
    for raw in lines:
        if not raw.strip():
            continue
        entry = json.loads(raw)
        if entry.get("run_id") == run_id:
            updated_lines.append(json.dumps(new_line, separators=(",", ":")))
            found = True
        else:
            updated_lines.append(raw.strip())

    if not found:
        updated_lines.append(json.dumps(new_line, separators=(",", ":")))

    with open(index_path, "w") as f:
        for line in updated_lines:
            f.write(line + "\n")
        f.flush()
