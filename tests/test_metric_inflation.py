"""Tests for the silent.metric_inflation.v1 operator (metric tier, spec §4).

Every operator ships with unit tests proving (a) a clean run passes and (b) the
mutated run "fails" per its tier, on 3 seeds, before merge. For the METRIC tier
"fails" means: the run completes, the model is HEALTHY (hidden within band), and
the REPORTED visible metric is inflated above the band.

The operator's scientific guarantee — the model is untouched — is proved as a
test: the saved checkpoint is BITWISE identical to a clean run's checkpoint at the
same seed. If that ever breaks, the mechanism has stopped being metric-only.

Reference numbers (band, tolerance) are ALWAYS read from reference/stats.yaml.
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

import pytest
import torch
import yaml

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.metric.metric_inflation import MetricInflationOperator, _STRENGTH_Q, _KNOB

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _load_stats() -> dict:
    with open(WORKLOAD_DIR / "reference" / "stats.yaml") as f:
        return yaml.safe_load(f)


def _load_tolerance() -> float:
    return _load_stats()["metric_hidden_test_acc"]["tolerance_lower"]


def _visible_band() -> tuple[float, float, float]:
    """Return (mean, std, upper=mean+2σ) for the visible metric."""
    v = _load_stats()["metric_visible_val_acc"]
    return v["mean"], v["std"], v["mean"] + 2 * v["std"]


def _hidden_band() -> tuple[float, float]:
    """Return (lower=mean-2σ=tolerance, upper=mean+2σ) for the hidden metric."""
    h = _load_stats()["metric_hidden_test_acc"]
    return h["mean"] - 2 * h["std"], h["mean"] + 2 * h["std"]


def _make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, workspace / fname)
    return workspace


def _skip_if_no_data():
    if not (WORKLOAD_DIR / ".data").exists() or not (WORKLOAD_DIR / ".hidden_data").exists():
        pytest.skip("Data not prepared; run `make data` first.")


def _run_training(workspace: Path, config: dict, seed: int, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    result = subprocess.run(
        [
            sys.executable, str(workspace / "train.py"),
            "--config", str(config_path),
            "--data-dir", str(WORKLOAD_DIR / ".data"),
            "--output-dir", str(output_dir),
            "--seed", str(seed),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr[-800:])
    return result.returncode


def _metrics_are_finite(output_dir: Path) -> bool:
    with open(output_dir / "metrics.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            for v in rec.values():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return False
    return True


def _evaluate_acc(output_dir: Path, config: dict) -> float:
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint
    ckpt = output_dir / "checkpoints" / "ckpt_final.pt"
    return evaluate_checkpoint(ckpt, WORKLOAD_DIR / ".hidden_data", config)["metric_hidden_test_acc"]


def _final_val_acc(output_dir: Path) -> float:
    with open(output_dir / "metrics.jsonl") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    return [l for l in lines if l.get("end_of_epoch")][-1]["metric_visible_val_acc"]


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


def _state_dict(ckpt_path: Path) -> dict:
    return torch.load(ckpt_path, map_location="cpu", weights_only=False)["model_state_dict"]


# --------------------------------------------------------------------------
# Fast tests (no training)
# --------------------------------------------------------------------------

class TestProtocol:
    def test_isinstance(self):
        assert isinstance(MetricInflationOperator(), IncidentOperator)

    def test_id(self):
        assert MetricInflationOperator().id == "silent.metric_inflation.v1"

    def test_layer_is_metric(self):
        assert MetricInflationOperator().layer == "metric"

    def test_accepted_classes_nonempty(self):
        classes = MetricInflationOperator().accepted_classes()
        assert isinstance(classes, frozenset) and classes
        assert "metric_inflation" in classes


class TestApply:
    @pytest.mark.parametrize("strength", ["mild", "moderate", "severe"])
    def test_mutates_metrics_knob(self, tmp_path, strength):
        workspace = _make_workspace(tmp_path)
        manifest = MetricInflationOperator().apply(workspace, Random(42), strength)

        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["metrics"]["eval_subset_fraction"] == _STRENGTH_Q[strength]

        assert isinstance(manifest, Manifest)
        assert manifest.operator_id == "silent.metric_inflation.v1"
        assert manifest.layer == "metric"
        assert manifest.strength == strength
        assert len(manifest.mutations) == 1
        m = manifest.mutations[0]
        assert m.file == "config.yaml"
        assert m.key_path == _KNOB
        assert m.original_value is None
        assert m.mutated_value == _STRENGTH_Q[strength]

    def test_ladder_is_monotone_and_nested(self):
        # Smaller q = stronger inflation; the kept sets are prefixes of one
        # confidence ordering, so they nest by construction.
        assert _STRENGTH_Q["severe"] < _STRENGTH_Q["moderate"] < _STRENGTH_Q["mild"]

    def test_invalid_strength(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="Unknown strength"):
            MetricInflationOperator().apply(workspace, Random(0), "extreme")

    def test_creates_metrics_section_if_absent(self, tmp_path):
        workspace = _make_workspace(tmp_path)
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        config.pop("metrics", None)
        with open(workspace / "config.yaml", "w") as f:
            yaml.dump(config, f)
        MetricInflationOperator().apply(workspace, Random(0), "moderate")
        with open(workspace / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["metrics"]["eval_subset_fraction"] == _STRENGTH_Q["moderate"]


class TestEvidence:
    def test_config_key_and_metric_window(self):
        refs = MetricInflationOperator().evidence()
        assert all(isinstance(r, EvidenceRef) for r in refs)
        assert [r.kind for r in refs] == ["config_key", "metric_window"]

    def test_config_key_is_the_mutated_knob(self):
        refs = MetricInflationOperator().evidence()
        ck = [r for r in refs if r.kind == "config_key"][0]
        assert ck.artifact_id == "config.yaml"
        assert ck.detail["key_path"] == _KNOB

    def test_metric_window_is_visible_series(self):
        refs = MetricInflationOperator().evidence()
        mw = [r for r in refs if r.kind == "metric_window"][0]
        assert mw.detail["series"] == "metric_visible_val_acc"


class TestAdmissibleRepairs:
    def test_schema(self):
        s = MetricInflationOperator().admissible_repairs()
        assert isinstance(s, RepairSpecSchema)
        assert s.repair_type == "config_patch"
        assert s.allowed_keys == [_KNOB]
        assert s.allowed_values == {_KNOB: [1.0]}
        assert s.absent_when_clean_keys == [_KNOB]

    def test_oracle_repair_is_unset_and_not_faulty(self):
        oracle = MetricInflationOperator().oracle_repair()
        assert oracle["repair_type"] == "config_patch"
        assert oracle["patches"] == {_KNOB: None}
        # oracle is the clean state, never a faulty q value
        assert None not in set(_STRENGTH_Q.values())


class TestIdentificationUniqueness:
    """The concept tokens must uniquely identify this operator."""

    @pytest.mark.parametrize("label", [
        "metric_inflation", "inflated_metric", "biased_evaluation",
        "selective_evaluation", "misleading_metric",
    ])
    def test_label_matches_only_this_operator(self, label):
        from harness.scoring import _matched_operators, _normalize_class
        from operators.registry import core_token_specs
        matched = _matched_operators(_normalize_class(label), core_token_specs())
        assert matched == ["silent.metric_inflation.v1"], matched


class TestRepairValidation:
    def _verify(self):
        import dataclasses
        from harness.build_case import _to_yaml_safe
        op = MetricInflationOperator()
        return {"admissible_repairs": yaml.safe_load(
            yaml.dump(_to_yaml_safe(dataclasses.asdict(op.admissible_repairs()))))}, op

    def test_null_unsets(self):
        from harness.evaluator.repair_spec import parse_repair_spec, validate_repair
        verify, op = self._verify()
        spec = parse_repair_spec({"repair_type": "config_patch", "patches": {_KNOB: None}})
        r = validate_repair(spec, verify, op.admissible_repairs().absent_when_clean_keys)
        assert r.valid, r.reason_codes

    def test_one_point_zero_accepted(self):
        from harness.evaluator.repair_spec import parse_repair_spec, validate_repair
        verify, _ = self._verify()
        spec = parse_repair_spec({"repair_type": "config_patch", "patches": {_KNOB: 1.0}})
        assert validate_repair(spec, verify).valid

    def test_partial_fraction_rejected(self):
        from harness.evaluator.repair_spec import parse_repair_spec, validate_repair
        verify, _ = self._verify()
        spec = parse_repair_spec({"repair_type": "config_patch", "patches": {_KNOB: 0.5}})
        r = validate_repair(spec, verify)
        assert not r.valid and "VALUE_OUT_OF_RANGE" in r.reason_codes

    def test_wrong_key_rejected(self):
        from harness.evaluator.repair_spec import parse_repair_spec, validate_repair
        verify, _ = self._verify()
        spec = parse_repair_spec({"repair_type": "config_patch", "patches": {"training.lr": 0.01}})
        r = validate_repair(spec, verify)
        assert not r.valid and "KEY_NOT_ALLOWED" in r.reason_codes


def test_w1_operator_segments_absent_from_workspace(tmp_path):
    """Operator-id segments must not appear in any agent-visible workspace byte."""
    _skip_if_no_data()
    workspace = _make_workspace(tmp_path)
    MetricInflationOperator().apply(workspace, Random(42), "moderate")
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    out = tmp_path / "run_output"
    assert _run_training(workspace, config, 42, out) == 0

    forbidden = ["silent", "metric_inflation"]
    violations = []
    for p in list(workspace.rglob("*")) + list(out.rglob("*")):
        if not p.is_file() or p.suffix in {".pt", ".npy", ".npz"}:
            continue
        try:
            text = p.read_text().lower()
        except UnicodeDecodeError:
            continue
        for token in forbidden:
            if token in text:
                violations.append(f"{p.name}: {token}")
    assert not violations, violations


# --------------------------------------------------------------------------
# Integration tests (actual training)
# --------------------------------------------------------------------------

_SEEDS = [0, 1, 2]


@pytest.mark.parametrize("seed", _SEEDS)
def test_clean_run_passes_tolerance(tmp_path, seed):
    _skip_if_no_data()
    tolerance = _load_tolerance()
    workspace = _make_workspace(tmp_path)
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    out = tmp_path / "output"
    assert _run_training(workspace, config, seed, out) == 0
    assert _evaluate_acc(out, config) >= tolerance


@pytest.mark.parametrize(
    "strength,seed",
    [(s, seed) for s in ["mild", "moderate", "severe"] for seed in _SEEDS],
)
def test_mutated_run_inflates_visible_while_model_healthy(tmp_path, strength, seed):
    """Metric tier: completes, finite, model HEALTHY (hidden in band), and the
    REPORTED visible metric is inflated above the band by >= 2σ margin."""
    _skip_if_no_data()
    v_mean, v_std, v_upper = _visible_band()
    h_lo, h_hi = _hidden_band()
    workspace = _make_workspace(tmp_path)

    MetricInflationOperator().apply(workspace, Random(seed), strength)
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    out = tmp_path / "output"
    assert _run_training(workspace, config, seed, out) == 0
    assert _metrics_are_finite(out)
    assert (out / "checkpoints" / "ckpt_final.pt").exists()

    # Model is HEALTHY: hidden test (always computed correctly) within the band.
    hidden = _evaluate_acc(out, config)
    assert h_lo <= hidden <= h_hi, (
        f"{strength}/{seed}: hidden={hidden:.6f} outside band [{h_lo:.6f},{h_hi:.6f}]"
    )

    # Reported visible metric inflated above the band, with a >= 2σ margin.
    reported = _final_val_acc(out)
    assert reported >= v_mean + 4 * v_std, (
        f"{strength}/{seed}: reported visible={reported:.6f} not >= mean+4σ="
        f"{v_mean + 4 * v_std:.6f} (needs a >=2σ margin beyond the band edge)"
    )


@pytest.mark.parametrize("seed", _SEEDS)
def test_checkpoint_bitwise_identical_to_clean(tmp_path, seed):
    """THE scientific guarantee: the mutation does not touch the model.

    A clean run and a faulty run at the same seed produce the SAME checkpoint
    tensors — the fault lives only in the reported metric.
    """
    _skip_if_no_data()
    workspace = _make_workspace(tmp_path)

    with open(workspace / "config.yaml") as f:
        clean_cfg = yaml.safe_load(f)
    out_clean = tmp_path / "clean"
    assert _run_training(workspace, clean_cfg, seed, out_clean) == 0

    faulty_cfg = yaml.safe_load(yaml.dump(clean_cfg))
    faulty_cfg.setdefault("metrics", {})["eval_subset_fraction"] = _STRENGTH_Q["moderate"]
    out_faulty = tmp_path / "faulty"
    assert _run_training(workspace, faulty_cfg, seed, out_faulty) == 0

    sd_clean = _state_dict(out_clean / "checkpoints" / "ckpt_final.pt")
    sd_faulty = _state_dict(out_faulty / "checkpoints" / "ckpt_final.pt")
    assert sd_clean.keys() == sd_faulty.keys()
    for k in sd_clean:
        assert torch.equal(sd_clean[k], sd_faulty[k]), (
            f"checkpoint tensor {k!r} differs — the fault touched the model"
        )

    # And the reported visible metric DID move (the fault is real).
    assert _final_val_acc(out_faulty) > _final_val_acc(out_clean)


def test_reported_metric_deterministic_across_processes(tmp_path):
    """L4: two separate subprocesses with the faulty config → identical metrics,
    including the biased reported val_acc (no per-process nondeterminism)."""
    _skip_if_no_data()
    workspace = _make_workspace(tmp_path)
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)
    config.setdefault("metrics", {})["eval_subset_fraction"] = _STRENGTH_Q["moderate"]

    runs = []
    for i in range(2):
        out = tmp_path / f"run_{i}"
        assert _run_training(workspace, config, 7, out) == 0
        runs.append(_extract_deterministic(out / "metrics.jsonl"))
    assert runs[0] == runs[1]


# --------------------------------------------------------------------------
# Recovery via verify_repair (new tier-aware verdict)
# --------------------------------------------------------------------------

def _build_metric_case(tmp_path: Path) -> tuple[Path, Path]:
    """Build one metric case under a temp project root (symlinked workload)."""
    project_root = tmp_path / "proj"
    (project_root / "workloads").mkdir(parents=True)
    (project_root / "workloads" / "tabular_adult").symlink_to(WORKLOAD_DIR)
    (project_root / "cases").mkdir()
    from harness.build_case import build_case
    case_dir = build_case(
        "tabular_adult", "silent.metric_inflation.v1", "moderate", 42,
        project_root=project_root,
    )
    return project_root, case_dir


def test_recovery_oracle_restores_visible_band(tmp_path):
    """Oracle repair (unset the knob) → verify_repair verdict 'recovered':
    the reported visible metric returns into the band AND hidden stays healthy."""
    _skip_if_no_data()
    project_root, case_dir = _build_metric_case(tmp_path)
    from harness.evaluator.verify_repair import verify_repair

    oracle = MetricInflationOperator().oracle_repair()
    result = verify_repair(case_dir, oracle, project_root=project_root)
    assert result["verdict"] == "recovered", result

    v_mean, v_std, v_upper = _visible_band()
    v_lo = v_mean - 2 * v_std
    tolerance = _load_tolerance()
    for r in result["per_seed_hidden_metrics"]:
        assert v_lo <= r["metric_visible_val_acc"] <= v_upper
        assert r["metric_hidden_test_acc"] >= tolerance


def test_recovery_wrong_key_is_rejected(tmp_path):
    """A repair on a non-admissible key is rejected — recovery is not free."""
    _skip_if_no_data()
    project_root, case_dir = _build_metric_case(tmp_path)
    from harness.evaluator.verify_repair import verify_repair
    result = verify_repair(
        case_dir, {"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
        project_root=project_root,
    )
    assert result["verdict"] == "rejected"
    assert "KEY_NOT_ALLOWED" in result["reason_codes"]


def test_verify_repair_trains_from_unpinned_parent_env(tmp_path, monkeypatch):
    """Regression for the Stage-2 gate bug: verify_repair spawned train.py with
    no thread-pin env, so from an UNPINNED parent every rerun exited 2 and became
    not_recovered by construction (138 cells). verify_repair must inject the pins
    itself and train successfully regardless of the parent environment.

    This also exercises build_case's spawn (which build_metric_case triggers) —
    both must inject the pins, so the whole path works from a bare parent env.
    """
    _skip_if_no_data()
    from harness.thread_pins import THREAD_CAPS

    # Simulate a bare/unpinned parent shell: strip ALL five caps from the env.
    for cap in THREAD_CAPS:
        monkeypatch.delenv(cap, raising=False)

    project_root, case_dir = _build_metric_case(tmp_path)  # build_case spawns train.py
    from harness.evaluator.verify_repair import verify_repair

    oracle = MetricInflationOperator().oracle_repair()
    result = verify_repair(case_dir, oracle, project_root=project_root)

    # It must have actually TRAINED (not exited 2 into a false not_recovered).
    assert result["verdict"] == "recovered", result
    for r in result["per_seed_hidden_metrics"]:
        assert r["exitcode"] == 0, r
        assert r["metric_hidden_test_acc"] is not None, r
        assert r["metric_visible_val_acc"] is not None, r
        assert "stderr_tail" not in r  # no failure recorded on a clean run


def test_verify_repair_subprocess_failure_is_verify_error_not_not_recovered(
    tmp_path, monkeypatch
):
    """A training subprocess that exits non-zero must yield the distinct
    verify_error verdict with the exit code + stderr recorded — never a silent
    not_recovered (which would assert 'trained but did not restore health')."""
    _skip_if_no_data()
    project_root, case_dir = _build_metric_case(tmp_path)  # real case (real build)

    import harness.evaluator.verify_repair as vr

    class _FailedProc:
        returncode = 2
        stdout = ""
        stderr = (
            "FATAL: training refuses to run without single-threaded math.\n"
            "  Not set to 1: OMP_NUM_THREADS\n"
        )

    # Only fake the TRAINING spawn (after the real build has completed).
    monkeypatch.setattr(vr.subprocess, "run", lambda *a, **k: _FailedProc())

    oracle = MetricInflationOperator().oracle_repair()
    result = vr.verify_repair(case_dir, oracle, project_root=project_root)

    assert result["verdict"] == "verify_error", result
    assert result["verdict"] != "not_recovered"
    assert "TRAINING_SUBPROCESS_FAILED" in result["reason_codes"]
    # Exit code and stderr recorded on every seed, and surfaced in details.
    assert result["per_seed_hidden_metrics"], result
    for r in result["per_seed_hidden_metrics"]:
        assert r["exitcode"] == 2, r
        assert "FATAL" in r.get("stderr_tail", ""), r
    assert any("exited 2" in d for d in result["details"]), result["details"]
