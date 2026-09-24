#!/usr/bin/env python3
"""CI guard for the release ARCHIVE policy (DECISIONS 2026-09-23).

1. No file under results_release/ may exceed 10 MB (large artifacts belong in the paper-time archive).
2. Only the three releases committed before the policy may exist in the repository:
   sweep1, stage2gate, h8_xprovider. New sweep releases (Stage 4 onward) are exported locally and NOT
   committed (.gitignore ignores results_release/* except these three); verify one locally with
   `make verify-release NAME=<sweep>`.

Run on a CI checkout (which holds only tracked files); locally, git-ignored release dirs are skipped.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 10 * 1024 * 1024
COMMITTED_RELEASES = {"sweep1", "stage2gate", "h8_xprovider"}


def _ignored(root: Path, path: Path) -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", str(path.relative_to(root))], cwd=root).returncode == 0
    except FileNotFoundError:          # no git (container): a CI checkout holds only tracked files
        return False


def check(root: Path) -> list[str]:
    rel = root / "results_release"
    problems = []
    if not rel.is_dir():
        return problems
    for d in sorted(p for p in rel.iterdir()):
        if d.name not in COMMITTED_RELEASES and not _ignored(root, d):
            problems.append(f"results_release/{d.name}: not one of the committed releases "
                            f"{sorted(COMMITTED_RELEASES)} — new releases are exported locally, never committed")
    for f in sorted(rel.rglob("*")):
        if f.is_file() and f.stat().st_size > MAX_BYTES and not _ignored(root, f):
            problems.append(f"{f.relative_to(root)}: {f.stat().st_size / 1e6:.1f} MB > 10 MB limit")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    problems = check(a.project_root)
    if problems:
        print("check_release_files: FAIL —\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"check_release_files: OK — only {sorted(COMMITTED_RELEASES)} under results_release/, no file > 10 MB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
