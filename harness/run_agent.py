"""Agent protocol and trial runner (spec §6).

Defines the minimal :class:`Agent` protocol and the :func:`run_trial`
function that executes one agent on one case, producing a provenance-rich
trial record with crash recovery.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from harness.provenance import (
    append_index,
    build_empty_record,
    capture_environment,
    finalize_record,
    write_record,
)
from harness.tools.tool_context import ToolContext
from harness.tools.tools import register_all_tools

try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Agent protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Agent(Protocol):
    """Minimal agent interface."""

    name: str

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        """Execute the agent's investigation and submit via tools.

        The agent uses ``tools.call()`` to investigate and must call
        ``tools.call("submit", ...)`` exactly once as the terminal action.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}_{suffix}"


# ---------------------------------------------------------------------------
# Trial runner
# ---------------------------------------------------------------------------

def run_trial(
    agent: Agent,
    case_dir: Path,
    project_root: Path | None = None,
    score: bool = True,
) -> dict:
    """Run one agent trial on one case.

    1. Capture environment before the agent starts.
    2. Write a partial record to disk (crash checkpoint).
    3. Run the agent in a try/finally block.
    4. Score free axes (detection, identification, evidence, safety)
       inline — no training cost.  Recovery is ``None`` (pending).
    5. Finalize and persist the record; append to index.jsonl.

    Args:
        agent: An object satisfying the :class:`Agent` protocol.
        case_dir: Path to the case directory.
        project_root: Project root directory (default: auto-detect).
        score: If ``True``, auto-score the free axes inline.

    Returns:
        Trial record dict, also written to
        ``results/<case_id>/trials/<agent_name>_<run_id>.yaml``.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    case_dir = Path(case_dir).resolve()

    with open(case_dir / "card.public.yaml") as f:
        card = yaml.safe_load(f)

    case_id = card["case_id"]
    run_id = _generate_run_id()

    # 1. Capture environment
    env = capture_environment(project_root, case_dir)

    # 2. Build empty record
    record = build_empty_record(case_id, agent.name, run_id, env)

    # 3. Create tool context
    tools = ToolContext(case_dir)
    register_all_tools(tools)

    # 4. Write partial record (crash checkpoint)
    record["status"] = "partial"
    write_record(project_root, record)

    # 4b. Give LLM agents access to the mutable record for incremental usage
    if hasattr(agent, "set_record"):
        agent.set_record(record)

    # 5. Run agent in try/finally
    t0 = time.monotonic()
    agent_error = None
    try:
        agent.run(case_dir, tools)
    except Exception as e:
        agent_error = e
    finally:
        wall_sec = time.monotonic() - t0

        # 6. Score free axes (no training cost)
        scores = None
        if agent_error is None and tools.submission is not None and score:
            from harness.scoring import score_diagnosis
            scores = score_diagnosis(
                {"submission": tools.submission,
                 "tool_transcript": tools.transcript},
                case_dir,
            )

        # 7. Finalize record
        record = finalize_record(record, tools, scores, wall_sec)
        record["status"] = "crashed" if agent_error is not None else "completed"

        # 8. Overwrite the partial record
        write_record(project_root, record, overwrite_partial=True)

        # 9. Append to index
        append_index(project_root, record)

    if agent_error is not None:
        raise agent_error

    return record


# ---------------------------------------------------------------------------
# Agent registry (for CLI)
# ---------------------------------------------------------------------------

_AGENT_REGISTRY: dict[str, str] = {
    "stub_oracle": "agents.stub_agent:StubAgent",
    "stub_degenerate": "agents.stub_degenerate:StubDegenerateAgent",
}


def _load_agent(name: str) -> Agent:
    """Load an agent by name from the registry."""
    if name not in _AGENT_REGISTRY:
        raise ValueError(
            f"Unknown agent {name!r}; known: {sorted(_AGENT_REGISTRY)}"
        )
    module_path, class_name = _AGENT_REGISTRY[name].rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an agent trial on a case (spec §6)",
    )
    parser.add_argument(
        "--case", type=Path, required=True,
        help="Path to the case directory",
    )
    parser.add_argument(
        "--agent", type=str, required=True,
        help="Agent name (e.g. stub_oracle, stub_degenerate)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: auto-detect)",
    )
    args = parser.parse_args()

    agent = _load_agent(args.agent)
    record = run_trial(agent, args.case, args.project_root)
    print(yaml.dump(record, default_flow_style=False, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
