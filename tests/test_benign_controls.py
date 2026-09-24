"""Benign-configuration controls (STAGE4 4.0.6): operators, design, qualification link, scoring, split.

CLAUDE.md's operator rule inverts for this tier: the change must NOT degrade the model. That is proven
at design time on 30 development seeds (docs/audits/benign_qualification.json — every operator here
must correspond to a QUALIFIED candidate), not by gating cases; here we test the operators' contract.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from random import Random

import pytest
import yaml

from operators.control.benign import BENIGN_OPERATORS
from operators.control.healthy import HealthyControlOperator
from operators.registry import all_operator_ids, get_operator

ROOT = Path(__file__).resolve().parent.parent
WL = ROOT / "workloads" / "tabular_adult"


def test_six_benign_operators_registered_as_controls():
    ids = [cls.id for cls in BENIGN_OPERATORS]
    assert len(ids) == 6 and set(ids) <= set(all_operator_ids())
    assert all(get_operator(i).layer == "control" for i in ids)
    assert [cls.FORM for cls in BENIGN_OPERATORS].count("added") == 1       # the new-key type
    assert {cls.FORM for cls in BENIGN_OPERATORS} == {"changed", "added"}


def test_every_benign_operator_is_a_qualified_candidate():
    from scripts.qualify_benign import CANDIDATES
    q = json.loads((ROOT / "docs" / "audits" / "benign_qualification.json").read_text())["results"]
    for cls in BENIGN_OPERATORS:
        match = [name for name, c in CANDIDATES.items() if c["edits"] == cls.EDITS and c["form"] == cls.FORM]
        assert len(match) == 1, cls.id
        assert q[match[0]]["qualified"] is True, (cls.id, match[0])


@pytest.mark.parametrize("cls", BENIGN_OPERATORS, ids=lambda c: c.id)
def test_apply_writes_exactly_the_edit(cls, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    shutil.copy2(WL / "config.yaml", ws / "config.yaml")
    clean = yaml.safe_load((WL / "config.yaml").read_text())
    m = cls().apply(ws, Random(0), "mild")
    cfg = yaml.safe_load((ws / "config.yaml").read_text())
    assert [mu.key_path for mu in m.mutations] == list(cls.EDITS)
    for path, value in cls.EDITS.items():
        sec, key = path.split(".")
        assert cfg[sec][key] == value
        orig = clean.get(sec, {}).get(key)
        assert m.mutations[0].original_value == orig
        # "added" = the key was absent in the clean config; "changed" = it existed with another value
        assert (orig is None) == (cls.FORM == "added") and orig != value
    # nothing else changed
    for sec, vals in clean.items():
        for k, v in (vals.items() if isinstance(vals, dict) else []):
            if f"{sec}.{k}" not in cls.EDITS:
                assert cfg[sec][k] == v


@pytest.mark.parametrize("cls", BENIGN_OPERATORS, ids=lambda c: c.id)
def test_ground_truth_is_a_healthy_control(cls):
    op, healthy = cls(), HealthyControlOperator()
    assert op.evidence() == [] and op.oracle_repair() is None
    rs = op.admissible_repairs()
    assert rs.repair_type == "none" and rs.allowed_keys == []
    assert op.accepted_classes() == healthy.accepted_classes()
    assert op.core_tokens() == healthy.core_tokens()


def test_design_is_152_with_benign_appended_on_disjoint_seeds():
    from scripts.build_all_cases import case_design_tuples
    t = case_design_tuples()
    assert len(t) == 152
    assert all(get_operator(o).layer != "control" or o == "control.healthy.v1" for o, _, _ in t[:128])
    benign = t[128:]
    seeds = [s for _, _, s in benign]
    assert sorted(seeds) == list(range(70, 94)) and len(set(seeds)) == 24
    per = {}
    for o, _, s in benign:
        per.setdefault(o, []).append(s)
    assert all(len(v) == 4 for v in per.values()) and len(per) == 6


def test_scoring_a_benign_control():
    from harness.scoring import _score_no_unnecessary_repair, score_detection, score_identification
    card = {"layer": "control", "operator_id": "control.benign_lr005.v1",
            "accepted_classes": sorted(HealthyControlOperator().accepted_classes())}
    healthy_call = {"diagnosis": {"detected": False, "operator_class": "none"}, "evidence_refs": []}
    assert score_detection(healthy_call, card)["correct"] and score_identification(healthy_call, card)["correct"]
    revert = {"diagnosis": {"detected": True, "operator_class": "lr_misconfiguration"}, "evidence_refs": [],
              "repair_spec": {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}}
    assert score_detection(revert, card)["correct"] is False                      # a false positive
    assert _score_no_unnecessary_repair(revert)["false_intervention"] is True     # reverting = intervention


def test_control_fpr_is_split_by_benign_form():
    from harness import sweep_stats as ss

    def rec(cid, form, detected):
        r = {"case_id": cid, "conditions": {"agent_type": "static", "anchor": "off"}, "prompt": {},
             "scores": {"detection": {"correct": not detected, "detected_predicted": detected}},
             "submission": {"diagnosis": {"detected": detected}}}
        return ss.attach_meta(r, {"operator_id": "control.x", "tier": "control", "benign_form": form})
    recs = [rec("h1", None, False), rec("h2", None, False),
            rec("c1", "changed", True), rec("c2", "changed", False), rec("a1", "added", True)]
    c = ss.control_fpr(recs)
    f = c["by_benign_form"]
    assert f["healthy (no edit)"]["off"]["n_fp"] == 0
    assert f["benign: changed value"]["off"]["n_fp"] == 1 and f["benign: new key"]["off"]["n_fp"] == 1
    # without benign controls the split is absent (frozen reports unchanged)
    assert "by_benign_form" not in ss.control_fpr(recs[:2])
