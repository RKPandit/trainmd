"""Stage 4 Part 1 pre-registered verdicts, computed MECHANICALLY from records (docs/PREREG_STAGE4_PART1).

Built and tested BEFORE the run so no verdict can be shaped after seeing data. Three analyses:

  h9_verdict       model dependence beyond leakage, with the Haiku HEADROOM rule
  h10_verdict      bare statistics close most of the off→rule detection gap, per model, Holm over models
  benign_verdict   paired arm contrast of benign false positives (two-sided), Holm over four contrasts

Every threshold is a module constant, so the pre-registration and the code name the same number. Inputs
are attached records (harness/sweep_stats.attach_meta); the exploratory no-passback arm is excluded here.
"""
from __future__ import annotations

import math
from statistics import NormalDist

from harness import sweep_stats as ss

ALPHA = 0.05
OFF, STATS, RULE = "off.v2", "stats.v2", "rule.v2"
REF_PROVIDER, CMP_PROVIDER = "anthropic", "openai"          # Haiku, Luna

# --- H9 --------------------------------------------------------------------------------------------
H9_NON_LEAKAGE = ("silent.lr_warmup.v1", "silent.label_corruption.v1", "silent.metric_inflation.v1")
H9_LEAKAGE = ("silent.data_leakage.v1", "silent.data_leakage_neutral.v1")
H9_HEADROOM_MAX_UPPER = 0.85      # an operator carries the decision only if Haiku's off upper bound < this
H9_MIN_CARRIERS = 2               # fewer decision-carrying non-leakage operators → INCONCLUSIVE
H9_SMALL_GAP = 0.20               # REFUTING needs every carrier's Δ upper bound below this

# --- H10 -------------------------------------------------------------------------------------------
H10_MIN_GAP = 0.30                # an operator enters f only if its rule − off detection gap ≥ this
H10_THRESHOLD = 0.5               # f compared against one half


def _primary(recs):
    return [r for r in recs if not r.get("_exploratory")]


def _det_rate(trials):
    return (sum(1 for t in trials if ss._detect_correct(t)) / len(trials)) if trials else None


def _rate_ci(trials, pred):
    """Case-clustered bootstrap 95% CI of a rate; at 0 or 1 the exact Clopper–Pearson interval over the
    number of unique cases (the bootstrap is degenerate there)."""
    ci = ss.bootstrap_ci(trials, lambda ts: (sum(1 for t in ts if pred(t)) / len(ts)) if ts else None)
    p, k = ci["point"], ci["n_cases"]
    if p is not None and k and p in (0.0, 1.0):
        lo, hi = ss.clopper_pearson(round(p * k), k)
        ci.update(lo=lo, hi=hi, exact=True)
    return ci


# =============================================================================== H9
def h9_verdict(recs) -> dict:
    recs = _primary(recs)
    off = [r for r in recs if r.get("_anchor") == OFF]
    ops = {}
    for op in H9_NON_LEAKAGE:
        rs = [r for r in off if r["_op"] == op]
        ref = [r for r in rs if r["_provider"] == REF_PROVIDER]
        cmp_ = [r for r in rs if r["_provider"] == CMP_PROVIDER]
        if not ref or not cmp_:
            ops[op] = {"status": "missing", "reason": "no off-anchor records for both models"}
            continue
        ref_ci = _rate_ci(ref, ss._detect_correct)
        carries = ref_ci["hi"] is not None and ref_ci["hi"] < H9_HEADROOM_MAX_UPPER
        ops[op] = {"ref_detect": ref_ci, "cmp_detect": _det_rate(cmp_),
                   "delta": _delta_ci(rs),
                   "status": "carries_decision" if carries else "no_headroom_untestable"}
    leak = [r for r in off if r["_op"] in H9_LEAKAGE]
    leak_delta = _delta_ci(leak) if leak else None
    carriers = [op for op, d in ops.items() if d["status"] == "carries_decision"]
    if len(carriers) < H9_MIN_CARRIERS:
        verdict, why = "INCONCLUSIVE", (f"{len(carriers)} decision-carrying non-leakage operator(s) "
                                        f"< {H9_MIN_CARRIERS} (headroom rule)")
    elif all(ops[o]["delta"]["lo"] > 0 for o in carriers):
        verdict, why = "CONFIRMING", "Δ lower bound > 0 on every decision-carrying operator"
    elif (all(ops[o]["delta"]["hi"] < H9_SMALL_GAP for o in carriers)
          and leak_delta is not None and leak_delta["lo"] > 0):
        verdict, why = "REFUTING", (f"Δ upper bound < {H9_SMALL_GAP} on every decision-carrying operator "
                                    "while leakage's lower bound > 0")
    else:
        verdict, why = "INCONCLUSIVE", "mixed, or gaps neither shown present nor shown small"
    return {"verdict": verdict, "reason": why, "carriers": carriers, "operators": ops,
            "leakage_delta": leak_delta, "multiplicity": "intersection-union (every carrier must pass "
            "at 95% individually) — no adjustment needed"}


