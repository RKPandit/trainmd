#!/usr/bin/env python3
"""Scorer-provenance guard (STAGE3_PLAN §0.4, ruling 3): the report's declared evidence scorer must
match the scorer actually recorded on that sweep's records.

A wrong statement about WHICH INSTRUMENT produced a number is a provenance error — worse than a small
numeric one, because everything downstream inherits it (this is exactly what happened: docs said "v2
primary" for Sweep 1 while the records carried v1). For each sweep with a committed release, this
reads the "evidence scorer: X" line from `docs/audits/sweep_<name>_generated.md` and asserts EVERY
release trial's `scores.evidence.scorer_version` == X. Fails loudly naming the sweep + the mismatch.
Runs from the committed release (results/ is gitignored). Same class as the CURRENT_STATE / numbers
guards: a documented fact about the instrument, machine-checked.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCORER_LINE = re.compile(r"evidence scorer:\s*(\S+)", re.I)


def _report_scorer(report: Path) -> str | None:
    if not report.exists():
        return None
    m = _SCORER_LINE.search(report.read_text())
    return m.group(1) if m else None


def check_sweep(root: Path, name: str) -> list[str]:
    errors: list[str] = []
    report = root / "docs" / "audits" / f"sweep_{name}_generated.md"
    declared = _report_scorer(report)
    if declared is None:
        return [f"{name}: no 'evidence scorer:' line in sweep_{name}_generated.md"]
    trials = root / "results_release" / name / "trials"
    versions = collections.Counter()
    for f in sorted(trials.glob("*.json")):
        ev = (json.loads(f.read_text()).get("scores") or {}).get("evidence")
        if isinstance(ev, dict) and ev.get("scorer_version"):
            versions[ev["scorer_version"]] += 1
    if not versions:
        return [f"{name}: no evidence scorer_version on any release trial"]
    present = dict(versions)
    off = {v: c for v, c in present.items() if v != declared}
    if off:
        errors.append(f"{name}: report declares '{declared}' but records carry {off} "
                     f"(all should be '{declared}')")
    return errors


def run(root: Path = ROOT) -> list[str]:
    errors = []
    rel = root / "results_release"
    if not rel.exists():
        return errors
    for d in sorted(rel.iterdir()):
        if (d / "trials").is_dir():
            errors += check_sweep(root, d.name)
    return errors


def main() -> int:
    errors = run()
    if errors:
        print("check_scorer_versions: FAIL — report scorer disagrees with the records:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_scorer_versions: OK — every sweep's report scorer matches its records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
