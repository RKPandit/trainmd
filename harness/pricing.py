"""Per-model price table for cost estimation.

Prices per million tokens (USD).

WARNING: These are approximate. Verify against provider pricing page
before reporting cost figures in the paper.
"""
from __future__ import annotations

from dataclasses import dataclass

_PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "output": 15.00,
        "cached_input": 0.30,
    },
    "claude-opus-4-20250514": {
        "input": 15.00,
        "output": 75.00,
        "cached_input": 1.50,
    },
    "claude-haiku-3-20250307": {
        "input": 0.25,
        "output": 1.25,
        "cached_input": 0.03,
    },
    "gpt-4o-2024-11-20": {
        "input": 2.50,
        "output": 10.00,
        "cached_input": 1.25,
    },
    "gpt-4o-mini-2024-07-18": {
        "input": 0.15,
        "output": 0.60,
        "cached_input": 0.075,
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
    replace full-price input tokens.

    Returns ``None`` if *model_id* is ``None`` or not in the price table.
    Returns a :class:`CostEstimate` with ``is_estimate=True`` otherwise.
    """
    if model_id is None:
        return None
    prices = _PRICE_TABLE.get(model_id)
    if prices is None:
        return None
    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input * prices["input"]
        + output_tokens * prices["output"]
        + cached_tokens * prices["cached_input"]
    ) / 1_000_000
    return CostEstimate(cost_usd=cost, is_estimate=True)
