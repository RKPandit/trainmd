"""Precondition for building cases (author's decision 2026-09-28): a workload's cases may be built only if the
CI `reference-change-guard` — which rebuilds every case when a committed reference or data pin changes — actually
watches THAT workload's committed reference files. Otherwise a later reference change would leave its cases
silently stale (judged against a band they were not built against).

The check reads the guard's own detection pattern out of `.github/workflows/ci.yml` (the `grep -qE "…"` in the
`refchg` step), so it can never drift from what CI does. A workload whose `reference/` is a symlink to another's
(tabular_adult_neutral → tabular_adult) is checked at the real path.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

_GREP = re.compile(r'grep -qE "([^"]+)"')
REPO_ROOT = Path(__file__).resolve().parent.parent      # the CI workflow is a property of the code repository


def guard_pattern(ci_root: Path = REPO_ROOT) -> re.Pattern:
    wf = yaml.safe_load((Path(ci_root) / ".github" / "workflows" / "ci.yml").read_text())
    steps = wf["jobs"]["reference-change-guard"]["steps"]
    run = next(s["run"] for s in steps if s.get("id") == "refchg")
    m = _GREP.search(run)
    if not m:
        raise RuntimeError("reference-change-guard: no `grep -qE \"…\"` detection pattern in the refchg step")
    return re.compile(m.group(1))


def unguarded_files(project_root: Path, workload_name: str, ci_root: Path = REPO_ROOT) -> list[str]:
    """Committed reference files of ``workload_name`` the guard does NOT watch (empty = guarded)."""
    root = Path(project_root).resolve()
    ref = Path(os.path.realpath(root / "workloads" / workload_name / "reference"))
    pat = guard_pattern(ci_root)
    rel = [str((ref / f).relative_to(root)) for f in ("stats.yaml", "data_manifest.yaml")]
    return [r for r in rel if not pat.search(r)]


def require_reference_guard(project_root: Path, workload_name: str, ci_root: Path = REPO_ROOT) -> None:
    missing = unguarded_files(project_root, workload_name, ci_root)
    if missing:
        raise SystemExit(
            f"FATAL: refusing to build {workload_name} cases — the CI reference-change-guard does not watch "
            f"{missing}. A later change to that reference would leave the cases stale. Extend the guard's detection "
            "pattern in .github/workflows/ci.yml (and its rebuild step) first (DECISIONS 2026-09-28).")
