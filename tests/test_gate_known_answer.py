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


def _leakage_case() -> str:
    """A real built data-leakage case, selected BY OPERATOR (was hard-coded case_0004)."""
    from tests._real_cases import real_case
    c = real_case(operator_id="silent.data_leakage.v1")
    if c is None:
        pytest.skip("no data-leakage case built (runs in build-and-certify)")
    return c.name


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
    _setup(tmp_path, _leakage_case())
    rows = run_gate(tmp_path, fast=True)
    assert [r for r in rows if r.status == "FAIL"] == []


# NOTE (DECISIONS 2026-09-20): the two planted-violation tests below were rewritten.
# The originals copied a HARDCODED case number (case_0004/case_0005) and skipped when
# cases/ was empty — so they SILENTLY SKIPPED in the fast lane (never ran) and, when
# they did run, mis-targeted (case_0005 was not a control). They now select the case
# type BY OPERATOR and use the exact functions the gate relies on — fast, no training,
# never skip. Triage also found the gate's oracle EVIDENCE check is tautological (oracle
# refs + primary scorer both operator-derived; evidence.yaml only a fallback), so
# evidence.yaml drift is invisible to it — closed by the validator's C13.
import dataclasses  # noqa: E402

from harness.validate_case import _check_c13_evidence_matches_operator  # noqa: E402
from harness.scoring import score_identification  # noqa: E402


def test_evidence_yaml_drift_caught_by_validator(tmp_path):
    """The gate's evidence check can't see evidence.yaml drift (tautological), so the
    VALIDATOR's C13 must: evidence.yaml MUST equal the operator's evidence()."""
    from operators.registry import get_operator
    op = get_operator("silent.data_leakage.v1")
    hidden = tmp_path / "case_x" / "hidden"
    hidden.mkdir(parents=True)
    refs = [dataclasses.asdict(e) for e in op.evidence()]
    hc = {"operator_id": "silent.data_leakage.v1"}
    (hidden / "evidence.yaml").write_text(yaml.dump(refs))
    assert _check_c13_evidence_matches_operator(tmp_path / "case_x", hc).passed  # clean
    (hidden / "evidence.yaml").write_text(yaml.dump(refs[:-1]))                  # drop a ref
    r = _check_c13_evidence_matches_operator(tmp_path / "case_x", hc)
    assert not r.passed and "drifted" in r.detail                               # caught


def test_gate_identification_detects_corrupted_accepted_classes():
    """The gate's oracle identification: a corrupted accepted_classes answer key must
    make the oracle's correct class no longer accepted. By operator; the corruption is
    a GENUINELY cross-fault label (data_leakage's tokens are {'leak'} only, so
    'learning_rate' is truly wrong — not a synonym)."""
    from operators.registry import get_operator
    op = get_operator("silent.data_leakage.v1")
    oracle_class = sorted(op.accepted_classes())[0]     # what the gate's oracle submits
    clean_hc = {"operator_id": "silent.data_leakage.v1",
                "accepted_classes": sorted(op.accepted_classes()),
                "core_tokens": [sorted(s) for s in op.core_tokens()], "layer": "dynamics"}
    assert score_identification(
        {"diagnosis": {"detected": True, "operator_class": oracle_class}}, clean_hc)["correct"]
    bad_hc = {**clean_hc, "accepted_classes": ["learning_rate"]}  # corrupted answer key
    assert not score_identification(
        {"diagnosis": {"detected": True, "operator_class": oracle_class}}, bad_hc)["correct"]


def test_corrupt_oracle_repair_is_caught(tmp_path):
    """Planted: an inadmissible oracle_repair → oracle recovery FAILs (full mode).

    verify_repair rejects the inadmissible repair before any training, so this
    stays fast."""
    name = _leakage_case()
    case_dir = _setup(tmp_path, name)
    v_path = case_dir / "hidden" / "verify.yaml"
    v = yaml.safe_load(v_path.read_text())
    # batch_size is not an allowed repair key for data_leakage.
    v["oracle_repair"] = {"repair_type": "config_patch", "patches": {"training.batch_size": 999}}
    v_path.write_text(yaml.dump(v))

    rows = run_gate(tmp_path, fast=False)
    assert _fails(rows, name, "recovery"), "gate did not flag the corrupt oracle_repair"
