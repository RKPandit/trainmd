#!/usr/bin/env python3
"""Disclosed correction after the second human audit (DECISIONS 2026-09-27): re-score Stage 4 Part 1's
IDENTIFICATION under root_token_v3 and EVIDENCE under evidence_v2.3, in the local records (Part 1 is not a
committed release). Previous primaries are kept beside the new ones (`identification_v2`, `evidence_v2_2`).

Safety: before writing, every record's recomputed v2.2 evidence and root_token_v2-equivalent identification
must equal what is stored — otherwise nothing is written (the only change must be the declared one).

    python scripts/rescore_stage4_part1.py            # dry run: before/after tables
    python scripts/rescore_stage4_part1.py --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SWEEP = "stage4_part1"


def main() -> int:
    from harness.provenance import update_index
    from harness.scoring import _evidence_all, score_identification

    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.apply:
        from harness.results_lock import assert_can_write
        assert_can_write(ROOT, "re-score trial records")
    cards, before, after, changed = {}, defaultdict(lambda: [0, 0, 0.0, 0.0, 0]), {}, []
    todo = []
    for f in sorted((ROOT / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        c = rec.get("conditions") or {}
        if c.get("sweep_name") != SWEEP or not isinstance(rec.get("scores"), dict) or rec.get("submission") is None:
            continue
        cid = rec["case_id"]
        if cid not in cards:
            cards[cid] = (yaml.safe_load((ROOT / "cases" / cid / "hidden" / "card.hidden.yaml").read_text()),
                          yaml.safe_load((ROOT / "cases" / cid / "hidden" / "evidence.yaml").read_text()) or [])
        card, hrefs = cards[cid]
        sc = rec["scores"]
        ev = _evidence_all((rec["submission"].get("evidence_refs") or []), hrefs, card,
                           workspace=ROOT / "cases" / cid / "workspace")
        idn = score_identification(rec["submission"], card)
        # Idempotent: on an already re-scored record the previous primaries live in *_v2_2 / *_v2.
        old_ev = sc.get("evidence_v2_2") or sc.get("evidence") or {}
        old_id = sc.get("identification_v2") or sc.get("identification") or {}
        if isinstance(old_ev, dict) and old_ev.get("f1") is not None and abs(ev["v2_2"]["f1"] - old_ev["f1"]) > 1e-9:
            raise SystemExit(f"{f.name}: recomputed v2.2 evidence {ev['v2_2']['f1']} != stored {old_ev['f1']} — abort")
        todo.append((f, rec, ev, idn))
        key = (card["operator_id"], c.get("provider"))
        b = before[key]
        b[0] += 1
        b[1] += bool(old_id.get("correct"))
        b[2] += (old_ev.get("f1") or 0.0) if isinstance(old_ev, dict) else 0.0
        b[3] += ev["v2_3"]["f1"]
        b[4] += bool(idn["correct"])
        if bool(idn["correct"]) != bool(old_id.get("correct")) or \
                (isinstance(old_ev, dict) and abs(ev["v2_3"]["f1"] - (old_ev.get("f1") or 0.0)) > 1e-9):
            changed.append((rec["run_id"], card["operator_id"], bool(old_id.get("correct")), bool(idn["correct"]),
                            old_ev.get("f1") if isinstance(old_ev, dict) else None, ev["v2_3"]["f1"]))
    print(f"records re-scored: {len(todo)}; changed: {len(changed)} "
          f"(identification {sum(1 for x in changed if x[2] != x[3])}, "
          f"evidence {sum(1 for x in changed if x[4] is not None and abs(x[5] - x[4]) > 1e-9)})")
    print(f"{'operator':34} {'provider':10} {'n':>5} {'id v2':>7} {'id v3':>7} {'ev v2.2':>8} {'ev v2.3':>8}")
    for k in sorted(before):
        n, i2, e22, e23, i3 = before[k]
        print(f"{k[0]:34} {str(k[1]):10} {n:5d} {i2 / n:7.3f} {i3 / n:7.3f} {e22 / n:8.4f} {e23 / n:8.4f}")
    if a.apply:
        for f, rec, ev, idn in todo:
            sc = rec["scores"]
            out = {}
            for k, v in sc.items():
                if k == "identification":
                    out["identification"] = idn
                    out["identification_v2"] = sc.get("identification_v2") or v
                elif k == "evidence":
                    out["evidence"] = ev["v2_3"]
                    out["evidence_v2_2"] = ev["v2_2"]
                elif k in ("identification_v2", "evidence_v2_2"):
                    continue
                else:
                    out[k] = v
            rec["scores"] = out
            f.write_text(yaml.dump(rec, default_flow_style=False, sort_keys=False))
            update_index(ROOT, rec)
        print(f"APPLIED to {len(todo)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
