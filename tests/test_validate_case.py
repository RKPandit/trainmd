"""Tests for harness/validate_case.py.

Uses a synthetic case fixture (no real training) to test each check's
pass and fail paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from harness.validate_case import (
    ValidationReport,
    validate_all,
    validate_case,
)


# ---------------------------------------------------------------------------
# Synthetic case fixture
# ---------------------------------------------------------------------------

# Reference stats that produce tolerance_lower = round(0.847 - 2 * 0.002, 6) = 0.843
_REF_MEAN = 0.847
_REF_STD = 0.002
_EXPECTED_TOLERANCE = round(_REF_MEAN - 2 * _REF_STD, 6)  # 0.843


def _make_case(
    root: Path,
    case_id: str = "case_0001",
    *,
    workload_name: str = "tabular_adult",
    operator_id: str = "silent.lr_warmup.v1",
    strength: str = "moderate",
    seed: int = 42,
    tolerance_lower: float | None = None,
    faulty_value: float = 0.78,
    hidden_eval_seeds: list[int] | None = None,
    mutated_value: float = 0.2,
) -> Path:
    """Build a minimal synthetic case directory for testing.

    Returns the case directory path.
    """
    if tolerance_lower is None:
        tolerance_lower = _EXPECTED_TOLERANCE
    if hidden_eval_seeds is None:
        hidden_eval_seeds = [100, 101, 102]

    case_dir = root / "cases" / case_id
    workspace = case_dir / "workspace"
    run_output = workspace / "run_output"
    hidden = case_dir / "hidden"

    for d in [
        hidden,
        workspace,
        run_output / "logs",
        run_output / "checkpoints",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # card.public.yaml
    public_card = {
        "case_id": case_id,
        "workload_family": "tabular",
        "workload_name": workload_name,
        "permitted_tools": ["read_log", "submit"],
        "permitted_edit_paths": ["workspace/config.yaml"],
        "agent_budget": {"max_tool_calls": 40},
        "artifact_inventory": ["workspace/config.yaml"],
    }
    with open(case_dir / "card.public.yaml", "w") as f:
        yaml.dump(public_card, f)

    # hidden/card.hidden.yaml
    hidden_card = {
        "case_id": case_id,
        "workload_name": workload_name,
        "operator_id": operator_id,
        "layer": "dynamics",
        "strength": strength,
        "seed": seed,
        "mutations": [{
            "file": "config.yaml",
            "key_path": "training.lr",
            "original_value": 0.01,
            "mutated_value": mutated_value,
            "description": "test mutation",
        }],
    }
    with open(hidden / "card.hidden.yaml", "w") as f:
        yaml.dump(hidden_card, f)

    # hidden/evidence.yaml
    evidence = [{"kind": "config_key", "artifact_id": "config.yaml",
                 "detail": {"key_path": "training.lr"}}]
    with open(hidden / "evidence.yaml", "w") as f:
        yaml.dump(evidence, f)

    # hidden/verify.yaml
    verify = {
        "tolerance_lower": tolerance_lower,
        "hidden_eval_seeds": hidden_eval_seeds,
        "faulty_value": faulty_value,
        "reference_metric_mean": _REF_MEAN,
        "reference_metric_std": _REF_STD,
        "admissible_repairs": {
            "repair_type": "config_patch",
            "allowed_keys": ["training.lr"],
            "value_ranges": {"training.lr": [0.001, 0.02]},
        },
    }
    with open(hidden / "verify.yaml", "w") as f:
        yaml.dump(verify, f)

    # workspace files — clean content (no forbidden tokens)
    (workspace / "train.py").write_text("# training script\nimport torch\n")
    config = {
        "workload": {"family": "tabular", "name": "tabular_adult"},
        "model": {"type": "mlp", "hidden_dims": [64, 32]},
        "training": {"epochs": 20, "batch_size": 256, "lr": mutated_value},
    }
    with open(workspace / "config.yaml", "w") as f:
        yaml.dump(config, f)

    # run_output artifacts
    metrics = [
        {"epoch": 0, "train_loss": 0.5, "metric_visible_val_acc": 0.75},
        {"epoch": 1, "train_loss": 0.4, "metric_visible_val_acc": 0.80},
    ]
    with open(run_output / "metrics.jsonl", "w") as f:
        for m in metrics:
            f.write(json.dumps(m) + "\n")

    (run_output / "logs" / "stdout.log").write_text("Epoch 0 complete\nEpoch 1 complete\n")

    resolved_config = dict(config)
    with open(run_output / "config.resolved.yaml", "w") as f:
        yaml.dump(resolved_config, f)

    (run_output / "exitcode").write_text("0\n")
    (run_output / "checkpoints" / "ckpt_final.pt").write_bytes(b"\x00" * 16)

    # Registry
    registry_path = root / "cases" / "registry.hidden.yaml"
    registry = {}
    if registry_path.exists():
        with open(registry_path) as f:
            registry = yaml.safe_load(f) or {}
    registry[case_id] = {
        "workload": workload_name,
        "operator": operator_id,
        "strength": strength,
        "seed": seed,
    }
    with open(registry_path, "w") as f:
        yaml.dump(registry, f)

    # Reference stats
    ref_dir = root / "workloads" / workload_name / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    stats = {
        "workload": workload_name,
        "metric_hidden_test_acc": {
            "mean": _REF_MEAN,
            "std": _REF_STD,
            "tolerance_lower": _EXPECTED_TOLERANCE,
        },
    }
    with open(ref_dir / "stats.yaml", "w") as f:
        yaml.dump(stats, f)

    return case_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidCasePasses:

    def test_valid_case_passes_all(self, tmp_path):
        """Known-good synthetic case passes all checks."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        assert report.passed, (
            f"Expected all checks to pass but failed: "
            + ", ".join(c.name + ": " + c.detail for c in report.failed)
        )


