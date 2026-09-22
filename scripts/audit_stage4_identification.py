#!/usr/bin/env python
"""STAGE 4.0.1 — identification matcher audit + null-delta re-score (root_token_v2).

Re-scores the identification axis for every deduped trial in Sweeps 1, 2, and 3
under the hardened matcher (root_token_v2) and compares to the STORED score, to
demonstrate the correction is a NULL-DELTA HARDENING: the v1 rule was exploitable
(free-substring concept match credited negations like "no_leakage" and off-concept
collisions like "memory_leak"), but the audit finds ZERO exploitation in the stored
data, so no published identification number moves.

Ground truth is taken from the record's OWN sealed accepted_classes + true operator
(rebuild-proof), NEVER today's cases/ cards — see docs/DECISIONS.md 2026-09-22 and
harness.sweep_stats.operator_from_record. Read-only: preserves the originals.

Usage:  python scripts/audit_stage4_identification.py
"""
from __future__ import annotations

import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.scoring import score_identification  # noqa: E402
from harness.sweep_stats import operator_from_record  # noqa: E402
SWEEPS = {"sweep1": "Sweep 1", "stage2gate": "Sweep 2", "h8_xprovider": "Sweep 3"}
# Rebuild-proof re-score operator per CONCEPT (uniqueness guard is spec-identical
# for the two leakage variants, so the canonical leakage op scores identically).
CONCEPT_OP = {
    "control.healthy.v1": "control.healthy.v1",
    "silent.data_leakage.v1": "silent.data_leakage.v1",
    "silent.data_leakage_neutral.v1": "silent.data_leakage.v1",
    "silent.lr_warmup.v1": "silent.lr_warmup.v1",
    "silent.label_corruption.v1": "silent.label_corruption.v1",
    "silent.metric_inflation.v1": "silent.metric_inflation.v1",
    "crash.shape_mismatch.v1": "crash.shape_mismatch.v1",
}


def _cell_key(r):
    c = r.get("conditions") or {}
    return (r.get("case_id"), c.get("sweep_name"), c.get("agent_type"),
            c.get("anchor"), c.get("provider"), c.get("model"), c.get("repeat_index"))


def _ts(r):
    return ((r.get("environment") or {}).get("timestamp_utc") or "", r.get("run_id") or "")


def load_deduped():
    groups = defaultdict(list)
    for f in glob.glob(str(ROOT / "results" / "*" / "trials" / "*.yaml")):
        try:
            d = yaml.safe_load(open(f))
        except Exception:
            continue
        if (d.get("conditions") or {}).get("sweep_name") in SWEEPS:
            groups[_cell_key(d)].append(d)
    out = []
    for g in groups.values():
        ok = [x for x in g if x.get("status") not in ("crashed", "partial", "failed")]
        out.append(max(ok or g, key=_ts))
    return out


def main():
    recs = load_deduped()
    per_sweep = Counter((r.get("conditions") or {}).get("sweep_name") for r in recs)

    flips = {"to_wrong": [], "to_correct": []}
    rate_old = defaultdict(lambda: [0, 0])   # (sweep, op) -> [correct, n]
    rate_new = defaultdict(lambda: [0, 0])
    nulls = []

    for r in recs:
        sn = (r.get("conditions") or {}).get("sweep_name")
        idsc = (r.get("scores") or {}).get("identification") or {}
        sub = r.get("submission")
        pred = ((sub or {}).get("diagnosis") or {}).get("operator_class") if sub else None
        concept_op = operator_from_record(r)   # rebuild-proof (None for no-op)

        if pred is None or concept_op is None:
            nulls.append((sn, r.get("case_id"), r.get("run_id"), pred, concept_op,
                          bool(idsc.get("correct"))))
            # a null-submission / unattributable record scores incorrect either way
            rate_old[(sn, concept_op)][1] += 1
            rate_new[(sn, concept_op)][1] += 1
            if idsc.get("correct"):
                rate_old[(sn, concept_op)][0] += 1
            continue

        stored_correct = bool(idsc.get("correct"))
        card = {"operator_id": CONCEPT_OP[concept_op],
                "accepted_classes": idsc.get("accepted_classes") or []}
        new = score_identification({"diagnosis": {"operator_class": pred}}, card)
        new_correct = bool(new["correct"])

        rate_old[(sn, concept_op)][1] += 1
        rate_new[(sn, concept_op)][1] += 1
        rate_old[(sn, concept_op)][0] += int(stored_correct)
        rate_new[(sn, concept_op)][0] += int(new_correct)

        if stored_correct and not new_correct:
            flips["to_wrong"].append((sn, r.get("case_id"), pred, concept_op))
        elif new_correct and not stored_correct:
            flips["to_correct"].append((sn, r.get("case_id"), pred, concept_op))

    print("=== dedup counts ===", dict(per_sweep), "total", len(recs))
    print("\n=== RE-SCORE DELTA (root_token_v1 stored -> root_token_v2) ===")
    print("flipped correct -> WRONG :", len(flips["to_wrong"]))
    print("flipped wrong -> CORRECT :", len(flips["to_correct"]))
    for k, v in flips.items():
        for row in v:
            print("   ", k, row)

    print("\n=== identification rate: stored (v1) vs re-scored (v2) ===")
    for sn in SWEEPS:
        keys = sorted((k for k in rate_new if k[0] == sn),
                      key=lambda k: (k[1] or "~none"))
        print(f"\n{SWEEPS[sn]}")
        for k in keys:
            oc, on = rate_old[k]
            nc, nn = rate_new[k]
            tag = "" if (oc, on) == (nc, nn) else "   <-- CHANGED"
            print(f"   {str(k[1]):34s} v1 {oc:4d}/{on:<4d}  v2 {nc:4d}/{nn:<4d}{tag}")

    print(f"\n=== NULL / unattributable no-op trials: {len(nulls)} ===")
    by_sweep = Counter(n[0] for n in nulls)
    print("by sweep:", dict(by_sweep))
    any_correct = [n for n in nulls if n[5]]
    any_pred = [n for n in nulls if n[3] is not None]
    print("null-submission (predicted_class is None):", sum(1 for n in nulls if n[3] is None))
    print("scored correct among nulls (should be 0):", len(any_correct))
    print("had a non-null predicted_class but no sealed key:", len(any_pred))


if __name__ == "__main__":
    main()
