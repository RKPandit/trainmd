"""Provenance of the RUNNING PROCESS, not the checkout (DECISIONS 2026-09-26).

Per-trial ``git rev-parse HEAD`` tracks the working directory: if the checkout a sweep runs from changes
branch mid-run, later trials record a commit whose code the running process never loaded (the Stage 4
Part 1 agents phase recorded four commits this way — all audited as harmless). This module records what
the process actually runs:

* ``start_commit`` / ``start_dirty`` — HEAD and the tracked-file dirty state ONCE, at the first call in
  the process (the sweep start), frozen for the life of the process;
* ``loaded_source_hash`` — a hash over every project source module the process has loaded (``harness``,
  ``agents``, ``operators``), each file hashed the FIRST time it is seen in ``sys.modules`` and never
  re-read, so a later edit on disk cannot change it. A module imported lazily mid-run is hashed when it
  first appears.

``git_dirty`` everywhere counts only TRACKED changes (``--untracked-files=no``; ignored files are never
listed), so it means "the committed code was modified" again.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGES = ("harness", "agents", "operators")

_START: dict | None = None
_SEEN: dict[str, tuple[str, str]] = {}      # module name -> (relative path, sha256 at first sight)


def git_head(root: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=root)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except FileNotFoundError:
        return "unknown"


def git_dirty(root: Path) -> bool:
    """True iff a TRACKED file differs from HEAD (untracked and gitignored files never count)."""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, cwd=root)
        return bool(r.stdout.strip()) if r.returncode == 0 else False
    except FileNotFoundError:
        return False


def _observe(root: Path) -> None:
    """Hash any project module not seen before (first sight only)."""
    root = Path(root).resolve()
    for name, mod in list(sys.modules.items()):
        if name in _SEEN or name.split(".")[0] not in PACKAGES:
            continue
        f = getattr(mod, "__file__", None)
        if not f or not f.endswith(".py"):
            continue
        p = Path(f).resolve()
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            continue                              # same package name, but not this project's file
        try:
            _SEEN[name] = (rel, hashlib.sha256(p.read_bytes()).hexdigest())
        except OSError:
            continue


def loaded_source_hash(root: Path) -> tuple[str, int]:
    _observe(root)
    items = sorted(_SEEN.values())
    h = hashlib.sha256("\n".join(f"{rel} {sha}" for rel, sha in items).encode()).hexdigest()
    return h, len(items)


def start(root: Path) -> dict:
    """Freeze the process's start provenance (idempotent: the FIRST call wins)."""
    global _START
    if _START is None:
        h, n = loaded_source_hash(root)
        _START = {"start_commit": git_head(root), "start_dirty": git_dirty(root),
                  "start_utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
                  "start_loaded_source_hash": h, "start_loaded_modules": n}
    return dict(_START)


def snapshot(root: Path) -> dict:
    """The per-trial ``process`` block: the frozen start provenance + the loaded-source hash now
    (it differs from the start hash only if a module was imported lazily since)."""
    s = start(root)
    h, n = loaded_source_hash(root)
    return {**s, "loaded_source_hash": h, "loaded_modules": n}


def _reset_for_tests() -> None:
    global _START
    _START = None
    _SEEN.clear()
