#!/usr/bin/env python3
"""Release FIELD INVENTORY: every key path that appears in a release, with the count of files holding it.

Why this exists: three documented claims about release content were wrong — `accepted_classes`,
`hidden_sigma_distance`, and `band_position_hidden` were each described as absent (or protected)
while being exported, because the docs described the release by INTENT while trial `scores` are
exported whole (DECISIONS 2026-09-23). Release-content statements now REFERENCE this inventory, which
is generated from the artifact itself; `scripts/check_release_claims.py` fails CI when a doc names a
field as absent from a release that the inventory shows present, or when an inventory is stale.

Written to ``results_release/<name>/FIELD_INVENTORY.json`` by ``export_release.py`` after every export
(and regenerable for an existing release with ``--write``, without touching any other release byte):

  {"sweep": name,
   "files": {"trials": N, "cases": M, "probes": P},
   "fields": {"trials": {"scores.band_position_hidden": 954, ...},     # key path -> files containing it
              "cases":  {...}, "probes": {...},
              "index.csv": {"<column>": N_rows_with_nonempty_value, ...},
              "release_meta.json": {...}}}

Key paths are dotted; list elements are written ``[]`` (``llm_transcript[].usage.input_tokens``). A path
is counted at most once per file. Only KEYS are recorded, never values.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_NAME = "FIELD_INVENTORY.json"


def key_paths(x, prefix: str = "") -> set[str]:
    """Every key path in a JSON value (dict keys dotted, list elements as ``[]``)."""
    out: set[str] = set()
    if isinstance(x, dict):
        for k, v in x.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.add(p)
            out |= key_paths(v, p)
    elif isinstance(x, list):
        for v in x:
            out |= key_paths(v, prefix + "[]")
    return out


def _count_dir(d: Path) -> tuple[int, dict[str, int]]:
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    c: Counter = Counter()
    for f in files:
        c.update(key_paths(json.loads(f.read_text())))
    return len(files), dict(sorted(c.items()))


def inventory(release_dir: Path) -> dict:
    name = release_dir.name
    n_trials, trials = _count_dir(release_dir / "trials")
    n_cases, cases = _count_dir(release_dir / "cases")
    n_probes, probes = _count_dir(release_dir / "probes")
    fields: dict = {"trials": trials, "cases": cases}
    files = {"trials": n_trials, "cases": n_cases}
    if n_probes:
        fields["probes"], files["probes"] = probes, n_probes
    idx = release_dir / "index.csv"
    if idx.exists():
        with open(idx, newline="") as fh:
            rows = list(csv.DictReader(fh))
        cols = rows[0].keys() if rows else []
        fields["index.csv"] = {c: sum(1 for r in rows if r.get(c) not in (None, "")) for c in sorted(cols)}
    meta = release_dir / "release_meta.json"
    if meta.exists():
        fields["release_meta.json"] = {p: 1 for p in sorted(key_paths(json.loads(meta.read_text())))}
    return {"sweep": name, "files": files, "fields": fields}


def render(inv: dict) -> str:
    return json.dumps(inv, indent=1, sort_keys=True) + "\n"


def write(release_dir: Path) -> Path:
    out = release_dir / INVENTORY_NAME
    out.write_text(render(inventory(release_dir)))
    return out


def is_current(release_dir: Path) -> bool:
    p = release_dir / INVENTORY_NAME
    return p.exists() and p.read_text() == render(inventory(release_dir))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", action="append", help="release name (repeatable; default: all)")
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--write", action="store_true", help="(re)write FIELD_INVENTORY.json")
    a = ap.parse_args()
    rel = a.project_root / "results_release"
    names = a.sweep or sorted(p.name for p in rel.iterdir() if (p / "trials").is_dir())
    stale = []
    for n in names:
        d = rel / n
        if a.write:
            print(f"wrote {write(d).relative_to(a.project_root)}")
        elif not is_current(d):
            stale.append(n)
    if stale:
        print(f"release_field_inventory: STALE or missing for {stale} — run "
              f"`python scripts/release_field_inventory.py --write --sweep <name>`", file=sys.stderr)
        return 1
    if not a.write:
        print(f"release_field_inventory: OK — {len(names)} inventory(ies) match their releases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