# ---------------------------------------------------------------------------
# WALL checks
# ---------------------------------------------------------------------------

class TestWallChecks:

    def test_w1_forbidden_token_in_workspace(self, tmp_path):
        """Injecting 'test_acc' into metrics.jsonl fails W1."""
        case_dir = _make_case(tmp_path)
        metrics_path = case_dir / "workspace" / "run_output" / "metrics.jsonl"
        with open(metrics_path, "a") as f:
            f.write(json.dumps({"test_acc": 0.9}) + "\n")

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "W1_workspace_no_hidden_tokens" in failed_names

    def test_w1_dynamic_operator_token(self, tmp_path):
        """Operator ID segments (e.g. 'lr_warmup') are caught in workspace."""
        case_dir = _make_case(tmp_path)
        log_path = case_dir / "workspace" / "run_output" / "logs" / "stdout.log"
        log_path.write_text("Detected lr_warmup issue\n")

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "W1_workspace_no_hidden_tokens" in failed_names

    def test_w2_incident_info_in_public_card(self, tmp_path):
        """Adding operator info to card.public.yaml fails W2."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "card.public.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        card["operator"] = "silent.lr_warmup.v1"
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "W2_public_card_no_incident_info" in failed_names

    def test_w3_overlapping_eval_seeds(self, tmp_path):
        """Hidden eval seeds overlapping [0..9] fails W3."""
        case_dir = _make_case(tmp_path, hidden_eval_seeds=[0, 1, 2])
        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "W3_hidden_eval_seeds_disjoint" in failed_names


# ---------------------------------------------------------------------------
# CONSISTENCY checks
# ---------------------------------------------------------------------------

class TestConsistencyChecks:

    def test_c1_case_id_mismatch(self, tmp_path):
        """Different case_id in public vs hidden card fails C1."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "card.public.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        card["case_id"] = "case_9999"
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C1_case_id_matches_directory" in failed_names

    def test_c2_workload_mismatch(self, tmp_path):
        """Different workload_name in public card fails C2."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "card.public.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        card["workload_name"] = "wrong_workload"
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C2_workload_name_consistent" in failed_names

    def test_c3_registry_entry_missing(self, tmp_path):
        """Empty registry fails C3."""
        case_dir = _make_case(tmp_path)
        registry_path = tmp_path / "cases" / "registry.hidden.yaml"
        with open(registry_path, "w") as f:
            yaml.dump({}, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C3_registry_entry_exists" in failed_names

    def test_c4_tolerance_mismatch(self, tmp_path):
        """Wrong tolerance_lower in verify.yaml fails C4."""
        case_dir = _make_case(tmp_path, tolerance_lower=0.999)
        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C4_tolerance_matches_reference" in failed_names

    def test_c5_faulty_above_tolerance(self, tmp_path):
        """faulty_value >= tolerance fails C5."""
        case_dir = _make_case(tmp_path, faulty_value=0.99)
        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C5_faulty_value_below_tolerance" in failed_names

    def test_c6_mutation_not_applied(self, tmp_path):
        """Deep check with wrong mutated_value in resolved config fails C6."""
        case_dir = _make_case(tmp_path, mutated_value=0.2)
        # Overwrite resolved config with different LR
        resolved_path = case_dir / "workspace" / "run_output" / "config.resolved.yaml"
        with open(resolved_path) as f:
            config = yaml.safe_load(f)
        config["training"]["lr"] = 0.01  # wrong — should be 0.2
        with open(resolved_path, "w") as f:
            yaml.dump(config, f)

        report = validate_case(case_dir, project_root=tmp_path, deep=True)
        failed_names = [c.name for c in report.failed]
        assert "C6_mutations_applied_in_config" in failed_names

    def test_c6_skipped_without_deep(self, tmp_path):
        """C6 is not run without --deep."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path, deep=False)
        check_names = [c.name for c in report.checks]
        assert "C6_mutations_applied_in_config" not in check_names


