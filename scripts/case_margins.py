"""Per-case tier-guard margin report (Stage 1b, item 4).

For every built case: hidden faulty_value vs the current reference tolerance_lower
and the margin, flagging anything within 2x the reference hidden std. Exits
non-zero if ANY case fails its tier guard: a dynamics faulty run must be < tol.
CONTROL and METRIC are REPORT-ONLY (never a guard failure) — their band position
is recorded, not gated: a control is retained at any band position (§5.1), and the
metric tier's "model untouched" guarantee is checkpoint bitwise identity (verified
in build_case / validate_case C12), NOT hidden-band position, which varies by seed
and runner microarch (L24, DECISIONS 2026-09-19). A crash has no checkpoint metric.

Reads the CURRENT workload reference and each case's frozen hidden/verify.yaml —
run it after building cases against the reference you intend to adopt.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
WORKLOAD = os.environ.get("WORKLOAD", "tabular_adult")

# Tiers whose model is HEALTHY, so hidden accuracy must CLEAR tolerance. control:
# no fault. metric: the fault is only in the reported metric; the model is fine.
_HEALTHY_MODEL_LAYERS = ("control", "metric")


def margin_flag(layer: str, fv: float, tol: float, two_std: float) -> tuple[float, bool, str]:
    """(margin, ok, flag) for one case's tier guard against tolerance.

    control (§5.1): RETAINED at any band position — never a guard failure; the
    flag records where it sits. metric: healthy model must clear tolerance
    (fv >= tol). dynamics: faulty model must fall below it (fv < tol). Pure and
    tier-complete so the tier-ripple test can assert all three layers behave.
    """
    if layer == "control":
        # §5.1: a control is RETAINED at ANY band position — never a guard
        # failure. Report where it sits vs the band (informational): rejecting an
        # out-of-band control is the selection bias §5.1 removed. `mean+2σ`
        # == tol + 2*two_std (mean == tol + two_std), so above-band ⇔ margin > 2*two_std.
        margin = fv - tol
        ok = True
        if margin < 0:
            flag = f"OUT-OF-BAND below ({margin:+.6f}, retained §5.1)"
        elif margin > 2 * two_std:
            flag = f"OUT-OF-BAND above ({margin:+.6f}, retained §5.1)"
        elif margin < two_std:
            flag = f"TIGHT (<2std, +{margin:.6f})"
        else:
            flag = ""
    elif layer == "metric":
        # Metric tier's "model untouched" guarantee is checkpoint BITWISE IDENTITY
        # to clean (build_case guard + validate_case C12), NOT hidden-band position
        # — which varies by seed and runner microarch (drift up to ~2.8σ, L24;
        # DECISIONS 2026-09-19). So RECORD where the healthy hidden sits but NEVER
        # fail on it (report-only, exactly like control).
        margin = fv - tol
        ok = True
        if margin < 0:
            flag = f"OUT-OF-BAND below ({margin:+.6f}; model untouched — verified by checkpoint)"
        elif margin > 2 * two_std:
            flag = f"OUT-OF-BAND above ({margin:+.6f}; model untouched — verified by checkpoint)"
        elif margin < two_std:
            flag = f"TIGHT (<2std, +{margin:.6f})"
        else:
            flag = ""
    else:  # dynamics faulty: must be < tol
        margin = tol - fv
        ok = margin > 0
        flag = "" if margin >= two_std else (
            "GUARD-FAIL: faulty>=tol" if not ok else f"TIGHT (<2std, {margin:+.6f})")
    return margin, ok, flag


def main() -> int:
    default_stats = ROOT / "workloads" / WORKLOAD / "reference" / "stats.yaml"
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", type=Path, default=default_stats,
                    help="reference stats.yaml to score margins against "
                         "(default: the committed workload reference; pass the 30-seed CANDIDATE "
                         "stats to preview margins before adoption, STAGE3_PLAN §0.5)")
    a = ap.parse_args()

    stats = yaml.safe_load(a.stats.read_text())
    hid = stats["metric_hidden_test_acc"]
    tol = hid["tolerance_lower"]
    std = hid["std"]
    two_std = 2 * std
    vis = stats["metric_visible_val_acc"]        # §5.2: also report the VISIBLE metric per case
    vmean, vstd = vis["mean"], vis["std"]
    print(f"reference stats: {a.stats}  (num_seeds={stats.get('num_seeds', '?')})")
    print(f"reference: tolerance_lower={tol:.6f}  hidden_std={std:.6f}  2*std={two_std:.6f}  "
          f"visible mean={vmean:.6f} std={vstd:.6f}")
    print(f"{'case':11} {'operator':16} {'strength':8} {'layer':10} {'faulty_value':13} {'margin':11} "
          f"{'visible':10} {'vis_zσ':8} {'flag'}")
    print("-" * 104)

    rows = []
    for cd in sorted(glob.glob(str(ROOT / "cases" / "case_*"))):
        cd = Path(cd)
        try:
            v = yaml.safe_load((cd / "hidden" / "verify.yaml").read_text())
            hc = yaml.safe_load((cd / "hidden" / "card.hidden.yaml").read_text())
        except FileNotFoundError:
            continue
        op = (hc.get("operator_id") or "?").split(".")[1] if hc.get("operator_id") else "?"
        layer = hc.get("layer")
        fv = v.get("faulty_value")
        vv = hc.get("faulty_visible_value")   # agent-facing visible metric (None for crash tier)
        rows.append((cd.name, op, hc.get("strength"), layer, fv, vv))

    if not rows:
        print("NO CASES FOUND — build them first (make docker-build-all-cases).", file=sys.stderr)
        return 1

    failures = []
    tight = []
    for cid, op, st, layer, fv, vv in rows:
        vis_str = f"{vv:.6f}" if isinstance(vv, (int, float)) else "n/a"
        vis_z = f"{(vv - vmean) / vstd:+.2f}" if isinstance(vv, (int, float)) else "n/a"
        if fv is None:  # crash tier: no checkpoint metric, trivially below tolerance
            print(f"{cid:11} {op:16} {str(st):8} {layer:10} {'None(crash)':13} {'n/a':11} "
                  f"{vis_str:10} {vis_z:8} crash<tol")
            continue
        margin, ok, flag = margin_flag(layer, fv, tol, two_std)
        if not ok:
            failures.append(cid)
        elif margin < two_std:
            tight.append((cid, round(margin, 6)))
        print(f"{cid:11} {op:16} {str(st):8} {layer:10} {fv:<13.6f} {margin:+.6f}  "
              f"{vis_str:10} {vis_z:8} {flag}")

    print("-" * 88)
    if tight:
        print("TIGHT (margin < 2x std, holds but watch): " + ", ".join(f"{c}({m:+})" for c, m in tight))
    if failures:
        print(f"TIER-GUARD FAILURES ({len(failures)}): {', '.join(failures)} — STOP; do not adjust operators to force a pass.", file=sys.stderr)
        return 1
    print(f"OK: all {len(rows)} cases satisfy their tier guard against tolerance {tol:.6f}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
