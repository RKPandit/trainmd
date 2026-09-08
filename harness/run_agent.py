"""Agent protocol and trial runner (spec §6).

Defines the minimal :class:`Agent` protocol and the :func:`run_trial`
function that executes one agent on one case, producing a trial record.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

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
) -> dict:
    """Run one agent trial on one case.

    Args:
        agent: An object satisfying the :class:`Agent` protocol.
        case_dir: Path to the case directory.
        project_root: Project root directory (default: auto-detect).

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

    # Create tool context and register tools
    tools = ToolContext(case_dir)
    register_all_tools(tools)

    # Run the agent
    agent.run(case_dir, tools)

    # Build trial record
    record = {
        "case_id": case_id,
        "agent_name": agent.name,
        "run_id": run_id,
        "submission": tools.submission,
        "tool_transcript": tools.transcript,
        "budget_used": tools.budget_total - tools.budget_remaining,
        "budget_total": tools.budget_total,
        "tokens_used": 0,
    }

    # Write to results/
    trials_dir = project_root / "results" / case_id / "trials"
    trials_dir.mkdir(parents=True, exist_ok=True)
    result_path = trials_dir / f"{agent.name}_{run_id}.yaml"
    with open(result_path, "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False)

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
