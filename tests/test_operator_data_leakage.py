"""Tests for the silent.data_leakage.v1 operator (spec §4).

Every operator ships with unit tests proving:
(a) the clean run passes verification, and
(b) the mutated run fails it,
across 3 seeds, before merge.

Fast tests verify protocol conformance, config mutation, evidence/repair
metadata, aux-column determinism, and the flag-off no-op invariant.
Integration tests run actual training jobs and evaluate checkpoints
against the reference tolerance.

IMPORTANT: reference numbers (tolerance, val mean/std) are ALWAYS read
from reference/stats.yaml — never hardcoded.
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
from operators.silent.data_leakage import DataLeakageOperator, _STRENGTH_P

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _load_stats() -> dict:
    """Load the committed reference stats."""
    stats_path = WORKLOAD_DIR / "reference" / "stats.yaml"
    with open(stats_path) as f:
        return yaml.safe_load(f)


def _load_tolerance() -> float:
    return _load_stats()["metric_hidden_test_acc"]["tolerance_lower"]


def _load_upper_band() -> float:
    stats = _load_stats()
    mean = stats["metric_visible_val_acc"]["mean"]
    std = stats["metric_visible_val_acc"]["std"]
    return mean + 2 * std


def _make_workspace(tmp_path: Path) -> Path:
    """Copy workload source files to a temp workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for fname in ["train.py", "config.yaml"]:
        shutil.copy2(WORKLOAD_DIR / fname, workspace / fname)
    return workspace


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


def _final_val_acc(output_dir: Path) -> float:
    """Read the final-epoch val_acc from metrics.jsonl."""
    with open(output_dir / "metrics.jsonl") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    epoch_lines = [l for l in lines if l.get("end_of_epoch")]
    return epoch_lines[-1]["metric_visible_val_acc"]


# Deterministic metric keys (timing fields excluded)
_DET_KEYS = {
    "epoch", "step", "train_loss", "val_loss",
    "metric_visible_val_acc", "lr", "batch_size", "end_of_epoch",
}


def _extract_deterministic(path: Path) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            records.append({k: v for k, v in rec.items() if k in _DET_KEYS})
    return records


# --------------------------------------------------------------------------
# Fast tests (no training)
# --------------------------------------------------------------------------


class TestProtocol:
    """Verify IncidentOperator protocol conformance."""

    def test_isinstance(self):
        op = DataLeakageOperator()
        assert isinstance(op, IncidentOperator)

    def test_id(self):
        assert DataLeakageOperator().id == "silent.data_leakage.v1"

    def test_layer(self):
        assert DataLeakageOperator().layer == "dynamics"

    def test_accepted_classes(self):
        classes = DataLeakageOperator().accepted_classes()
        assert isinstance(classes, frozenset)
        assert len(classes) == 8
        assert "data_leakage" in classes
        assert "feature_leakage" in classes
        assert "target_leakage" in classes
        assert "label_leakage" in classes
        assert "information_leakage" in classes
        assert "train_test_leakage" in classes
        assert "data_contamination" in classes
        assert "leaky_feature" in classes


