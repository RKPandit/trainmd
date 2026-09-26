"""Provenance of the RUNNING PROCESS (harness/process_provenance.py; DECISIONS 2026-09-26): the start
commit is frozen at sweep start, the loaded-source hash does not follow later edits on disk, and the
dirty flag counts only tracked changes.
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness import process_provenance as pp

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git (not in the canonical container)")


def _git(root: Path, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "HOME": str(root)})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    pkg = root / "harness"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (root / ".gitignore").write_text("ignored.txt\n")
    (root / "tracked.txt").write_text("v1\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "c1")
    pp._reset_for_tests()
    yield root
    pp._reset_for_tests()


def _head(root):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()


@needs_git
def test_dirty_counts_only_tracked_changes(repo):
    (repo / "untracked.txt").write_text("x")
    (repo / "ignored.txt").write_text("x")
    assert pp.git_dirty(repo) is False                      # untracked + ignored never count
    (repo / "tracked.txt").write_text("v2\n")
    assert pp.git_dirty(repo) is True


@needs_git
def test_start_commit_is_frozen_for_the_process(repo):
    first = _head(repo)
    s1 = pp.start(repo)
    (repo / "tracked.txt").write_text("v2\n")
    _git(repo, "commit", "-qam", "c2")                       # the folder moves on mid-run
    assert _head(repo) != first
    snap = pp.snapshot(repo)
    assert snap["start_commit"] == s1["start_commit"] == first
    assert snap["start_dirty"] is False and snap["pid"] == s1["pid"]


def test_loaded_source_hash_ignores_later_edits_but_sees_new_imports(tmp_path, monkeypatch):
    # No git needed. A throwaway module inside a package named like the project's, under the root.
    repo = tmp_path
    pp._reset_for_tests()
    pkg = repo / "agents"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod_a.py").write_text("X = 1\n")
    (pkg / "mod_b.py").write_text("Y = 1\n")
    monkeypatch.syspath_prepend(str(repo))
    for m in ("agents", "agents.mod_a", "agents.mod_b"):
        sys.modules.pop(m, None)
    try:
        importlib.import_module("agents.mod_a")
        h0, n0 = pp.loaded_source_hash(repo)
        (pkg / "mod_a.py").write_text("X = 2  # edited on disk after load\n")
        assert pp.loaded_source_hash(repo) == (h0, n0)        # already-loaded code: hash unchanged
        importlib.import_module("agents.mod_b")                # a lazy import mid-run
        h1, n1 = pp.loaded_source_hash(repo)
        assert n1 == n0 + 1 and h1 != h0
    finally:
        for m in ("agents", "agents.mod_a", "agents.mod_b"):
            sys.modules.pop(m, None)
        pp._reset_for_tests()


def test_without_git_the_process_block_says_unknown_not_a_guess(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))                  # no git on PATH
    pp._reset_for_tests()
    try:
        s = pp.start(tmp_path)
        assert s["start_commit"] == "unknown" and s["start_dirty"] is False
    finally:
        pp._reset_for_tests()


@needs_git
def test_trial_environment_carries_the_process_block(repo, tmp_path):
    from harness.provenance import capture_environment
    case = tmp_path / "case"
    case.mkdir()
    env = capture_environment(repo, case)
    assert {"start_commit", "start_dirty", "start_utc", "pid", "loaded_source_hash",
            "start_loaded_source_hash"} <= set(env["process"])
    assert env["process"]["start_commit"] == _head(repo) and env["git_dirty"] is False
