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

# Visible-metric reference band (public-card healthy-run anchor).
_REF_VIS_MEAN = 0.856848
_REF_VIS_STD = 0.001512


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
        "reference_visible_metric": {
            "series": "metric_visible_val_acc",
            "mean": _REF_VIS_MEAN,
            "std": _REF_VIS_STD,
        },
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
        "accepted_classes": ["lr_misconfiguration", "learning_rate",
                             "lr_too_high", "lr_warmup"],
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
        "oracle_repair": {"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
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
        "metric_visible_val_acc": {
            "mean": _REF_VIS_MEAN,
            "std": _REF_VIS_STD,
        },
        "metric_hidden_test_acc": {
            "mean": _REF_MEAN,
            "std": _REF_STD,
            "tolerance_lower": _EXPECTED_TOLERANCE,
        },
    }
    with open(ref_dir / "stats.yaml", "w") as f:
        yaml.dump(stats, f)

    return case_dir


def _make_execution_case(
    root: Path,
    case_id: str = "case_0001",
    *,
    workload_name: str = "tabular_adult",
    operator_id: str = "crash.shape_mismatch.v1",
    strength: str = "moderate",
    seed: int = 42,
) -> Path:
    """Build a synthetic execution-tier (crash) case for testing.

    Key differences from _make_case:
    - layer="execution"
    - No ckpt_final.pt
    - faulty_value=None (null in YAML)
    - exitcode=1
    - stdout.log has a traceback
    - metrics.jsonl is empty
    """
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

    # card.public.yaml — no ckpt_final.pt in inventory
    public_card = {
        "case_id": case_id,
        "workload_family": "tabular",
        "workload_name": workload_name,
        "permitted_tools": ["read_log", "submit"],
        "permitted_edit_paths": ["workspace/config.yaml"],
        "agent_budget": {"max_tool_calls": 40},
        "reference_visible_metric": {
            "series": "metric_visible_val_acc",
            "mean": _REF_VIS_MEAN,
            "std": _REF_VIS_STD,
        },
        "artifact_inventory": [
            "workspace/config.yaml",
            "workspace/run_output/exitcode",
            "workspace/run_output/logs/stdout.log",
        ],
    }
    with open(case_dir / "card.public.yaml", "w") as f:
        yaml.dump(public_card, f)

    # hidden/card.hidden.yaml
    hidden_card = {
        "case_id": case_id,
        "workload_name": workload_name,
        "operator_id": operator_id,
        "layer": "execution",
        "strength": strength,
        "seed": seed,
        "mutations": [{
            "file": "config.yaml",
            "key_path": "model.input_dim",
            "original_value": None,
            "mutated_value": 10,
            "description": "test mutation",
        }],
        "accepted_classes": ["shape_mismatch", "dimension_mismatch",
                             "input_dimension", "input_dim_mismatch",
                             "model_shape_error"],
    }
    with open(hidden / "card.hidden.yaml", "w") as f:
        yaml.dump(hidden_card, f)

    # hidden/evidence.yaml
    evidence = [
        {"kind": "config_key", "artifact_id": "config.yaml",
         "detail": {"key_path": "model.input_dim"}},
        {"kind": "line_range", "artifact_id": "logs/stdout.log",
         "detail": {"start_line": 2, "end_line": 24}},
    ]
    with open(hidden / "evidence.yaml", "w") as f:
        yaml.dump(evidence, f)

    # hidden/verify.yaml — faulty_value is null
    verify = {
        "tolerance_lower": _EXPECTED_TOLERANCE,
        "hidden_eval_seeds": [100, 101, 102],
        "faulty_value": None,
        "reference_metric_mean": _REF_MEAN,
        "reference_metric_std": _REF_STD,
        "admissible_repairs": {
            "repair_type": "config_patch",
            "allowed_keys": ["model.input_dim"],
            "value_ranges": {"model.input_dim": [90, 120]},
        },
        "oracle_repair": {"repair_type": "config_patch", "patches": {"model.input_dim": 105}},
    }
    with open(hidden / "verify.yaml", "w") as f:
        yaml.dump(verify, f)

    # workspace files
    (workspace / "train.py").write_text("# training script\nimport torch\n")
    config = {
        "workload": {"family": "tabular", "name": "tabular_adult"},
        "model": {"type": "mlp", "hidden_dims": [64, 32], "input_dim": 10},
        "training": {"epochs": 20, "batch_size": 256, "lr": 0.01},
    }
    with open(workspace / "config.yaml", "w") as f:
        yaml.dump(config, f)

    # run_output artifacts — crash: empty metrics, traceback log, no checkpoint
    (run_output / "metrics.jsonl").write_text("")
    (run_output / "logs" / "stdout.log").write_text(
        "2026-01-01 [INFO] Training seed=42\n"
        "2026-01-01 [ERROR] Training failed:\n"
        "Traceback (most recent call last):\n"
        "  File train.py, line 211, in train\n"
        "RuntimeError: mat1 and mat2 shapes cannot be multiplied\n"
    )

    resolved_config = dict(config)
    with open(run_output / "config.resolved.yaml", "w") as f:
        yaml.dump(resolved_config, f)

    (run_output / "exitcode").write_text("1\n")
    # NO ckpt_final.pt — crash tier

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
        "metric_visible_val_acc": {
            "mean": _REF_VIS_MEAN,
            "std": _REF_VIS_STD,
        },
        "metric_hidden_test_acc": {
            "mean": _REF_MEAN,
            "std": _REF_STD,
            "tolerance_lower": _EXPECTED_TOLERANCE,
        },
    }
    with open(ref_dir / "stats.yaml", "w") as f:
        yaml.dump(stats, f)

    return case_dir


