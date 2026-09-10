"""Tests for the crash.shape_mismatch.v1 operator (spec §4).

This is the first crash-tier (execution layer) operator.  Unlike silent
operators that produce completed-but-bad runs, crash operators produce
jobs that FAIL (exitcode != 0, no valid checkpoint).

Every operator ships with unit tests proving:
(a) the clean run passes verification, and
(b) the mutated run fails it (here: crashes),
across 3 seeds, before merge.

Fast tests (no training) verify protocol conformance, config mutation,
and evidence/repair metadata.  Integration tests run actual training
jobs and verify crash behavior and oracle recovery.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from random import Random

import pytest
import yaml

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.crash.shape_mismatch import ShapeMismatchOperator, _STRENGTH_DIM

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _load_tolerance() -> float:
    """Load tolerance_lower from the committed reference stats."""
    stats_path = WORKLOAD_DIR / "reference" / "stats.yaml"
    with open(stats_path) as f:
        stats = yaml.safe_load(f)
    return stats["metric_hidden_test_acc"]["tolerance_lower"]


def _make_workspace(tmp_path: Path) -> Path:
    """Copy workload source files to a temp workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for fname in ["train.py", "config.yaml"]:
        shutil.copy2(WORKLOAD_DIR / fname, workspace / fname)
    return workspace


# --------------------------------------------------------------------------
# Fast tests (no training)
# --------------------------------------------------------------------------


class TestProtocol:
    """Verify IncidentOperator protocol conformance."""

    def test_isinstance(self):
        op = ShapeMismatchOperator()
        assert isinstance(op, IncidentOperator)

    def test_id(self):
        assert ShapeMismatchOperator().id == "crash.shape_mismatch.v1"

    def test_layer(self):
        assert ShapeMismatchOperator().layer == "execution"

    def test_accepted_classes(self):
        classes = ShapeMismatchOperator().accepted_classes()
        assert isinstance(classes, frozenset)
        assert len(classes) > 0
        assert "shape_mismatch" in classes
        assert "dimension_mismatch" in classes