def _delta_ci(rs):
    """Δ = detection(Luna) − detection(Haiku), case-clustered (both models ran every case)."""
    def delta(ts):
        a = _det_rate([t for t in ts if t["_provider"] == CMP_PROVIDER])
        b = _det_rate([t for t in ts if t["_provider"] == REF_PROVIDER])
        return None if a is None or b is None else a - b
    return ss.bootstrap_ci(rs, delta)


# =============================================================================== H10
def h10_verdict(recs) -> dict:
    recs = _primary(recs)
    faulty = [r for r in recs if r.get("_tier") != "control" and r.get("_anchor") in (OFF, STATS, RULE)]
    models = {}
    for prov in (REF_PROVIDER, CMP_PROVIDER):
        mine = [r for r in faulty if r["_provider"] == prov]
        eligible, gaps = [], {}
        for op in sorted({r["_op"] for r in mine}):
            rs = [r for r in mine if r["_op"] == op]
            lo, hi = (_det_rate([r for r in rs if r["_anchor"] == a]) for a in (OFF, RULE))
            gaps[op] = None if lo is None or hi is None else round(hi - lo, 4)
            if gaps[op] is not None and gaps[op] >= H10_MIN_GAP:
                eligible.append(op)
        if not eligible:
            models[prov] = {"verdict": "UNTESTABLE", "reason": f"no operator with rule − off ≥ {H10_MIN_GAP}",
                            "gaps": gaps, "eligible": []}
            continue
        pool = [r for r in mine if r["_op"] in eligible]

        def f(ts):
            o, s, u = (_det_rate([t for t in ts if t["_anchor"] == a]) for a in (OFF, STATS, RULE))
            if o is None or s is None or u is None or abs(u - o) < 1e-9:
                return None
            return (s - o) / (u - o)

        ci, boots = _bootstrap_with_draws(pool, f)
        below = sum(1 for v in boots if v < H10_THRESHOLD)
        p = min(1.0, 2 * min(below, len(boots) - below) / len(boots)) if boots else 1.0
        models[prov] = {"f": ci, "p_two_sided": p, "gaps": gaps, "eligible": eligible,
                        "n_resamples_used": len(boots)}
    tested = [m for m in models if "p_two_sided" in models[m]]
    rejected = _holm({m: models[m]["p_two_sided"] for m in tested})
    for m in tested:
        d = models[m]
        pt = d["f"]["point"]
        if rejected[m] and pt is not None and pt > H10_THRESHOLD:
            d["verdict"] = "CONFIRMING"
        elif rejected[m] and pt is not None and pt < H10_THRESHOLD:
            d["verdict"] = "REFUTING"
        else:
            d["verdict"] = "INCONCLUSIVE"         # not rejected, or f̂ exactly 0.5
    return {"models": models, "multiplicity": f"Holm over the {len(tested)} tested model(s), α = {ALPHA}"}


def _bootstrap_with_draws(recs, statistic, n=ss.N_RESAMPLES, seed=ss.SEED):
    """ss.bootstrap_ci plus the resampled values (for a bootstrap p-value); same case resampling."""
    import random
    by_case = ss._by_case(recs)
    cases = sorted(by_case)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [rng.choice(cases) for _ in cases]
        v = statistic([t for c in pick for t in by_case[c]])
        if v is not None:
            vals.append(v)
    s = sorted(vals)
    ci = {"point": statistic(recs), "lo": s[int(0.025 * len(s))] if s else None,
          "hi": s[int(0.975 * len(s)) - 1] if s else None, "n_cases": len(cases), "n_trials": len(recs)}
    return ci, vals


def band_benefit_descriptive(recs) -> dict:
    """SECONDARY / descriptive (the former H10 ordering): per model × operator × anchored arm, the raw
    band benefit B = detect(arm) − detect(off) and the headroom-normalised benefit B / (1 − detect(off))
    (None when off is already at 1). No verdict."""
    recs = _primary(recs)
    faulty = [r for r in recs if r.get("_tier") != "control"]
    out = {}
    for prov in (REF_PROVIDER, CMP_PROVIDER):
        for op in sorted({r["_op"] for r in faulty if r["_provider"] == prov}):
            rs = [r for r in faulty if r["_provider"] == prov and r["_op"] == op]
            off = _det_rate([r for r in rs if r["_anchor"] == OFF])
            for arm in (STATS, RULE):
                a = _det_rate([r for r in rs if r["_anchor"] == arm])
                if off is None or a is None:
                    continue
                out[(prov, op, arm)] = {"off": off, "arm": a, "benefit": a - off,
                                        "normalised": None if off >= 1 else (a - off) / (1 - off),
                                        "symptom": rs[0].get("_symptom")}
    return out


