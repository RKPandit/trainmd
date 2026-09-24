"""Release archive policy guard: 10 MB file limit + only the three committed releases (both directions)."""
from pathlib import Path

from scripts import check_release_files as c

ROOT = Path(__file__).resolve().parent.parent


def _root(tmp: Path) -> Path:
    for name in ("sweep1", "stage2gate", "h8_xprovider"):
        (tmp / "results_release" / name).mkdir(parents=True)
        (tmp / "results_release" / name / "index.csv").write_text("x\n")
    return tmp


def test_clean_tree_passes(tmp_path):
    assert c.check(_root(tmp_path)) == []


def test_file_over_10mb_fails(tmp_path):
    root = _root(tmp_path)
    big = root / "results_release" / "h8_xprovider" / "big.bin"
    with open(big, "wb") as fh:
        fh.truncate(10 * 1024 * 1024 + 1)
    probs = c.check(root)
    assert len(probs) == 1 and "big.bin" in probs[0] and "10 MB" in probs[0]


def test_new_release_dir_fails(tmp_path):
    root = _root(tmp_path)
    (root / "results_release" / "part1").mkdir()
    probs = c.check(root)
    assert len(probs) == 1 and "results_release/part1" in probs[0]


def test_repository_passes():
    assert c.check(ROOT) == []


def test_new_release_dirs_are_gitignored():
    rules = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]
    assert "/results_release/*" in rules
    for name in c.COMMITTED_RELEASES:
        assert f"!/results_release/{name}/" in rules
