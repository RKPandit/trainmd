"""The single anchor legacy-mapping function (STAGE3_PLAN §0.3).

Three-arm anchor design: ``off`` | ``numbers`` | ``rule`` (L10). Legacy Sweep-1 records use
``on`` for what is now ``rule`` (numbers + the explicit decision sentence). This is the ONE place
the mapping lives; analysis code normalizes ``conditions.anchor`` exactly once, at load, so no
downstream filter ever sees a legacy value (the bug class where a filter for ``"on"`` runs AFTER
normalization and silently matches nothing — docs/DECISIONS.md 2026-09-15).

Records on disk are never rewritten; the mapping is applied only in analysis.
"""
from __future__ import annotations

_LEGACY = {"on": "rule"}


def normalize_anchor(anchor: str | None) -> str | None:
    """Map a legacy anchor value to its current three-arm name (``on`` -> ``rule``)."""
    return _LEGACY.get(anchor, anchor)
