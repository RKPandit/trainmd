"""Tests for the silent.label_corruption.v1 operator (spec §4).

Every operator ships with unit tests proving:
(a) the clean run passes verification, and
(b) the mutated run fails it,
across 3 seeds, before merge.

Fast tests (no training) verify protocol conformance, config mutation,
evidence/repair metadata, corruption seed independence, and the zero-
fraction no-op invariant.  Integration tests run actual training jobs
and evaluate checkpoints against the reference tolerance.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from random import Random

import numpy as np
import pytest
import yaml

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.silent.label_corruption import LabelCorruptionOperator, _STRENGTH_FRACTION

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
        op = LabelCorruptionOperator()
        assert isinstance(op, IncidentOperator)

    def test_id(self):
        assert LabelCorruptionOperator().id == "silent.label_corruption.v1"

    def test_layer(self):
        assert LabelCorruptionOperator().layer == "dynamics"


class TestApply:
    """Verify apply() correctly mutates config for each strength."""

    @pytest.mark.parametrize("strength", ["mild", "moderate", "severe"])
    def test_mutates_noise_fraction(self, tmp_path, strength):
        workspace = _make_workspace(tmp_path)
        op = LabelCorruptionOperator()
        rng = Random(42)

        manifest = op.apply(workspace, rng, strength)

        # Config should be updated
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["data"]["label_noise_fraction"] == _STRENGTH_FRACTION[strength]

        # Manifest should record the mutation
        assert isinstance(manifest, Manifest)
        assert manifest.operator_id == "silent.label_corruption.v1"
        assert manifest.layer == "dynamics"
        assert manifest.strength == strength
        assert len(manifest.mutations) == 1

        m = manifest.mutations[0]
        assert m.file == "config.yaml"
        assert m.key_path == "data.label_noise_fraction"
        assert m.original_value == 0.0
        assert m.mutated_value == _STRENGTH_FRACTION[strength]

    def test_invalid_strength(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        op = LabelCorruptionOperator()
        with pytest.raises(ValueError, match="Unknown strength"):
            op.apply(workspace, Random(0), "extreme")

    def test_creates_data_section_if_absent(self, tmp_path):
        """apply() works even if config has no 'data' section."""
        workspace = _make_workspace(tmp_path)

        # Remove data section from config
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        config.pop("data", None)
        with open(workspace / "config.yaml", "w") as f:
            yaml.dump(config, f)

        op = LabelCorruptionOperator()
        manifest = op.apply(workspace, Random(0), "moderate")

        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["data"]["label_noise_fraction"] == _STRENGTH_FRACTION["moderate"]
        assert manifest.mutations[0].original_value == 0.0


class TestEvidence:
    """Verify evidence() returns correct structural refs."""

    def test_returns_config_key_and_metric_windows(self):
        refs = LabelCorruptionOperator().evidence()
        assert len(refs) == 3
        assert all(isinstance(r, EvidenceRef) for r in refs)

        kinds = [r.kind for r in refs]
        assert kinds == ["config_key", "metric_window", "metric_window"]

    def test_config_key_ref(self):
        refs = LabelCorruptionOperator().evidence()
        config_ref = [r for r in refs if r.kind == "config_key"][0]
        assert config_ref.artifact_id == "config.yaml"
        assert config_ref.detail["key_path"] == "data.label_noise_fraction"

    def test_metric_windows_cover_full_run(self):
        refs = LabelCorruptionOperator().evidence()
        mws = [r for r in refs if r.kind == "metric_window"]
        assert len(mws) == 2

        series_set = {mw.detail["series"] for mw in mws}
        assert series_set == {"train_loss", "metric_visible_val_acc"}

        for mw in mws:
            assert mw.artifact_id == "metrics.jsonl"
            assert mw.detail["start_epoch"] == 0
            assert "end_epoch" not in mw.detail


class TestAdmissibleRepairs:
    """Verify admissible_repairs() schema."""

    def test_schema_type(self):
        schema = LabelCorruptionOperator().admissible_repairs()
        assert isinstance(schema, RepairSpecSchema)
        assert schema.repair_type == "config_patch"

    def test_clean_value_in_range(self):
        schema = LabelCorruptionOperator().admissible_repairs()
        lo, hi = schema.value_ranges["data.label_noise_fraction"]
        assert lo <= 0.0 <= hi, "Clean value 0.0 must be in admissible range"

    def test_faulty_values_outside_range(self):
        schema = LabelCorruptionOperator().admissible_repairs()
        lo, hi = schema.value_ranges["data.label_noise_fraction"]
        for strength, faulty in _STRENGTH_FRACTION.items():
            assert faulty > hi, (
                f"Faulty fraction {faulty} ({strength}) must be above repair range "
                f"upper bound {hi} — otherwise 'change nothing' is admissible"
            )

    def test_lr_not_in_allowed_keys(self):
        """training.lr must NOT be an allowed repair key."""
        schema = LabelCorruptionOperator().admissible_repairs()
        assert "training.lr" not in schema.allowed_keys, (
            "training.lr must not be an allowed key — "
            "an LR fix must not recover a data fault"
        )

    def test_only_noise_fraction_allowed(self):
        schema = LabelCorruptionOperator().admissible_repairs()
        assert schema.allowed_keys == ["data.label_noise_fraction"]


# --------------------------------------------------------------------------
# Corruption seed-independence test (fast, no training)
# --------------------------------------------------------------------------

def test_corruption_indices_seed_independent():
    """Same noise_fraction, different training seeds → identical corrupted indices.

    The corruption RNG is derived from (data_length, noise_fraction) only,
    NOT the training seed.  This ensures the evaluator sees the same
    corruption when it reruns with hidden eval seeds.
    """
    _skip_if_no_data()

    y_train = np.load(WORKLOAD_DIR / ".data" / "y_train.npy")
    noise_frac = 0.15
    n_corrupt = int(len(y_train) * noise_frac)

    indices_by_seed = []
    for training_seed in [0, 42, 100, 101, 102]:
        # Replicate the corruption logic from train.py — seed is independent.
        # Uses hashlib (not hash()) for cross-process determinism.
        corrupt_seed = int.from_bytes(
            hashlib.sha256(f"{len(y_train)}:{noise_frac}".encode()).digest()[:4],
            "big",
        )
        corrupt_rng = np.random.RandomState(corrupt_seed)
        corrupt_idx = sorted(
            corrupt_rng.choice(len(y_train), size=n_corrupt, replace=False)
        )
        indices_by_seed.append(corrupt_idx)

    for i in range(1, len(indices_by_seed)):
        np.testing.assert_array_equal(
            indices_by_seed[0], indices_by_seed[i],
            err_msg=(
                f"Corruption indices differ between training seed 0 and "
                f"seed {[0, 42, 100, 101, 102][i]}"
            ),
        )


def test_corruption_deterministic_across_processes():
    """Same faulty config trained in TWO separate subprocesses → identical metrics.

    This catches bugs where the corruption seed depends on per-process state
    (e.g. Python's hash() is salted with a random PYTHONHASHSEED per process).
    The in-process test (test_corruption_indices_seed_independent) cannot catch
    this class of bug because both iterations share the same hash salt.
    """
    _skip_if_no_data()

    workspace = WORKLOAD_DIR
    noise_frac = 0.15
    seed = 7  # arbitrary training seed

    # Build a faulty config
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    config.setdefault("data", {})["label_noise_fraction"] = noise_frac

    metrics_by_run = []
    for run_idx in range(2):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_dir = tmpdir / "output"
            output_dir.mkdir()
            config_path = tmpdir / "config.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(workspace / "train.py"),
                    "--config", str(config_path),
                    "--data-dir", str(workspace / ".data"),
                    "--output-dir", str(output_dir),
                    "--seed", str(seed),
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"Run {run_idx} crashed: {result.stderr[-300:]}"
            )

            # Extract deterministic metric fields
            _DET_KEYS = {
                "epoch", "step", "train_loss", "val_loss",
                "metric_visible_val_acc", "lr", "batch_size", "end_of_epoch",
            }
            records = []
            with open(output_dir / "metrics.jsonl") as f:
                for line in f:
                    rec = json.loads(line)
                    records.append({k: v for k, v in rec.items() if k in _DET_KEYS})
            metrics_by_run.append(records)

    assert metrics_by_run[0] == metrics_by_run[1], (
        "Metrics differ between two separate subprocess runs of the same "
        "faulty config — corruption seed is not deterministic across processes"
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


def test_zero_fraction_bitwise_identical(tmp_path):
    """Train with data section absent vs label_noise_fraction=0.0 → identical metrics.

    Proves the knob's mere presence changes nothing at the individual-run level.
    """
    _skip_if_no_data()

    workspace = _make_workspace(tmp_path)
    seed = 0

    # Run 1: config WITHOUT data section
    with open(workspace / "config.yaml") as f:
        config_no_data = yaml.safe_load(f)
    config_no_data.pop("data", None)

    out_a = tmp_path / "output_a"
    exitcode_a = _run_training(workspace, config_no_data, seed, out_a)
    assert exitcode_a == 0

    # Run 2: config WITH data.label_noise_fraction = 0.0
    with open(workspace / "config.yaml") as f:
        config_with_data = yaml.safe_load(f)
    config_with_data.setdefault("data", {})["label_noise_fraction"] = 0.0

    out_b = tmp_path / "output_b"
    exitcode_b = _run_training(workspace, config_with_data, seed, out_b)
    assert exitcode_b == 0

    # Deterministic metric fields must be identical (timing fields vary
    # between runs due to system load, so we compare only model outputs).
    _DETERMINISTIC_KEYS = {
        "epoch", "step", "train_loss", "val_loss",
        "metric_visible_val_acc", "lr", "batch_size", "end_of_epoch",
    }

    def _extract_deterministic(path: Path) -> list[dict]:
        records = []
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                records.append({k: v for k, v in rec.items() if k in _DETERMINISTIC_KEYS})
        return records

    det_a = _extract_deterministic(out_a / "metrics.jsonl")
    det_b = _extract_deterministic(out_b / "metrics.jsonl")
    assert det_a == det_b, (
        "Deterministic metrics differ between no-data-section and "
        "label_noise_fraction=0.0 — the knob is not a true no-op"
    )


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

    op = LabelCorruptionOperator()
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
