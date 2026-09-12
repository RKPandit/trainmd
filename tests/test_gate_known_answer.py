"""Planted-violation tests for the known-answer gate (spec §7, §8).

Prove the gate is non-hollow: each corruption of ground truth is caught and
NAMED in the table (the right case + axis goes FAIL), and a clean case yields
no FAIL.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from harness.gate_known_answer import run_gate

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "cases"
WL = REPO / "workloads" / "tabular_adult"


def _setup(tmp: Path, case_name: str) -> Path:
    """Copy one real case into a tmp project root + symlink the workload."""
    src = CASES / case_name
    if not src.exists():
        pytest.skip(f"{case_name} not built")
    dst_cases = tmp / "cases"
    dst_cases.mkdir(parents=True)
    shutil.copytree(src, dst_cases / case_name)
    # Symlink the workload (needed only for full-mode recovery integrity read).
    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for f in ["train.py", "config.yaml", "datautil.py"]:
        (wl / f).symlink_to((WL / f).resolve())
    (wl / "reference").mkdir()
    (wl / "reference" / "stats.yaml").symlink_to((WL / "reference" / "stats.yaml").resolve())
    for d in [".data", ".hidden_data"]:
        if (WL / d).exists():
            (wl / d).symlink_to((WL / d).resolve())
    return dst_cases / case_name


def _fails(rows, case, axis):
    return [r for r in rows if r.case == case and r.axis == axis and r.status == "FAIL"]


def test_clean_case_yields_no_fail(tmp_path):
    _setup(tmp_path, "case_0004")
    rows = run_gate(tmp_path, fast=True)
    assert [r for r in rows if r.status == "FAIL"] == []


def test_dropped_evidence_ref_is_caught(tmp_path):
    """Planted: drop a hidden evidence ref → oracle evidence_f1 goes FAIL."""
    case_dir = _setup(tmp_path, "case_0004")
    ev_path = case_dir / "hidden" / "evidence.yaml"
    ev = yaml.safe_load(ev_path.read_text())
    ev_path.write_text(yaml.dump(ev[:-1]))  # drop the last ref

    rows = run_gate(tmp_path, fast=True)
    assert _fails(rows, "case_0004", "evidence_f1"), "gate did not flag the dropped ref"


def test_control_missing_accepted_classes_is_caught(tmp_path):
    """Planted: a control with empty accepted_classes → oracle identification FAILs."""
    case_dir = _setup(tmp_path, "case_0005")
    hc_path = case_dir / "hidden" / "card.hidden.yaml"
    hc = yaml.safe_load(hc_path.read_text())
    hc["accepted_classes"] = []
    hc_path.write_text(yaml.dump(hc))

    rows = run_gate(tmp_path, fast=True)
    assert _fails(rows, "case_0005", "identification"), "gate did not flag broken accepted_classes"


def test_corrupt_oracle_repair_is_caught(tmp_path):
    """Planted: an inadmissible oracle_repair → oracle recovery FAILs (full mode).

    verify_repair rejects the inadmissible repair before any training, so this
    stays fast."""
    case_dir = _setup(tmp_path, "case_0004")
    v_path = case_dir / "hidden" / "verify.yaml"
    v = yaml.safe_load(v_path.read_text())
    # batch_size is not an allowed repair key for data_leakage.
    v["oracle_repair"] = {"repair_type": "config_patch", "patches": {"training.batch_size": 999}}
    v_path.write_text(yaml.dump(v))

    rows = run_gate(tmp_path, fast=False)
    assert _fails(rows, "case_0004", "recovery"), "gate did not flag the corrupt oracle_repair"
