"""Tests for the evaluator repair verification pipeline (spec §7).

Fast tests (TestParseRepairSpec, TestValidateRepair) exercise the schema parser
and validator without any training.  Integration tests build a real case and run
``verify_repair`` end-to-end on hidden seeds.

The empirical sweep (M2.2b) found that ALL values in the admissible range
[0.001, 0.02] recover for lr_warmup on tabular_adult, with the lowest observed
hidden_test_acc being 0.844759 (lr=0.018, seed=100) — still above tolerance
0.843535.  The not_recovered verdict path is tested by artificially elevating
tolerance_lower in verify.yaml.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from harness.evaluator.repair_spec import (
    KEY_NOT_ALLOWED,
    MALFORMED,
    REPAIR_TYPE_UNSUPPORTED,
    VALUE_OUT_OF_RANGE,
    VALUE_TYPE_INVALID,
    RepairSubmission,
    ValidationResult,
    parse_repair_spec,
    validate_repair,
)
from harness.evaluator.verify_repair import verify_repair

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ==========================================================================
# Shared verify dict (matches structure produced by build_case)
# ==========================================================================

SAMPLE_VERIFY = {
    "tolerance_lower": 0.843535,
    "hidden_eval_seeds": [100, 101, 102],
    "faulty_value": 0.78,
    "reference_metric_mean": 0.847649,
    "reference_metric_std": 0.002057,
    "admissible_repairs": {
        "repair_type": "config_patch",
        "allowed_keys": ["training.lr"],
        "value_ranges": {"training.lr": [0.001, 0.02]},
        "allowed_paths": [],
        "description": "Patch training.lr to a value in [0.001, 0.02].",
    },
}


# ==========================================================================
# Fast tests — _set_nested (mutation replay / repair-patch applier)
# ==========================================================================

class TestUnsetNested:
    """_unset_nested deletes an injected key so the workload derives its default."""

    def test_deletes_leaf(self):
        from harness.evaluator.verify_repair import _unset_nested
        d = {"model": {"input_dim": 50, "hidden": 64}}
        _unset_nested(d, "model.input_dim")
        assert d == {"model": {"hidden": 64}}

    def test_absent_leaf_is_noop(self):
        from harness.evaluator.verify_repair import _unset_nested
        d = {"model": {"hidden": 64}}
        _unset_nested(d, "model.input_dim")
        assert d == {"model": {"hidden": 64}}

    def test_absent_parent_is_noop(self):
        from harness.evaluator.verify_repair import _unset_nested
        d = {"training": {"lr": 0.01}}
        _unset_nested(d, "model.input_dim")
        assert d == {"training": {"lr": 0.01}}


class TestNullUnsetValidation:
    """null value validates ONLY on a declared absent-when-clean key."""

    _VERIFY = {
        "admissible_repairs": {
            "repair_type": "config_patch",
            "allowed_keys": ["model.input_dim"],
            "value_ranges": {"model.input_dim": [90, 120]},
        }
    }

    def test_null_on_absent_when_clean_key_valid(self):
        spec = parse_repair_spec(
            {"repair_type": "config_patch", "patches": {"model.input_dim": None}}
        )
        result = validate_repair(spec, self._VERIFY, ["model.input_dim"])
        assert result.valid is True
        assert result.reason_codes == []

    def test_null_on_normal_key_type_invalid(self):
        spec = parse_repair_spec(
            {"repair_type": "config_patch", "patches": {"model.input_dim": None}}
        )
        result = validate_repair(spec, self._VERIFY, [])  # not absent-when-clean
        assert result.valid is False
        assert VALUE_TYPE_INVALID in result.reason_codes


class TestSetNested:
    """_set_nested must create missing parent sections (absent-when-clean)."""

    def test_existing_path_overwrites(self):
        from harness.evaluator.verify_repair import _set_nested
        d = {"training": {"lr": 0.01}}
        _set_nested(d, "training.lr", 0.1)
        assert d["training"]["lr"] == 0.1

    def test_absent_parent_is_created(self):
        """Replaying data.include_aux_feature into a config with no data:.

        This is the exact regression from the absent-when-clean change:
        the clean config no longer carries a data: block, so the parent
        section must be created on replay rather than KeyError.
        """
        from harness.evaluator.verify_repair import _set_nested
        config = {"training": {"lr": 0.01}}  # no "data" key
        _set_nested(config, "data.include_aux_feature", False)
        assert config["data"]["include_aux_feature"] is False

    def test_deep_missing_chain_is_created(self):
        from harness.evaluator.verify_repair import _set_nested
        d = {}
        _set_nested(d, "a.b.c", 1)
        assert d["a"]["b"]["c"] == 1

    def test_non_dict_intermediate_is_replaced(self):
        """An empty data: that parses to None is replaced with a fresh dict."""
        from harness.evaluator.verify_repair import _set_nested
        d = {"data": None}
        _set_nested(d, "data.label_noise_fraction", 0.0)
        assert d["data"]["label_noise_fraction"] == 0.0


# ==========================================================================
# Fast tests — parse_repair_spec
# ==========================================================================

class TestParseRepairSpec:
    """Unit tests for the structural parser."""

    def test_valid_parse(self):
        raw = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
        result = parse_repair_spec(raw)
        assert isinstance(result, RepairSubmission)
        assert result.repair_type == "config_patch"
        assert result.patches == {"training.lr": 0.01}

    def test_missing_repair_type(self):
        with pytest.raises(ValueError, match="repair_type"):
            parse_repair_spec({"patches": {"training.lr": 0.01}})

    def test_missing_patches(self):
        with pytest.raises(ValueError, match="patches"):
            parse_repair_spec({"repair_type": "config_patch"})

    def test_extra_fields(self):
        with pytest.raises(ValueError, match="Unexpected"):
            parse_repair_spec({
                "repair_type": "config_patch",
                "patches": {"training.lr": 0.01},
                "extra": "nope",
            })

    def test_empty_patches(self):
        with pytest.raises(ValueError, match="empty"):
            parse_repair_spec({"repair_type": "config_patch", "patches": {}})

    def test_non_dict_input(self):
        with pytest.raises(ValueError, match="dict"):
            parse_repair_spec("not a dict")

    def test_non_dict_patches(self):
        with pytest.raises(ValueError, match="dict"):
            parse_repair_spec({"repair_type": "config_patch", "patches": [1, 2]})

    def test_non_string_patch_key(self):
        with pytest.raises(ValueError, match="string"):
            parse_repair_spec({"repair_type": "config_patch", "patches": {123: 0.01}})

    def test_non_string_repair_type(self):
        with pytest.raises(ValueError, match="string"):
            parse_repair_spec({"repair_type": 42, "patches": {"training.lr": 0.01}})


# ==========================================================================
# Fast tests — validate_repair
# ==========================================================================

class TestValidateRepair:
    """Unit tests for the semantic validator."""

    def test_valid_repair(self):
        spec = RepairSubmission(repair_type="config_patch", patches={"training.lr": 0.01})
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is True
        assert result.reason_codes == []

    def test_key_not_allowed(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.batch_size": 128},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert KEY_NOT_ALLOWED in result.reason_codes

    def test_value_out_of_range_above(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": 0.05},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes

    def test_value_out_of_range_below(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": 0.0001},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes

    def test_boundary_lower(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": 0.001},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is True

    def test_boundary_upper(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": 0.02},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is True

    def test_value_type_invalid(self):
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": "high"},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_TYPE_INVALID in result.reason_codes

    def test_unsupported_repair_type(self):
        spec = RepairSubmission(
            repair_type="code_patch",
            patches={"training.lr": 0.01},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert REPAIR_TYPE_UNSUPPORTED in result.reason_codes

    def test_multiple_violations(self):
        """Two bad keys → two KEY_NOT_ALLOWED codes (no short-circuit)."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.batch_size": 128, "model.dropout": 0.5},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert result.reason_codes.count(KEY_NOT_ALLOWED) == 2

    def test_mixed_violations(self):
        """Bad key + out-of-range value → both codes present."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": 99.0, "training.batch_size": 128},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes
        assert KEY_NOT_ALLOWED in result.reason_codes

    def test_reject_bool_true(self):
        """bool True passes isinstance(int) but must be rejected."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": True},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_TYPE_INVALID in result.reason_codes

    def test_reject_bool_false(self):
        """bool False passes isinstance(int) but must be rejected."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": False},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_TYPE_INVALID in result.reason_codes

    def test_reject_nan(self):
        """NaN bypasses range comparisons; must be explicitly rejected."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": float("nan")},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes

    def test_reject_inf(self):
        """Positive infinity must be rejected."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": float("inf")},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes

    def test_reject_neg_inf(self):
        """Negative infinity must be rejected."""
        spec = RepairSubmission(
            repair_type="config_patch",
            patches={"training.lr": float("-inf")},
        )
        result = validate_repair(spec, SAMPLE_VERIFY)
        assert result.valid is False
        assert VALUE_OUT_OF_RANGE in result.reason_codes


# ==========================================================================
# Integration tests — full verify_repair pipeline
# ==========================================================================

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case into a temp project-root and return (case_dir, project_root).

    Reuses the same temp structure pattern as test_workspace_isolation.
    """
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("verify_repair")

    # Mirror workload directory
    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)

    ref = wl / "reference"
    ref.mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", ref / "stats.yaml")

    (wl / ".data").symlink_to(data_dir.resolve())
    (wl / ".hidden_data").symlink_to(hidden_dir.resolve())

    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id="silent.lr_warmup.v1",
        strength="moderate",
        seed=42,
        project_root=tmp,
    )
    return case_dir, tmp


