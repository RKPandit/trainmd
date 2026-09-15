"""Tests for the reproducibility guards (STAGE3_PLAN §0.3-C): manifest/plan schema + numbers-provenance.

The real repo passes both; a planted malformed manifest and a planted invented analysis number
each fail loudly, naming the problem.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


schema = _load("check_manifest_schema")
nums = _load("check_analysis_numbers")


# --- schema -------------------------------------------------------------- #

def test_real_manifests_and_plans_validate():
    assert schema.run(ROOT) == []


def test_malformed_manifest_fails(tmp_path):
    (tmp_path / "sweeps").mkdir()
    # invalid YAML: an unquoted inline "#6"/colon prose (the exact class that slipped through once)
    (tmp_path / "sweeps" / "x_manifest.yaml").write_text(
        "sweep_name: x\nhardware:\n  note: run after PR #6: broke\n bad indent\n")
    errs = schema.run(tmp_path)
    assert any("x_manifest.yaml" in e for e in errs), errs


def test_manifest_missing_required_key_fails(tmp_path):
    (tmp_path / "sweeps").mkdir()
    (tmp_path / "sweeps" / "y_manifest.yaml").write_text("sweep_name: y\n")  # missing agent_phase etc.
    errs = schema.check_file(tmp_path / "sweeps" / "y_manifest.yaml")
    assert any("agent_phase" in e for e in errs), errs


# --- numbers provenance -------------------------------------------------- #

def test_real_analysis_numbers_have_a_source():
    assert nums.run(ROOT) == []


def test_invented_analysis_number_is_flagged(tmp_path):
    gen = tmp_path / "gen.md"
    ana = tmp_path / "ana.md"
    gen.write_text("detection 0.250 [0.083, 0.417]\n")
    ana.write_text("The effect was 0.250, and also a made-up 0.999 here.\n")
    orphans = nums.check_pair(ana, gen)
    assert any("number 0.999" in o for o in orphans)
    assert not any("number 0.250" in o for o in orphans)  # present in gen -> not flagged


def test_src_marker_exempts_a_line(tmp_path):
    gen = tmp_path / "gen.md"
    ana = tmp_path / "ana.md"
    gen.write_text("nothing numeric here\n")
    ana.write_text("cost was 12.34 dollars  <!-- src: manifest -->\n")
    assert nums.check_pair(ana, gen) == []
