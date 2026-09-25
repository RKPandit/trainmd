"""The four disjoint seed sets (STAGE3_PLAN §5.2).

Single source of truth so reference generation, case building, and validation
cannot drift. §5.2 moves the reference OFF the control/calibration seeds to cure
the seed-collision circularity (control FPR biased LOW — LIMITATIONS L3): a
control must be judged against a band NO run of its own helped estimate.

Sets (pairwise disjoint — `assert_disjoint()` enforces it, a validator check
fails on any reuse):

- REFERENCE      200–229  band estimation (was [0–29]; moved here in §5.2)
- DEVELOPMENT      0–29   operator qualification / Step 0 / calibration
                          (the OLD reference seeds, repurposed — never the band)
- HIDDEN_EVAL    100–102  the evaluator's hidden test seeds
- CONFIRMATORY_FAULTY  42–43   faulty cases used in sweeps
- CONFIRMATORY_CONTROL 50–69   control cases used in sweeps (≥20; moved off {0,1,2})
- CONFIRMATORY_BENIGN  70–93 ∪ 110–157  benign-configuration control cases (STAGE4 4.0.6: 6 change types ×
                          4 per 24-seed block; 3 blocks = 72 cases — 110–157 added 2026-09-25 for power)

CONFIRMATORY = faulty ∪ control (the seeds a sweep's cases are built on).
"""
from __future__ import annotations

REFERENCE: frozenset[int] = frozenset(range(200, 230))      # 200–229
DEVELOPMENT: frozenset[int] = frozenset(range(0, 30))        # 0–29
HIDDEN_EVAL: frozenset[int] = frozenset({100, 101, 102})     # 100–102
CONFIRMATORY_FAULTY: frozenset[int] = frozenset({42, 43, 44, 45, 46, 47})  # 42–47 (H8 power: 6 seeds → MDD ~0.25)
CONFIRMATORY_CONTROL: frozenset[int] = frozenset(range(50, 70))  # 50–69 (20 controls)
CONFIRMATORY_BENIGN: frozenset[int] = frozenset(range(70, 94)) | frozenset(range(110, 158))  # 3 blocks × 24
CONFIRMATORY: frozenset[int] = CONFIRMATORY_FAULTY | CONFIRMATORY_CONTROL | CONFIRMATORY_BENIGN

# Named sets in the order they are reported / checked.
NAMED_SETS: dict[str, frozenset[int]] = {
    "reference": REFERENCE,
    "development": DEVELOPMENT,
    "hidden_eval": HIDDEN_EVAL,
    "confirmatory_faulty": CONFIRMATORY_FAULTY,
    "confirmatory_control": CONFIRMATORY_CONTROL,
    "confirmatory_benign": CONFIRMATORY_BENIGN,
}


def disjointness_violations() -> list[str]:
    """Return a list of human-readable pairwise-overlap violations (empty = clean)."""
    violations: list[str] = []
    names = list(NAMED_SETS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            overlap = NAMED_SETS[a] & NAMED_SETS[b]
            if overlap:
                violations.append(f"{a} ∩ {b} = {sorted(overlap)}")
    return violations


def assert_disjoint() -> None:
    """Fail loudly if any two seed sets overlap (import-time invariant)."""
    v = disjointness_violations()
    if v:
        raise AssertionError("seed sets are not disjoint (STAGE3_PLAN §5.2): " + "; ".join(v))


# The disjointness invariant holds at import time — a bad edit fails immediately.
assert_disjoint()
