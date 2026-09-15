#!/usr/bin/env python3
"""Re-score every stored trial's EVIDENCE under v2.1 (STAGE3_PLAN §0.4). Free — no model calls, no
training, ground truth never touched.

Sets `scores.evidence` = v2.1 (bipartite one-to-one, the corrected primary), preserving
`scores.evidence_v2` and `scores.evidence_v1` beside it for audit. Overwrites the record file and
updates index.jsonl. Prints the per-operator + per-sweep v2→v2.1 delta, the count moved, and the
largest individual drops — the disclosure checkpoint (report before committing).
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _hidden(root: Path, cid: str):
    hp = root / "cases" / cid / "hidden" / "card.hidden.yaml"
    ep = root / "cases" / cid / "hidden" / "evidence.yaml"
    if not hp.exists():
        return None, None
    return yaml.safe_load(hp.read_text()), (yaml.safe_load(ep.read_text()) or [] if ep.exists() else [])


def rescore(root: Path, apply: bool) -> dict:
    from harness.scoring import _evidence_triple
    from harness.provenance import update_index

    per = collections.defaultdict(list)      # (sweep, operator) -> [(old_f1, new_f1)]
    moved = []                               # (sweep, op, cid, old, new, delta, n_refs)
    n = written = 0
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        scores = rec.get("scores")
        if not isinstance(scores, dict) or "evidence" not in scores:
            continue
        cid = rec["case_id"]
        hcard, hrefs = _hidden(root, cid)
        if hcard is None:
            continue
        if not isinstance(scores.get("evidence"), dict):
            continue  # no evidence block to rescore (e.g. recovery-only record)
        old = (scores.get("evidence") or {}).get("f1")
        sub = rec.get("submission")
        if sub is None:
            # no submission: evidence is the zero/clean block already; just mirror v2==v1==primary.
            scores.setdefault("evidence_v2", scores["evidence"])
            scores.setdefault("evidence_v1", scores.get("evidence_v1", scores["evidence"]))
            new_primary = scores["evidence"]
        else:
            v21, v2, v1 = _evidence_triple(sub.get("evidence_refs", []) or [], hrefs, hcard)
            scores["evidence"], scores["evidence_v2"], scores["evidence_v1"] = v21, v2, v1
            new_primary = v21
        new = new_primary.get("f1")
        op = hcard.get("operator_id", "?")
        sw = (rec.get("conditions") or {}).get("sweep_name", "?")
        if old is not None and new is not None:
            per[(sw, op)].append((old, new))
            d = round(new - old, 4)
            if abs(d) > 1e-9:
                nrefs = len((sub or {}).get("evidence_refs", []) or [])
                moved.append((sw, op, cid, old, new, d, nrefs))
        n += 1
        if apply:
            f.write_text(yaml.dump(rec, default_flow_style=False, sort_keys=False))
            try:
                update_index(root, rec)
            except Exception:
                pass
            written += 1
    return {"n": n, "written": written, "per": per, "moved": moved}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--apply", action="store_true", help="overwrite records (default: dry-run report)")
    a = ap.parse_args()
    r = rescore(a.project_root, a.apply)
    print(f"trials={r['n']}  moved={len(r['moved'])}  written={r['written']}  ({'APPLIED' if a.apply else 'DRY-RUN'})")
    print("\n=== per (sweep, operator): mean v2, mean v2.1, Δ, n ===")
    for k in sorted(r["per"]):
        rows = r["per"][k]
        mv2 = sum(x[0] for x in rows) / len(rows)
        mv21 = sum(x[1] for x in rows) / len(rows)
        flag = "  <-- MOVED" if abs(mv21 - mv2) > 1e-9 else ""
        print(f"  {k[0]:10} {k[1]:28} v2={mv2:.4f} v2.1={mv21:.4f} Δ={mv21 - mv2:+.4f} n={len(rows)}{flag}")
    if r["moved"]:
        print("\n=== largest individual drops ===")
        for row in sorted(r["moved"], key=lambda x: x[5])[:10]:
            print(f"  {row[0]} {row[1]} {row[2]}: {row[3]:.3f} -> {row[4]:.3f} (Δ{row[5]:+.3f}, {row[6]} refs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
