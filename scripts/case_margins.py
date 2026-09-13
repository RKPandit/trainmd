"""Per-case tier-guard margin report (Stage 1b, item 4).

For every built case: hidden faulty_value vs the current reference tolerance_lower
and the margin, flagging anything within 2x the reference hidden std. Exits
non-zero if ANY case fails its tier guard (a dynamics faulty run must be < tol;
a control must be >= tol; a crash trivially has no checkpoint metric).

Reads the CURRENT workload reference and each case's frozen hidden/verify.yaml —
run it after building cases against the reference you intend to adopt.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
WORKLOAD = os.environ.get("WORKLOAD", "tabular_adult")


def main() -> int:
    stats = yaml.safe_load((ROOT / "workloads" / WORKLOAD / "reference" / "stats.yaml").read_text())
    hid = stats["metric_hidden_test_acc"]
    tol = hid["tolerance_lower"]
    std = hid["std"]
    two_std = 2 * std
    print(f"reference: tolerance_lower={tol:.6f}  hidden_std={std:.6f}  2*std={two_std:.6f}")
    print(f"{'case':11} {'operator':16} {'strength':8} {'layer':10} {'faulty_value':13} {'margin':11} {'flag'}")
    print("-" * 88)

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
        rows.append((cd.name, op, hc.get("strength"), layer, fv))

    if not rows:
        print("NO CASES FOUND — build them first (make docker-build-all-cases).", file=sys.stderr)
        return 1

    failures = []
    tight = []
    for cid, op, st, layer, fv in rows:
        if fv is None:  # crash tier: no checkpoint metric, trivially below tolerance
            print(f"{cid:11} {op:16} {str(st):8} {layer:10} {'None(crash)':13} {'n/a':11} crash<tol")
            continue
        if layer == "control":
            margin = fv - tol  # must be >= 0 (healthy clears tolerance)
            ok = margin >= 0
            flag = "" if margin >= two_std else ("GUARD-FAIL: healthy<tol" if not ok else f"TIGHT (<2std, +{margin:.6f})")
        else:  # dynamics faulty: must be < tol
            margin = tol - fv
            ok = margin > 0
            flag = "" if margin >= two_std else ("GUARD-FAIL: faulty>=tol" if not ok else f"TIGHT (<2std, {margin:+.6f})")
        if not ok:
            failures.append(cid)
        elif margin < two_std:
            tight.append((cid, round(margin, 6)))
        print(f"{cid:11} {op:16} {str(st):8} {layer:10} {fv:<13.6f} {margin:+.6f}  {flag}")

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
