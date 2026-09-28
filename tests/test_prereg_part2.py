"""Stage 4 Part 2 pre-registered verdicts (harness/prereg_part2.py) on SYNTHETIC data, before any Part 2 trial:
confirm, refute by the opposite direction, refute by "shown small", inconclusive, untestable (headroom), and the
Holm edge cases; plus the document ↔ code agreement."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from harness import prereg_part2 as p2

ROOT = Path(__file__).resolve().parent.parent
MECH_OPS = {"data_leakage": ["silent.data_leakage.v1", "silent.data_leakage_neutral.v1"],
            "label_corruption": ["silent.label_corruption.v1"], "lr_warmup": ["silent.lr_warmup.v1"],
            "metric_inflation": ["silent.metric_inflation.v1"]}
COND = {"H11": {"less": ("gpt-5.6-luna", {"effort": "none"}), "more": ("gpt-5.6-luna", {"effort": "medium"})},
        "H12": {"less": ("claude-sonnet-5", {"thinking": "disabled"}), "more": ("claude-sonnet-5", {"effort": "xhigh"})}}


def _rec(case, op, cond, detected, agent="static", anchor="off.v2", pilot=False):
    model, c = cond
    return {"case_id": case, "_op": op, "_tier": "dynamics", "_agent": agent, "_anchor": anchor,
            "_exploratory": False, "model": {"model_id": model},
            "conditions": {**c, **({"pilot": True} if pilot else {})},
            "scores": {"detection": {"correct": detected}}}


def _world(hyp, less_rates, more_rates, n_per_op=18, reps=2, seed=0, paired_ties=False):
    """Synthetic trials for one hypothesis: per mechanism a detection rate for each condition."""
    rng = random.Random(seed)
    recs = []
    for mech, ops in MECH_OPS.items():
        for op in ops:
            for i in range(n_per_op):
                case = f"{op}:{i}"
                for _ in range(reps):
                    u = rng.random()
                    recs.append(_rec(case, op, COND[hyp]["less"], u < less_rates[mech]))
                    v = u if paired_ties else rng.random()
                    recs.append(_rec(case, op, COND[hyp]["more"], v < more_rates[mech]))
    return recs


LOW = {m: 0.30 for m in MECH_OPS}
HIGH = {m: 0.80 for m in MECH_OPS}
MID = {m: 0.50 for m in MECH_OPS}


def _verdicts(recs):
    return p2.part2_verdicts(recs)


def test_confirming_both():
    v = _verdicts(_world("H11", LOW, HIGH) + _world("H12", LOW, HIGH, seed=1))
    assert v["H11"]["verdict"] == v["H12"]["verdict"] == "CONFIRMING"
    assert v["H11"]["holm_m"] == 2 and v["H11"]["delta"] > 0.4


def test_refuting_opposite_direction():
    # less-reasoning at 0.70 (headroom) and more-reasoning far lower
    v = _verdicts(_world("H11", {m: 0.70 for m in MECH_OPS}, {m: 0.20 for m in MECH_OPS})
                  + _world("H12", LOW, HIGH, seed=1))
    assert v["H11"]["verdict"] == "REFUTING (opposite direction)"


def test_refuting_shown_small_with_identical_paired_outcomes():
    # every paired trial identical → every Δ* is exactly 0: ties count half, p = 1, interval [0, 0]
    v = _verdicts(_world("H11", MID, MID, paired_ties=True) + _world("H12", LOW, HIGH, seed=1))
    assert v["H11"]["p"] == 1.0 and v["H11"]["verdict"] == "REFUTING (shown small)"
    assert "no change larger than 0.15" in v["H11"]["why"] and "Haiku–Luna gap" in v["H11"]["why"]


def test_refuting_shown_small_with_noise():
    recs = _world("H12", MID, {m: 0.52 for m in MECH_OPS}, n_per_op=60, reps=4, seed=7) + _world("H11", LOW, HIGH)
    v = _verdicts(recs)
    assert v["H12"]["verdict"] == "REFUTING (shown small)", (v["H12"]["lo"], v["H12"]["hi"], v["H12"]["p"])


def _constructed(hyp, n=18):
    """Per operator: less = 9 hits / 9 misses; more = the same except 4 misses → hits and 2 hits → misses, so
    Δ̂ = 2/18 ≈ 0.11 per operator with 6 discordant cases — a positive but noisy effect by construction."""
    recs = []
    for ops in MECH_OPS.values():
        for op in ops:
            for i in range(n):
                less = i < 9
                more = (not less and i < 13) or (less and i >= 2)       # misses 9..12 → hits; hits 0,1 → misses
                recs.append(_rec(f"{op}:{i}", op, COND[hyp]["less"], less))
                recs.append(_rec(f"{op}:{i}", op, COND[hyp]["more"], more))
    return recs


def test_inconclusive_when_interval_crosses_the_margin():
    v = _verdicts(_constructed("H12") + _world("H11", LOW, HIGH))
    h = v["H12"]
    assert h["delta"] == pytest.approx(2 / 18)
    assert h["verdict"] == "INCONCLUSIVE", (h["lo"], h["hi"], h["p"])
    assert h["hi"] > 0.15 and not h["holm_rejected"]


def test_untestable_when_less_reasoning_is_near_ceiling_and_holm_drops_to_one():
    ceiling = {m: 1.0 for m in MECH_OPS} | {"lr_warmup": 0.3}          # only 1 mechanism with headroom
    v = _verdicts(_world("H11", ceiling, {m: 1.0 for m in MECH_OPS}) + _world("H12", LOW, HIGH, seed=1))
    assert v["H11"]["verdict"] == "UNTESTABLE" and "no headroom" in v["H11"]["why"]
    assert v["H11"]["eligible"] == ["lr_warmup"]
    assert v["H12"]["holm_m"] == 1


def test_headroom_reads_only_the_less_reasoning_condition():
    recs = _world("H11", {m: 0.30 for m in MECH_OPS} | {"data_leakage": 1.0}, HIGH) + _world("H12", LOW, HIGH, seed=1)
    v = _verdicts(recs)
    assert "data_leakage" not in v["H11"]["eligible"] and len(v["H11"]["eligible"]) == 3


def _r(p, delta=0.2, lo=0.05, hi=0.35):
    return {"testable": True, "p": p, "delta": delta, "lo": lo, "hi": hi}


@pytest.mark.parametrize("p11,p12,want11,want12", [
    (0.024, 0.049, True, True),       # first step at α/2, second at α
    (0.026, 0.001, True, True),       # order by p: 0.001 ≤ 0.025, then 0.026 ≤ 0.05
    (0.026, 0.030, False, False),     # smallest p fails α/2 → testing stops
    (0.001, 0.051, True, False),
    (0.025, 0.050, True, True),       # boundaries inclusive
])
def test_holm_edges(p11, p12, want11, want12):
    out = p2.decide({"H11": _r(p11), "H12": _r(p12)})
    assert out["H11"]["holm_rejected"] is want11 and out["H12"]["holm_rejected"] is want12


def test_holm_with_one_untestable_uses_alpha():
    out = p2.decide({"H11": {"testable": False, "reason": "0 eligible"}, "H12": _r(0.04)})
    assert out["H12"]["holm_rejected"] is True and out["H12"]["verdict"] == "CONFIRMING"
    assert out["H11"]["verdict"] == "UNTESTABLE"


def test_not_rejected_small_vs_inconclusive_boundary():
    assert p2.decide({"H11": _r(0.5, 0.0, -0.149, 0.149)})["H11"]["verdict"] == "REFUTING (shown small)"
    assert p2.decide({"H11": _r(0.5, 0.0, -0.15, 0.10)})["H11"]["verdict"] == "INCONCLUSIVE"     # open interval


def test_pilot_and_other_arms_and_react_and_crash_are_excluded():
    base = [_rec("c1", "silent.lr_warmup.v1", COND["H11"]["less"], True)]
    noise = [_rec("c1", "silent.lr_warmup.v1", COND["H11"]["less"], False, pilot=True),
             _rec("c1", "silent.lr_warmup.v1", COND["H11"]["less"], False, agent="react"),
             _rec("c1", "silent.lr_warmup.v1", COND["H11"]["less"], False, anchor="stats.v2"),
             _rec("c2", "crash.shape_mismatch.v1", COND["H11"]["less"], False)]
    assert p2.primary_trials(base + noise, COND["H11"]["less"]) == base


def test_two_sided_p_counts_ties_half():
    assert p2.two_sided_p([0.0] * 10) == 1.0
    assert p2.two_sided_p([0.1] * 10) == 0.0
    assert p2.two_sided_p([-0.1] * 2 + [0.1] * 8) == pytest.approx(0.4)


def test_document_names_the_same_numbers_as_the_code():
    hyp = (ROOT / "docs" / "HYPOTHESES.md").read_text()
    doc = hyp[hyp.index("## Stage 4 Part 2 — PRE-REGISTRATION"):]            # the LOCKED text
    for token in (f"{p2.HEADROOM_MAX_UPPER}", f"±{p2.SMALL_MARGIN}", "10,000", "T/2", "no change larger than 0.15",
                  p2.HAIKU_LUNA_GAP, "Holm"):
        assert token in doc, token


def test_report_renders_part2_section_and_not_part1():
    from harness import report_gen
    recs = _world("H11", LOW, HIGH) + _world("H12", LOW, HIGH, seed=1)
    for r in recs:
        r["_provider"] = "openai" if r["model"]["model_id"].startswith("gpt") else "anthropic"
    part2 = report_gen._prereg_part2_tables(recs)
    assert any("Stage 4 Part 2" in ln for ln in part2) and any("H11" in ln and "CONFIRMING" in ln for ln in part2)
    assert report_gen._prereg_part1_tables(recs) == []          # no Haiku → Part 1 verdicts never render here
    assert report_gen._prereg_part2_tables([]) == []
