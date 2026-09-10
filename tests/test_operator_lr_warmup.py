"""Tests for the silent.lr_warmup.v1 operator (spec §4).

Every operator ships with unit tests proving:
(a) the clean run passes verification, and
(b) the mutated run fails it,
across 3 seeds, before merge.

Fast tests (no training) verify protocol conformance, config mutation,
and evidence/repair metadata.  Integration tests run actual training
jobs and evaluate checkpoints against the reference tolerance.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from random import Random

import pytest
import yaml

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.silent.lr_warmup import LrWarmupOperator, _STRENGTH_LR

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
        op = LrWarmupOperator()
        assert isinstance(op, IncidentOperator)

    def test_id(self):
        assert LrWarmupOperator().id == "silent.lr_warmup.v1"

    def test_layer(self):
        assert LrWarmupOperator().layer == "dynamics"

    def test_accepted_classes(self):
        classes = LrWarmupOperator().accepted_classes()
        assert isinstance(classes, frozenset)
        assert len(classes) > 0
        assert "lr_misconfiguration" in classes


class TestApply:
    """Verify apply() correctly mutates config for each strength."""

    @pytest.mark.parametrize("strength", ["mild", "moderate", "severe"])
    def test_mutates_lr(self, tmp_path, strength):
        workspace = _make_workspace(tmp_path)
        op = LrWarmupOperator()
        rng = Random(42)

        manifest = op.apply(workspace, rng, strength)

        # Config should be updated
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["training"]["lr"] == _STRENGTH_LR[strength]

        # Manifest should record the mutation
        assert isinstance(manifest, Manifest)
        assert manifest.operator_id == "silent.lr_warmup.v1"
        assert manifest.layer == "dynamics"
        assert manifest.strength == strength
        assert len(manifest.mutations) == 1

        m = manifest.mutations[0]
        assert m.file == "config.yaml"
        assert m.key_path == "training.lr"
        assert m.original_value == 0.01
        assert m.mutated_value == _STRENGTH_LR[strength]

    def test_invalid_strength(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        op = LrWarmupOperator()
        with pytest.raises(ValueError, match="Unknown strength"):
            op.apply(workspace, Random(0), "extreme")


class TestEvidence:
    """Verify evidence() returns correct structural refs."""

    def test_returns_config_key_and_metric_windows(self):
        refs = LrWarmupOperator().evidence()
        assert len(refs) == 3
        assert all(isinstance(r, EvidenceRef) for r in refs)

        kinds = [r.kind for r in refs]
        assert kinds == ["config_key", "metric_window", "metric_window"]

    def test_config_key_ref(self):
        refs = LrWarmupOperator().evidence()
        config_ref = [r for r in refs if r.kind == "config_key"][0]
        assert config_ref.artifact_id == "config.yaml"
        assert config_ref.detail["key_path"] == "training.lr"

    def test_metric_windows_cover_full_run(self):
        refs = LrWarmupOperator().evidence()
        mws = [r for r in refs if r.kind == "metric_window"]
        assert len(mws) == 2

        series_set = {mw.detail["series"] for mw in mws}
        assert series_set == {"train_loss", "metric_visible_val_acc"}

        for mw in mws:
            assert mw.artifact_id == "metrics.jsonl"
            assert mw.detail["start_epoch"] == 0
            # end_epoch omitted — high LR corrupts the entire run
            assert "end_epoch" not in mw.detail


class TestAdmissibleRepairs:
    """Verify admissible_repairs() schema."""

    def test_schema_type(self):
        schema = LrWarmupOperator().admissible_repairs()
        assert isinstance(schema, RepairSpecSchema)
        assert schema.repair_type == "config_patch"

    def test_reference_value_in_range(self):
        schema = LrWarmupOperator().admissible_repairs()
        lo, hi = schema.value_ranges["training.lr"]
        assert lo <= 0.01 <= hi, "Reference LR 0.01 must be in admissible range"

    def test_faulty_values_outside_range(self):
        schema = LrWarmupOperator().admissible_repairs()
        lo, hi = schema.value_ranges["training.lr"]
        for strength, faulty_lr in _STRENGTH_LR.items():
            assert faulty_lr > hi, (
                f"Faulty LR {faulty_lr} ({strength}) must be above repair range "
                f"upper bound {hi} — otherwise 'change nothing' is admissible"
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
    import sys
    import subprocess

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


def _metrics_are_finite(output_dir: Path) -> bool:
    """Check that all numeric values in metrics.jsonl are finite."""
    with open(output_dir / "metrics.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            for v in rec.values():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return False
    return True


def _evaluate_acc(output_dir: Path, config: dict) -> float:
    """Evaluate checkpoint and return hidden test accuracy."""
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint

    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    result = evaluate_checkpoint(ckpt, hidden_dir, config)
    return result["metric_hidden_test_acc"]


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

    acc = _evaluate_acc(output_dir, config)
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
def test_mutated_run_fails_tolerance(tmp_path, strength, seed):
    """Mutated run must complete (exitcode=0), have finite metrics, and fail tolerance."""
    _skip_if_no_data()

    tolerance = _load_tolerance()
    workspace = _make_workspace(tmp_path)

    op = LrWarmupOperator()
    op.apply(workspace, Random(seed), strength)

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, seed, output_dir)

    # Silent-layer invariant: run must complete
    assert exitcode == 0, (
        f"Mutated run crashed (strength={strength}, seed={seed}); "
        "silent operators must produce completed runs"
    )

    # Silent-layer invariant: all metrics finite
    assert _metrics_are_finite(output_dir), (
        f"Mutated run produced NaN/Inf metrics (strength={strength}, seed={seed}); "
        "silent operators must produce finite metrics"
    )

    # Checkpoint must exist
    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    assert ckpt.exists(), (
        f"Checkpoint missing (strength={strength}, seed={seed})"
    )

    # Must fail tolerance
    acc = _evaluate_acc(output_dir, config)
    assert acc < tolerance, (
        f"Mutated run seed={seed} strength={strength} "
        f"acc={acc:.6f} >= tolerance={tolerance:.6f} — "
        "operator must reliably degrade accuracy below tolerance"
    )
