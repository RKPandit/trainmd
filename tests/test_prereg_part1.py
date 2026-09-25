"""Stage 4 Part 1 pre-registered verdicts on SYNTHETIC data (harness/prereg_part1.py), built before the
run: each hypothesis has a case that must CONFIRM, one that must REFUTE, and the edge cases the
pre-registration names (lr_warmup at Haiku's ceiling → untestable; < 2 carriers → inconclusive; a CI
that merely includes 0 → inconclusive). Plus the statistical primitives against published values.
"""
from __future__ import annotations

import pytest

from harness import prereg_part1 as pp

LR, LC, MI = pp.H9_NON_LEAKAGE
LEAK, NEUT = pp.H9_LEAKAGE
H, L = pp.REF_PROVIDER, pp.CMP_PROVIDER
N_CASES = 18


def _trial(case, op, prov, arm, correct, tier="dynamics", benign=None, detected=None):
    return {"case_id": case, "_op": op, "_provider": prov, "_anchor": arm, "_tier": tier,
            "_benign_form": benign, "_agent": "static",
            "scores": {"detection": {"correct": correct}},
            "submission": {"diagnosis": {"detected": correct if detected is None else detected}}}


def _cells(op, prov, arm, k, per_case=4):
    """Cases 0..k-1 of the operator detected (all trials), the rest missed."""
    return [_trial(f"{op}#{i}", op, prov, arm, i < k) for i in range(N_CASES) for _ in range(per_case)]


def _h9_data(haiku: dict, luna: dict):
    recs = []
    for op in (LR, LC, MI, LEAK, NEUT):
        recs += _cells(op, H, pp.OFF, round(haiku[op] * N_CASES))
        recs += _cells(op, L, pp.OFF, round(luna[op] * N_CASES))
    return recs


BASE_H = {LR: 17 / 18, LC: 4 / 18, MI: 4 / 18, LEAK: 1 / 18, NEUT: 2 / 18}


# --------------------------------------------------------------------------- H9
def test_h9_confirms_with_lr_at_ceiling_reported_untestable():
    luna = {LR: 1.0, LC: 15 / 18, MI: 15 / 18, LEAK: 15 / 18, NEUT: 15 / 18}
    v = pp.h9_verdict(_h9_data(BASE_H, luna))
    assert v["operators"][LR]["status"] == "no_headroom_untestable"     # Sweep 1: 0.94 → no headroom
    assert v["carriers"] == [LC, MI]
    assert v["verdict"] == "CONFIRMING"


def test_h9_refutes_only_when_the_gap_is_shown_small():
    luna = {LR: 1.0, LC: 5 / 18, MI: 4 / 18, LEAK: 15 / 18, NEUT: 15 / 18}
    v = pp.h9_verdict(_h9_data(BASE_H, luna))
    assert all(v["operators"][o]["delta"]["hi"] < pp.H9_SMALL_GAP for o in v["carriers"])
    assert v["leakage_delta"]["lo"] > 0
    assert v["verdict"] == "REFUTING"


def test_h9_ci_including_zero_but_not_small_is_inconclusive():
    # Luna's hits on DIFFERENT cases than Haiku's: Δ ≈ +0.11, wide CI including 0, upper ≥ 0.20
    recs = []
    for op in (LR, LEAK, NEUT):
        recs += _cells(op, H, pp.OFF, round(BASE_H[op] * N_CASES))
        recs += _cells(op, L, pp.OFF, 15)
    for op in (LC, MI):
        recs += _cells(op, H, pp.OFF, 4)
        recs += [_trial(f"{op}#{i}", op, L, pp.OFF, i >= 12) for i in range(N_CASES) for _ in range(4)]
    v = pp.h9_verdict(recs)
    assert v["carriers"] == [LC, MI]
    d = v["operators"][LC]["delta"]
    assert d["lo"] <= 0 <= d["hi"] and d["hi"] >= pp.H9_SMALL_GAP
    assert v["verdict"] == "INCONCLUSIVE"


def test_h9_fewer_than_two_carriers_is_inconclusive_even_with_big_gaps():
    haiku = {**BASE_H, MI: 1.0}                  # metric_inflation also at ceiling → one carrier left
    luna = {LR: 1.0, LC: 1.0, MI: 1.0, LEAK: 1.0, NEUT: 1.0}
    v = pp.h9_verdict(_h9_data(haiku, luna))
    assert v["carriers"] == [LC]
    assert v["verdict"] == "INCONCLUSIVE" and "headroom" in v["reason"]


