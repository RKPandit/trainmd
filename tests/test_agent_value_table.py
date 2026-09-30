"""What-does-the-agent-add table (reviewer fix 5, 2026-09-27): mechanism pooling and end-to-end scoring."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from harness import sweep_stats as ss
from operators.registry import all_operator_ids

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("avt", ROOT / "scripts" / "agent_value_table.py")
avt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avt)


def test_every_faulty_operator_has_a_mechanism_and_leakage_variants_share_one():
    faulty = [o for o in all_operator_ids(None) if not o.startswith("control.")]      # every workload
    assert sorted(faulty) == sorted(ss.MECHANISM)
    assert ss.mechanism_of("silent.data_leakage.v1") == ss.mechanism_of("silent.data_leakage_neutral.v1")
    w1 = [o for o in all_operator_ids() if not o.startswith("control.")]
    assert len({ss.MECHANISM[o] for o in w1}) == len(w1) - 1          # workload 1: only leakage has two variants
    # Part 3 image operators map to the same FAMILY where the fault is; the LR fault is its own mechanism.
    assert ss.mechanism_of("silent.pixel_tag_leakage_neutral.v1") == "data_leakage"
    assert ss.mechanism_of("silent.confident_subset_neutral.v1") == "metric_inflation"
    assert ss.mechanism_of("silent.decay_unit.v1") not in {ss.MECHANISM[o] for o in w1}
    with pytest.raises(KeyError):
        ss.mechanism_of("silent.not_an_operator.v1")


def _t(case, op, tier, detected, correct, idc, valid=True):
    return {"case_id": case, "_op": op, "_tier": tier, "_benign_form": None,
            "submission": {"diagnosis": {"detected": detected}} if valid else None,
            "scores": {"detection": {"correct": correct}, "identification": {"correct": idc}},
            "compliance": {"missing_fields": []}}


def test_leakage_variants_do_not_double_count_in_the_pooled_rate():
    trials = [_t("a", "silent.data_leakage.v1", "dynamics", True, True, True),
              _t("b", "silent.data_leakage_neutral.v1", "dynamics", True, True, True),
              _t("c", "silent.lr_warmup.v1", "dynamics", False, False, False)]
    # per-operator mean would be 2/3; by mechanism it is mean(1.0 leakage, 0.0 lr) = 0.5
    assert avt._mech_macro(ss._detect_correct)(trials) == 0.5


def test_empty_diagnosis_is_a_miss_on_faulty_and_never_a_false_alarm():
    trials = [_t("a", "silent.lr_warmup.v1", "dynamics", None, False, False, valid=False),
              _t("h", "control.healthy.v1", "control", None, False, False, valid=False),
              _t("g", "control.healthy.v1", "control", True, False, False)]
    assert avt._mech_macro(ss._detect_correct)(trials) == 0.0
    assert avt._ctrl_rate(lambda t: ss._detected(t) is True)(trials) == 0.5
