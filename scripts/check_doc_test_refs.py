#!/usr/bin/env python3
"""CI guard: every TEST named in LIMITATIONS / FINDINGS must exist.

LIMITATIONS L29 and FINDINGS F15 described a submit-crash fix as landed that had never been built
(DECISIONS 2026-09-23). The rule since then: a doc that claims a fix landed names the test that proves
it — and this check makes the name load-bearing. It scans the docs for test references

    tests/test_x.py            test_x.py            tests/test_x.py::test_name    ...::Class::test_name

and fails if a referenced file is missing, or a referenced class / function (``::`` parts; a
parametrize id ``[...]`` is ignored) is not defined in that file.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("docs/LIMITATIONS.md", "docs/FINDINGS.md")
REF = re.compile(r"(?<![\w/])(?:tests/)?(test_[A-Za-z0-9_]+\.py)((?:::[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\s`]*\])?)*)")


def _defined(path: Path) -> set[tuple[str, ...]]:
    """Every (name,) and (Class, name) defined at module / class level."""
    tree = ast.parse(path.read_text())
    out: set[tuple[str, ...]] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add((node.name,))
        elif isinstance(node, ast.ClassDef):
            out.add((node.name,))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add((node.name, sub.name))
    return out


def check(root: Path) -> list[str]:
    problems = []
    for doc in DOCS:
        p = root / doc
        if not p.exists():
            continue
        for line_no, line in enumerate(p.read_text().splitlines(), 1):
            for fname, parts in REF.findall(line):
                test_file = root / "tests" / fname
                where = f"{doc}:{line_no}"
                if not test_file.exists():
                    problems.append(f"{where}: names tests/{fname}, which does not exist")
                    continue
                names = tuple(re.sub(r"\[.*\]$", "", x) for x in parts.split("::") if x)
                if names and names not in _defined(test_file):
                    problems.append(f"{where}: names tests/{fname}::{'::'.join(names)}, "
                                    "which is not defined in that file")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    problems = check(a.project_root)
    if problems:
        print("check_doc_test_refs: FAIL —\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"check_doc_test_refs: OK — every test named in {', '.join(DOCS)} exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
