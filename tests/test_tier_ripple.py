"""Tier-ripple guard: every tier-aware surface must handle ALL fault layers.

PR #1 added the metric tier and taught build_case, validate_case, and scoring
about it — but missed scripts/case_margins.py, which applied the dynamics rule to
metric cases and turned CI red. This test asserts each tier-aware surface behaves
correctly for dynamics / control / metric, so the NEXT new tier (or a module that
forgets an existing one) fails here instead of in CI.

Layers and their model health:
  dynamics — faulty model; hidden accuracy must fall BELOW tolerance.
  control  — healthy model, no fault; hidden accuracy must CLEAR tolerance.
  metric   — healthy model, metric-only fault; hidden accuracy must CLEAR tolerance.
  execution (crash) — no checkpoint metric; handled separately (not here).
"""
from __future__ import annotations

_TOL = 0.843535
_TWO_STD = 0.004114
_HEALTHY_LAYERS = ("control", "metric")   # model healthy → hidden must clear tol
_FAULTY_MODEL_LAYERS = ("dynamics",)      # model degraded → hidden below tol


def test_case_margins_handles_all_layers():
    from scripts.case_margins import margin_flag

    for layer in _HEALTHY_LAYERS:
        _, ok, flag = margin_flag(layer, _TOL + 0.01, _TOL, _TWO_STD)
        assert ok and "GUARD-FAIL" not in flag, (layer, flag)
        _, ok_bad, flag_bad = margin_flag(layer, _TOL - 0.01, _TOL, _TWO_STD)
        assert not ok_bad and "GUARD-FAIL" in flag_bad, (layer, flag_bad)
    for layer in _FAULTY_MODEL_LAYERS:
        _, ok, flag = margin_flag(layer, _TOL - 0.01, _TOL, _TWO_STD)
        assert ok and "GUARD-FAIL" not in flag, (layer, flag)
        _, ok_bad, _ = margin_flag(layer, _TOL + 0.01, _TOL, _TWO_STD)
        assert not ok_bad, layer


def test_score_detection_handles_all_layers():
    from harness.scoring import score_detection
    sub = {"diagnosis": {"detected": True, "operator_class": "x"}}
    # faulty tiers (dynamics, metric) → there IS an incident to detect
    for layer in ("dynamics", "metric"):
        assert score_detection(sub, {"layer": layer})["detected_actual"] is True, layer
    # control → healthy, no incident
    assert score_detection(sub, {"layer": "control"})["detected_actual"] is False


def test_validate_c5_handles_all_layers():
    from harness.validate_case import _check_c5
    healthy = {"faulty_value": _TOL + 0.01, "tolerance_lower": _TOL}
    degraded = {"faulty_value": _TOL - 0.01, "tolerance_lower": _TOL}
    for layer in _HEALTHY_LAYERS:
        assert _check_c5(healthy, {"layer": layer}).passed, layer
        assert not _check_c5(degraded, {"layer": layer}).passed, layer
    for layer in _FAULTY_MODEL_LAYERS:
        assert _check_c5(degraded, {"layer": layer}).passed, layer
        assert not _check_c5(healthy, {"layer": layer}).passed, layer


def test_validate_f5_checkpoint_required_for_completing_tiers(tmp_path):
    from harness.validate_case import _check_f5
    # No checkpoint present → every completing tier must FAIL F5.
    for layer in ("dynamics", "control", "metric"):
        assert not _check_f5(tmp_path, {"layer": layer}).passed, layer
    # Checkpoint present → every completing tier passes.
    ckpt = tmp_path / "workspace" / "run_output" / "checkpoints"
    ckpt.mkdir(parents=True)
    (ckpt / "ckpt_final.pt").write_text("stub")
    for layer in ("dynamics", "control", "metric"):
        assert _check_f5(tmp_path, {"layer": layer}).passed, layer


def test_every_registered_operator_layer_is_known():
    from operators.registry import all_operator_ids, get_operator
    known = {"dynamics", "control", "metric", "execution"}
    for op_id in all_operator_ids():
        layer = get_operator(op_id).layer
        assert layer in known, f"{op_id} has unknown layer {layer!r}"