def _make_control_case(
    root: Path,
    case_id: str = "case_0001",
    *,
    faulty_value: float | None = None,
    evidence: list | None = None,
    inject_public_token: str | None = None,
) -> Path:
    """Build a synthetic control-tier case by converting a dynamics scaffold.

    Control invariants: layer=control, empty mutations, empty evidence, no
    admissible repair, null oracle_repair, faulty_value >= tolerance (healthy).
    """
    import dataclasses

    from operators.control.healthy import HealthyControlOperator

    case_dir = _make_case(root, case_id)
    hidden = case_dir / "hidden"

    hc = yaml.safe_load((hidden / "card.hidden.yaml").read_text())
    hc["layer"] = "control"
    hc["operator_id"] = "control.healthy.v1"
    hc["mutations"] = []
    hc["accepted_classes"] = ["none", "healthy", "no_incident", "no_fault", "nothing_wrong"]
    (hidden / "card.hidden.yaml").write_text(yaml.dump(hc))

    (hidden / "evidence.yaml").write_text(yaml.dump(evidence if evidence is not None else []))

    v = yaml.safe_load((hidden / "verify.yaml").read_text())
    v["faulty_value"] = faulty_value if faulty_value is not None else _REF_MEAN  # >= tolerance
    v["admissible_repairs"] = dataclasses.asdict(HealthyControlOperator().admissible_repairs())
    v["oracle_repair"] = None
    (hidden / "verify.yaml").write_text(yaml.dump(v))

    reg_path = root / "cases" / "registry.hidden.yaml"
    reg = yaml.safe_load(reg_path.read_text())
    reg[case_id]["operator"] = "control.healthy.v1"
    reg_path.write_text(yaml.dump(reg))

    if inject_public_token is not None:
        card_path = case_dir / "card.public.yaml"
        card = yaml.safe_load(card_path.read_text())
        card["description"] = f"this is a {inject_public_token} case"
        card_path.write_text(yaml.dump(card))

    return case_dir


class TestW4HiddenValueScan:

    def test_valid_case_has_no_hidden_value_leak(self, tmp_path):
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        w4 = [c for c in report.checks if c.name == "W4_hidden_values_not_in_workspace"][0]
        assert w4.passed, w4.detail

    def test_planted_tolerance_in_log_is_caught(self, tmp_path):
        """Planted: the formatted tolerance_lower written into a workspace log →
        W4 fails and names the file/offset/value."""
        case_dir = _make_case(tmp_path)
        formatted = f"{_EXPECTED_TOLERANCE:.6f}"
        log = case_dir / "workspace" / "run_output" / "logs" / "stdout.log"
        log.write_text(log.read_text() + f"\nDEBUG threshold={formatted}\n")

        report = validate_case(case_dir, project_root=tmp_path)
        w4 = [c for c in report.checks if c.name == "W4_hidden_values_not_in_workspace"][0]
        assert not w4.passed
        assert "tolerance_lower" in w4.detail
        assert "stdout.log" in w4.detail


