"""Baseline table for the neutral-key data_leakage cases (v3 Part 2).

For every built `silent.data_leakage_neutral.v1` case, run the config-delta baseline
B2 (and B0/B1/B3) through the standard scorer and report detection + identification +
the submitted repair. Expected on the neutral cases: B2 DETECTS (a config delta on the
newly-present opt_c keys) and submits the RECOVERING repair (unset opt_c / opt_c_level),
but IDENTIFIES 0/6 — its only "class" output is the raw config leaf `opt_c`, which
matches neither accepted_classes nor the {leak} core tokens.

Runs natively in CI after the cases are built. Recovery *verification* (verify_repair)
is the FULL known-answer gate's job; here we show the repair B2 submits.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
sys.path.insert(0, str(ROOT))

from harness import baselines as B  # noqa: E402

TARGET = "silent.data_leakage_neutral.v1"


def _neutral_cases() -> list[str]:
    reg = yaml.safe_load((ROOT / "cases" / "registry.hidden.yaml").read_text()) or {}
    return sorted(cid for cid, e in reg.items()
                  if isinstance(e, dict) and e.get("operator") == TARGET)


def main() -> int:
    cases = _neutral_cases()
    if not cases:
        print(f"No {TARGET} cases built — nothing to report.")
        return 1
    print(f"=== BASELINES on {len(cases)} neutral cases ({TARGET}) ===")
    hdr = f"{'case':>10} | {'B2 detect':>9} {'B2 identify':>11} {'B2 repair keys':>34} | {'B0d':>4} {'B1d':>4} {'B3id':>5}"
    print(hdr)
    print("-" * len(hdr))
    det = ident = 0
    for cid in cases:
        cd = ROOT / "cases" / cid
        b2_sub, b2_sc = B.score_baseline(cd, "b2", project_root=ROOT)
        b0_sub, b0_sc = B.score_baseline(cd, "b0", project_root=ROOT)
        b1_sub, b1_sc = B.score_baseline(cd, "b1", project_root=ROOT)
        b3_sub, b3_sc = B.score_baseline(cd, "b3", project_root=ROOT)
        d = bool(b2_sc["detection"]["correct"])
        i = bool(b2_sc["identification"]["correct"])
        det += d
        ident += i
        repair_keys = sorted((b2_sub.get("repair_spec") or {}).get("patches", {}).keys())
        print(f"{cid:>10} | {str(d):>9} {str(i):>11} {','.join(repair_keys):>34} | "
              f"{str(bool(b0_sc['detection']['correct'])):>4} "
              f"{str(bool(b1_sc['detection']['correct'])):>4} "
              f"{str(bool(b3_sc['identification']['correct'])):>5}")
    print()
    print(f"B2 on neutral cases: detect {det}/{len(cases)}, identify {ident}/{len(cases)} "
          f"(expected: detect {len(cases)}/{len(cases)}, identify 0/{len(cases)})")
    # The instrument claim is falsified if B2 ever identifies the neutral fault.
    if ident != 0:
        print("UNEXPECTED: B2 identified a neutral case — the neutral key carried a token.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
