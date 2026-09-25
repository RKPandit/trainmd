#!/usr/bin/env python3
"""Re-score stored trials' EVIDENCE under the current primary scorer, v2.2 (DECISIONS 2026-09-25; v2.1
per STAGE3_PLAN §0.4 before it). Free — no model calls, no training.

Sets `scores.evidence` = v2.2 (v2.1 + the operator's code-path evidence set), preserving
`scores.evidence_v2_1`, `scores.evidence_v2` and `scores.evidence_v1` beside it for audit. Overwrites
the record file and updates index.jsonl. Prints the per-operator + per-sweep before→after delta, the
count moved, and the largest individual moves — the disclosure checkpoint (report before committing).

Code-path spans are resolved against the workload source the agents ACTUALLY READ: `--source-rev`
(the sweep's manifest git_commit) rebuilds each case's train.py/datautil.py from git at that commit
(operators edit config only, so workspace code == workload source). Without it, the current case
workspace is used. `--sweep` restricts the rescore to named sweeps (records of other sweeps are left
untouched on their own scorer).
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


def _git_file(root: Path, rev: str, path: str) -> str:
    """File content at ``rev``, following an in-repo symlink (git stores its target as the blob)."""
    import posixpath
    import subprocess
    for _ in range(5):
        mode = subprocess.run(["git", "-C", str(root), "ls-tree", rev, path],
                              capture_output=True, text=True, check=True).stdout.split()
        blob = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{path}"],
                              capture_output=True, text=True, check=True).stdout
        if not mode or mode[0] != "120000":
            return blob
        path = posixpath.normpath(posixpath.join(posixpath.dirname(path), blob.strip()))
    raise RuntimeError(f"symlink chain too deep at {rev}:{path}")


def _source_workspace(root: Path, rev: str, workload: str, cache: dict) -> Path:
    """A temp dir holding the workload's train.py + datautil.py as of ``rev`` (cached per workload)."""
    import tempfile
    if workload not in cache:
        d = Path(tempfile.mkdtemp(prefix=f"evsrc_{workload}_"))
        for fn in ("train.py", "datautil.py"):
            (d / fn).write_text(_git_file(root, rev, f"workloads/{workload}/{fn}"))
        cache[workload] = d
    return cache[workload]


def _workload_name(root: Path, cid: str) -> str:
    card = yaml.safe_load((root / "cases" / cid / "card.public.yaml").read_text())
    return card["workload_name"]


def rescore(root: Path, apply: bool, sweeps: set[str] | None = None, source_rev: str | None = None) -> dict:
    from harness.scoring import _evidence_triple
    from harness.provenance import update_index

    src_cache: dict = {}

    per = collections.defaultdict(list)      # (sweep, operator) -> [(old_f1, new_f1)]
    moved = []                               # (sweep, op, cid, old, new, delta, n_refs)
    n = written = 0
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        scores = rec.get("scores")
        if not isinstance(scores, dict) or "evidence" not in scores:
            continue
        if sweeps is not None and (rec.get("conditions") or {}).get("sweep_name") not in sweeps:
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
            # no submission: evidence is the zero/clean block already; mirror it into the audit keys.
            scores.setdefault("evidence_v2_1", scores["evidence"])
            scores.setdefault("evidence_v2", scores["evidence"])
            scores.setdefault("evidence_v1", scores.get("evidence_v1", scores["evidence"]))
            new_primary = scores["evidence"]
        else:
            ws = (_source_workspace(root, source_rev, _workload_name(root, cid), src_cache) if source_rev
                  else root / "cases" / cid / "workspace")
            v22, v21, v2, v1 = _evidence_triple(sub.get("evidence_refs", []) or [], hrefs, hcard,
                                                workspace=ws)
            if not v22.get("code_path_set") and getattr(_op(hcard), "CODE_PATH", None):
                raise RuntimeError(f"{cid}: operator declares CODE_PATH but it did not resolve against {ws}")
            rec["scores"] = scores = _with_evidence(scores, v22, v21, v2, v1)
            new_primary = v22
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


def _with_evidence(scores: dict, v22: dict, v21: dict, v2: dict, v1: dict) -> dict:
    """``scores`` with the four evidence blocks replaced, in a stable order (evidence, evidence_v2_1,
    evidence_v2, evidence_v1 at evidence's position); every other key keeps its place."""
    ev = {"evidence": v22, "evidence_v2_1": v21, "evidence_v2": v2, "evidence_v1": v1}
    out = {}
    for k, v in scores.items():
        if k == "evidence":
            out.update(ev)
        elif k not in ev:
            out[k] = v
    return out