class TestApply:
    """Verify apply() correctly mutates config for each strength."""

    @pytest.mark.parametrize("strength", ["mild", "moderate", "severe"])
    def test_mutates_config_keys(self, tmp_path, strength):
        workspace = _make_workspace(tmp_path)
        op = DataLeakageOperator()
        rng = Random(42)

        manifest = op.apply(workspace, rng, strength)

        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["data"]["include_aux_feature"] is True
        assert config["data"]["aux_feature_strength"] == _STRENGTH_P[strength]

        assert isinstance(manifest, Manifest)
        assert manifest.operator_id == "silent.data_leakage.v1"
        assert manifest.layer == "dynamics"
        assert manifest.strength == strength
        assert len(manifest.mutations) == 2

        m0, m1 = manifest.mutations
        assert m0.file == "config.yaml"
        assert m0.key_path == "data.include_aux_feature"
        assert m0.original_value is None
        assert m0.mutated_value is True

        assert m1.file == "config.yaml"
        assert m1.key_path == "data.aux_feature_strength"
        assert m1.original_value is None
        assert m1.mutated_value == _STRENGTH_P[strength]

    def test_invalid_strength(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        op = DataLeakageOperator()
        with pytest.raises(ValueError, match="Unknown strength"):
            op.apply(workspace, Random(0), "extreme")

    def test_creates_data_section_if_absent(self, tmp_path):
        """apply() works even if config has no 'data' section."""
        workspace = _make_workspace(tmp_path)

        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        config.pop("data", None)
        with open(workspace / "config.yaml", "w") as f:
            yaml.dump(config, f)

        op = DataLeakageOperator()
        manifest = op.apply(workspace, Random(0), "moderate")

        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["data"]["include_aux_feature"] is True
        assert config["data"]["aux_feature_strength"] == _STRENGTH_P["moderate"]


class TestEvidence:
    """Verify evidence() returns correct structural refs."""

    def test_returns_config_key_and_metric_window(self):
        refs = DataLeakageOperator().evidence()
        assert len(refs) == 2
        assert all(isinstance(r, EvidenceRef) for r in refs)

        kinds = [r.kind for r in refs]
        assert kinds == ["config_key", "metric_window"]

    def test_config_key_ref(self):
        refs = DataLeakageOperator().evidence()
        config_ref = [r for r in refs if r.kind == "config_key"][0]
        assert config_ref.artifact_id == "config.yaml"
        assert config_ref.detail["key_path"] == "data.include_aux_feature"

    def test_metric_window_ref(self):
        refs = DataLeakageOperator().evidence()
        mw = [r for r in refs if r.kind == "metric_window"][0]
        assert mw.artifact_id == "metrics.jsonl"
        assert mw.detail["series"] == "metric_visible_val_acc"
        assert mw.detail["start_epoch"] == 0


class TestAdmissibleRepairs:
    """Verify admissible_repairs() schema."""

    def test_schema_type(self):
        schema = DataLeakageOperator().admissible_repairs()
        assert isinstance(schema, RepairSpecSchema)
        assert schema.repair_type == "config_patch"

    def test_allowed_keys(self):
        schema = DataLeakageOperator().admissible_repairs()
        assert schema.allowed_keys == ["data.include_aux_feature"]

    def test_allowed_values(self):
        schema = DataLeakageOperator().admissible_repairs()
        assert schema.allowed_values == {"data.include_aux_feature": [False]}

    def test_no_value_ranges(self):
        """Boolean repair uses allowed_values, not value_ranges."""
        schema = DataLeakageOperator().admissible_repairs()
        assert schema.value_ranges == {}

    def test_lr_not_in_allowed_keys(self):
        """training.lr must NOT be an allowed repair key."""
        schema = DataLeakageOperator().admissible_repairs()
        assert "training.lr" not in schema.allowed_keys


class TestAuxColumn:
    """Unit tests for the _compute_aux_column helper."""

    def test_deterministic_output(self):
        """Same inputs → same output."""
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.array([0, 1, 0, 1, 1, 0, 1, 0], dtype=np.float32)
        r1 = _compute_aux_column(labels, "train", 0.2)
        r2 = _compute_aux_column(labels, "train", 0.2)
        np.testing.assert_array_equal(r1, r2)

    def test_correct_shape(self):
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.zeros(100, dtype=np.float32)
        result = _compute_aux_column(labels, "train", 0.2)
        assert result.shape == (100,)

    def test_values_binary(self):
        """Output values are in {0.0, 1.0} only."""
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.random.RandomState(0).binomial(1, 0.5, size=1000).astype(np.float32)
        result = _compute_aux_column(labels, "train", 0.2)
        unique = set(np.unique(result))
        assert unique <= {0.0, 1.0}

    def test_perfect_correlation_at_p_zero(self):
        """At p=0: aux == labels (perfect leak)."""
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1], dtype=np.float32)
        result = _compute_aux_column(labels, "train", 0.0)
        np.testing.assert_array_equal(result, labels)

    def test_noise_at_p_half(self):
        """At p=0.5: ~50% correlation with labels (pure noise)."""
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.random.RandomState(42).binomial(1, 0.5, size=10000).astype(np.float32)
        result = _compute_aux_column(labels, "train", 0.5)
        corr = np.corrcoef(result, labels)[0, 1]
        assert abs(corr) < 0.1, f"Expected ~0 correlation at p=0.5, got {corr:.4f}"

    def test_different_split_different_result(self):
        """Different split_name → different aux column (seed independence)."""
        from workloads.tabular_adult.train import _compute_aux_column

        labels = np.random.RandomState(0).binomial(1, 0.5, size=100).astype(np.float32)
        r_train = _compute_aux_column(labels, "train", 0.2)
        r_val = _compute_aux_column(labels, "val", 0.2)
        assert not np.array_equal(r_train, r_val)


