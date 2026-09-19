"""Live provider smoke test (~$2 cap) — NON-STUDY, throwaway.

Validates a second-provider LLMClient end to end against the real API WITHOUT
touching any benchmark case, study prompt, or hidden material. It exercises the
full round-trip the adapter must get right:

  - tool-call translation (the model must emit a native `submit` tool call),
  - usage/token accounting (accumulated across N calls),
  - the API-reported model string (from LLMResponse.raw),
  - the STRUCTURED-OUTPUT FOLDING RATE: how often the model folds the structured
    `repair_spec` into a sibling string field instead of the structured field
    (measured with harness.submission_repair.recover_folded_repair_spec, the same
    detector the scorer uses).

Integrity: the prompt is a synthetic toy ("a learning rate is 10x too high"),
NOT a study diagnostic prompt, and no case is built or read. Safe to run from any
session — it exposes zero study material before the sweep pre-registration.

Usage:
    OPENAI_API_KEY=... python scripts/smoke_provider.py --provider openai \
        --model gpt-5-mini --n 15 --max-cost-usd 2.0
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.pricing import estimate_cost
from harness.submission_repair import recover_folded_repair_spec

# A throwaway, non-study submit schema: the same STRUCTURED repair_spec shape the
# real submit uses (so folding is measured against a real structured field), with
# a toy, non-diagnostic instruction.
_SUBMIT_TOOL = [{
    "name": "submit",
    "description": "Submit your fix for the toy script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "diagnosis": {"type": "string", "description": "one-line diagnosis"},
            "repair_spec": {
                "type": "object",
                "description": "structured repair",
                "properties": {
                    "repair_type": {"type": "string"},
                    "patches": {"type": "object"},
                },
                "required": ["repair_type", "patches"],
            },
            "rationale": {"type": "string", "description": "short rationale"},
        },
        "required": ["diagnosis", "repair_spec"],
    },
}]

_TOY_PROMPT = (
    "You are fixing a toy training script. Its learning rate `training.lr` is set "
    "to 0.1, which is 10x too high; the correct value is 0.01. Call the `submit` "
    "tool. Put a structured object in the `repair_spec` field with "
    "repair_type='config_patch' and patches={'training.lr': 0.01}. Do not put the "
    "repair anywhere else."
)


def _make_client(provider: str, model: str):
    if provider == "openai":
        from harness.llm.openai_client import OpenAIClient
        return OpenAIClient(model=model, temperature=1.0)
    if provider == "anthropic":
        from harness.llm.anthropic_client import AnthropicClient
        return AnthropicClient(model=model, temperature=1.0)
    raise SystemExit(f"Unknown provider {provider!r}; supported: openai, anthropic")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", required=True, help="exact API model ID, e.g. gpt-5-mini")
    ap.add_argument("--n", type=int, default=15, help="number of independent submit prompts")
    ap.add_argument("--max-cost-usd", type=float, default=2.0, help="hard stop before exceeding")
    a = ap.parse_args()

    client = _make_client(a.provider, a.model)

    n_submit = n_folded = n_no_submit = 0
    in_tok = out_tok = cached_tok = 0
    api_model = None
    reasons: dict[str, int] = {}

    for i in range(a.n):
        # Cost guard: stop before exceeding the cap, using tokens so far.
        est = estimate_cost(a.model, in_tok, out_tok, cached_tok)
        if est is not None and est.cost_usd >= a.max_cost_usd:
            print(f"[stop] cost estimate ${est.cost_usd:.4f} >= cap ${a.max_cost_usd:.2f} "
                  f"after {i} calls", file=sys.stderr)
            break

        resp = client.complete(
            [{"role": "user", "content": _TOY_PROMPT}], _SUBMIT_TOOL, max_tokens=1024,
        )
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens
        cached_tok += resp.usage.cached_tokens
        api_model = (resp.raw or {}).get("model", api_model)

        submit = next((tc for tc in resp.tool_calls if tc.name == "submit"), None)
        if submit is None or not isinstance(submit.arguments, dict):
            n_no_submit += 1
            print(f"  [{i+1:2}/{a.n}] no structured submit (stop={resp.stop_reason})")
            continue
        n_submit += 1
        fold = recover_folded_repair_spec(submit.arguments)
        reasons[fold.reason] = reasons.get(fold.reason, 0) + 1
        if fold.warning:  # recovered / ambiguous / folded_unparseable
            n_folded += 1
        print(f"  [{i+1:2}/{a.n}] submit fold-reason={fold.reason}")

    fold_rate = (n_folded / n_submit) if n_submit else float("nan")
    est = estimate_cost(a.model, in_tok, out_tok, cached_tok)

    print("\n==== provider smoke summary ====")
    print(f"provider/model:      {a.provider} / {a.model}")
    print(f"API-reported model:  {api_model}")
    print(f"calls:               {n_submit + n_no_submit}")
    print(f"structured submits:  {n_submit}  (no-submit: {n_no_submit})")
    print(f"folded submits:      {n_folded}")
    print(f"FOLDING RATE:        {fold_rate:.3f}  (folded / structured submits)")
    print(f"fold reasons:        {reasons}")
    print(f"tokens:              in={in_tok} out={out_tok} cached={cached_tok}")
    if est is not None:
        print(f"cost estimate:       ${est.cost_usd:.4f} (is_estimate={est.is_estimate}; "
              f"VERIFY vs provider billing)")
    else:
        print("cost estimate:       unknown (model not in price table)")
    return 0


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("No provider API key in env (OPENAI_API_KEY / ANTHROPIC_API_KEY). "
              "This smoke makes live paid calls; set the key and re-run.", file=sys.stderr)
        raise SystemExit(3)
    raise SystemExit(main())
