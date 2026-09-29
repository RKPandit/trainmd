"""Stage 4 Part 2 pre-registered verdicts, computed MECHANICALLY from records (HYPOTHESES "Stage 4 Part 2").

Written and tested BEFORE any Part 2 trial (tests/test_prereg_part2.py), so no verdict can be shaped after
seeing data. Two confirmatory within-model reasoning interventions:

  H11  GPT-5.6 Luna, reasoning.effort none vs medium (both strict tool schemas)
  H12  Sonnet 5, thinking disabled vs effort xhigh

Primary measure: off-anchor detection, END-TO-END, static agent, NON-CRASH faulty cases, aggregated by
MECHANISM — D = the unweighted mean over the ELIGIBLE mechanisms of each mechanism's detection rate (the two
leakage variants are one mechanism, harness.sweep_stats.MECHANISM). Δ = D(more reasoning) − D(less reasoning),
paired by case. Every threshold is a module constant, so the pre-registration and the code name the same number.
Inputs are attached records (harness/sweep_stats.attach_meta); pilot / probe trials never reach here (the
loaders drop them) and are refused again below.
"""
from __future__ import annotations

import random

from harness import prereg_part1 as pp1
from harness import sweep_stats as ss

ALPHA = 0.05
OFF = "off.v2"
AGENT = "static"
# What a DESCRIPTIVE Part 2 sweep's report shows instead of verdicts (author 2026-09-29).
DESCRIPTIVE_SWEEP_NOTE = ("Not applicable: Stage B is descriptive; H11/H12 are computed from the static Stage A sweep "
                          "(see the stage4_part2 report).")
CRASH_MECHANISMS = frozenset({"shape_mismatch"})     # excluded in advance: detected from the exit code
HEADROOM_MAX_UPPER = 0.85     # a mechanism carries the decision only if the LESS-reasoning upper bound < this
MIN_MECHANISMS = 2            # fewer eligible mechanisms → "no headroom — untestable"
SMALL_MARGIN = 0.15           # REFUTING (shown small): the 95% interval of Δ lies inside (−0.15, +0.15)
N_BOOT = 10_000
HAIKU_LUNA_GAP = "0.50–0.83"  # Part 1's off-anchor Haiku–Luna gap the interventions are meant to explain

# (model_id, {conditions that must match}) for the less- and more-reasoning condition of each hypothesis.
HYPOTHESES = {
    "H11": {"title": "GPT-5.6 Luna — reasoning none vs medium (both strict)", "seed": 20260928,
            "less": ("gpt-5.6-luna", {"effort": "none"}), "more": ("gpt-5.6-luna", {"effort": "medium"})},
    "H12": {"title": "Sonnet 5 — thinking off vs xhigh", "seed": 20260929,
            "less": ("claude-sonnet-5", {"thinking": "disabled"}), "more": ("claude-sonnet-5", {"effort": "xhigh"})},
}

SMALL_WORDING = (f"no change larger than {SMALL_MARGIN} — small against the {HAIKU_LUNA_GAP} Haiku–Luna gap it is "
                 "meant to explain")


def _matches(r: dict, cond) -> bool:
    model, want = cond
    c = r.get("conditions") or {}
    if (r.get("model") or {}).get("model_id") != model:
        return False
    for k in ("effort", "thinking"):
        if c.get(k) != want.get(k):
            return False
    return True


def primary_trials(recs, cond) -> list[dict]:
    """Static, off-anchor, non-crash faulty trials of one condition (pilot / exploratory refused)."""
    out = []
    for r in recs:
        if (r.get("conditions") or {}).get("pilot") or r.get("_exploratory"):
            continue
        if r.get("_tier") == "control" or r.get("_agent") != AGENT or r.get("_anchor") != OFF:
            continue
        if ss.mechanism_of(r["_op"]) in CRASH_MECHANISMS or not _matches(r, cond):
            continue
        out.append(r)
    return out


def _by_mech_case(trials) -> dict:
    out: dict = {}
    for t in trials:
        out.setdefault(ss.mechanism_of(t["_op"]), {}).setdefault(t["case_id"], []).append(t)
    return out


def _rate(trials) -> float | None:
    return sum(1 for t in trials if ss._detect_correct(t)) / len(trials) if trials else None


def headroom(less_trials) -> dict:
    """Per mechanism: the LESS-reasoning condition's detection with its 95% interval (case-clustered bootstrap;
    exact Clopper–Pearson over cases at 0 or 1) and whether it carries the decision (upper bound < 0.85)."""
    out = {}
    for mech, cases in sorted(_by_mech_case(less_trials).items()):
        ci = pp1._rate_ci([t for ts in cases.values() for t in ts], ss._detect_correct)
        out[mech] = {"less_detect": ci, "eligible": ci["hi"] is not None and ci["hi"] < HEADROOM_MAX_UPPER}
    return out


def _D(by_mech: dict, draws: dict) -> float:
    rates = []
    for mech, cases in draws.items():
        ts = [t for c in cases for t in by_mech[mech].get(c, [])]
        rates.append(_rate(ts))
    return sum(rates) / len(rates)


