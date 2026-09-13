"""Unset-repair oracle-equivalence (post-hoc correction, item 2 / amendment 4).

For every absent-when-clean key, unsetting it (null → delete the injected key)
must recover IDENTICALLY on the hidden seeds to patching the reference value,
because deleting the key lets the workload derive its clean default:

    unset model.input_dim          ≡ model.input_dim = 105
    unset data.include_aux_feature ≡ data.include_aux_feature = False
    unset data.label_noise_fraction ≡ data.label_noise_fraction = 0.0

These are full integration tests (build a case, run verify on 3 hidden seeds
twice per operator), so they are CPU-heavy but bounded (<10 min, spec §CLAUDE).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.evaluator.verify_repair import verify_repair

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"

# operator_id → (absent-when-clean key, reference value equivalent to unset)
_CASES = {
    "crash.shape_mismatch.v1": ("model.input_dim", 105),
    "silent.data_leakage.v1": ("data.include_aux_feature", False),
    "silent.label_corruption.v1": ("data.label_noise_fraction", 0.0),
}


def _mirror_workload(tmp: Path) -> Path:
    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)
    ref = wl / "reference"
    ref.mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", ref / "stats.yaml")
    (wl / ".data").symlink_to((WORKLOAD_DIR / ".data").resolve())
    (wl / ".hidden_data").symlink_to((WORKLOAD_DIR / ".hidden_data").resolve())
    return wl


@pytest.fixture(scope="module", params=sorted(_CASES))
def built_case(request, tmp_path_factory):
    if not (WORKLOAD_DIR / ".data").exists() or not (WORKLOAD_DIR / ".hidden_data").exists():
        pytest.skip("Data not prepared; run `make data` first.")

    operator_id = request.param
    tmp = tmp_path_factory.mktemp("unset_" + operator_id.split(".")[1])
    _mirror_workload(tmp)

    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id=operator_id,
        strength="moderate",
        seed=42,
        project_root=tmp,
    )
    return operator_id, case_dir, tmp


def _metrics(result):
    return [r["metric_hidden_test_acc"] for r in result["per_seed_hidden_metrics"]]


def test_unset_recovers_like_reference_value(built_case):
    """unset (null) recovers, and per-seed metrics match the reference-value repair."""
    operator_id, case_dir, project_root = built_case
    key, ref_value = _CASES[operator_id]

    value_repair = {"repair_type": "config_patch", "patches": {key: ref_value}}
    unset_repair = {"repair_type": "config_patch", "patches": {key: None}}

    value_result = verify_repair(case_dir, value_repair, project_root)
    unset_result = verify_repair(case_dir, unset_repair, project_root)

    # Both recover.
    assert value_result["verdict"] == "recovered", operator_id
    assert unset_result["verdict"] == "recovered", operator_id

    # Identical per-seed hidden metrics (deterministic training).
    assert _metrics(unset_result) == _metrics(value_result), operator_id