def test_h9_headroom_uses_haiku_only():
    """The headroom status must not change when only Luna's data change (it cannot favour a gap)."""
    a = pp.h9_verdict(_h9_data(BASE_H, {o: 1.0 for o in BASE_H}))
    b = pp.h9_verdict(_h9_data(BASE_H, {o: 0.0 for o in BASE_H}))
    assert {o: d["status"] for o, d in a["operators"].items()} == \
           {o: d["status"] for o, d in b["operators"].items()}


# --------------------------------------------------------------------------- H10
def _h10_data(rates: dict):
    """rates[prov][op] = (off, stats, rule) detection."""
    recs = []
    for prov, ops in rates.items():
        for op, trio in ops.items():
            for arm, r in zip((pp.OFF, pp.STATS, pp.RULE), trio):
                recs += _cells(op, prov, arm, round(r * N_CASES), per_case=2)
    return recs


def test_h10_confirms_and_excludes_small_gap_operators():
    ops = {LR: (17 / 18, 17 / 18, 1.0), LC: (4 / 18, 16 / 18, 1.0), MI: (4 / 18, 16 / 18, 1.0)}
    v = pp.h10_verdict(_h10_data({H: ops, L: ops}))
    for m in (H, L):
        assert v["models"][m]["eligible"] == [LC, MI]                  # lr: rule − off < 0.30
        assert v["models"][m]["verdict"] == "CONFIRMING"
        assert v["models"][m]["f"]["lo"] >= pp.H10_THRESHOLD


def test_h10_refutes():
    ops = {LC: (4 / 18, 6 / 18, 1.0), MI: (4 / 18, 5 / 18, 1.0)}
    v = pp.h10_verdict(_h10_data({H: ops, L: ops}))
    for m in (H, L):
        assert v["models"][m]["verdict"] == "REFUTING"
        assert v["models"][m]["f"]["hi"] < pp.H10_THRESHOLD


def test_h10_untestable_when_no_gap_to_close():
    ops = {LR: (17 / 18, 17 / 18, 1.0), LC: (15 / 18, 16 / 18, 1.0)}
    v = pp.h10_verdict(_h10_data({H: ops, L: ops}))
    assert {v["models"][m]["verdict"] for m in (H, L)} == {"UNTESTABLE"}


def test_h10_near_half_is_inconclusive():
    ops = {LC: (4 / 18, 11 / 18, 1.0), MI: (4 / 18, 10 / 18, 1.0)}
    v = pp.h10_verdict(_h10_data({H: ops, L: ops}))
    assert {v["models"][m]["verdict"] for m in (H, L)} == {"INCONCLUSIVE"}


def test_band_benefit_is_headroom_normalised():
    ops = {LR: (17 / 18, 1.0, 1.0), LC: (4 / 18, 16 / 18, 1.0)}
    bb = pp.band_benefit_descriptive(_h10_data({H: ops}))
    assert bb[(H, LR, pp.STATS)]["normalised"] == pytest.approx(1.0)      # closes all remaining headroom
    assert bb[(H, LC, pp.STATS)]["benefit"] == pytest.approx(12 / 18)


# --------------------------------------------------------------------------- benign
def _benign(prov, arm, fp_cases, n=24):
    return [_trial(f"b{i}", "control.benign_x.v1", prov, arm, correct=i not in fp_cases, tier="control",
                   benign="changed", detected=i in fp_cases) for i in range(n)]


def test_benign_two_sided_increase_decrease_inconclusive():
    recs = (_benign(H, pp.OFF, set()) + _benign(H, pp.RULE, set(range(10))) + _benign(H, pp.STATS, {3})
            + _benign(L, pp.OFF, set(range(10))) + _benign(L, pp.RULE, set()) + _benign(L, pp.STATS, set(range(10))))
    v = pp.benign_verdict(recs)
    c = v["contrasts"]
    assert c[f"{H}:rule-off"]["verdict"] == "INCREASE" and c[f"{H}:rule-off"]["cells"] == [0, 10, 0, 14]
    assert c[f"{H}:stats-off"]["verdict"] == "INCONCLUSIVE"
    assert c[f"{L}:rule-off"]["verdict"] == "DECREASE"
    assert c[f"{L}:stats-off"]["verdict"] == "INCONCLUSIVE"            # identical flags: no discordance
    assert v["per_provider"] == {H: "INCREASE", L: "DECREASE"}


def test_benign_holm_is_stricter_than_unadjusted():
    # 6 one-way flips: exact p = 0.031 < 0.05, but alone among four contrasts it must clear α/4
    recs = (_benign(H, pp.OFF, set()) + _benign(H, pp.RULE, set(range(6))) + _benign(H, pp.STATS, set())
            + _benign(L, pp.OFF, set()) + _benign(L, pp.RULE, set()) + _benign(L, pp.STATS, set()))
    c = pp.benign_verdict(recs)["contrasts"][f"{H}:rule-off"]
    assert c["p_mcnemar"] < 0.05 and c["verdict"] == "INCONCLUSIVE"