# =============================================================================== benign
def benign_verdict(recs) -> dict:
    recs = _primary(recs)
    benign = [r for r in recs if r.get("_tier") == "control" and r.get("_benign_form")]
    contrasts = {}
    for prov in (REF_PROVIDER, CMP_PROVIDER):
        mine = [r for r in benign if r["_provider"] == prov]
        fp = {(r["case_id"], r["_anchor"]): ss._detected(r) is True for r in mine}
        for arm in (STATS, RULE):
            cases = sorted({c for c, a in fp if a == arm} & {c for c, a in fp if a == OFF})
            e = sum(1 for c in cases if fp[(c, arm)] and fp[(c, OFF)])
            f = sum(1 for c in cases if fp[(c, arm)] and not fp[(c, OFF)])
            g = sum(1 for c in cases if not fp[(c, arm)] and fp[(c, OFF)])
            h = len(cases) - e - f - g
            key = f"{prov}:{arm.split('.')[0]}-off"
            if not cases:
                contrasts[key] = {"available": False}
                continue
            d, lo, hi = newcombe_paired(e, f, g, h)
            contrasts[key] = {"available": True, "n_pairs": len(cases), "cells": [e, f, g, h],
                              "fpr_arm": (e + f) / len(cases), "fpr_off": (e + g) / len(cases),
                              "delta": d, "lo": lo, "hi": hi, "p_mcnemar": mcnemar_exact(f, g)}
    avail = {k: v["p_mcnemar"] for k, v in contrasts.items() if v.get("available")}
    rejected = _holm(avail)
    for k in avail:
        c = contrasts[k]
        c["verdict"] = ("INCREASE" if c["delta"] > 0 else "DECREASE") if rejected[k] else "INCONCLUSIVE"
    per_provider = {}
    for prov in (REF_PROVIDER, CMP_PROVIDER):
        vs = {contrasts[k]["verdict"] for k in contrasts if k.startswith(prov + ":") and "verdict" in contrasts[k]}
        per_provider[prov] = ("MIXED" if {"INCREASE", "DECREASE"} <= vs else
                              "INCREASE" if "INCREASE" in vs else "DECREASE" if "DECREASE" in vs else
                              "INCONCLUSIVE")
    return {"contrasts": contrasts, "per_provider": per_provider,
            "multiplicity": f"Holm over the {len(avail)} contrasts (exact McNemar), α = {ALPHA}, two-sided"}


# =============================================================================== primitives
_Z = NormalDist().inv_cdf(0.975)


def _wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    d = 1 + _Z * _Z / n
    c = p + _Z * _Z / (2 * n)
    h = _Z * math.sqrt(p * (1 - p) / n + _Z * _Z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def newcombe_paired(e: int, f: int, g: int, h: int) -> tuple[float, float, float]:
    """Newcombe (1998) METHOD 10: θ = (f − g)/n with Wilson score limits for the two marginals and a
    continuity-corrected φ (numerator max(eh − fg − n/2, 0) when eh > fg; φ = 0 if a marginal is 0).
    Cells: e = both positive, f = first only, g = second only, h = neither."""
    n = e + f + g + h
    p1, p2 = (e + f) / n, (e + g) / n
    l2, u2 = _wilson(e + f, n)
    l3, u3 = _wilson(e + g, n)
    den = math.sqrt((e + f) * (g + h) * (e + g) * (f + h))
    num = e * h - f * g
    if num > 0:
        num = max(num - n / 2, 0.0)
    phi = num / den if den else 0.0
    dl2, du2, dl3, du3 = p1 - l2, u2 - p1, p2 - l3, u3 - p2
    theta = (f - g) / n
    delta = math.sqrt(max(dl2 ** 2 - 2 * phi * dl2 * du3 + du3 ** 2, 0.0))
    eps = math.sqrt(max(du2 ** 2 - 2 * phi * du2 * dl3 + dl3 ** 2, 0.0))
    return theta, max(-1.0, theta - delta), min(1.0, theta + eps)


def mcnemar_exact(f: int, g: int) -> float:
    """Exact two-sided McNemar p: binomial(f + g, 1/2) on the discordant pairs (1.0 when none)."""
    n = f + g
    if n == 0:
        return 1.0
    k = min(f, g)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _holm(pvals: dict, alpha: float = ALPHA) -> dict:
    """Holm step-down: {name: rejected}."""
    out = {k: False for k in pvals}
    m = len(pvals)
    for i, (k, p) in enumerate(sorted(pvals.items(), key=lambda kv: (kv[1], kv[0]))):
        if p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out