class TestControlTier:

    def test_valid_control_passes(self, tmp_path):
        case_dir = _make_control_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        assert report.passed, [c.name + ":" + c.detail for c in report.failed]

    def test_c5_control_below_tolerance_fails(self, tmp_path):
        """Planted: a 'healthy' control whose metric is below tolerance is caught."""
        case_dir = _make_control_case(tmp_path, faulty_value=0.5)  # below tolerance
        report = validate_case(case_dir, project_root=tmp_path)
        assert "C5_faulty_value_below_tolerance" in [c.name for c in report.failed]

    def test_f6_control_with_evidence_fails(self, tmp_path):
        """Planted: a control that ships non-empty evidence is caught."""
        evidence = [{"kind": "config_key", "artifact_id": "config.yaml",
                     "detail": {"key_path": "training.lr"}}]
        case_dir = _make_control_case(tmp_path, evidence=evidence)
        report = validate_case(case_dir, project_root=tmp_path)
        assert "F6_control_shape" in [c.name for c in report.failed]

    def test_w2_control_token_in_public_card_fails(self, tmp_path):
        """Planted: the word 'control' leaking into the public card fails W2."""
        case_dir = _make_control_case(tmp_path, inject_public_token="control")
        report = validate_case(case_dir, project_root=tmp_path)
        assert "W2_public_card_no_incident_info" in [c.name for c in report.failed]


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
# CONSISTENCY — reference band anchor (C9)
# ---------------------------------------------------------------------------

