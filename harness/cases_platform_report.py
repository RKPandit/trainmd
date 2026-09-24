"""Aggregate canonical-platform report over locally-built cases (evaluator-side).

INTEGRITY (CLAUDE.md rule #1): ``cases/*/hidden/`` is read ONLY by the evaluator.
This module is that reader; `make doctor` invokes it INSIDE the canonical container
(the evaluator container), never from the host shell. To keep the surface as narrow
as the question ("are my local cases canonical?"), it emits ONLY an aggregate — how
many cases are canonical vs non-canonical, and the distinct CPU vendor_id strings
found. It never prints a per-case row or any other hidden-card field.

A case is canonical iff its ``build_cpu`` provenance (stamped at build time,
harness/build_case.py) names a native-amd64 vendor_id — the same vendors the
platform guard accepts (harness/platform_guard.py). Emulated builds (Rosetta's
``VirtualApple``, qemu) are non-canonical.

Output: one JSON object on stdout, e.g.
    {"total": 152, "canonical": 152, "non_canonical": 0, "vendors": ["GenuineIntel"]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from harness.platform_guard import _NATIVE_VENDORS


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _vendor_of(build_cpu: str) -> str:
    """The vendor_id token — the first whitespace-delimited field of build_cpu
    (cpu_provenance formats it as ``"<vendor_id> <model name>"``)."""
    build_cpu = (build_cpu or "").strip()
    return build_cpu.split(None, 1)[0] if build_cpu else "?"


def report(project_root: Path | None = None) -> dict:
    root = project_root or _repo_root()
    cases_dir = root / "cases"
    total = canonical = non_canonical = 0
    vendors: set[str] = set()

    for card in sorted(cases_dir.glob("case_*/hidden/card.hidden.yaml")):
        with open(card) as f:
            data = yaml.safe_load(f) or {}
        build_cpu = data.get("build_cpu", "")
        vendor = _vendor_of(build_cpu)
        total += 1
        vendors.add(vendor)
        if vendor in _NATIVE_VENDORS:
            canonical += 1
        else:
            non_canonical += 1

    return {
        "total": total,
        "canonical": canonical,
        "non_canonical": non_canonical,
        "vendors": sorted(vendors),
    }


def main() -> int:
    print(json.dumps(report()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
