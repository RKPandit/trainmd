"""Per-model price table for cost estimation.

Prices per million tokens (USD).

Verified from docs.anthropic.com/en/docs/about-claude/pricing (Sep 2026).
Claude 4.7+ uses a newer tokenizer that counts ~30% more tokens for the
same text, so these estimates are a lower bound on actual cost.

WARNING: is_estimate is always True.  Verify against the provider's billing
page before reporting cost figures in the paper.
"""
from __future__ import annotations

import ast
import functools
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Verified Sep 2026 from docs.anthropic.com/en/docs/about-claude/pricing.
# cached_input is the cache-read (hit) price; cache_write is the cache-WRITE price.
# Anthropic rates re-verified 2026-09-23 against platform.claude.com/docs/en/about-claude/pricing
# (5-minute cache writes = 1.25x input — the only TTL this harness uses; 1-hour writes are 2x and
# are NOT priced here because they are never requested). If a model's cache price cannot be
# confirmed, set it to None — estimate_cost falls back to the full input price (reads) or 1.25x
# input (writes), so a missing entry never silently undercounts.
_PRICE_TABLE: dict[str, dict[str, float | None]] = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cached_input": 0.10,    # confirmed: $0.10 in pricing table
        "cache_write": 1.25,     # verified 2026-09-23: 5m cache writes $1.25/MTok (1.25x)
    },
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cached_input": 0.20,    # confirmed: $0.20 in pricing table
        "cache_write": 2.50,     # verified 2026-09-23: 5m cache writes $2.50/MTok
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,    # confirmed: $0.50 in pricing table
        "cache_write": 6.25,     # verified 2026-09-23: 5m cache writes $6.25/MTok
    },
    "claude-opus-5-5": {
        "input": 4.00,
        "output": 20.00,
        "cached_input": 0.20,    # verified 2026-09-24: cache hits 0.05x on Opus 5.5 ($0.20/MTok)
        "cache_write": 5.00,     # verified 2026-09-24: 5m cache writes $5/MTok (1.25x)
    },
    # --- Second provider (OpenAI GPT-5.6 Luna, cost-efficient tier). Rates
    # verified from OpenAI's model docs 2026-09-19 (post-July-30 cut: Luna -80%);
    # is_estimate stays True per this file's rule (only a billing statement is
    # authoritative). LONG-CONTEXT METER: above 272K input tokens, input (and
    # cached input / cache writes) is billed at 2x and output at 1.5x. Our prompts
    # are far below 272K, so estimate_cost uses the STANDARD rates below; the
    # threshold is recorded (harness/llm/openai_client.py _MODEL_METADATA) so a
    # future large-context workload does not silently double-bill.
    "gpt-5.6-luna": {
        "input": 0.20,          # verified — per-1M input
        "output": 1.20,         # verified — per-1M output
        "cached_input": 0.02,   # verified — cached input at 10% of standard input
        # Verified 2026-09-23 (developers.openai.com/api/docs/pricing, gpt-5.6-luna standard,
        # short context: input $0.20 · cached $0.02 · cache writes $0.25 · output $1.20).
        # GPT-5.6+ bills automatic-cache writes at 1.25x input — not priced before this change.
        "cache_write": 0.25,
    },
    # GPT-6 (Stage 4 Part 2). Verified 2026-09-24 from the RAW model/pricing pages
    # (developers.openai.com/api/docs/models/gpt-6-*; standard tier, short context <= 272K input).
    "gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01, "cache_write": 0.125},
    "gpt-6-sol": {"input": 2.00, "output": 10.00, "cached_input": 0.20, "cache_write": 2.50},
}


@dataclass(frozen=True)
class CostEstimate:
    """Estimated cost for an LLM call.

    ``is_estimate`` is always ``True`` — prices come from an approximate
    table that must be verified against the provider's pricing page before
    any cost figure is published.
    """

    cost_usd: float
    is_estimate: bool = True


