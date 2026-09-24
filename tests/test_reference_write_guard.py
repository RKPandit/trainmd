"""Reference generation refuses to write through a symlink (DECISIONS 2026-09-23)."""
from pathlib import Path

import pytest

from harness.reference_run import refuse_symlinked_reference

ROOT = Path(__file__).resolve().parent.parent


def test_real_directory_is_allowed(tmp_path):
    (tmp_path / "wl" / "reference").mkdir(parents=True)
    refuse_symlinked_reference(tmp_path / "wl" / "reference")          # no exception


def test_symlinked_reference_is_refused(tmp_path):
    (tmp_path / "a" / "reference").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "reference").symlink_to(tmp_path / "a" / "reference")
    with pytest.raises(SystemExit, match="through a symlink"):
        refuse_symlinked_reference(tmp_path / "b" / "reference")


def test_symlinked_parent_is_refused(tmp_path):
    (tmp_path / "real_wl" / "reference").mkdir(parents=True)
    (tmp_path / "linked_wl").symlink_to(tmp_path / "real_wl")
    with pytest.raises(SystemExit):
        refuse_symlinked_reference(tmp_path / "linked_wl" / "reference")


def test_the_neutral_workload_reference_is_refused():
    neutral = ROOT / "workloads" / "tabular_adult_neutral" / "reference"
    if not neutral.is_symlink():
        pytest.skip("neutral reference is not a symlink in this checkout")
    with pytest.raises(SystemExit):
        refuse_symlinked_reference(neutral)


def test_session_guard_detects_a_modified_reference(tmp_path, monkeypatch):
    import conftest
    wl = tmp_path / "workloads" / "wl" / "reference"
    wl.mkdir(parents=True)
    (wl / "stats.yaml").write_text("a: 1\n")
    monkeypatch.setattr(conftest, "_REPO", tmp_path)
    snap = conftest._reference_hashes()
    monkeypatch.setattr(conftest, "_REFERENCE_SNAPSHOT", dict(snap))
    assert conftest.changed_reference_files() == []
    (wl / "stats.yaml").write_text("a: 2\n")
    assert conftest.changed_reference_files() == ["workloads/wl/reference/stats.yaml"]


def test_conftest_defines_each_hook_once():
    """Two pytest_sessionfinish defs in one conftest: the second silently replaces the first (this
    nearly disabled the reference guard when #41's skip guard and #43 landed together)."""
    import re
    names = re.findall(r"^def (pytest_\w+)\(", (ROOT / "tests" / "conftest.py").read_text(), re.M)
    assert len(names) == len(set(names)), sorted(n for n in names if names.count(n) > 1)
