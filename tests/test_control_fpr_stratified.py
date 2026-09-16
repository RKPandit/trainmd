"""§5.1: control_fpr stratifies by VISIBLE band position (the key, by mechanism),
with the HIDDEN band position reported alongside as a case-quality label, and a
frozen-safe fallback.

The stratification key is the VISIBLE band position because a control false positive
is a visible-metric event end to end: the agent reads metric_visible_val_acc,
compares it to the band it was given, and flags. The hidden band position has no
causal path to that outcome (the agent never sees it) — it is a case-quality label.
(Both metrics are equally platform-sensitive native-vs-emulated, so robustness is not
the basis; the platform guard ensures native-only artifacts.) The breakdown is GATED
on the explicit visible label being present on every control record: it exists only
on §5.1-rebuilt cases, so frozen pre-§5.1 sweeps render the pooled table unchanged.
"""
from __future__ import annotations

from harness.sweep_stats import control_fpr


def _ctrl(case_id, anchor, detected, band_vis, band_hid=None):
    return {
        "_tier": "control",
        "_op": "control.healthy.v1",
        "_anchor": anchor,
        "case_id": case_id,
        "_band_vis": band_vis,                    # the stratification KEY (by mechanism)
        "_band_hid": band_hid if band_hid is not None else band_vis,
        "submission": {"diagnosis": {"detected": detected}},
        "scores": {},
    }


def test_control_fpr_stratifies_on_visible_band_with_hidden_alongside():
    recs = [
        _ctrl("c1", "numbers", False, "in_band"),
        _ctrl("c2", "numbers", True, "below_band"),   # out-of-band FP (visible)
        _ctrl("c3", "numbers", True, "above_band"),   # out-of-band FP (visible)
        _ctrl("c4", "off", False, "in_band"),
    ]
    out = control_fpr(recs)
    assert out["available"] is True
    assert out["stratified"] is True
    assert out["stratify_key"] == "visible_band_position"   # VISIBLE is the key
    numbers = out["per_arm"]["numbers"]
    assert numbers["point"] == 2 / 3
    band = out["by_band"]["numbers"]                        # keyed on visible
    assert band["in_band"]["point"] == 0.0
    assert band["in_band"]["n_cases"] == 1
    assert band["out_of_band"]["point"] == 1.0
    assert band["out_of_band"]["n_cases"] == 2
    assert sorted(band["out_of_band"]["fp_cases"]) == ["c2", "c3"]
    assert "by_band_hidden" in out                          # hidden reported alongside


def test_control_fpr_stratified_without_hidden_labels_still_keys_on_visible():
    # visible present, hidden absent → still stratified (visible), no hidden breakdown.
    recs = [
        {"_tier": "control", "_op": "control.healthy.v1", "_anchor": "numbers",
         "case_id": "c1", "_band_vis": "in_band", "_band_hid": None,
         "submission": {"diagnosis": {"detected": False}}, "scores": {}},
        {"_tier": "control", "_op": "control.healthy.v1", "_anchor": "numbers",
         "case_id": "c2", "_band_vis": "below_band", "_band_hid": None,
         "submission": {"diagnosis": {"detected": True}}, "scores": {}},
    ]
    out = control_fpr(recs)
    assert out["stratified"] is True
    assert "by_band" in out
    assert "by_band_hidden" not in out


def test_control_fpr_falls_back_to_pooled_when_visible_label_missing():
    recs = [
        _ctrl("c1", "numbers", False, "in_band"),
        {"_tier": "control", "_op": "control.healthy.v1", "_anchor": "numbers",
         "case_id": "c2", "_band_vis": None, "_band_hid": "in_band",   # pre-§5.1: no visible label
         "submission": {"diagnosis": {"detected": True}}, "scores": {}},
    ]
    out = control_fpr(recs)
    assert out["available"] is True
    assert out["stratified"] is False
    assert "by_band" not in out          # nothing added → legacy rendering, byte-identical
    assert "numbers" in out["per_arm"]   # pooled per-arm table still produced


def test_control_fpr_unavailable_without_controls():
    assert control_fpr([{"_tier": "dynamics"}])["available"] is False
