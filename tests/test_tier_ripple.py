"""Tier-ripple guard: every tier-aware surface must handle ALL fault layers.

PR #1 added the metric tier and taught build_case, validate_case, and scoring
about it — but missed scripts/case_margins.py, which applied the dynamics rule to
metric cases and turned CI red. This test asserts each tier-aware surface behaves
correctly for dynamics / control / metric, so the NEXT new tier (or a module that
forgets an existing one) fails here instead of in CI.

Layers and their model health:
  dynamics — faulty model; hidden accuracy must fall BELOW tolerance.
  control  — healthy model, no fault; RETAINED at any band position (§5.1) and
             labelled — an out-of-band control is no longer a guard failure.
  metric   — healthy model, metric-only fault; hidden accuracy must CLEAR tolerance.
  execution (crash) — no checkpoint metric; handled separately (not here).
"""
from __future__ import annotations

_TOL = 0.843719          # 30-seed reference band (§0.5)
_TWO_STD = 0.004274
_MEAN = 0.847993         # 30-seed hidden mean; mean - 2σ == _TOL (§0.5)
_STD = 0.002137
_FAULTY_MODEL_LAYERS = ("dynamics",)      # model degraded → hidden below tol


def test_case_margins_handles_all_layers():
    from scripts.case_margins import margin_flag

    # metric (2026-09-19): REPORT-ONLY on band position — never a GUARD-FAIL. The
    # "model untouched" guarantee is checkpoint bitwise identity (build_case /
    # validate_case C12), not band position (varies by seed/runner, L24). Below tol
    # is recorded, not failed.
    _, ok, flag = margin_flag("metric", _TOL + 0.01, _TOL, _TWO_STD)
    assert ok and "GUARD-FAIL" not in flag, flag
    _, ok_below, flag_below = margin_flag("metric", _TOL - 0.01, _TOL, _TWO_STD)
    assert ok_below and "GUARD-FAIL" not in flag_below, flag_below
    assert "OUT-OF-BAND below" in flag_below, flag_below

    # control (§5.1): retained at ANY band position — never a GUARD-FAIL.
    for fv in (_TOL + 0.01, _TOL - 0.01, _TOL + 3 * _TWO_STD):
        _, ok, flag = margin_flag("control", fv, _TOL, _TWO_STD)
        assert ok and "GUARD-FAIL" not in flag, (fv, flag)
    # ...and an out-of-band control is labelled as such.
    _, _, flag_below = margin_flag("control", _TOL - 0.01, _TOL, _TWO_STD)
    assert "OUT-OF-BAND" in flag_below, flag_below

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
    from harness.validate_case import _check_c5, _band_position
    healthy = {"faulty_value": _TOL + 0.01, "tolerance_lower": _TOL}
    degraded = {"faulty_value": _TOL - 0.01, "tolerance_lower": _TOL}

    # metric (2026-09-19): C5 NO LONGER band-gates the metric tier — the "model
    # untouched" guarantee is checkpoint bitwise identity (C12), and the clean
    # model's band position varies by seed/runner (L24), so a below-band healthy
    # draw is legitimate. Both pass C5; identity is asserted by C12 elsewhere.
    assert _check_c5(healthy, {"layer": "metric"}).passed
    assert _check_c5(degraded, {"layer": "metric"}).passed
    # dynamics (unchanged): faulty below tolerance passes; above fails.
    for layer in _FAULTY_MODEL_LAYERS:
        assert _check_c5(degraded, {"layer": layer}).passed, layer
        assert not _check_c5(healthy, {"layer": layer}).passed, layer

    # control (§5.1): RETAINED at any band position; band_position_hidden must be
    # PRESENT and CONSISTENT with the recorded metric vs the committed reference.
    def ctrl(value):
        return {"faulty_value": value, "tolerance_lower": _TOL,
                "reference_metric_mean": _MEAN, "reference_metric_std": _STD,
                "band_position_hidden": _band_position(value, _MEAN, _STD)}
    for value in (_MEAN, _TOL - 0.01, _MEAN + 3 * _STD):   # in_band, below, above — all valid
        assert _check_c5(ctrl(value), {"layer": "control"}).passed, value
    # missing band_position → FAIL
    v = ctrl(_MEAN); v.pop("band_position_hidden")
    assert not _check_c5(v, {"layer": "control"}).passed
    # PLANTED VIOLATION: stored band disagrees with the metric → FAIL
    bad = ctrl(_TOL - 0.01)          # metric is actually below_band
    bad["band_position_hidden"] = "in_band"
    assert not _check_c5(bad, {"layer": "control"}).passed


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