def test_exploratory_records_are_excluded():
    recs = _benign(H, pp.OFF, set()) + _benign(H, pp.RULE, set(range(10)))
    for r in recs:
        r["_exploratory"] = True
    assert not pp.benign_verdict(recs)["contrasts"][f"{H}:rule-off"]["available"]


# --------------------------------------------------------------------------- primitives
# Newcombe (1998) Statist. Med. 17:2635, Table III, method 10 (cells e, f, g, h).
NEWCOMBE_TABLE_III_M10 = [
    ((36, 12, 2, 0), (0.0569, 0.3404)), ((20, 12, 2, 16), (0.0562, 0.3292)),
    ((18, 12, 2, 18), (0.0562, 0.3290)), ((36, 14, 0, 0), (0.1528, 0.4167)),
    ((35, 14, 0, 1), (0.1461, 0.4175)), ((18, 14, 0, 18), (0.1441, 0.3963)),
    ((2, 97, 1, 0), (0.8721, 0.9854)), ((1, 97, 1, 1), (0.8736, 0.9850)),   # published 0.8736 (0.87367)
    ((0, 29, 1, 0), (0.6666, 0.9882)), ((2, 98, 0, 0), (0.9178, 0.9945)),
    ((1, 98, 0, 1), (0.9171, 0.9916)), ((0, 30, 0, 0), (0.8395, 1.0)),
    ((54, 0, 0, 0), (-0.0664, 0.0664)), ((53, 0, 0, 1), (-0.0729, 0.0729)),
    ((30, 0, 0, 24), (-0.0358, 0.0358)), ((27, 0, 0, 27), (-0.0351, 0.0351)),
]


@pytest.mark.parametrize("cells,expected", NEWCOMBE_TABLE_III_M10)
def test_newcombe_method10_matches_published_table(cells, expected):
    _, lo, hi = pp.newcombe_paired(*cells)
    assert abs(lo - expected[0]) <= 1.1e-4 and abs(hi - expected[1]) <= 1.1e-4


def test_mcnemar_exact_and_holm():
    assert pp.mcnemar_exact(0, 0) == 1.0
    assert pp.mcnemar_exact(8, 0) == pytest.approx(2 / 256)
    assert pp.mcnemar_exact(10, 1) == pytest.approx(2 * 12 / 2048)
    assert pp._holm({"a": 0.01, "b": 0.04}) == {"a": True, "b": True}
    assert pp._holm({"a": 0.03, "b": 0.04}) == {"a": False, "b": False}


# --------------------------------------------------------------------------- report wiring
def test_generated_report_renders_the_verdicts():
    from harness import report_gen
    recs = _h9_data(BASE_H, {LR: 1.0, LC: 15 / 18, MI: 15 / 18, LEAK: 15 / 18, NEUT: 15 / 18})
    ops = {LC: (4 / 18, 16 / 18, 1.0), MI: (4 / 18, 16 / 18, 1.0)}
    recs += _h10_data({H: ops, L: ops})
    recs += (_benign(H, pp.OFF, set()) + _benign(H, pp.RULE, set(range(10))) + _benign(H, pp.STATS, set())
             + _benign(L, pp.OFF, set()) + _benign(L, pp.RULE, set()) + _benign(L, pp.STATS, set()))
    for r in recs:
        r["conditions"] = {"agent_type": "static", "anchor": r["_anchor"].split(".")[0],
                           "provider": r["_provider"]}
        for k in ("_symptom", "_sig_vis", "_sig_hid", "_band_vis", "_band_hid", "_strength", "_seed"):
            r.setdefault(k, None)
    md = report_gen.generate(recs, {"name": "synthetic"})
    sec = md[md.index("## Pre-registered verdicts"):]
    assert "H9 — model dependence beyond leakage: **CONFIRMING**" in sec
    assert "no_headroom_untestable" in sec
    assert f"{H} **INCREASE**" in sec
    h10 = sec[sec.index("### H10"):sec.index("### Benign")]           # verdict logic tested above;
    assert {ln.split("|")[1].strip() for ln in h10.splitlines()        # here: one row per model
            if ln.startswith(("| anthropic", "| openai"))} == {H, L}


