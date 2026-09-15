#!/usr/bin/env python3
"""Numbers-provenance guard (STAGE3_PLAN §0.3-C, answer 1).

An analysis narrative may interpret but must not INVENT numbers: every numeric literal in an
`_analysis.md` must appear in that sweep's machine-generated `_generated.md` (the only place a number
is authored), within a small rounding tolerance. A number that legitimately comes from elsewhere
(a manifest cost, an external paper, a probe) is exempted by an inline `<!-- src: ... -->` marker on
its line. Fails naming each orphan — the same principle as the CURRENT_STATE guard: if a human doc
and the machine record disagree, one is stale and CI says which.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# analysis doc (relative to docs/audits/) -> sweep whose generated report is its machine source
_PAIRS = {
    "sweep_stage2gate_2026-09-15.md": "stage2gate",
}

_NUM = re.compile(r"-?\d+\.\d+")            # decimals only (rates / CIs); integers are too noisy
_SRC = re.compile(r"<!--\s*src:", re.I)     # a line-level provenance exemption
_TOL = 3                                     # round both sides to this many decimals


def _nums(text: str) -> set[str]:
    return {f"{round(float(m), _TOL):.{_TOL}f}" for m in _NUM.findall(text)}


def check_pair(analysis_path: Path, generated_path: Path) -> list[str]:
    if not analysis_path.exists() or not generated_path.exists():
        return [f"missing file: {analysis_path.name if not analysis_path.exists() else generated_path.name}"]
    gen_nums = _nums(generated_path.read_text())
    orphans = []
    for i, line in enumerate(analysis_path.read_text().splitlines(), 1):
        if _SRC.search(line) or line.lstrip().startswith("#"):  # markers + markdown headers exempt
            continue
        for m in _NUM.findall(line):
            key = f"{round(float(m), _TOL):.{_TOL}f}"
            if key not in gen_nums:
                orphans.append(f"{analysis_path.name}:{i} number {m} not in {generated_path.name} "
                               f"(add <!-- src: ... --> if it comes from elsewhere): {line.strip()[:80]}")
    return orphans


def run(root: Path = ROOT) -> list[str]:
    errors = []
    for analysis, sweep in _PAIRS.items():
        errors += check_pair(root / "docs" / "audits" / analysis,
                             root / "docs" / "audits" / f"sweep_{sweep}_generated.md")
    return errors


def main() -> int:
    errors = run()
    if errors:
        print("check_analysis_numbers: FAIL — analysis numbers with no machine source:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_analysis_numbers: OK — every analysis number has a generated-report source or a marker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