def estimate_cost(
    model_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    table: dict | None = None,
) -> CostEstimate | None:
    """Estimate the BILLED cost in USD from the built-in price table (or ``table``).

    *input_tokens* is the TOTAL prompt size; *cached_tokens* (reads) and *cache_write_tokens*
    are subsets of it and replace full-price input tokens at their own rates (cache-write pricing
    is not an additive fee — each input token is priced at exactly one of uncached / read / write).
    An unverified ``cached_input`` price falls back to the full input rate, and an unverified
    ``cache_write`` price falls back to 1.25x input (the documented premium on every model this
    harness prices), so a missing entry never silently undercounts.

    Returns ``None`` if *model_id* is ``None`` or not in the price table.
    Returns a :class:`CostEstimate` with ``is_estimate=True`` otherwise.
    """
    if model_id is None:
        return None
    prices = (_PRICE_TABLE if table is None else table).get(model_id)
    if prices is None:
        return None

    cache_price = prices.get("cached_input")
    if cache_price is None:
        # Unverified cache price — fall back to full input price
        cache_price = prices["input"]
    write_price = prices.get("cache_write")
    if write_price is None:
        write_price = 1.25 * prices["input"]

    billable_input = max(0, input_tokens - cached_tokens - cache_write_tokens)
    cost = (
        billable_input * prices["input"]
        + output_tokens * prices["output"]
        + cached_tokens * cache_price
        + cache_write_tokens * write_price
    ) / 1_000_000
    return CostEstimate(cost_usd=cost, is_estimate=True)


def uncached_equivalent_cost(
    model_id: str | None,
    input_tokens: int,
    output_tokens: int,
) -> CostEstimate | None:
    """What the same tokens would cost with NO caching (every input token at the full input
    rate). Reported beside the billed cost so sweeps that use caching stay comparable with
    Sweeps 1–3, which ran without it."""
    return estimate_cost(model_id, input_tokens, output_tokens)


# --------------------------------------------------------------------------- #
# Price-table versioning — so the R8 audit can recompute any trial's cost from the
# table it was actually priced with (not today's).
# --------------------------------------------------------------------------- #

def table_version(table: dict) -> str:
    """Content hash of a price table (canonical JSON, sorted keys)."""
    blob = json.dumps(table, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


PRICE_TABLE_VERSION = table_version(_PRICE_TABLE)   # recorded on every trial at run time

_REPO = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=None)
def _table_at_commit(commit: str) -> dict | None:
    """``_PRICE_TABLE`` as of ``commit`` — read from git history and PARSED (ast.literal_eval of the
    assignment), never executed. None if git, the commit, or the table is unavailable."""
    try:
        src = subprocess.run(["git", "show", f"{commit}:harness/pricing.py"], cwd=_REPO,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    for node in ast.parse(src).body:
        target = (node.target if isinstance(node, ast.AnnAssign) else
                  node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None)
        if isinstance(target, ast.Name) and target.id == "_PRICE_TABLE" and node.value is not None:
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


@functools.lru_cache(maxsize=1)
def _history() -> dict:
    """The committed archive of every historical price table (scripts/build_price_table_history.py):
    resolves tables with NO git — the canonical container does not ship git."""
    p = _REPO / "harness" / "price_table_history.json"
    return json.loads(p.read_text()) if p.exists() else {"tables": {}, "commits": {}}


def price_table_for_record(rec: dict) -> tuple[dict | None, str]:
    """The price table a trial was priced with, and how it was resolved.

    1. ``usage.price_table_version`` recorded (2026-09-23 on) → that exact table (today's, or from the
       committed archive, which is content-addressed so the match is exact).
    2. Otherwise the table at the trial's ``harness_git_commit`` — from the committed archive's
       commit index, else (commits newer than the archive, host only) read from git.
    Returns (None, reason) when the table cannot be reconstructed — the caller must report that,
    never treat it as a pass."""
    hist = _history()
    recorded = (rec.get("usage") or {}).get("price_table_version")
    if recorded:
        if recorded == PRICE_TABLE_VERSION:
            return _PRICE_TABLE, "recorded_version=current"
        if recorded in hist["tables"]:
            return hist["tables"][recorded], f"recorded_version={recorded}"
        return None, f"recorded price_table_version {recorded} not in the archive"
    env = rec.get("environment") or {}
    # The code the process ran (schema 1.2+), else the checkout's HEAD at the trial.
    commit = (env.get("process") or {}).get("start_commit") or env.get("harness_git_commit")
    if not commit:
        return None, "no harness_git_commit on record"
    v = hist["commits"].get(commit)
    if v is not None:
        return hist["tables"][v], f"table_at_commit={commit[:12]} (archive)"
    table = _table_at_commit(commit)
    if table is None:
        return None, f"price table unavailable for commit {commit[:12]} (not archived; no git)"
    return table, f"table_at_commit={commit[:12]} (git)"