# --------------------------------------------------------------------------
# Oracle recovery (lr=0.01, the reference value)
# --------------------------------------------------------------------------

def test_oracle_repair_recovers(built_case):
    """The oracle repair (lr=0.01) must produce verdict='recovered'."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    }
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "recovered"
    assert len(result["per_seed_hidden_metrics"]) == 3

    for seed_result in result["per_seed_hidden_metrics"]:
        assert seed_result["exitcode"] == 0
        assert seed_result["metric_hidden_test_acc"] is not None
        assert seed_result["metric_hidden_test_acc"] >= 0.843535

    assert result["integrity"]["hash_verified"] is True
    assert "hashes" in result["integrity"]
    assert len(result["integrity"]["hashes"]) == 5
    assert result["compute_spent_sec"] > 0


# --------------------------------------------------------------------------
# Not-recovered (artificially elevated tolerance)
# --------------------------------------------------------------------------

def test_insufficient_repair_not_recovered(built_case):
    """Verify not_recovered path with artificially high tolerance.

    All admissible-range LR values recover for lr_warmup (see DECISIONS.md),
    so we elevate tolerance_lower to 0.99 to force the not_recovered verdict.
    This validates the verdict logic and the per-seed metric collection.
    """
    case_dir, project_root = built_case

    # Temporarily patch verify.yaml with high tolerance
    verify_path = case_dir / "hidden" / "verify.yaml"
    with open(verify_path) as f:
        original_verify = yaml.safe_load(f)

    patched_verify = dict(original_verify)
    patched_verify["tolerance_lower"] = 0.99

    try:
        with open(verify_path, "w") as f:
            yaml.dump(patched_verify, f, default_flow_style=False, sort_keys=False)

        repair = {
            "repair_type": "config_patch",
            "patches": {"training.lr": 0.01},
        }
        result = verify_repair(case_dir, repair, project_root)

        assert result["verdict"] == "not_recovered"
        assert len(result["per_seed_hidden_metrics"]) == 3

        # All seeds should complete but fail the elevated tolerance
        for seed_result in result["per_seed_hidden_metrics"]:
            assert seed_result["exitcode"] == 0
            assert seed_result["metric_hidden_test_acc"] is not None
            assert seed_result["metric_hidden_test_acc"] < 0.99

    finally:
        # Restore original verify.yaml
        with open(verify_path, "w") as f:
            yaml.dump(original_verify, f, default_flow_style=False, sort_keys=False)


# --------------------------------------------------------------------------
# Rejection tests (no training runs)
# --------------------------------------------------------------------------

def test_reject_key_not_allowed(built_case):
    """Disallowed key → rejected, zero reruns."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.batch_size": 128},
    }
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "rejected"
    assert KEY_NOT_ALLOWED in result["reason_codes"]
    assert result["per_seed_hidden_metrics"] == []


