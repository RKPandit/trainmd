"""Shared numeric tolerances for reference-derived comparisons.

`DERIVED_STAT_EPSILON`: any check comparing a value DERIVED via arithmetic from
statistics stored at 6 decimal places in `reference/stats.yaml` (mean, std,
tolerance_lower) must use this ONE constant, not a per-check literal. Rationale:
full-precision-then-round vs round-then-recompute can differ by up to ~1e-6 at
6dp, so a strict 1e-9 false-fails on ordinary rounding (it happened to the 200-229
band at §5.2); 2e-6 absorbs that while still catching a wrong FORMULA (2sigma vs
3sigma differs ~2e-3), which is the real bug these checks guard against.

NOT for EXACT COPIES: a value copied verbatim from stats.yaml (e.g. validate_case
C9's public-card band mean/std) is not derived and must match exactly (1e-9).

STAGE3_PLAN §5.2; DECISIONS 2026-09-14 (verify_reference), 2026-09-16 (unified).
"""
DERIVED_STAT_EPSILON = 2e-6