# ---------------------------------------------------------------------------
# CONSISTENCY — index and recovery linkage (C7, C8)
# ---------------------------------------------------------------------------

class TestIndexAndRecoveryChecks:

    def test_c7_index_drift(self, tmp_path):
        """Stale index entry with wrong evidence_f1 fails C7."""
        case_dir = _make_case(tmp_path)
        case_id = "case_0001"
        run_id = "20260101T000000Z_aaaaaa"

        # Create a trial record
        trials_dir = tmp_path / "results" / case_id / "trials"
        trials_dir.mkdir(parents=True)
        record = {
            "case_id": case_id,
            "agent_name": "test_agent",
            "run_id": run_id,
            "status": "completed",
            "model": {"model_id": None},
            "usage": {"total_tokens": 0, "estimated_cost_usd": None,
                      "cost_is_estimate": True, "input_tokens": 0,
                      "output_tokens": 0, "cached_tokens": 0},
            "environment": {"harness_git_commit": "abc", "timestamp_utc": "2026-01-01"},
            "scores": {
                "detection": {"correct": True},
                "identification": {"correct": True},
                "evidence": {"f1": 0.8},
                "recovery": {"verdict": "recovered"},
                "safety": {},
            },
        }
        with open(trials_dir / f"test_agent_{run_id}.yaml", "w") as f:
            yaml.dump(record, f)

        # Write stale index with wrong evidence_f1
        index_path = tmp_path / "results" / "index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        stale_line = {
            "case_id": case_id,
            "agent_name": "test_agent",
            "run_id": run_id,
            "model_id": None,
            "detection_correct": True,
            "identification_correct": True,
            "evidence_f1": 0.0,  # STALE — should be 0.8
            "recovery_verdict": "recovered",
            "total_tokens": 0,
            "estimated_cost_usd": None,
            "cost_is_estimate": True,
            "harness_git_commit": "abc",
            "status": "completed",
            "timestamp_utc": "2026-01-01",
        }
        with open(index_path, "w") as f:
            f.write(json.dumps(stale_line) + "\n")

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C7_index_matches_record" in failed_names

    def test_c7_no_trials_skips(self, tmp_path):
        """No results directory means C7 passes (skipped)."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        c7 = [c for c in report.checks if c.name == "C7_index_matches_record"][0]
        assert c7.passed
        assert "skipped" in c7.detail

    def test_c8_orphaned_recovery(self, tmp_path):
        """Recovery file with no matching trial fails C8."""
        case_dir = _make_case(tmp_path)
        case_id = "case_0001"

        results_dir = tmp_path / "results" / case_id
        results_dir.mkdir(parents=True, exist_ok=True)

        # Recovery file pointing to nonexistent trial
        recovery = {
            "case_id": case_id,
            "run_id": "20260101T000000Z_verify",
            "trial_run_id": "20260101T000000Z_nonexistent",
            "verdict": "recovered",
        }
        with open(results_dir / "recovery_20260101T000000Z_nonexistent.yaml", "w") as f:
            yaml.dump(recovery, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C8_recovery_files_linked" in failed_names

    def test_c8_no_recovery_files_skips(self, tmp_path):
        """No recovery files means C8 passes (skipped)."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        c8 = [c for c in report.checks if c.name == "C8_recovery_files_linked"][0]
        assert c8.passed
        assert "skipped" in c8.detail


# ---------------------------------------------------------------------------
# WELL_FORMEDNESS checks
# ---------------------------------------------------------------------------

class TestWellFormednessChecks:

    def test_f1_missing_file(self, tmp_path):
        """Removing a required file fails F1."""
        case_dir = _make_case(tmp_path)
        (case_dir / "workspace" / "run_output" / "exitcode").unlink()

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "F1_required_files_exist" in failed_names

    def test_f2_missing_hidden_card_field(self, tmp_path):
        """Removing 'mutations' from card.hidden.yaml fails F2."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "hidden" / "card.hidden.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        del card["mutations"]
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "F2_hidden_card_required_fields" in failed_names

    def test_f3_missing_verify_field(self, tmp_path):
        """Removing 'admissible_repairs' from verify.yaml fails F3."""
        case_dir = _make_case(tmp_path)
        verify_path = case_dir / "hidden" / "verify.yaml"
        with open(verify_path) as f:
            verify = yaml.safe_load(f)
        del verify["admissible_repairs"]
        with open(verify_path, "w") as f:
            yaml.dump(verify, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "F3_verify_yaml_required_fields" in failed_names


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

class TestValidateAll:

    def test_validate_all(self, tmp_path):
        """Two cases: one good, one with broken tolerance → mixed results."""
        _make_case(tmp_path, case_id="case_0001")
        _make_case(tmp_path, case_id="case_0002", tolerance_lower=0.999)

        reports = validate_all(project_root=tmp_path)
        assert len(reports) == 2

        by_id = {r.case_id: r for r in reports}
        assert by_id["case_0001"].passed
        assert not by_id["case_0002"].passed