def test_reject_value_out_of_range(built_case):
    """Out-of-range value → rejected, zero reruns."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.05},
    }
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "rejected"
    assert VALUE_OUT_OF_RANGE in result["reason_codes"]
    assert result["per_seed_hidden_metrics"] == []


def test_reject_malformed(built_case):
    """Missing repair_type → rejected with MALFORMED, zero reruns."""
    case_dir, project_root = built_case
    repair = {"patches": {"training.lr": 0.01}}
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "rejected"
    assert MALFORMED in result["reason_codes"]
    assert result["per_seed_hidden_metrics"] == []


def test_reject_unsupported_type(built_case):
    """Unsupported repair_type → rejected."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "code_patch",
        "patches": {"training.lr": 0.01},
    }
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "rejected"
    assert REPAIR_TYPE_UNSUPPORTED in result["reason_codes"]
    assert result["per_seed_hidden_metrics"] == []


def test_reject_value_type_invalid(built_case):
    """Non-numeric value for ranged key → rejected."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": "high"},
    }
    result = verify_repair(case_dir, repair, project_root)

    assert result["verdict"] == "rejected"
    assert VALUE_TYPE_INVALID in result["reason_codes"]
    assert result["per_seed_hidden_metrics"] == []


# --------------------------------------------------------------------------
# Result structure and output
# --------------------------------------------------------------------------

def test_standalone_does_not_write_to_disk(built_case):
    """Standalone verify_repair (no trial_run_id) must NOT write a result file.

    Regression: standalone calls previously wrote <run_id>.yaml directly
    into results/<case_id>/, creating orphans invisible to C8.
    """
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    }
    result = verify_repair(case_dir, repair, project_root)

    result_dir = project_root / "results" / result["case_id"]
    # No file with the run_id should exist
    orphan_path = result_dir / f"{result['run_id']}.yaml"
    assert not orphan_path.exists(), (
        f"Standalone verify_repair wrote orphan file {orphan_path}"
    )


def test_trial_linked_result_written_to_disk(built_case):
    """verify_repair WITH trial_run_id writes recovery_<id>.yaml."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    }
    trial_id = "test_trial_linked_000000"
    result = verify_repair(case_dir, repair, project_root, trial_run_id=trial_id)

    result_dir = project_root / "results" / result["case_id"]
    result_path = result_dir / f"recovery_{trial_id}.yaml"
    assert result_path.exists()

    with open(result_path) as f:
        written = yaml.safe_load(f)
    assert written["case_id"] == result["case_id"]
    assert written["verdict"] == result["verdict"]
    assert written["trial_run_id"] == trial_id


