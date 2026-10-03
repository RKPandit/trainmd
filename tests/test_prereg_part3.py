"""Stage 4 Part 3 pre-registered verdicts (harness/prereg_part3.py) on SYNTHETIC data, before any Part 3 trial:
confirm (with and without its clause), refute by the opposite direction, refute by "shown small", inconclusive,
untestable (headroom), Holm with the intersection–union p, and the document ↔ code agreement."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from harness import prereg_part3 as p3

ROOT = Path(__file__).resolve().parent.parent
FAULT_OPS = {"data_leakage": ["silent.pixel_tag_leakage.v1", "silent.pixel_tag_leakage_neutral.v1"],
             "label_corruption": ["silent.label_flip.v1"], "lr_decay_unit": ["silent.decay_unit.v1"],
             "metric_inflation": ["silent.confident_subset.v1", "silent.confident_subset_neutral.v1"]}
CONTROL_OPS = ["control.healthy_image.v1"] * 20 + [f"control.benign_img_t{i}.v1" for i in range(7) for _ in range(12)]


@pytest.fixture(autouse=True)
def _fast_bootstrap(monkeypatch):
    monkeypatch.setattr(p3, "N_BOOT", 2000)
    monkeypatch.setattr(p3, "N_BOOT_HEADROOM", 1000)


def _rec(case, op, cond, agent, arm, *, correct=None, alarm=None, control=False):
    model, c = cond[0], dict(cond[1])
    det = {"detected_predicted": alarm, "correct": not alarm} if control else \
        {"detected_predicted": bool(correct), "correct": bool(correct)}
    return {"case_id": case, "_op": op, "_tier": "control" if control else "dynamics", "_agent": agent,
            "_anchor": arm, "_exploratory": False, "model": {"model_id": model}, "conditions": dict(c),
            "scores": {"detection": det}}


def world(cond, agent, arm, det, fa, *, n_per_op=18, reps=None, seed=0, u=None):
    """Synthetic trials of one condition × agent × arm: `det` = {mechanism: detection rate} (or one number), `fa` =
    control false-alarm rate. `u` (shared uniforms) makes two worlds PAIRED trial by trial."""
    reps = reps or (2 if agent == p3.STATIC else 1)
    rng = random.Random(seed)
    draw = (lambda key: u.setdefault(key, rng.random())) if u is not None else (lambda key: rng.random())
    recs = []
    for mech, ops in FAULT_OPS.items():
        rate = det[mech] if isinstance(det, dict) else det
        for op in ops:
            for i in range(n_per_op):
                for r in range(reps):
                    recs.append(_rec(f"{op}:{i}", op, cond, agent, arm, correct=draw((op, i, r, agent)) < rate))
    for j, op in enumerate(CONTROL_OPS):
        recs.append(_rec(f"ctl:{j}", op, cond, agent, arm, alarm=draw(("c", j, agent)) < fa, control=True))
    return recs


def verdicts(recs):
    return p3.part3_verdicts(recs)


# ---------------------------------------------------------------- H13a / H13b
def test_h13a_confirming_via_false_alarms():
    recs = world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.99, 0.90) + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.90, 0.0, seed=1)
    r = p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]
    assert r["verdict"] == "CONFIRMING" and r["clause"]["met"] and r["delta"] > 0.6


def test_h13a_confirming_j_only_when_the_gap_comes_from_detection():
    recs = world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.30, 0.05) + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.90, 0.0, seed=1)
    r = p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]
    assert r["verdict"] == "CONFIRMING (J only)" and not r["clause"]["met"]


def test_h13b_confirming_via_misses():
    recs = world(p3.LUNA_NONE, p3.REACT, p3.OFF, 0.20, 0.02) + world(p3.LUNA_MED, p3.REACT, p3.OFF, 0.85, 0.02, seed=1)
    r = p3.decide({"H13b": p3.h13(recs, p3.REACT)})["H13b"]
    assert r["verdict"] == "CONFIRMING" and r["clause"]["component"] == "DET" and r["clause"]["met"]


def test_h13_refuting_opposite_direction():
    recs = world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.80, 0.0) + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.20, 0.3, seed=1)
    assert p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]["verdict"] == "REFUTING (opposite direction)"


def test_h13_refuting_shown_small():
    u: dict = {}
    recs = (world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.5, 0.05, u=u)
            + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.5, 0.05, u=u))                     # identical, paired
    r = p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]
    assert r["verdict"] == "REFUTING (shown small)" and r["lo"] == r["hi"] == 0


def test_h13_inconclusive_with_few_cases():
    recs = (world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.45, 0.1, n_per_op=3, seed=5)
            + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.60, 0.1, n_per_op=3, seed=6))
    assert p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]["verdict"] == "INCONCLUSIVE"


def test_h13_untestable_without_headroom():
    recs = world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 1.0, 0.0) + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 1.0, 0.0, seed=1)
    r = p3.decide({"H13a": p3.h13(recs, p3.STATIC)})["H13a"]
    assert r["verdict"] == "UNTESTABLE" and "headroom" in r["why"]


# ---------------------------------------------------------------- H14
def test_h14_tests_only_conditions_with_headroom():
    recs = (world(p3.SONNET_OFF, p3.REACT, p3.OFF, 0.40, 0.0) + world(p3.SONNET_OFF, p3.REACT, p3.STATS, 0.90, 0.0, seed=1)
            + world(p3.LUNA_MED, p3.REACT, p3.OFF, 1.0, 0.0, seed=2) + world(p3.LUNA_MED, p3.REACT, p3.STATS, 1.0, 0.0, seed=3))
    v = p3.decide(p3.h14(recs))
    assert v["H14[Sonnet 5 thinking off]"]["verdict"] == "CONFIRMING"
    assert v["H14[GPT-5.6 Luna medium]"]["verdict"] == "UNTESTABLE"
    assert v["H14[Haiku 4.5]"]["verdict"] == "UNTESTABLE"                 # no trials
    assert set(v["H14[Sonnet 5 thinking off]"]["mechanisms"]) == set(p3.SILENT_MECHANISMS)


# ---------------------------------------------------------------- H15 (intersection–union)
def _h15_world(haiku, luna, **kw):
    out = []
    for i, agent in enumerate((p3.STATIC, p3.REACT)):                  # fixed seeds (str hashes are randomized)
        out += world(p3.HAIKU, agent, p3.OFF, haiku, 0.0, seed=10 + i, **kw)
        out += world(p3.LUNA_MED, agent, p3.OFF, luna, 0.0, seed=20 + i, **kw)
    return out


def test_h15_confirming_uses_the_intersection_union_p():
    r = p3.h15(_h15_world(0.3, 0.9))
    assert r["kind"] == "iu" and r["p"] == max(r["per_mechanism"][m]["p"] for m in r["eligible"])
    assert p3.decide({"H15": r})["H15"]["verdict"] == "CONFIRMING"


def test_h15_refuting_shown_small():
    u: dict = {}
    recs = []
    for agent in (p3.STATIC, p3.REACT):
        recs += world(p3.HAIKU, agent, p3.OFF, 0.5, 0.0, u=u) + world(p3.LUNA_MED, agent, p3.OFF, 0.5, 0.0, u=u)
    assert p3.decide({"H15": p3.h15(recs)})["H15"]["verdict"] == "REFUTING (shown small)"


def test_h15_refuting_opposite_direction():
    assert p3.decide({"H15": p3.h15(_h15_world(0.6, 0.1))})["H15"]["verdict"] == "REFUTING (opposite direction)"


def test_h15_untestable_when_haiku_is_at_ceiling():
    assert p3.decide({"H15": p3.h15(_h15_world(1.0, 1.0))})["H15"]["verdict"] == "UNTESTABLE"


# ---------------------------------------------------------------- H16 (H10 rule on J)
def _h16_world(off, stats, rule, cond=p3.HAIKU):
    return (world(cond, p3.STATIC, p3.OFF, off, 0.0) + world(cond, p3.STATIC, p3.STATS, stats, 0.0, seed=1)
            + world(cond, p3.STATIC, p3.RULE, rule, 0.0, seed=2))


def test_h16_confirming_and_refuting():
    v = p3.decide(p3.h16(_h16_world(0.2, 0.85, 0.95)))
    assert v["H16[Haiku 4.5]"]["verdict"] == "CONFIRMING"
    assert v["H16[GPT-5.6 Luna medium]"]["verdict"] == "UNTESTABLE"         # no trials
    assert p3.decide(p3.h16(_h16_world(0.2, 0.3, 0.95)))["H16[Haiku 4.5]"]["verdict"] == "REFUTING"


def test_h16_untestable_without_a_gap():
    assert p3.decide(p3.h16(_h16_world(0.8, 0.85, 0.9)))["H16[Haiku 4.5]"]["verdict"] == "UNTESTABLE"


# ---------------------------------------------------------------- H17
def test_h17_confirming_and_headroom_from_the_react_side():
    recs = (world(p3.SONNET_OFF, p3.STATIC, p3.OFF, 0.95, 0.0) + world(p3.SONNET_OFF, p3.REACT, p3.OFF, 0.50, 0.0, seed=1))
    assert p3.decide({"H17": p3.h17(recs)})["H17"]["verdict"] == "CONFIRMING"
    ceil = (world(p3.SONNET_OFF, p3.STATIC, p3.OFF, 1.0, 0.0) + world(p3.SONNET_OFF, p3.REACT, p3.OFF, 1.0, 0.0, seed=1))
    assert p3.decide({"H17": p3.h17(ceil)})["H17"]["verdict"] == "UNTESTABLE"


# ---------------------------------------------------------------- Holm (one family)
def test_holm_is_one_family_over_the_testable_tests_including_the_iu_p():
    res = {
        "A": {"testable": True, "kind": "delta", "p": 0.004, "delta": 0.3, "lo": 0.1, "hi": 0.5},
        "B": {"testable": True, "kind": "delta", "p": 0.02, "delta": 0.2, "lo": 0.05, "hi": 0.4},
        "H15": {"testable": True, "kind": "iu", "p": 0.03, "eligible": ["x", "y"],
                "per_mechanism": {"x": {"lo": 0.1, "hi": 0.5, "p": 0.01}, "y": {"lo": 0.05, "hi": 0.4, "p": 0.03}}},
        "U": {"testable": False, "reason": "headroom"},
    }
    v = p3.decide(res)
    assert all(v[k]["holm_m"] == 3 for k in ("A", "B", "H15"))
    # Holm at α = 0.05, m = 3: 0.004 ≤ 0.05/3, 0.02 ≤ 0.05/2, 0.03 ≤ 0.05/1 → all three rejected
    assert v["A"]["holm_rejected"] and v["B"]["holm_rejected"] and v["H15"]["holm_rejected"]
    assert v["H15"]["verdict"] == "CONFIRMING" and v["U"]["verdict"] == "UNTESTABLE"
    res["B"]["p"] = 0.03
    res["H15"]["p"] = 0.04
    v = p3.decide(res)                         # 0.03 > 0.05/2 → B and everything after it not rejected
    assert v["A"]["holm_rejected"] and not v["B"]["holm_rejected"] and not v["H15"]["holm_rejected"]


def test_all_tests_present_in_the_family():
    names = set(p3.analyse_all([]))
    assert names == {"H13a", "H13b", "H14[Haiku 4.5]", "H14[Sonnet 5 thinking off]", "H14[GPT-5.6 Luna medium]",
                     "H15", "H16[Haiku 4.5]", "H16[GPT-5.6 Luna medium]", "H17"}


# ---------------------------------------------------------------- document ↔ code
def test_document_names_the_same_numbers_as_the_code():
    hyp = (ROOT / "docs" / "HYPOTHESES.md").read_text()
    doc = hyp[hyp.index("## Stage 4 Part 3 — PRE-REGISTRATION"):]            # the LOCKED text
    for token in (f"{p3.HEADROOM_MAX_UPPER}", f"±{p3.SMALL_MARGIN}", f"{p3.H15_SMALL_UPPER}", f"{p3.H16_MIN_GAP}",
                  "10,000", "T/2", "Holm", "½·ΔĴ", "intersection–union", "complete agent configuration",
                  "H13a", "H13b", "H14", "H15", "H16", "H17", "Luna medium is not tested"):
        assert token in doc, token


# ---------------------------------------------------------------- reports: one sweep never renders a partial family
def test_a_single_part3_sweep_points_to_the_combined_verdicts_and_renders_no_verdict():
    from harness import report_gen
    static_only = world(p3.LUNA_NONE, p3.STATIC, p3.OFF, 0.99, 0.9) + world(p3.LUNA_MED, p3.STATIC, p3.OFF, 0.9, 0.0, seed=1)
    react_only = world(p3.LUNA_NONE, p3.REACT, p3.OFF, 0.2, 0.0) + world(p3.LUNA_MED, p3.REACT, p3.OFF, 0.85, 0.0, seed=1)
    for recs in (static_only, react_only):
        out = "\n".join(report_gen._prereg_part3_tables(recs))
        assert p3.PER_SWEEP_NOTE in out and "Pre-registered verdicts" not in out
        for term in ("CONFIRMING", "REFUTING", "INCONCLUSIVE", "UNTESTABLE"):
            assert term not in out
    both = "\n".join(report_gen._prereg_part3_tables(static_only + react_only))
    assert "Pre-registered verdicts (Stage 4 Part 3)" in both and "| H13a |" in both and "| H13b |" in both
