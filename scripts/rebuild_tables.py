#!/usr/bin/env python3
"""Rebuild a sweep's generated report FROM THE RELEASE ONLY (STAGE3_PLAN §0.3-B7).

The external-reviewer path: recompute every table in `docs/audits/sweep_<name>_generated.md` from
`results_release/<name>/` alone and assert a byte-match with the committed report. It must run from a
clean checkout with NO `cases/`, NO `results/`, and NO importable registry — the analysis reads
tier/symptom/σ from the release's per-case metadata. If any analysis path reached back into the
registry to resolve an operator's tier, this would fail (that coupling is what makes external
verification impossible).
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def rebuild(release_dir: Path, name: str, expected_path: Path | None) -> tuple[int, str]:
    from harness import report_gen  # imports only sweep_stats + anchors — NO registry
    md = report_gen.generate_from_release(release_dir, name)
    if expected_path is not None:
        expected = Path(expected_path).read_text()
        if md != expected:
            diff = "".join(difflib.unified_diff(
                expected.splitlines(keepends=True), md.splitlines(keepends=True),
                fromfile="committed", tofile="rebuilt-from-release"))
            return 1, diff
    return 0, md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", required=True)
    ap.add_argument("--release-dir", type=Path, default=None,
                    help="default: <project-root>/results_release/<sweep>")
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--expect", type=Path, default=None,
                    help="committed generated report to assert byte-match (default: "
                         "docs/audits/sweep_<sweep>_generated.md under project-root)")
    a = ap.parse_args()
    release_dir = a.release_dir or (a.project_root / "results_release" / a.sweep)
    expect = a.expect if a.expect is not None else (a.project_root / "docs" / "audits" / f"sweep_{a.sweep}_generated.md")
    if not expect.exists():
        expect = None  # no committed report to check against; just print
    code, out = rebuild(release_dir, a.sweep, expect)
    if code == 0:
        print(f"rebuild_tables: OK — {a.sweep} report reproduces from the release alone.")
    else:
        print(f"rebuild_tables: MISMATCH — {a.sweep} rebuilt-from-release != committed report:\n", file=sys.stderr)
        print(out, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