def test_result_structure(built_case):
    """Result dict must contain all required fields."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    }
    result = verify_repair(case_dir, repair, project_root)

    required_keys = {
        "case_id", "run_id", "verdict", "reason_codes",
        "per_seed_hidden_metrics", "compute_spent_sec",
        "repair_spec", "integrity", "details",
    }
    assert required_keys <= set(result.keys()), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )
    assert isinstance(result["run_id"], str)
    assert result["repair_spec"] == repair


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def test_determinism(built_case):
    """Same repair spec on same case must produce identical per-seed metrics."""
    case_dir, project_root = built_case
    repair = {
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    }

    r1 = verify_repair(case_dir, repair, project_root)
    r2 = verify_repair(case_dir, repair, project_root)

    assert r1["verdict"] == r2["verdict"]
    for s1, s2 in zip(
        r1["per_seed_hidden_metrics"], r2["per_seed_hidden_metrics"]
    ):
        assert s1["seed"] == s2["seed"]
        assert s1["metric_hidden_test_acc"] == s2["metric_hidden_test_acc"]
        assert s1["exitcode"] == s2["exitcode"]


# --------------------------------------------------------------------------
# Backfill guard: old cases without workload_name in hidden card
# --------------------------------------------------------------------------

def test_missing_workload_name_in_hidden_card_raises(built_case):
    """Cases predating trusted workload identity must raise, not fallback.

    If card.hidden.yaml lacks 'workload_name', verify_repair must raise
    ValueError telling the user to rebuild. It must NOT silently fall back
    to card.public.yaml — that would reintroduce the vulnerability.
    """
    case_dir, project_root = built_case
    hidden_card_path = case_dir / "hidden" / "card.hidden.yaml"

    with open(hidden_card_path) as f:
        original = yaml.safe_load(f)

    # Remove workload_name to simulate old case
    stripped = {k: v for k, v in original.items() if k != "workload_name"}

    try:
        with open(hidden_card_path, "w") as f:
            yaml.dump(stripped, f, default_flow_style=False, sort_keys=False)

        repair = {
            "repair_type": "config_patch",
            "patches": {"training.lr": 0.01},
        }
        with pytest.raises(ValueError, match="rebuild with build_case"):
            verify_repair(case_dir, repair, project_root)
    finally:
        with open(hidden_card_path, "w") as f:
            yaml.dump(original, f, default_flow_style=False, sort_keys=False)


# --------------------------------------------------------------------------
# Tampered public card has no effect
# --------------------------------------------------------------------------

def test_tampered_public_card_no_effect(built_case):
    """Modifying card.public.yaml workload_name must not affect verification.

    verify_repair reads workload_name from the hidden card, so a tampered
    public card is ignored.
    """
    case_dir, project_root = built_case
    public_card_path = case_dir / "card.public.yaml"

    with open(public_card_path) as f:
        original = yaml.safe_load(f)

    # Tamper with workload_name in public card
    tampered = dict(original)
    tampered["workload_name"] = "bogus_workload"

    try:
        with open(public_card_path, "w") as f:
            yaml.dump(tampered, f, default_flow_style=False, sort_keys=False)

        repair = {
            "repair_type": "config_patch",
            "patches": {"training.lr": 0.01},
        }
        result = verify_repair(case_dir, repair, project_root)

        # Must still succeed — workload_name comes from hidden card
        assert result["verdict"] == "recovered"
    finally:
        with open(public_card_path, "w") as f:
            yaml.dump(original, f, default_flow_style=False, sort_keys=False)


# ==========================================================================
# Invariant: EVERY registered operator round-trips through the evaluator
# ==========================================================================
#
# A convention change anywhere (e.g. absent-when-clean removing a config
# section) must not silently break mutation replay or repair for any
# operator.  For each registered operator we build a real case and run its
# oracle repair through verify_repair end-to-end, asserting recovered.
#
# The oracle repair per operator is enumerated here; iterating the registry
# means a newly-registered operator with no oracle entry fails loudly rather
# than being skipped.

# operator_id -> (strength, oracle repair patches)
_ORACLE_REPAIRS = {
    "silent.lr_warmup.v1": ("moderate", {"training.lr": 0.01}),
    "silent.label_corruption.v1": ("moderate", {"data.label_noise_fraction": 0.0}),
    "silent.data_leakage.v1": ("moderate", {"data.include_aux_feature": False}),
    "crash.shape_mismatch.v1": ("moderate", {"model.input_dim": 105}),
}


def _setup_tmp_workload(tmp: Path) -> Path:
    """Mirror the tabular_adult workload into a temp project root."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)
    (wl / "reference").mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", wl / "reference" / "stats.yaml")
    (wl / ".data").symlink_to(data_dir.resolve())
    (wl / ".hidden_data").symlink_to(hidden_dir.resolve())
    return wl