def paired_bootstrap(less_trials, more_trials, mechs, seed, n=N_BOOT) -> dict:
    """Δ̂ and B Δ* from case resamples STRATIFIED by mechanism, paired (only cases present in both conditions)."""
    L, M = _by_mech_case(less_trials), _by_mech_case(more_trials)
    strata = {m: sorted(set(L.get(m, {})) & set(M.get(m, {}))) for m in sorted(mechs)}
    strata = {m: cs for m, cs in strata.items() if cs}
    full = {m: cs for m, cs in strata.items()}
    delta = _D(M, full) - _D(L, full)
    rng = random.Random(seed)
    boots = []
    for _ in range(n):
        draw = {m: [rng.choice(cs) for _ in cs] for m, cs in strata.items()}
        boots.append(_D(M, draw) - _D(L, draw))
    return {"delta": delta, "boots": boots, "clusters": {m: len(cs) for m, cs in strata.items()}}


def two_sided_p(boots) -> float:
    """p for Δ = 0: p = min(1, 2·min(L + T/2, U + T/2)/B); L, U = resamples below / above 0, T = exact ties
    (paired detection differences are discrete, so ties are common and count half to each tail)."""
    below = sum(1 for d in boots if d < 0)
    above = sum(1 for d in boots if d > 0)
    ties = len(boots) - below - above
    return min(1.0, 2 * min(below + ties / 2, above + ties / 2) / len(boots))


def percentile_ci(boots) -> tuple[float, float]:
    """The ⌊0.025·B⌋-th and (⌊0.975·B⌋ − 1)-th order statistics (0-indexed), as H10."""
    v = sorted(boots)
    return v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]


def analyse(recs, name: str, spec=None) -> dict:
    """One hypothesis's statistics BEFORE multiplicity: headroom, eligible mechanisms, Δ̂, p, interval."""
    spec = spec or HYPOTHESES[name]
    less, more = primary_trials(recs, spec["less"]), primary_trials(recs, spec["more"])
    out = {"name": name, "title": spec["title"], "n_less": len(less), "n_more": len(more)}
    if not less or not more:
        return {**out, "testable": False, "reason": "missing: no primary trials for one condition"}
    hr = headroom(less)
    eligible = [m for m, d in hr.items() if d["eligible"]]
    out.update(headroom=hr, eligible=eligible)
    per_mech = {}
    for m in sorted(hr):
        b = paired_bootstrap(less, more, [m], spec["seed"], n=2000)
        lo, hi = percentile_ci(b["boots"])
        per_mech[m] = {"delta": b["delta"], "lo": lo, "hi": hi}
    out["per_mechanism"] = per_mech
    if len(eligible) < MIN_MECHANISMS:
        return {**out, "testable": False,
                "reason": f"{len(eligible)} eligible mechanism(s) < {MIN_MECHANISMS} (headroom rule)"}
    b = paired_bootstrap(less, more, eligible, spec["seed"])
    lo, hi = percentile_ci(b["boots"])
    return {**out, "testable": True, "delta": b["delta"], "lo": lo, "hi": hi, "p": two_sided_p(b["boots"]),
            "clusters": b["clusters"], "B": len(b["boots"])}


def decide(results: dict) -> dict:
    """Holm over the TESTABLE hypotheses (α = 0.05), then the verdict per hypothesis."""
    testable = {k: r["p"] for k, r in results.items() if r.get("testable")}
    rejected = pp1._holm(testable, ALPHA) if testable else {}
    out = {}
    for k, r in results.items():
        if not r.get("testable"):
            out[k] = {**r, "verdict": "UNTESTABLE", "why": f"no headroom — untestable ({r.get('reason')})"}
            continue
        rej = rejected[k]
        if rej and r["delta"] > 0:
            v, why = "CONFIRMING", "Holm-rejected; Δ in the declared direction (more reasoning, higher detection)"
        elif rej and r["delta"] < 0:
            v, why = "REFUTING (opposite direction)", "Holm-rejected; Δ opposite to the declared direction"
        elif not rej and -SMALL_MARGIN < r["lo"] and r["hi"] < SMALL_MARGIN:
            v, why = "REFUTING (shown small)", SMALL_WORDING
        else:
            v, why = "INCONCLUSIVE", "not rejected by Holm, and the interval is not inside ±0.15" if not rej \
                else "Holm-rejected with Δ̂ = 0 exactly"
        out[k] = {**r, "verdict": v, "why": why, "holm_rejected": rej, "holm_m": len(testable)}
    return out


def part2_verdicts(recs) -> dict:
    return decide({k: analyse(recs, k) for k in HYPOTHESES})


def present(recs) -> bool:
    """True iff any record belongs to a Part 2 confirmatory condition (so the report renders the section)."""
    return any(_matches(r, s[c]) for r in recs for s in HYPOTHESES.values() for c in ("less", "more"))
