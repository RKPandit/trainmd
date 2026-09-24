"""check_doc_test_refs: a test named in LIMITATIONS / FINDINGS must exist (both directions)."""
from __future__ import annotations

from pathlib import Path

from scripts import check_doc_test_refs as c

ROOT = Path(__file__).resolve().parent.parent


def _repo(tmp: Path, doc_text: str) -> Path:
    (tmp / "docs").mkdir()
    (tmp / "tests").mkdir()
    (tmp / "tests" / "test_real.py").write_text(
        "def test_a():\n    pass\n\nclass TestK:\n    def test_b(self):\n        pass\n")
    (tmp / "docs" / "LIMITATIONS.md").write_text(doc_text)
    return tmp


def test_existing_references_pass(tmp_path):
    root = _repo(tmp_path, "Fixed; proven by `tests/test_real.py`, `tests/test_real.py::test_a`, "
                           "`test_real.py::TestK::test_b` and `tests/test_real.py::test_a[x-1]`.\n")
    assert c.check(root) == []


def test_missing_file_fails(tmp_path):
    root = _repo(tmp_path, "The fix landed (`tests/test_ghost.py`).\n")
    assert c.check(root) == ["docs/LIMITATIONS.md:1: names tests/test_ghost.py, which does not exist"]


def test_missing_function_fails(tmp_path):
    root = _repo(tmp_path, "See `tests/test_real.py::test_nope` and `tests/test_real.py::TestK::test_a`.\n")
    probs = c.check(root)
    assert len(probs) == 2 and "test_nope" in probs[0] and "TestK::test_a" in probs[1]


def test_repository_docs_pass():
    assert c.check(ROOT) == []
