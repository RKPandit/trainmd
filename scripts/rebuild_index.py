#!/usr/bin/env python3
"""Rebuild results/index.jsonl from every trial record file (the records are the single source of truth;
each index row is harness.provenance._index_line(record)). Written atomically (temp file + rename).

    python scripts/rebuild_index.py [--compare BACKUP_INDEX]

With --compare, every row of the backup index is checked against the rebuilt row for the same run_id and the
differences are listed (a row may legitimately differ only where its record changed after the backup).
Created after the 2026-09-27 index corruption (DECISIONS 2026-09-27).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def rebuild(root: Path) -> tuple[list[dict], list[str]]:
    from harness.provenance import _index_line
    rows, problems = [], []
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        try:
            rec = yaml.safe_load(f.read_text())
            rows.append(_index_line(rec))
        except Exception as e:           # a record that cannot be read is reported, never silently skipped
            problems.append(f"{f.relative_to(root)}: {e}")
    rows.sort(key=lambda r: (str(r.get("timestamp_utc") or ""), str(r["run_id"])))
    return rows, problems


def write_atomic(path: Path, rows: list[dict]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".index.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compare", type=Path, default=None)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.project_root
    from harness.results_lock import assert_can_write
    assert_can_write(root, "rebuild results/index.jsonl")
    rows, problems = rebuild(root)
    if problems:
        print("UNREADABLE RECORDS (index NOT written):\n  " + "\n  ".join(problems))
        return 1
    ids = [r["run_id"] for r in rows]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        print(f"DUPLICATE run_ids across record files (index NOT written): {dups[:10]}")
        return 1
    write_atomic(root / "results" / "index.jsonl", rows)
    print(f"rebuilt results/index.jsonl: {len(rows)} rows from {len(rows)} record files (one per record)")
    if a.compare:
        back = {}
        for ln in a.compare.read_text().splitlines():
            if ln.strip():
                e = json.loads(ln)
                back[e["run_id"]] = e
        new = {r["run_id"]: r for r in rows}
        missing = sorted(set(back) - set(new))
        differ = sorted(k for k in set(back) & set(new) if back[k] != new[k])
        print(f"backup rows: {len(back)}; reproduced exactly: {len(set(back) & set(new)) - len(differ)}; "
              f"differ: {len(differ)}; in backup but no record: {len(missing)}; new since backup: "
              f"{len(set(new) - set(back))}")
        for k in differ[:10]:
            d = {f: (back[k].get(f), new[k].get(f)) for f in set(back[k]) | set(new[k]) if back[k].get(f) != new[k].get(f)}
            print(f"  differs {k}: {d}")
        if missing:
            print(f"  in backup, no record: {missing[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
