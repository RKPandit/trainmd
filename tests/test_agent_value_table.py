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


# ---- external review 2026-09-30: exact intervals at 0/1, J, full-condition rows, counts from the data --------
def _tt(case, op, tier, detected, correct, benign=None, model="gpt-5.6-luna", **cond):
    t = _t(case, op, tier, detected, correct, correct)
    t.update({"_benign_form": benign, "model": {"model_id": model}, "conditions": cond,
              "usage": {"estimated_cost_usd": 0.001}})
    return t


def test_zero_event_rates_carry_the_exact_interval_not_zero_zero():
    trials = [_tt(f"f{i}", "silent.pixel_tag_leakage.v1", "dynamics", False, False) for i in range(10)]
    trials += [_tt(f"c{i}", "control.healthy_image.v1", "control", False, True) for i in range(20)]
    s = avt.summarize(trials, verified_repair=False)
    assert s["det"]["point"] == 0.0 and s["det"]["exact"] and s["det"]["hi"] > 0.2      # CP over 10 cases
    assert s["far"]["point"] == 0.0 and s["far"]["exact"] and 0.15 < s["far"]["hi"] < 0.2  # 20 cases → ≈ 0.168
    assert s["rep"] is None and "not verified" in "\n".join(avt._main_table([("B", s)]))
    assert s["n_ctrl"] == 20 and s["n_healthy"] == 20 and s["n_benign"] == 0


def test_j_is_detection_minus_false_alarms():
    trials = [_tt("f1", "silent.label_flip.v1", "dynamics", True, True),
              _tt("f2", "silent.label_flip.v1", "dynamics", False, False),
              _tt("c1", "control.benign_img_bs256.v1", "control", True, False, benign="changed"),
              _tt("c2", "control.healthy_image.v1", "control", False, True),
              _tt("c3", "control.healthy_image.v1", "control", False, True),
              _tt("c4", "control.healthy_image.v1", "control", False, True)]
    assert avt._j(trials) == 0.5 - 0.25


def test_rows_are_per_full_condition_not_per_model():
    from harness.report_gen import condition_of
    a = _tt("f", "silent.label_flip.v1", "dynamics", True, True, effort="none", strict_tools=True)
    b = _tt("f", "silent.label_flip.v1", "dynamics", True, True, effort="medium", strict_tools=True)
    assert condition_of(a) != condition_of(b)
    assert "condition_of(r)" in (ROOT / "scripts" / "agent_value_table.py").read_text()


def test_deterministic_baseline_macro_is_not_a_degenerate_interval():
    # B0-like: crash mechanism all detected, another mechanism none → macro 0.5, bootstrap degenerate
    trials = [_tt(f"x{i}", "crash.channel_mismatch.v1", "execution", True, True) for i in range(18)]
    trials += [_tt(f"y{i}", "silent.label_flip.v1", "dynamics", False, False) for i in range(18)]
    ci = avt._macro_ci(trials, ss._detect_correct)
    assert ci["point"] == 0.5 and ci.get("exact_macro") and ci["lo"] < 0.5 < ci["hi"]
