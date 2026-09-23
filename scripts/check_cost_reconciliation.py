#!/usr/bin/env python3
"""Sweep-level cost reconciliation: sum of per-trial ESTIMATES vs the billed actual_spend_usd.

R8 checks each trial's estimate against its own token counts; it cannot catch a systematic gap
between the estimates and what the providers actually billed (unpriced cache writes, unrecorded
crashed attempts, a stale rate). This check closes that loop per released sweep:

  estimate = sum of usage.estimated_cost_usd over the release's trials (the committed, CI-visible
             records — trusted probes are excluded from releases and cost nothing)
  actual   = actual_spend_usd from sweeps/<name>_manifest.yaml (entered from the billing
             statements; falls back to the release's manifest copy)

  ratio = actual / estimate.  PASS iff |ratio − 1| <= TOLERANCE; FAIL otherwise.
  actual_spend_usd null → PENDING (not a failure: the bills have not been entered yet).

TOLERANCE = ±5% on the sweep total. Known, bounded sources of gap: attempts that crashed before a
record was written; provider rounding; and, through Sweep 3, Luna cache writes that were never
priced (≤ ≈$0.18 on H8, <1% of its total — LIMITATIONS L6). A gap beyond 5% is a real pricing or
accounting error to investigate, not noise. If the manifest also carries actual_spend_by_provider
({provider: usd}), per-provider ratios are REPORTED (not gated: per-provider totals are small and the
pre-Stage-4 Luna write gap alone can exceed 5% of Luna's share).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOLERANCE = 0.05


def _manifest(root: Path, name: str) -> dict:
    for p in (root / "sweeps" / f"{name}_manifest.yaml",
              root / "results_release" / name / f"{name}_manifest.yaml"):
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def reconcile(root: Path, name: str) -> dict:
    rel = root / "results_release" / name
    est, by_prov = 0.0, {}
    for f in sorted((rel / "trials").glob("*.json")):
        rec = json.loads(f.read_text())
        cost = (rec.get("usage") or {}).get("estimated_cost_usd") or 0.0
        prov = ((rec.get("conditions") or {}).get("provider")
                or (rec.get("model") or {}).get("provider") or "anthropic")
        est += cost
        by_prov[prov] = by_prov.get(prov, 0.0) + cost
    man = _manifest(root, name)
    actual = man.get("actual_spend_usd")
    out = {"sweep": name, "estimate_usd": round(est, 4), "actual_usd": actual,
           "estimate_by_provider": {k: round(v, 4) for k, v in sorted(by_prov.items())}}
    # Per-provider ratios are reported whenever any provider's bill is entered — including while
    # the sweep total is still PENDING on another provider's figure (a partial entry).
    per = {p: v for p, v in (man.get("actual_spend_by_provider") or {}).items() if v is not None}
    if per:
        out["ratio_by_provider"] = {p: (round(per[p] / by_prov[p], 4) if by_prov.get(p) else None)
                                    for p in sorted(per)}
    if actual is None:
        out["status"] = "PENDING"
        return out
    ratio = actual / est if est else float("inf")
    out["ratio"] = round(ratio, 4)
    out["status"] = "PASS" if abs(ratio - 1) <= TOLERANCE else "FAIL"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    sweeps = sorted(p.name for p in (a.project_root / "results_release").iterdir()
                    if (p / "trials").is_dir()) if (a.project_root / "results_release").is_dir() else []
    failed = False
    for name in sweeps:
        r = reconcile(a.project_root, name)
        line = f"{r['status']:7s} {name}: estimate ${r['estimate_usd']:.4f}"
        if r["actual_usd"] is None:
            line += " · actual_spend_usd not yet entered"
        else:
            line += f" · actual ${r['actual_usd']:.4f} · ratio {r['ratio']:.4f} (tolerance ±{TOLERANCE:.0%})"
        if r.get("ratio_by_provider"):
            line += f" · by provider (reported) {r['ratio_by_provider']}"
        print(line)
        failed |= r["status"] == "FAIL"
    if failed:
        print("check_cost_reconciliation: FAIL — billed spend differs from the summed estimates "
              f"by more than ±{TOLERANCE:.0%}; investigate pricing/accounting.", file=sys.stderr)
        return 1
    print(f"check_cost_reconciliation: OK — {len(sweeps)} released sweep(s) within ±{TOLERANCE:.0%} "
          "or pending billed figures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