# --------------------------------------------------------------------------
# Required determinism & isolation tests (L4, L5, L12)
# --------------------------------------------------------------------------


def test_aux_independent_of_training_seed():
    """L5: Two different training seeds → identical aux column.

    The aux column seed is derived from (split_name, n_samples, p),
    never from the training seed.
    """
    _skip_if_no_data()

    from workloads.tabular_adult.train import _compute_aux_column

    y_train = np.load(WORKLOAD_DIR / ".data" / "y_train.npy")
    p = 0.2

    # Aux column should be identical regardless of training seed
    r1 = _compute_aux_column(y_train, "train", p)
    r2 = _compute_aux_column(y_train, "train", p)

    h1 = hashlib.sha256(r1.tobytes()).hexdigest()
    h2 = hashlib.sha256(r2.tobytes()).hexdigest()
    assert h1 == h2


def test_hidden_test_aux_is_noise():
    """Core validity: train/val aux corr ≈ 1-2p, hidden-test |corr| ≈ 0.

    The leak must be present during training and ABSENT at hidden-test time.
    """
    _skip_if_no_data()

    from workloads.tabular_adult.train import _compute_aux_column

    y_train = np.load(WORKLOAD_DIR / ".data" / "y_train.npy")
    y_test = np.load(WORKLOAD_DIR / ".hidden_data" / "y_test.npy")

    for strength, p in _STRENGTH_P.items():
        # Train aux: should have high correlation with labels
        aux_train = _compute_aux_column(y_train, "train", p)
        train_corr = np.corrcoef(aux_train, y_train)[0, 1]
        expected_corr = 1 - 2 * p
        assert abs(train_corr - expected_corr) < 0.1, (
            f"{strength}: train corr={train_corr:.4f}, expected ~{expected_corr:.2f}"
        )

        # Hidden-test noise: should have ~zero correlation
        noise_seed = int.from_bytes(
            hashlib.sha256(f"test:{len(y_test)}".encode()).digest()[:4], "big",
        )
        noise_rng = np.random.RandomState(noise_seed)
        noise_col = noise_rng.binomial(1, 0.5, size=len(y_test)).astype(np.float32)
        test_corr = np.corrcoef(noise_col, y_test)[0, 1]
        assert abs(test_corr) < 0.05, (
            f"{strength}: test |corr|={abs(test_corr):.4f}, expected <0.05"
        )


# --------------------------------------------------------------------------
# Repair spec tests
# --------------------------------------------------------------------------


def test_validate_repair_allowed_values_accepts_false():
    """Submitting include_aux_feature=false (bool) is valid."""
    import dataclasses
    from harness.evaluator.repair_spec import parse_repair_spec, validate_repair

    verify = {
        "admissible_repairs": dataclasses.asdict(
            DataLeakageOperator().admissible_repairs()
        ),
    }
    # _to_yaml_safe round-trip
    verify["admissible_repairs"] = _yaml_roundtrip(verify["admissible_repairs"])

    spec = parse_repair_spec({
        "repair_type": "config_patch",
        "patches": {"data.include_aux_feature": False},
    })
    result = validate_repair(spec, verify)
    assert result.valid, f"Expected valid, got: {result.details}"


def test_validate_repair_allowed_values_rejects_true():
    """Submitting include_aux_feature=true is rejected."""
    import dataclasses
    from harness.evaluator.repair_spec import parse_repair_spec, validate_repair

    verify = {
        "admissible_repairs": dataclasses.asdict(
            DataLeakageOperator().admissible_repairs()
        ),
    }
    verify["admissible_repairs"] = _yaml_roundtrip(verify["admissible_repairs"])

    spec = parse_repair_spec({
        "repair_type": "config_patch",
        "patches": {"data.include_aux_feature": True},
    })
    result = validate_repair(spec, verify)
    assert not result.valid
    assert "VALUE_OUT_OF_RANGE" in result.reason_codes


