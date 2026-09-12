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
    build_empty_record,
    capture_environment,
    finalize_record,
    update_index,
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
    allow_trusted: bool = False,
    conditions: dict | None = None,
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

    # Trusted agents read hidden/ ground truth directly (bypassing the sealed
    # tool layer).  They are diagnostic probes, NEVER contestants — refuse to
    # run one unless the caller explicitly opts in, so a trusted result can
    # never be produced (and later scored/aggregated) by accident.
    is_trusted = getattr(agent, "is_trusted", False)
    if is_trusted and not allow_trusted:
        raise PermissionError(
            f"Agent {getattr(agent, 'name', agent)!r} is trusted (reads hidden/ "
            f"directly) and must not run as a contestant. Pass allow_trusted=True "
            f"(CLI --allow-trusted) only for harness gates."
        )

    case_dir = Path(case_dir).resolve()

    with open(case_dir / "card.public.yaml") as f:
        card = yaml.safe_load(f)

    case_id = card["case_id"]
    run_id = _generate_run_id()

    # 1. Capture environment
    env = capture_environment(project_root, case_dir)

    # 2. Build empty record
    record = build_empty_record(case_id, agent.name, run_id, env)
    record["trusted"] = is_trusted  # excluded from aggregates; never a contestant

    # Sweep-condition labels (null for ad-hoc runs; the runner passes them in).
    if conditions:
        record["conditions"].update(conditions)

    # Copy the case's symptom_direction into the record so the index carries it.
    try:
        _hc = yaml.safe_load((case_dir / "hidden" / "card.hidden.yaml").read_text())
        record["symptom_direction"] = (_hc or {}).get("symptom_direction")
    except Exception:
        record["symptom_direction"] = None

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
        if agent_error is not None:
            record["termination_reason"] = "crashed"

        # 7b. Flag supersession (False at trial time — built against current card)
        from harness.provenance import mark_card_superseded
        mark_card_superseded(record, case_dir)

        # 8. Overwrite the partial record
        write_record(project_root, record, overwrite_partial=True)

        # 9. Update index (insert or rewrite from record state)
        update_index(project_root, record)

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

def _print_cost_summary(record: dict) -> None:
    """Print a human-readable cost summary after a trial."""
    usage = record.get("usage", {})
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    total = inp + out

    model_block = record.get("model", {})
    model_id = model_block.get("model_id") if isinstance(model_block, dict) else None
    status = record.get("status", "unknown")

    # Compute cost estimate
    from harness.pricing import estimate_cost
    est = estimate_cost(model_id, inp, out, usage.get("cached_tokens", 0))

    trial_path = record.get("_trial_path", "")
    print(f"\nTrial:  {trial_path}")
    print(f"Model:  {model_id or 'none'}")
    print(f"Tokens: {inp} in + {out} out = {total} total")
    if est is not None:
        print(f"Cost:   ~${est.cost_usd:.4f} (estimate — verify before paper)")
    else:
        print("Cost:   unknown (model not in price table)")
    print(f"Status: {status}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an agent trial on a case (spec §6)",
    )
    parser.add_argument(
        "--case", type=Path, required=True,
        help="Path to the case directory",
    )
    parser.add_argument(
        "--agent", type=str, default=None,
        help="Agent name (e.g. stub_oracle, stub_degenerate)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="LLM model ID (e.g. claude-haiku-4-5-20251001); creates LLMAgent",
    )
    parser.add_argument(
        "--provider", type=str, default="anthropic",
        help="LLM provider (default: anthropic)",
    )
    parser.add_argument(
        "--temperature", type=float, default=1.0,
        help="Sampling temperature (default: 1.0)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=15,
        help="Max agent turns (default: 15)",
    )
    parser.add_argument(
        "--max-response-tokens", type=int, default=8192,
        help="Max tokens per LLM response (default: 8192)",
    )
    parser.add_argument(
        "--agent-type", type=str, default="react", choices=["react", "static"],
        help="LLM agent mode: react (tool loop) or static (one-shot full context)",
    )
    parser.add_argument(
        "--anchor", type=str, default="on", choices=["on", "off"],
        help="Reference-band anchor in the prompt: on (default) or off",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: auto-detect)",
    )
    parser.add_argument(
        "--allow-trusted", action="store_true", default=False,
        help="Permit a trusted (hidden-reading) probe agent to run — harness gates only",
    )
    args = parser.parse_args()

    # Must specify either --agent or --model, not both, not neither
    if args.agent and args.model:
        parser.error("Specify --agent or --model, not both")
    if not args.agent and not args.model:
        parser.error("Specify --agent (registry) or --model (LLM)")

    if args.model:
        # Create LLM agent with the specified provider
        if args.provider == "anthropic":
            from harness.llm.anthropic_client import AnthropicClient
            client = AnthropicClient(
                model=args.model, temperature=args.temperature,
            )
        else:
            parser.error(f"Unknown provider {args.provider!r}; supported: anthropic")

        if args.agent_type == "static":
            from agents.static_agent import StaticContextAgent
            agent: Agent = StaticContextAgent(
                client,
                model_id=args.model,
                temperature=args.temperature,
                max_response_tokens=args.max_response_tokens,
                provider=args.provider,
                anchor=args.anchor,
            )
        else:
            from agents.llm_agent import LLMAgent
            agent = LLMAgent(
                client,
                model_id=args.model,
                temperature=args.temperature,
                max_turns=args.max_turns,
                max_response_tokens=args.max_response_tokens,
                provider=args.provider,
                anchor=args.anchor,
            )
    else:
        agent = _load_agent(args.agent)

    cli_conditions = (
        {"agent_type": args.agent_type, "anchor": args.anchor} if args.model else None
    )
    record = run_trial(
        agent, args.case, args.project_root, allow_trusted=args.allow_trusted,
        conditions=cli_conditions,
    )

    # Store trial path for summary display
    case_id = record.get("case_id", "unknown")
    run_id = record.get("run_id", "unknown")
    agent_name = record.get("agent_name", "unknown")
    record["_trial_path"] = (
        f"results/{case_id}/trials/{agent_name}_{run_id}.yaml"
    )

    if args.model:
        _print_cost_summary(record)
    else:
        print(yaml.dump(record, default_flow_style=False, sort_keys=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