def patch_release(root: Path, name: str) -> dict:
    """Carry the rescored evidence into a COMMITTED release IN PLACE — only the evidence blocks of each
    trial's `scores` and index.csv's `evidence_f1` change; per-case metadata, transcripts and every
    other byte stay as released (a full re-export would re-derive per-case metadata from today's
    rebuilt cards). Re-runs the hidden-value wall scan and regenerates FIELD_INVENTORY.json."""
    import csv
    import io
    import json
    from scripts.export_release import _scan_release
    from scripts.release_field_inventory import write as write_inventory

    out_dir = root / "results_release" / name
    local = {}
    for f in (root / "results").glob("*/trials/*.yaml"):
        rec = yaml.safe_load(f.read_text())
        if (rec.get("conditions") or {}).get("sweep_name") == name:
            local[(rec["case_id"], rec["run_id"])] = rec
    f1 = {}
    n = 0
    for f in sorted((out_dir / "trials").glob("*.json")):
        rel = json.loads(f.read_text())
        rec = local.get((rel["case_id"], rel["run_id"]))
        if rec is None:
            raise RuntimeError(f"release trial {f.name} has no local record")
        sc, rsc = rel.get("scores"), rec.get("scores") or {}
        if isinstance(sc, dict) and isinstance(sc.get("evidence"), dict):
            rel["scores"] = _with_evidence(sc, rsc["evidence"], rsc.get("evidence_v2_1", rsc["evidence"]),
                                           rsc["evidence_v2"], rsc["evidence_v1"])
            f.write_text(json.dumps(rel, indent=1, default=str))
            n += 1
        f1[(rel["case_id"], rel["run_id"])] = ((rel.get("scores") or {}).get("evidence") or {}).get("f1")
    idx = out_dir / "index.csv"
    with open(idx, newline="") as fh:        # CRLF rows, as csv.DictWriter wrote them
        rows = list(csv.DictReader(fh))
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        v = f1[(r["case_id"], r["run_id"])]
        r["evidence_f1"] = "" if v is None else str(v)
        w.writerow(r)
    with open(idx, "w", newline="") as fh:
        fh.write(buf.getvalue())
    case_ids = {p.stem for p in (out_dir / "cases").glob("*.json")}
    hits = _scan_release(root, out_dir, case_ids)
    if hits:
        raise SystemExit("patch_release: HIDDEN-VALUE LEAK:\n  " + "\n  ".join(hits[:20]))
    write_inventory(out_dir)
    return {"patched_trials": n}


def _op(hcard: dict):
    from operators.registry import get_operator
    return get_operator(hcard.get("operator_id", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--apply", action="store_true", help="overwrite records (default: dry-run report)")
    ap.add_argument("--sweep", action="append", help="only rescore records of this sweep (repeatable)")
    ap.add_argument("--source-rev", help="git commit whose workload source the agents read (manifest git_commit)")
    ap.add_argument("--patch-release", action="store_true",
                    help="with --apply and one --sweep: carry the rescore into results_release/<sweep> in place")
    a = ap.parse_args()
    r = rescore(a.project_root, a.apply, set(a.sweep) if a.sweep else None, a.source_rev)
    print(f"trials={r['n']}  moved={len(r['moved'])}  written={r['written']}  ({'APPLIED' if a.apply else 'DRY-RUN'})")
    print("\n=== per (sweep, operator): mean before, mean after (primary), Δ, n ===")
    for k in sorted(r["per"]):
        rows = r["per"][k]
        mb = sum(x[0] for x in rows) / len(rows)
        ma = sum(x[1] for x in rows) / len(rows)
        flag = "  <-- MOVED" if abs(ma - mb) > 1e-9 else ""
        print(f"  {k[0]:12} {k[1]:32} before={mb:.4f} after={ma:.4f} Δ={ma - mb:+.4f} n={len(rows)}{flag}")
    if r["moved"]:
        print(f"\n=== moves: {sum(1 for m in r['moved'] if m[5] > 0)} up, "
              f"{sum(1 for m in r['moved'] if m[5] < 0)} down ===")
        print("=== largest individual moves ===")
        for row in sorted(r["moved"], key=lambda x: -abs(x[5]))[:10]:
            print(f"  {row[0]} {row[1]} {row[2]}: {row[3]:.3f} -> {row[4]:.3f} (Δ{row[5]:+.3f}, {row[6]} refs)")
    if a.patch_release:
        if not (a.apply and a.sweep and len(a.sweep) == 1):
            raise SystemExit("--patch-release needs --apply and exactly one --sweep")
        print(f"\nrelease patched: {patch_release(a.project_root, a.sweep[0])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