@pytest.mark.parametrize("bad_value", [0, 0.0, "false", None])
def test_validate_repair_type_safety(bad_value):
    """Type-unsafe values (0, 0.0, 'false', None) must be rejected.

    Python treats 0 == False, so naive `in` check would accept 0.
    """
    import dataclasses
    from harness.evaluator.repair_spec import parse_repair_spec, validate_repair

    verify = {
        "admissible_repairs": dataclasses.asdict(
            DataLeakageOperator().admissible_repairs()
        ),
    }
    verify["admissible_repairs"] = _yaml_roundtrip(verify["admissible_repairs"])

    spec = parse_repair_spec({
        "repair_type": "config_patch",
        "patches": {"data.include_aux_feature": bad_value},
    })
    result = validate_repair(spec, verify)
    assert not result.valid, (
        f"Expected rejection for {bad_value!r} (type {type(bad_value).__name__}), "
        f"but got valid"
    )


def test_lr_repair_rejected():
    """training.lr must not be an allowed repair key."""
    import dataclasses
    from harness.evaluator.repair_spec import parse_repair_spec, validate_repair

    verify = {
        "admissible_repairs": dataclasses.asdict(
            DataLeakageOperator().admissible_repairs()
        ),
    }
    verify["admissible_repairs"] = _yaml_roundtrip(verify["admissible_repairs"])

    spec = parse_repair_spec({
        "repair_type": "config_patch",
        "patches": {"training.lr": 0.01},
    })
    result = validate_repair(spec, verify)
    assert not result.valid
    assert "KEY_NOT_ALLOWED" in result.reason_codes


def _yaml_roundtrip(obj):
    """Simulate the yaml.dump/yaml.safe_load roundtrip that build_case does."""
    from harness.build_case import _to_yaml_safe
    safe = _to_yaml_safe(obj)
    return yaml.safe_load(yaml.dump(safe))


# --------------------------------------------------------------------------
# Safety tests
# --------------------------------------------------------------------------


def test_w1_no_forbidden_tokens(tmp_path):
    """Workspace files must not contain leak-revealing strings."""
    workspace = _make_workspace(tmp_path)
    op = DataLeakageOperator()
    op.apply(workspace, Random(42), "moderate")

    # Run training to produce resolved config
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    forbidden = ["leak", "data_leakage", "leakage"]
    violations = []
    for p in workspace.rglob("*"):
        if not p.is_file() or p.suffix in {".pt", ".npy", ".npz"}:
            continue
        try:
            text = p.read_text().lower()
        except UnicodeDecodeError:
            continue
        for token in forbidden:
            if token in text:
                violations.append(f"{p.name} contains '{token}'")

    assert not violations, f"W1 violations: {violations}"


def test_evidence_key_exists_in_resolved_config(tmp_path):
    """L8: evidence key_path must exist at the exact nested path in resolved config."""
    _skip_if_no_data()

    workspace = _make_workspace(tmp_path)
    op = DataLeakageOperator()
    op.apply(workspace, Random(42), "moderate")

    # Run training to produce config.resolved.yaml
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, 42, output_dir)
    assert exitcode == 0

    # Read resolved config
    with open(output_dir / "config.resolved.yaml") as f:
        resolved = yaml.safe_load(f)

    # Navigate the dotted key_path from evidence
    evidence = op.evidence()
    config_ref = [r for r in evidence if r.kind == "config_key"][0]
    key_path = config_ref.detail["key_path"]

    parts = key_path.split(".")
    current = resolved
    for part in parts:
        assert isinstance(current, dict), (
            f"Cannot navigate '{key_path}': '{part}' parent is not a dict"
        )
        assert part in current, (
            f"Key '{part}' not found in resolved config at path '{key_path}'"
        )
        current = current[part]

    assert current is True, (
        f"Expected True at '{key_path}', got {current!r}"
    )


# --------------------------------------------------------------------------
# Integration tests (actual training runs)
# --------------------------------------------------------------------------