def _all_registered_operators():
    from harness.build_case import _OPERATOR_REGISTRY
    return sorted(_OPERATOR_REGISTRY)


@pytest.mark.parametrize("operator_id", _all_registered_operators())
def test_every_operator_oracle_round_trips(operator_id, tmp_path):
    """Build each operator's case and confirm its oracle repair recovers.

    This is the invariant that catches convention changes (like
    absent-when-clean) that break mutation replay for a specific operator.

    Control-tier operators are exempt: they inject no fault and recover via the
    free ``no_unnecessary_repair`` axis, not through ``verify_repair``.
    """
    from harness.build_case import _OPERATOR_REGISTRY

    if _OPERATOR_REGISTRY[operator_id]().layer == "control":
        pytest.skip("control tier has no verify_repair recovery path")

    assert operator_id in _ORACLE_REPAIRS, (
        f"{operator_id} has no oracle repair in _ORACLE_REPAIRS; add one so "
        f"the every-operator round-trip invariant covers it"
    )
    strength, patch = _ORACLE_REPAIRS[operator_id]

    _setup_tmp_workload(tmp_path)
    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id=operator_id,
        strength=strength,
        seed=42,
        project_root=tmp_path,
    )

    result = verify_repair(
        case_dir,
        {"repair_type": "config_patch", "patches": patch},
        tmp_path,
    )

    assert result["verdict"] == "recovered", (
        f"{operator_id} oracle repair {patch} did not recover: {result}"
    )
    assert len(result["per_seed_hidden_metrics"]) == 3
    for seed_result in result["per_seed_hidden_metrics"]:
        assert seed_result["exitcode"] == 0
        assert seed_result["metric_hidden_test_acc"] is not None