# --------------------------------------------------------------------------- H10: document == code
def _doc_h10_rule(recs):
    """H10's decision rule re-implemented from the PRE-REGISTRATION TEXT (steps 1–4), independently of
    harness/prereg_part1.py — only the record accessors and the eligible-operator set are shared."""
    import random
    out = {}
    for prov in (H, L):
        trials = [r for r in recs if r["_provider"] == prov and r["_tier"] != "control"]

        def rate(ts, arm):
            xs = [t for t in ts if t["_anchor"] == arm]
            return sum(1 for t in xs if t["scores"]["detection"]["correct"]) / len(xs) if xs else None

        elig = [op for op in sorted({r["_op"] for r in trials})
                if (lambda rs: rate(rs, pp.OFF) is not None and rate(rs, pp.RULE) is not None
                    and rate(rs, pp.RULE) - rate(rs, pp.OFF) >= 0.30)([r for r in trials if r["_op"] == op])]
        if not elig:
            out[prov] = ("UNTESTABLE", None, None)
            continue
        pool = [r for r in trials if r["_op"] in elig]

        def f(ts):
            o, s, u = rate(ts, pp.OFF), rate(ts, pp.STATS), rate(ts, pp.RULE)
            if o is None or s is None or u is None or abs(u - o) < 1e-9:
                return None
            return (s - o) / (u - o)

        cases = sorted({r["case_id"] for r in pool})
        by = {c: [r for r in pool if r["case_id"] == c] for c in cases}
        rng = random.Random(20260913)                                    # step 1
        kept = []
        for _ in range(10_000):
            v = f([t for c in [rng.choice(cases) for _ in cases] for t in by[c]])
            if v is not None:
                kept.append(v)
        B, Lo = len(kept), sum(1 for v in kept if v < 0.5)
        out[prov] = (None, min(1.0, 2 * min(Lo, B - Lo) / B), f(pool))   # step 2
    tested = sorted((p, m) for m, (v, p, _) in out.items() if v is None)  # step 3: by p, then name
    rejected, m = set(), len(tested)
    for i, (p, name) in enumerate(tested, 1):
        if p <= 0.05 / (m - i + 1):
            rejected.add(name)
        else:
            break
    verdicts = {}
    for name, (v, p, fh) in out.items():                                  # step 4
        verdicts[name] = v or ("CONFIRMING" if name in rejected and fh > 0.5 else
                               "REFUTING" if name in rejected and fh < 0.5 else "INCONCLUSIVE")
    return verdicts


@pytest.mark.parametrize("haiku,luna,expected", [
    ((15, 15), (15, 15), {H: "CONFIRMING", L: "CONFIRMING"}),
    ((6, 5), (6, 5), {H: "REFUTING", L: "REFUTING"}),
    ((11, 11), (10, 12), {H: "INCONCLUSIVE", L: "INCONCLUSIVE"}),
    # Holm boundary: Haiku p ≈ 0.046 is rejected at α/1 only because Luna (p ≈ 0.001) went first …
    ((13, 14), (15, 15), {H: "CONFIRMING", L: "CONFIRMING"}),
    # … and is NOT rejected when it is the smaller p and must clear α/2 (unadjusted p < 0.05).
    ((13, 14), (11, 11), {H: "INCONCLUSIVE", L: "INCONCLUSIVE"}),
])
def test_h10_document_rule_matches_code(haiku, luna, expected):
    rates = {H: {LC: (4 / 18, haiku[0] / 18, 1.0), MI: (4 / 18, haiku[1] / 18, 1.0)},
             L: {LC: (4 / 18, luna[0] / 18, 1.0), MI: (4 / 18, luna[1] / 18, 1.0)}}
    recs = _h10_data(rates)
    code = {m: d["verdict"] for m, d in pp.h10_verdict(recs)["models"].items()}
    assert code == _doc_h10_rule(recs) == expected


def test_h10_document_states_the_codes_rule():
    from pathlib import Path
    # The LOCKED pre-registration (docs/HYPOTHESES.md, Stage 4 Part 1 section) is authoritative.
    doc = (Path(__file__).resolve().parent.parent / "docs" / "HYPOTHESES.md").read_text()
    doc = doc[doc.index("## Stage 4 Part 1 — PRE-REGISTRATION"):]
    h10 = doc[doc.index("### H10"):doc.index("### Benign-configuration controls")]
    for phrase in ("B₀ = 10,000", "random.Random(20260913)", "p = min(1, 2 · min(L, B − L) / B)",
                   "p ≤ α / (m − i + 1)", "rejected and f̂ > 0.5", "rejected and f̂ < 0.5", "≥ 0.30"):
        assert phrase in h10, phrase
    assert (pp.ALPHA, pp.H10_MIN_GAP, pp.H10_THRESHOLD, ss_seed()) == (0.05, 0.30, 0.5, 20260913)


def ss_seed():
    from harness import sweep_stats as ss
    assert ss.N_RESAMPLES == 10_000
    return ss.SEED