class TestApply:
    """Verify apply() correctly mutates config for each strength."""

    @pytest.mark.parametrize("strength", ["mild", "moderate", "severe"])
    def test_mutates_input_dim(self, tmp_path, strength):
        workspace = _make_workspace(tmp_path)
        op = ShapeMismatchOperator()
        rng = Random(42)

        manifest = op.apply(workspace, rng, strength)

        # Config should be updated
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["model"]["input_dim"] == _STRENGTH_DIM[strength]

        # Manifest should record the mutation
        assert isinstance(manifest, Manifest)
        assert manifest.operator_id == "crash.shape_mismatch.v1"
        assert manifest.layer == "execution"
        assert manifest.strength == strength
        assert len(manifest.mutations) == 1

        m = manifest.mutations[0]
        assert m.file == "config.yaml"
        assert m.key_path == "model.input_dim"
        assert m.original_value is None  # key absent in clean config
        assert m.mutated_value == _STRENGTH_DIM[strength]

    def test_invalid_strength(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        op = ShapeMismatchOperator()
        with pytest.raises(ValueError, match="Unknown strength"):
            op.apply(workspace, Random(0), "extreme")


class TestEvidence:
    """Verify evidence() returns correct structural refs."""

    def test_returns_config_key_and_line_range(self):
        refs = ShapeMismatchOperator().evidence()
        assert len(refs) == 2
        assert all(isinstance(r, EvidenceRef) for r in refs)

        kinds = [r.kind for r in refs]
        assert kinds == ["config_key", "line_range"]

    def test_config_key_ref(self):
        refs = ShapeMismatchOperator().evidence()
        config_ref = [r for r in refs if r.kind == "config_key"][0]
        assert config_ref.artifact_id == "config.yaml"
        assert config_ref.detail["key_path"] == "model.input_dim"

    def test_line_range_ref(self):
        refs = ShapeMismatchOperator().evidence()
        lr_ref = [r for r in refs if r.kind == "line_range"][0]
        assert lr_ref.artifact_id == "logs/stdout.log"
        assert lr_ref.detail["start_line"] == 2
        assert lr_ref.detail["end_line"] == 24


class TestAdmissibleRepairs:
    """Verify admissible_repairs() schema."""

    def test_schema_type(self):
        schema = ShapeMismatchOperator().admissible_repairs()
        assert isinstance(schema, RepairSpecSchema)
        assert schema.repair_type == "config_patch"

    def test_correct_value_in_range(self):
        schema = ShapeMismatchOperator().admissible_repairs()
        lo, hi = schema.value_ranges["model.input_dim"]
        assert lo <= 105 <= hi, "Correct input_dim 105 must be in admissible range"

    def test_faulty_values_outside_range(self):
        schema = ShapeMismatchOperator().admissible_repairs()
        lo, hi = schema.value_ranges["model.input_dim"]
        for strength, faulty_dim in _STRENGTH_DIM.items():
            assert faulty_dim < lo, (
                f"Faulty dim {faulty_dim} ({strength}) must be below repair range "
                f"lower bound {lo} — otherwise 'change nothing' is admissible"
            )


# --------------------------------------------------------------------------
# Integration tests (actual training runs)
# --------------------------------------------------------------------------

_INTEGRATION_SEEDS = [0, 1, 2]


def _skip_if_no_data():
    """Skip integration tests if data hasn't been prepared."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")


def _run_training(workspace: Path, config: dict, seed: int, output_dir: Path) -> int:
    """Run a training job and return exitcode."""
    import subprocess
    import sys

    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    result = subprocess.run(
        [
            sys.executable,
            str(workspace / "train.py"),
            "--config", str(config_path),
            "--data-dir", str(WORKLOAD_DIR / ".data"),
            "--output-dir", str(output_dir),
            "--seed", str(seed),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode


@pytest.mark.parametrize("seed", _INTEGRATION_SEEDS)
def test_clean_run_passes_tolerance(tmp_path, seed):
    """Clean config on each seed must produce acc >= tolerance_lower."""
    _skip_if_no_data()

    tolerance = _load_tolerance()
    workspace = _make_workspace(tmp_path)

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, seed, output_dir)
    assert exitcode == 0, "Clean training run failed"

    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint

    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    result = evaluate_checkpoint(ckpt, hidden_dir, config)
    acc = result["metric_hidden_test_acc"]

    assert acc >= tolerance, (
        f"Clean run seed={seed} acc={acc:.6f} < tolerance={tolerance:.6f}"
    )


@pytest.mark.parametrize(
    "strength,seed",
    [
        (s, seed)
        for s in ["mild", "moderate", "severe"]
        for seed in _INTEGRATION_SEEDS
    ],
)
def test_mutated_run_crashes(tmp_path, strength, seed):
    """Mutated run must crash (exitcode != 0), produce no checkpoint,
    and have RuntimeError traceback in stdout.log."""
    _skip_if_no_data()

    workspace = _make_workspace(tmp_path)

    op = ShapeMismatchOperator()
    op.apply(workspace, Random(seed), strength)

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, seed, output_dir)

    # Crash-tier invariant: run must fail
    assert exitcode != 0, (
        f"Mutated run completed (strength={strength}, seed={seed}); "
        "crash operators must fail"
    )

    # No checkpoint produced
    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    assert not ckpt.exists(), (
        f"Checkpoint exists (strength={strength}, seed={seed}); "
        "crash operators must not produce checkpoints"
    )

    # Traceback in stdout.log
    log_path = output_dir / "logs" / "stdout.log"
    assert log_path.exists(), "stdout.log missing after crash"
    log_text = log_path.read_text()
    assert "RuntimeError" in log_text, "stdout.log missing RuntimeError"
    assert "shapes cannot be multiplied" in log_text, (
        "stdout.log missing shape mismatch message"
    )


@pytest.mark.parametrize("seed", [100, 101, 102])
def test_oracle_repair_recovers(tmp_path, seed):
    """Repair with model.input_dim=105 must complete and pass tolerance.

    Uses hidden eval seeds [100, 101, 102] to match recovery verification.
    """
    _skip_if_no_data()

    tolerance = _load_tolerance()
    workspace = _make_workspace(tmp_path)

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Set oracle repair value
    config.setdefault("model", {})["input_dim"] = 105

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, seed, output_dir)
    assert exitcode == 0, f"Oracle repair crashed on seed={seed}"

    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    assert ckpt.exists(), f"Oracle repair missing checkpoint on seed={seed}"

    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint

    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    result = evaluate_checkpoint(ckpt, hidden_dir, config)
    acc = result["metric_hidden_test_acc"]

    assert acc >= tolerance, (
        f"Oracle repair seed={seed} acc={acc:.6f} < tolerance={tolerance:.6f}"
    )
