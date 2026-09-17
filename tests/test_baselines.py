"""Non-LLM baselines (STAGE3_PLAN Part 1): each baseline on a planted faulty and a
planted control; B4 ROC on a synthetic separable set; baselines score through the
STANDARD scorer; and a baseline can never read the hidden answer key."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from harness import baselines as B

REPO = Path(__file__).resolve().parents[1]
_VMEAN, _VSTD = 0.857079, 0.00184  # visible band the public card advertises


def _visible_case(tmp: Path, val_accs, resolved=None, mean=_VMEAN, std=_VSTD, crash=False):
    """A case with only the AGENT-VISIBLE artifacts (no hidden card)."""
    cd = tmp / "case_0001"
    ro = cd / "workspace" / "run_output"
    ro.mkdir(parents=True)
    (cd / "card.public.yaml").write_text(yaml.dump(
        {"case_id": "case_0001",
         "reference_visible_metric": {"series": "metric_visible_val_acc", "mean": mean, "std": std}}))
    if not crash:
        lines = [json.dumps({"epoch": i, "step": i + 1, "train_loss": 0.3,
                             "metric_visible_val_acc": v, "end_of_epoch": True})
                 for i, v in enumerate(val_accs)]
        (ro / "metrics.jsonl").write_text("\n".join(lines) + "\n")
    (ro / "config.resolved.yaml").write_text(yaml.dump(
        resolved or {"workload": {"name": "tabular_adult"}, "training": {"lr": 0.01}}))
    (ro / "exitcode").write_text("1" if crash else "0")
    return cd


# ---- B1 band detector ----------------------------------------------------
def test_b1_flags_out_of_band(tmp_path):
    cd = _visible_case(tmp_path, [0.857, 0.858, 0.840])  # last epoch far below mean-2σ
    sub = B.b1(B.VisibleSurface(cd, REPO))
    assert sub["diagnosis"]["detected"] is True
    ev = sub["evidence_refs"][0]
    assert ev["kind"] == "metric_window" and ev["detail"]["series"] == "metric_visible_val_acc"


def test_b1_in_band_not_flagged(tmp_path):
    cd = _visible_case(tmp_path, [0.856, 0.857, 0.858])
    assert B.b1(B.VisibleSurface(cd, REPO))["diagnosis"]["detected"] is False


def test_b1_crash_is_not_detected_by_construction(tmp_path):
    # crash tier: no metrics -> detected=False is the CORRECT answer to "metric out of band"
    cd = _visible_case(tmp_path, [], crash=True)
    s = B.VisibleSurface(cd, REPO)
    assert s.is_crash() is True
    assert B.b1(s)["diagnosis"]["detected"] is False


def test_b1_arm_conditional_band(tmp_path):
    # a tighter arm-given band flags a run the public band would not
    cd = _visible_case(tmp_path, [0.8595, 0.8596])
    assert B.b1(B.VisibleSurface(cd, REPO))["diagnosis"]["detected"] is False
    tight = B.b1(B.VisibleSurface(cd, REPO), band=(0.856, 0.859))
    assert tight["diagnosis"]["detected"] is True


# ---- B2 config-delta -----------------------------------------------------
def test_b2_flags_changed_key_with_id_evidence_repair(tmp_path):
    cd = _visible_case(tmp_path, [0.857],
                       resolved={"workload": {"name": "tabular_adult"}, "training": {"lr": 0.5}})
    sub = B.b2(B.VisibleSurface(cd, REPO))
    assert sub["diagnosis"]["detected"] is True
    assert sub["diagnosis"]["operator_class"] == "lr"
    assert sub["evidence_refs"][0]["kind"] == "config_key"
    assert sub["evidence_refs"][0]["detail"]["key_path"] == "training.lr"
    assert sub["repair_spec"]["patches"]["training.lr"] == 0.01  # reset to clean


def test_b2_newly_present_key_is_unset(tmp_path):
    cd = _visible_case(tmp_path, [0.857],
                       resolved={"workload": {"name": "tabular_adult"},
                                 "metrics": {"eval_subset_fraction": 0.1}})
    sub = B.b2(B.VisibleSurface(cd, REPO))
    assert sub["diagnosis"]["detected"] is True
    assert sub["repair_spec"]["patches"]["metrics.eval_subset_fraction"] is None  # unset


def test_b2_clean_not_flagged(tmp_path):
    clean = yaml.safe_load((Path(__file__).resolve().parents[1] /
                            "workloads/tabular_adult/config.yaml").read_text())
    cd = _visible_case(tmp_path, [0.857], resolved=clean)
    assert B.b2(B.VisibleSurface(cd, REPO))["diagnosis"]["detected"] is False


# ---- B3 union ------------------------------------------------------------
def test_b3_union_prefers_b2(tmp_path):
    cd = _visible_case(tmp_path, [0.840],  # out of band (B1 fires)
                       resolved={"workload": {"name": "tabular_adult"}, "training": {"lr": 0.5}})
    sub = B.b3(B.VisibleSurface(cd, REPO))
    assert sub["diagnosis"]["detected"] is True
    assert sub["evidence_refs"][0]["kind"] == "config_key"  # from B2


def test_b3_falls_back_to_b1(tmp_path):
    cd = _visible_case(tmp_path, [0.840])  # clean config, but out of band
    sub = B.b3(B.VisibleSurface(cd, REPO))
    assert sub["diagnosis"]["detected"] is True
    assert sub["evidence_refs"][0]["kind"] == "metric_window"  # only B1's evidence


# ---- B4 reference-informed oracle ROC ------------------------------------
def test_b4_roc_auc_on_separable_set():
    # faulty cases far out (high |z|), controls near mean (low |z|) -> AUC 1.0
    scores = [(6.0, True), (5.0, True), (4.0, True)] + [(0.3, False), (0.5, False), (0.2, False)]
    out = B.b4_roc(scores)
    assert out["available"] and out["auc"] == 1.0
    op = B.operating_point_for_rate(out["roc"], target_tpr=1.0)
    assert op is not None and op["tpr"] == 1.0


def test_b4_crash_ranks_below_and_is_labelled_oracle():
    scores = [(None, True), (5.0, True), (0.3, False)]  # a crash (None) among faulty
    out = B.b4_roc(scores)
    assert "ORACLE" in out["note"]


# ---- scored through the STANDARD scorer ----------------------------------
def test_baseline_scores_through_standard_scorer(tmp_path):
    # a minimal control case WITH a hidden card so the standard scorer can grade it
    cd = _visible_case(tmp_path, [0.856, 0.857])
    hidden = cd / "hidden"
    hidden.mkdir()
    (hidden / "card.hidden.yaml").write_text(yaml.dump(
        {"case_id": "case_0001", "layer": "control", "operator_id": "control.healthy.v1",
         "accepted_classes": ["none", "healthy", "no_incident", "no_fault", "nothing_wrong"],
         "core_tokens": [["none", "healthy", "no_incident", "nothing_wrong", "no_fault"]]}))
    (hidden / "evidence.yaml").write_text(yaml.dump([]))
    submission, scores = B.score_baseline(cd, "b1", project_root=REPO)
    # in-band control -> B1 says not detected -> correct on a healthy run
    assert set(scores) >= {"detection", "identification", "evidence"}
    assert scores["detection"]["detected_predicted"] is False
    assert scores["detection"]["correct"] is True


# ---- no hidden-card access -----------------------------------------------
def test_baseline_cannot_read_hidden_card(tmp_path):
    cd = _visible_case(tmp_path, [0.857])
    (cd / "hidden").mkdir()
    (cd / "hidden" / "card.hidden.yaml").write_text("layer: control\n")
    s = B.VisibleSurface(cd, REPO)
    with pytest.raises(B.HiddenAccessError):
        s._read("hidden/card.hidden.yaml")
    with pytest.raises(B.HiddenAccessError):
        s._read("hidden/verify.yaml")
