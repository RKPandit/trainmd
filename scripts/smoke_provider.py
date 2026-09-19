"""Live provider smoke — EPHEMERAL throwaway case, NON-STUDY prompt, ~$2 cap.

Validates a second-provider LLMClient end to end against the real API WITHOUT
touching any study case or hidden material of the sweep design.

Integrity (why this shape):
  - Builds a THROWAWAY faulty case whose (operator, seed) tuple is PROVABLY NOT
    in the sweep design — a positive assertion (`_assert_off_design`), not an
    assumption — so no model ever sees a case that the H8 cross-provider
    comparison will later depend on.
  - The case lives OUTSIDE the repo's cases/ (under /tmp/smoke_<ts>/), never
    enters the registry, the case design, or any plan file, and is DELETED in a
    finally block. Its numbers are non-canonical (built under the
    TRAINMD_ALLOW_NONCANONICAL_BUILD override) and are never committed.
  - The instruction is a GENERIC diagnostic prompt, not the study's anchored
    prompt — no study prompt text is exposed before pre-registration.

It exercises the full round-trip the adapter must get right: tool-call
translation, tool_result translation, usage/token accounting, the API-reported
model string, and the STRUCTURED-OUTPUT FOLDING RATE (how often the model folds
the structured repair_spec into a sibling string field, via
harness.submission_repair.recover_folded_repair_spec — the scorer's detector).

Usage:
    OPENAI_API_KEY=... python scripts/smoke_provider.py --provider openai \
        --model gpt-5-mini --n 10 --max-cost-usd 2.0
    # No-key pipeline self-test (build+assert+loop+fold+delete, scripted fake):
    python scripts/smoke_provider.py --fake
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from agents.llm_agent import TOOLS_SCHEMA
from harness.pricing import estimate_cost
from harness.submission_repair import recover_folded_repair_spec
from harness.tools.tools import ToolContext, register_all_tools

# GENERIC, non-study instruction: no reference band, no anchor arm, no study
# framing. Just "investigate this run and submit".
_GENERIC_PROMPT = (
    "You are inspecting the output of a small machine-learning training run. "
    "Use the available tools to investigate the run's config, metrics, logs, and "
    "code. Decide whether the training is misconfigured, then call the `submit` "
    "tool with a `diagnosis` object and, if you propose a fix, a structured "
    "`repair_spec` (an object with `repair_type` and `patches`). Put the repair in "
    "the structured `repair_spec` field, not in prose. Keep your investigation to "
    "a few tool calls."
)


def _design_tuples() -> set[tuple[str, int]]:
    """(operator_id, seed) pairs in the committed sweep design — the source of
    truth is the code enumeration, not the built registry."""
    from scripts.build_all_cases import case_design_tuples
    return {(op, sd) for op, _st, sd in case_design_tuples()}


def _all_reserved_seeds() -> set[int]:
    from harness.seed_sets import NAMED_SETS
    reserved: set[int] = set()
    for s in NAMED_SETS.values():
        reserved |= set(s)
    return reserved


def _assert_off_design(operator_id: str, seed: int) -> None:
    """POSITIVE check: fail loudly unless (operator, seed) is provably NOT in the
    sweep design and the seed is in NO reserved seed set."""
    design = _design_tuples()
    if (operator_id, seed) in design:
        raise SystemExit(
            f"REFUSING: ({operator_id}, seed={seed}) IS in the sweep design — "
            f"a smoke must never touch a study case."
        )
    reserved = _all_reserved_seeds()
    if seed in reserved:
        raise SystemExit(
            f"REFUSING: seed {seed} is a reserved study seed {sorted(reserved)} — "
            f"pick a seed outside every set."
        )
    print(f"[assert] ({operator_id}, seed={seed}) is NOT in the {len(design)}-tuple "
          f"design and seed is not reserved — safe throwaway.")


def _run_react_trial(client, case_dir: Path, max_turns: int = 6):
    """One bounded ReAct trial with the generic prompt. Returns
    (submit_args_or_None, usage_tuple, api_model)."""
    tools = ToolContext(case_dir)
    register_all_tools(tools)
    messages: list[dict] = [{"role": "user", "content": _GENERIC_PROMPT}]
    in_tok = out_tok = cached = reasoning = 0
    api_model = None
    submit_args = None

    for _turn in range(max_turns):
        resp = client.complete(messages, TOOLS_SCHEMA, max_tokens=1024)
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens
        cached += resp.usage.cached_tokens
        reasoning += (resp.raw or {}).get("reasoning_tokens", 0)
        api_model = (resp.raw or {}).get("model", api_model)

        assistant_content: list[dict] = []
        if resp.text:
            assistant_content.append({"type": "text", "text": resp.text})
        for tc in resp.tool_calls:
            assistant_content.append({"type": "tool_use", "id": tc.id,
                                      "name": tc.name, "input": tc.arguments})
        if not assistant_content:
            break
        messages.append({"role": "assistant", "content": assistant_content})
        if not resp.tool_calls:
            break

        tool_results = []
        for tc in resp.tool_calls:
            try:
                result = tools.call(tc.name, **tc.arguments) \
                    if isinstance(tc.arguments, dict) else {"status": "error",
                    "error": "NON_DICT_ARGS"}
            except Exception as e:  # noqa: BLE001 - faithful tool error
                result = {"status": "error", "error": "TOOL_EXECUTION_ERROR",
                          "detail": str(e)}
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id,
                                 "content": json.dumps(result)})
            if tc.name == "submit" and isinstance(tc.arguments, dict) \
                    and result.get("status") == "ok":
                submit_args = tc.arguments
        messages.append({"role": "user", "content": tool_results})
        if submit_args is not None:
            break

    return submit_args, (in_tok, out_tok, cached, reasoning), api_model


def _make_client(provider: str, model: str, fake: bool, effort: str = "medium"):
    if fake:
        from harness.llm.client import (FakeLLMClient, LLMResponse,
                                        ToolCallRequest, Usage)
        good = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
        # Trial 1: read a tool, then submit STRUCTURED. Trial 2: submit FOLDED.
        scripted = [
            LLMResponse(text="checking config", tool_calls=[
                ToolCallRequest(id="c1", name="read_config",
                                arguments={"key_path": "training.lr"})],
                stop_reason="tool_use", usage=Usage(120, 20)),
            LLMResponse(text=None, tool_calls=[
                ToolCallRequest(id="s1", name="submit", arguments={
                    "diagnosis": {"summary": "lr too high"}, "evidence_refs": [],
                    "repair_spec": good, "rationale": "structured"})],
                stop_reason="tool_use", usage=Usage(140, 30)),
            LLMResponse(text=None, tool_calls=[
                ToolCallRequest(id="s2", name="submit", arguments={
                    "diagnosis": {"summary": "lr too high"}, "evidence_refs": [],
                    "repair_spec": None,
                    "rationale": "fix: " + json.dumps(good)})],
                stop_reason="tool_use", usage=Usage(130, 25)),
        ]
        return FakeLLMClient(scripted)
    if provider == "openai":
        from harness.llm.openai_client import OpenAIClient
        return OpenAIClient(model=model, temperature=1.0,
                            reasoning_effort=effort)
    if provider == "anthropic":
        from harness.llm.anthropic_client import AnthropicClient
        return AnthropicClient(model=model, temperature=1.0)
    raise SystemExit(f"Unknown provider {provider!r}; supported: openai, anthropic")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default="gpt-5.6-luna", help="exact API model ID")
    ap.add_argument("--reasoning-effort", default="medium",
                    choices=["none", "low", "medium", "high", "xhigh", "max"],
                    help="OpenAI reasoning.effort, pinned explicitly (default: medium)")
    ap.add_argument("--operator", default="silent.lr_warmup.v1",
                    help="a FAULTY operator so there is something to diagnose")
    ap.add_argument("--strength", default="mild")
    ap.add_argument("--seed", type=int, default=90001,
                    help="a seed OUTSIDE every study seed set (asserted)")
    ap.add_argument("--workload", default="tabular_adult")
    ap.add_argument("--n", type=int, default=10, help="ReAct trials (folding-rate n)")
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    ap.add_argument("--fake", action="store_true",
                    help="pipeline self-test with a scripted FakeLLMClient (no key, no cost)")
    a = ap.parse_args()

    # 1. POSITIVE off-design assertion (before building anything).
    _assert_off_design(a.operator, a.seed)

    n = 2 if a.fake else a.n  # fake path scripts exactly 2 trials
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    smoke_root = Path(f"/tmp/smoke_{ts}") / "root"
    case_dir = None
    try:
        # 2. Ephemeral project root OUTSIDE the repo; reuse workload data via symlink.
        smoke_root.mkdir(parents=True)
        os.symlink(_REPO / "workloads", smoke_root / "workloads")
        os.environ["TRAINMD_ALLOW_NONCANONICAL_BUILD"] = "1"  # ephemeral, deleted below

        from harness.build_case import build_case
        case_dir = build_case(a.workload, a.operator, a.strength, a.seed,
                              project_root=smoke_root, force=True)
        case_dir = Path(case_dir)
        # Hard invariant: the throwaway is under /tmp and NOT under the repo.
        assert str(case_dir).startswith("/tmp/"), case_dir
        assert _REPO not in case_dir.parents, "throwaway must not be inside the repo"
        print(f"[build] throwaway case at {case_dir}")

        client = _make_client(a.provider, a.model, a.fake, a.reasoning_effort)
        descr = client.describe() if hasattr(client, "describe") else {}

        n_submit = n_folded = n_no_submit = 0
        in_tok = out_tok = cached_tok = reasoning_tok = 0
        api_model = None
        reasons: dict[str, int] = {}

        for i in range(n):
            est = estimate_cost(a.model, in_tok, out_tok, cached_tok)
            if not a.fake and est is not None and est.cost_usd >= a.max_cost_usd:
                print(f"[stop] est ${est.cost_usd:.4f} >= cap ${a.max_cost_usd:.2f} "
                      f"after {i} trials", file=sys.stderr)
                break
            submit_args, (ti, to, tc, tr), am = _run_react_trial(client, case_dir)
            in_tok += ti; out_tok += to; cached_tok += tc; reasoning_tok += tr
            api_model = am or api_model
            if submit_args is None:
                n_no_submit += 1
                print(f"  [{i+1:2}/{n}] no submit")
                continue
            n_submit += 1
            fold = recover_folded_repair_spec(submit_args)
            reasons[fold.reason] = reasons.get(fold.reason, 0) + 1
            if fold.warning:
                n_folded += 1
            print(f"  [{i+1:2}/{n}] submit OK  fold-reason={fold.reason}")

        fold_rate = (n_folded / n_submit) if n_submit else float("nan")
        est = estimate_cost(a.model, in_tok, out_tok, cached_tok)
        print("\n==== provider smoke summary ====")
        print(f"mode:                {'FAKE self-test' if a.fake else 'LIVE'}")
        print(f"provider/model:      {a.provider} / {a.model}")
        print(f"API-reported model:  {api_model}")
        print(f"reasoning_effort:    {descr.get('reasoning_effort', 'n/a (no effort knob)')}")
        print(f"knowledge_cutoff:    {descr.get('knowledge_cutoff', 'n/a')}")
        print(f"throwaway tuple:     {a.operator} / {a.strength} / seed {a.seed} "
              f"(off-design, asserted)")
        print(f"trials:              {n_submit + n_no_submit}")
        print(f"submitted correctly: {n_submit}  (no-submit: {n_no_submit})")
        print(f"folded submits:      {n_folded}")
        print(f"folding (observed):  {n_folded}/{n_submit}  (rate={fold_rate:.3f})")
        print("  NOTE: this is a SMOKE on ONE easy case, n too small to estimate a "
              "provider folding rate (e.g. 0/10 has a ~26% 95% upper bound). The "
              "per-provider folding rate is a Sweep-3 secondary, measured over the "
              "full cell count (docs/HYPOTHESES.md).")
        print(f"fold reasons:        {reasons}")
        print(f"tokens:              in={in_tok} out={out_tok} cached={cached_tok}")
        print(f"  of which reasoning: {reasoning_tok} (billed as output, counted in out=)")
        if est is not None:
            print(f"cost estimate:       ${est.cost_usd:.4f} (is_estimate={est.is_estimate}; "
                  f"UNVERIFIED price — confirm vs provider billing)")
        else:
            print("cost estimate:       unknown (model not in price table)")
        return 0
    finally:
        # 3. ALWAYS delete the throwaway; confirm it is gone.
        root = smoke_root.parent
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        gone = not root.exists()
        print(f"[cleanup] throwaway {root} deleted: {gone}")
        if not gone:  # pragma: no cover
            print(f"WARNING: could not delete {root}", file=sys.stderr)


if __name__ == "__main__":
    fake = "--fake" in sys.argv
    if not fake and not os.environ.get("OPENAI_API_KEY") \
            and not os.environ.get("ANTHROPIC_API_KEY"):
        print("No provider API key in env (OPENAI_API_KEY / ANTHROPIC_API_KEY). "
              "This smoke makes live paid calls; set the key and re-run, or use "
              "--fake for the no-cost pipeline self-test.", file=sys.stderr)
        raise SystemExit(3)
    raise SystemExit(main())