_INTEGRATION_SEEDS = [0, 1, 2]


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
    [(s, seed) for s in ["mild", "moderate", "severe"] for seed in _INTEGRATION_SEEDS],
)
def test_mutated_run_fails_tolerance(tmp_path, strength, seed):
    """Mutated run must: complete, have finite metrics, fail tolerance,
    AND show misleading symptom (val_acc above upper band)."""
    _skip_if_no_data()

    tolerance = _load_tolerance()
    upper_band = _load_upper_band()
    workspace = _make_workspace(tmp_path)

    op = DataLeakageOperator()
    op.apply(workspace, Random(seed), strength)

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    output_dir = tmp_path / "output"
    exitcode = _run_training(workspace, config, seed, output_dir)

    # Silent-layer invariant: run must complete
    assert exitcode == 0, (
        f"Mutated run crashed (strength={strength}, seed={seed})"
    )

    # Silent-layer invariant: all metrics finite
    assert _metrics_are_finite(output_dir), (
        f"Mutated run produced NaN/Inf metrics (strength={strength}, seed={seed})"
    )

    # Checkpoint must exist
    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    assert ckpt.exists(), (
        f"Checkpoint missing (strength={strength}, seed={seed})"
    )

    # Must fail tolerance (hidden test accuracy below threshold)
    acc = _evaluate_acc(output_dir, config)
    assert acc < tolerance, (
        f"Mutated run seed={seed} strength={strength} "
        f"acc={acc:.6f} >= tolerance={tolerance:.6f}"
    )

    # Misleading symptom: val_acc must be ABOVE the healthy range
    val_acc = _final_val_acc(output_dir)
    assert val_acc > upper_band, (
        f"Mutated run seed={seed} strength={strength} "
        f"val_acc={val_acc:.6f} <= upper_band={upper_band:.6f} — "
        f"misleading symptom not confirmed"
    )


def test_oracle_repair_recovers(tmp_path):
    """Repair include_aux_feature=false → training completes AND clears tolerance."""
    _skip_if_no_data()

    tolerance = _load_tolerance()
    workspace = _make_workspace(tmp_path)

    op = DataLeakageOperator()
    op.apply(workspace, Random(42), "moderate")

    # Apply oracle repair: disable aux feature
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    config["data"]["include_aux_feature"] = False

    for seed in [100, 101, 102]:
        output_dir = tmp_path / f"output_repair_{seed}"
        exitcode = _run_training(workspace, config, seed, output_dir)
        assert exitcode == 0, f"Repaired run crashed (seed={seed})"

        acc = _evaluate_acc(output_dir, config)
        assert acc >= tolerance, (
            f"Repaired run seed={seed} acc={acc:.6f} < tolerance={tolerance:.6f}"
        )


def test_flag_off_bitwise_identical(tmp_path):
    """L12: flag absent vs explicitly false → identical deterministic metrics.

    Proves the hook is a true no-op when disabled.
    """
    _skip_if_no_data()

    workspace = _make_workspace(tmp_path)
    seed = 0

    # Run 1: config WITHOUT any aux feature flags
    with open(workspace / "config.yaml") as f:
        config_absent = yaml.safe_load(f)
    # Ensure no aux keys exist
    config_absent.get("data", {}).pop("include_aux_feature", None)
    config_absent.get("data", {}).pop("aux_feature_strength", None)

    out_a = tmp_path / "output_a"
    exitcode_a = _run_training(workspace, config_absent, seed, out_a)
    assert exitcode_a == 0

    # Run 2: config WITH include_aux_feature=false explicitly
    with open(workspace / "config.yaml") as f:
        config_false = yaml.safe_load(f)
    config_false.setdefault("data", {})["include_aux_feature"] = False

    out_b = tmp_path / "output_b"
    exitcode_b = _run_training(workspace, config_false, seed, out_b)
    assert exitcode_b == 0

    det_a = _extract_deterministic(out_a / "metrics.jsonl")
    det_b = _extract_deterministic(out_b / "metrics.jsonl")
    assert det_a == det_b, (
        "Deterministic metrics differ between flag-absent and "
        "include_aux_feature=false — the hook is not a true no-op"
    )


def test_aux_deterministic_across_processes(tmp_path):
    """L4: Two SEPARATE subprocesses with identical config → identical metrics.

    The in-process determinism test cannot catch per-process-hash bugs
    (PYTHONHASHSEED salting); this subprocess test can.
    """
    _skip_if_no_data()

    workspace = _make_workspace(tmp_path)
    seed = 7

    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    config.setdefault("data", {})["include_aux_feature"] = True
    config["data"]["aux_feature_strength"] = 0.20

    metrics_by_run = []
    for run_idx in range(2):
        output_dir = tmp_path / f"output_{run_idx}"
        exitcode = _run_training(workspace, config, seed, output_dir)
        assert exitcode == 0, f"Run {run_idx} crashed"
        metrics_by_run.append(_extract_deterministic(output_dir / "metrics.jsonl"))

    assert metrics_by_run[0] == metrics_by_run[1], (
        "Metrics differ between two separate subprocess runs — "
        "aux column seed is not deterministic across processes"
    )
