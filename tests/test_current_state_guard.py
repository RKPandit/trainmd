"""Tests for scripts/check_current_state.py — the CURRENT_STATE.md consistency guard.

The real repo must pass; a planted stale count or a planted forbidden phrase must fail with the
offending field named.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "check_current_state", ROOT / "scripts" / "check_current_state.py"
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------- #
# Happy path: the committed repo is self-consistent
# --------------------------------------------------------------------------- #

def test_real_repo_facts_consistent():
    assert guard.check_facts(guard.load_declared(), ROOT) == []


def test_real_repo_no_language_drift():
    assert guard.check_language(guard._live_docs(ROOT), ROOT) == []


def test_main_passes_on_real_repo():
    assert guard.main() == 0


# --------------------------------------------------------------------------- #
# Planted stale facts fail, naming the field
# --------------------------------------------------------------------------- #

def test_planted_stale_case_count_fails():
    declared = guard.load_declared()
    declared["case_count"] = 27  # stale (design has 33)
    errors = guard.check_facts(declared, ROOT)
    assert any("case_count" in e for e in errors), errors


def test_case_count_does_not_require_built_registry():
    """Guard A regression: the case_count check derives the expected count from the DESIGN
    (operators/registry.py), so it must not require the generated, gitignored
    cases/registry.hidden.yaml — this guard runs in a fresh CI clone BEFORE cases are built.
    Previously it read the file unconditionally and crashed with FileNotFoundError."""
    reg = ROOT / "cases" / "registry.hidden.yaml"
    backup = reg.read_bytes() if reg.is_file() else None
    try:
        if reg.is_file():
            reg.unlink()
        errors = guard.check_facts(guard.load_declared(), ROOT)
        assert not any("case_count" in e for e in errors), errors
    finally:
        if backup is not None:
            reg.parent.mkdir(parents=True, exist_ok=True)
            reg.write_bytes(backup)


def test_planted_corrections_mismatch_fails():
    declared = guard.load_declared()
    declared["corrections_count"] = 3  # FINDINGS/LIMITATIONS say 4
    errors = guard.check_facts(declared, ROOT)
    assert any("corrections_count" in e for e in errors), errors


def test_planted_operator_drift_fails():
    declared = guard.load_declared()
    declared["operators"] = declared["operators"][:-1]  # drop one
    declared["operators_count"] = len(declared["operators"])
    errors = guard.check_facts(declared, ROOT)
    assert any("operators" in e for e in errors), errors


def test_planted_bad_image_digest_fails():
    declared = guard.load_declared()
    declared["canonical_image_digest"] = "sha256:deadbeef"
    errors = guard.check_facts(declared, ROOT)
    assert any("image_digest" in e for e in errors), errors


# --------------------------------------------------------------------------- #
# Language drift: assertions flagged; historical / quoted mentions spared
# --------------------------------------------------------------------------- #

def test_planted_forbidden_phrase_flagged(tmp_path):
    f = tmp_path / "somedoc.md"
    f.write_text(
        "The benchmark currently has 27 cases.\n"       # bare present-tense -> flag
        "H1 confirmed for the leakage operator.\n"       # -> flag
    )
    errors = guard.check_language([f], tmp_path)
    assert any("27/28 cases" in e for e in errors), errors
    assert any("H1 confirmed" in e for e in errors), errors


def test_historical_and_quoted_mentions_are_spared(tmp_path):
    f = tmp_path / "record.md"
    f.write_text(
        "Sweep 1 ran on 27 cases.\n"                     # historical cue -> spared
        'Fix the "27 cases" comment to be registry-driven.\n'  # quoted -> spared
        "H1 confirmed was later refuted by the Stage-2 gate.\n"  # 'refut'/'was' -> spared
    )
    assert guard.check_language([f], tmp_path) == []
