"""Per-model price table for cost estimation.

Prices per million tokens (USD).

Verified from docs.anthropic.com/en/docs/about-claude/pricing (Sep 2026).
Claude 4.7+ uses a newer tokenizer that counts ~30% more tokens for the
same text, so these estimates are a lower bound on actual cost.

WARNING: is_estimate is always True.  Verify against the provider's billing
page before reporting cost figures in the paper.
"""
from __future__ import annotations

from dataclasses import dataclass

# Verified Sep 2026 from docs.anthropic.com/en/docs/about-claude/pricing.
# cached_input is the cache-read (hit) price.  If a model's cache price
# cannot be confirmed, set it to None — estimate_cost falls back to full
# input price so we never silently undercount.
_PRICE_TABLE: dict[str, dict[str, float | None]] = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cached_input": 0.10,    # confirmed: $0.10 in pricing table
    },
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cached_input": 0.20,    # confirmed: $0.20 in pricing table
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,    # confirmed: $0.50 in pricing table
    },
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
) -> CostEstimate | None:
    """Estimate cost in USD from the built-in price table.

    Cached tokens are subtracted from *input_tokens* for pricing — they
    replace full-price input tokens.  If the model's ``cached_input`` price
    is ``None`` (unverified), cached tokens are charged at the full input
    rate so we never silently undercount.

    Returns ``None`` if *model_id* is ``None`` or not in the price table.
    Returns a :class:`CostEstimate` with ``is_estimate=True`` otherwise.
    """
    if model_id is None:
        return None
    prices = _PRICE_TABLE.get(model_id)
    if prices is None:
        return None

    cache_price = prices.get("cached_input")
    if cache_price is None:
        # Unverified cache price — fall back to full input price
        cache_price = prices["input"]

    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input * prices["input"]
        + output_tokens * prices["output"]
        + cached_tokens * cache_price
    ) / 1_000_000
    return CostEstimate(cost_usd=cost, is_estimate=True)