class TestReferenceBandCheck:

    def test_c9_band_matches_reference(self, tmp_path):
        """A card band equal to the visible reference stats passes C9."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        c9 = [c for c in report.checks if c.name == "C9_reference_band_matches_reference"][0]
        assert c9.passed, c9.detail

    def test_c9_band_mismatch_fails(self, tmp_path):
        """A perturbed band mean fails C9."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "card.public.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        card["reference_visible_metric"]["mean"] = 0.5  # wrong
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C9_reference_band_matches_reference" in failed_names

    def test_c9_band_missing_fails(self, tmp_path):
        """A card without the band fails C9 (every case must carry the anchor)."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "card.public.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        card.pop("reference_visible_metric", None)
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C9_reference_band_matches_reference" in failed_names

    def test_public_card_excludes_hidden_metrics(self, tmp_path):
        """Public card carries the visible band but no hidden mean/tolerance."""
        case_dir = _make_case(tmp_path)
        text = (case_dir / "card.public.yaml").read_text()
        # Visible anchor present.
        assert "metric_visible_val_acc" in text
        assert str(_REF_VIS_MEAN) in text
        # Hidden numbers absent.
        assert str(_REF_MEAN) not in text
        assert str(_EXPECTED_TOLERANCE) not in text
        assert "tolerance" not in text.lower()
        assert "hidden" not in text.lower()


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

    def test_c8_catches_non_recovery_prefix_orphan(self, tmp_path):
        """C8 catches orphaned recovery-shaped files even without recovery_ prefix.

        Regression: C8 previously only globbed recovery_*.yaml, missing
        orphans written by standalone verify_repair calls with no trial_run_id.
        """
        case_dir = _make_case(tmp_path)
        case_id = "case_0001"

        results_dir = tmp_path / "results" / case_id
        results_dir.mkdir(parents=True, exist_ok=True)

        # Orphan: recovery-shaped content, no trial_run_id, non-recovery_ filename
        orphan = {
            "case_id": case_id,
            "run_id": "20260101T000000Z_abcdef",
            "verdict": "recovered",
            "per_seed_hidden_metrics": [{"seed": 100, "metric_hidden_test_acc": 0.85}],
        }
        with open(results_dir / "20260101T000000Z_abcdef.yaml", "w") as f:
            yaml.dump(orphan, f)

        report = validate_case(case_dir, project_root=tmp_path)
        c8 = [c for c in report.checks if c.name == "C8_recovery_files_linked"][0]
        assert not c8.passed
        assert "orphan" in c8.detail.lower()

    def test_c8_ignores_non_recovery_yaml(self, tmp_path):
        """C8 ignores YAML files that are not recovery-shaped."""
        case_dir = _make_case(tmp_path)
        case_id = "case_0001"

        results_dir = tmp_path / "results" / case_id
        results_dir.mkdir(parents=True, exist_ok=True)

        # Non-recovery file (no verdict or per_seed_hidden_metrics)
        misc = {"some_key": "some_value", "notes": "not a recovery result"}
        with open(results_dir / "misc_notes.yaml", "w") as f:
            yaml.dump(misc, f)

        report = validate_case(case_dir, project_root=tmp_path)
        c8 = [c for c in report.checks if c.name == "C8_recovery_files_linked"][0]
        assert c8.passed


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

    def test_f4_missing_accepted_classes(self, tmp_path):
        """Missing accepted_classes in card.hidden.yaml fails F4."""
        case_dir = _make_case(tmp_path)
        card_path = case_dir / "hidden" / "card.hidden.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        del card["accepted_classes"]
        with open(card_path, "w") as f:
            yaml.dump(card, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "F4_accepted_classes" in failed_names

    def test_f5_dynamics_needs_checkpoint(self, tmp_path):
        """Dynamics-tier case missing ckpt_final.pt fails F5."""
        case_dir = _make_case(tmp_path)
        # Remove checkpoint (dynamics tier should have it)
        ckpt = case_dir / "workspace" / "run_output" / "checkpoints" / "ckpt_final.pt"
        ckpt.unlink()

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "F5_checkpoint_tier_match" in failed_names

    def test_f5_execution_no_checkpoint_passes(self, tmp_path):
        """Execution-tier case without ckpt_final.pt passes F5."""
        case_dir = _make_execution_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        f5 = [c for c in report.checks if c.name == "F5_checkpoint_tier_match"][0]
        assert f5.passed

    def test_f3_null_faulty_value_accepted(self, tmp_path):
        """verify.yaml with faulty_value: null passes F3."""
        case_dir = _make_execution_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        f3 = [c for c in report.checks if c.name == "F3_verify_yaml_required_fields"][0]
        assert f3.passed

    def test_c5_null_faulty_value_execution_passes(self, tmp_path):
        """C5 passes for execution tier with faulty_value=null."""
        case_dir = _make_execution_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        c5 = [c for c in report.checks if c.name == "C5_faulty_value_below_tolerance"][0]
        assert c5.passed

    def test_c5_null_faulty_value_dynamics_fails(self, tmp_path):
        """C5 fails for dynamics tier with faulty_value=null."""
        case_dir = _make_case(tmp_path)
        # Set faulty_value to null on a dynamics-tier case
        verify_path = case_dir / "hidden" / "verify.yaml"
        with open(verify_path) as f:
            verify = yaml.safe_load(f)
        verify["faulty_value"] = None
        with open(verify_path, "w") as f:
            yaml.dump(verify, f)

        report = validate_case(case_dir, project_root=tmp_path)
        failed_names = [c.name for c in report.failed]
        assert "C5_faulty_value_below_tolerance" in failed_names

    def test_execution_case_passes_all(self, tmp_path):
        """Known-good synthetic execution-tier case passes all checks."""
        case_dir = _make_execution_case(tmp_path)
        report = validate_case(case_dir, project_root=tmp_path)
        assert report.passed, (
            f"Expected all checks to pass but failed: "
            + ", ".join(c.name + ": " + c.detail for c in report.failed)
        )


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


# ---------------------------------------------------------------------------
# F3: allowed_values support
# ---------------------------------------------------------------------------

class TestF3AllowedValues:

    def test_f3_allowed_values_accepted(self, tmp_path):
        """verify.yaml with allowed_values (no value_ranges) passes F3."""
        case_dir = _make_case(tmp_path)
        # Replace value_ranges with allowed_values in verify.yaml
        verify_path = case_dir / "hidden" / "verify.yaml"
        with open(verify_path) as f:
            verify = yaml.safe_load(f)
        del verify["admissible_repairs"]["value_ranges"]
        verify["admissible_repairs"]["allowed_values"] = {
            "data.include_aux_feature": [False],
        }
        verify["admissible_repairs"]["allowed_keys"] = ["data.include_aux_feature"]
        with open(verify_path, "w") as f:
            yaml.dump(verify, f)

        report = validate_case(case_dir)
        f3 = [c for c in report.checks if c.name == "F3_verify_yaml_required_fields"]
        assert len(f3) == 1
        assert f3[0].passed, f"F3 failed: {f3[0].detail}"

    def test_f3_requires_ranges_or_values(self, tmp_path):
        """verify.yaml missing both value_ranges and allowed_values fails F3."""
        case_dir = _make_case(tmp_path)
        verify_path = case_dir / "hidden" / "verify.yaml"
        with open(verify_path) as f:
            verify = yaml.safe_load(f)
        del verify["admissible_repairs"]["value_ranges"]
        with open(verify_path, "w") as f:
            yaml.dump(verify, f)

        report = validate_case(case_dir)
        f3 = [c for c in report.checks if c.name == "F3_verify_yaml_required_fields"]
        assert len(f3) == 1
        assert not f3[0].passed

    def test_f3_value_ranges_still_accepted(self, tmp_path):
        """Existing verify.yaml format with value_ranges still passes (backward compat)."""
        case_dir = _make_case(tmp_path)
        report = validate_case(case_dir)
        f3 = [c for c in report.checks if c.name == "F3_verify_yaml_required_fields"]
        assert len(f3) == 1
        assert f3[0].passed
