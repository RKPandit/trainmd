"""Verify that a regenerated reference matches the committed snapshot.

With the data pinned to committed hashes (data_prep provenance check), training
data is identical across runners, but float REDUCTION ORDER differs across amd64
microarchitectures (AVX-512 vs AVX2 FMA) — native training is byte-exact only
WITHIN a microarch. So this check is tolerance-based, and scoped to what the
benchmark actually depends on:

FAIL conditions (a genuine regression, not microarch noise):
  * metric_visible_val_acc.mean / metric_hidden_test_acc.mean differ by > 2e-3.
    (2x the max observed cross-microarch mean divergence: val 4.28e-4 = 0.28σ,
    hidden 9.73e-4 = 0.47σ of the reference stds.)
  * metric_hidden_test_acc.tolerance_lower differs by > 6e-3. tolerance_lower is
    NOT provenance detail — it is the pass/fail threshold every silent case is
    built against, and its observed cross-microarch divergence (2.99e-3) already
    exceeds the tightest case-guard margin (1.37e-3), so it needs a bound (2x
    observed = 6e-3).
  * DERIVATION invariant (exact, platform-independent): the generated
    tolerance_lower must equal round(hidden_mean - 2*hidden_std, 6) within 1e-9.
    A mismatch there is a real bug in how the threshold is computed, not noise.

INFORMATIONAL (printed every run, never fails): std, min/max, and every per-seed
/ per-epoch value — these are σ-estimates and per-epoch samples, inherently
noisier across microarchs, and NOT consumed by case validation (C4/C9/C11
re-derive from the committed file). The MAX per-epoch delta is printed so the
empirical cross-microarch distribution accumulates in CI logs for free.

See docs/DECISIONS.md (2026-09-14) and docs/LIMITATIONS.md L18.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_MEAN_TOL = 2e-3
_TOLERANCE_LOWER_TOL = 6e-3
# The derivation invariant is "exact" modulo storage: stats.yaml stores mean/std
# rounded to 6 decimals, while the stored tolerance_lower was computed from
# full-precision values, so recomputing from the stored inputs carries ≤~1.5e-6.
# 2e-6 still catches a wrong FORMULA (2σ vs 3σ differs by ~2e-3), which is the bug
# this guards against — not a "within 1e-9" that would false-fail on rounding.
_DERIVATION_TOL = 2e-6

_MEAN_FIELDS = ("metric_visible_val_acc.mean", "metric_hidden_test_acc.mean")
_TOLERANCE_FIELD = "metric_hidden_test_acc.tolerance_lower"


def _flatten(obj: object, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _num(x: object):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def main() -> int:
    p = argparse.ArgumentParser(description="Verify reference stats match (tolerance-based)")
    p.add_argument("committed", type=Path)
    p.add_argument("generated", type=Path)
    p.add_argument("--mean-tol", type=float, default=_MEAN_TOL)
    p.add_argument("--tolerance-lower-tol", type=float, default=_TOLERANCE_LOWER_TOL)
    args = p.parse_args()

    committed = _flatten(yaml.safe_load(args.committed.read_text()))
    generated = _flatten(yaml.safe_load(args.generated.read_text()))

    failures: list[str] = []

    def _delta(field: str):
        a, b = _num(committed.get(field)), _num(generated.get(field))
        if a is None or b is None:
            failures.append(f"  {field}: missing on one side ({committed.get(field)!r}/{generated.get(field)!r})")
            return None
        return abs(a - b)

    # ---- FAIL fields: the two means + tolerance_lower --------------------
    for field in _MEAN_FIELDS:
        d = _delta(field)
        if d is not None:
            print(f"  {field}: Δ={d:.3e} (tol {args.mean_tol:.1e})")
            if d > args.mean_tol:
                failures.append(f"  {field}: Δ={d:.3e} EXCEEDS mean tolerance {args.mean_tol:.1e}")
    d_tol = _delta(_TOLERANCE_FIELD)
    if d_tol is not None:
        print(f"  {_TOLERANCE_FIELD}: Δ={d_tol:.3e} (tol {args.tolerance_lower_tol:.1e})")
        if d_tol > args.tolerance_lower_tol:
            failures.append(f"  {_TOLERANCE_FIELD}: Δ={d_tol:.3e} EXCEEDS tolerance {args.tolerance_lower_tol:.1e}")

    # ---- DERIVATION invariant (exact): tolerance_lower == mean - 2*std ---
    gm, gs, gt = (_num(generated.get("metric_hidden_test_acc.mean")),
                  _num(generated.get("metric_hidden_test_acc.std")),
                  _num(generated.get(_TOLERANCE_FIELD)))
    if None not in (gm, gs, gt):
        expected = round(gm - 2 * gs, 6)
        if abs(gt - expected) > _DERIVATION_TOL:
            failures.append(
                f"  tolerance_lower derivation: stored {gt} != round(mean-2*std,6)={expected} "
                f"— a real threshold-computation bug, not microarch noise")
        else:
            print(f"  tolerance_lower derivation OK: {gt} == round({gm}-2*{gs},6)")

    # ---- INFORMATIONAL: std/min/max + max per-epoch delta (never fails) --
    per_epoch_max, pe_field = 0.0, None
    other_max, other_field = 0.0, None
    for k in set(committed) & set(generated):
        if k in _MEAN_FIELDS or k == _TOLERANCE_FIELD:
            continue
        a, b = _num(committed.get(k)), _num(generated.get(k))
        if a is None or b is None:
            continue
        d = abs(a - b)
        if ".epochs[" in k:
            if d > per_epoch_max:
                per_epoch_max, pe_field = d, k
        elif d > other_max:
            other_max, other_field = d, k
    print(f"  [info] max per-epoch delta: {per_epoch_max:.3e}" + (f" at {pe_field}" if pe_field else ""))
    print(f"  [info] max other (std/min/max) delta: {other_max:.3e}" + (f" at {other_field}" if other_field else ""))

    if failures:
        print("\nFAIL: reference regression (beyond cross-microarch noise):", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("PASS: means within 2e-3, tolerance_lower within 6e-3 + derivation exact; "
          "std/per-epoch informational.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
