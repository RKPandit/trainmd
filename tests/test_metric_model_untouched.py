"""Metric tier's guarantee is CHECKPOINT BITWISE IDENTITY, not band position.

Planted-violation tests for the validator (DECISIONS 2026-09-19):
- a checkpoint that differs from the certified-clean one FAILS (C12);
- a clean model whose hidden accuracy sits OUTSIDE the band but is bitwise-
  identical PASSES (C5 no longer gates the metric tier on band; C12 checks identity).
No training: a tiny torch checkpoint stands in for the real one.
"""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from harness.build_case import model_state_sha256
from harness.validate_case import _check_c5, _check_c12_metric_model_untouched


def _write_ckpt(case_dir, tensors):
    ck = case_dir / "workspace" / "run_output" / "checkpoints"
    ck.mkdir(parents=True)
    path = ck / "ckpt_final.pt"
    torch.save({"model_state_dict": tensors}, path)
    return path


def test_c12_passes_when_checkpoint_matches_certified_clean(tmp_path):
    ckpt = _write_ckpt(tmp_path, {"w": torch.tensor([1.0, 2.0, 3.0])})
    card = {"layer": "metric", "checkpoint_bitwise_identical_to_clean": True,
            "clean_model_sha256": model_state_sha256(ckpt)}
    r = _check_c12_metric_model_untouched(tmp_path, card)
    assert r.passed, r.detail


def test_c12_fails_when_checkpoint_differs_from_clean(tmp_path):
    _write_ckpt(tmp_path, {"w": torch.tensor([1.0, 2.0, 3.0])})
    # Recorded sha is for a DIFFERENT (clean) model -> shipped checkpoint differs.
    card = {"layer": "metric", "checkpoint_bitwise_identical_to_clean": True,
            "clean_model_sha256": "0" * 64}
    r = _check_c12_metric_model_untouched(tmp_path, card)
    assert not r.passed
    assert "differs from the clean run" in r.detail


def test_c12_fails_when_identity_not_certified(tmp_path):
    ckpt = _write_ckpt(tmp_path, {"w": torch.tensor([1.0])})
    card = {"layer": "metric", "clean_model_sha256": model_state_sha256(ckpt)}  # no flag
    assert not _check_c12_metric_model_untouched(tmp_path, card).passed


def test_c12_not_applicable_to_non_metric(tmp_path):
    r = _check_c12_metric_model_untouched(tmp_path, {"layer": "dynamics"})
    assert r.passed and "n/a" in r.detail


def test_c5_metric_no_longer_gates_on_band(tmp_path):
    # Clean model BELOW tolerance (outside band) — used to FAIL C5; must now PASS
    # (identity is the guarantee, checked by C12).
    verify = {"faulty_value": 0.844355, "tolerance_lower": 0.844655,
              "band_position_hidden": "below_band",
              "reference_metric_mean": 0.848248, "reference_metric_std": 0.001796}
    card = {"layer": "metric"}
    assert _check_c5(verify, card).passed
