"""Stage 4 Part 3 pre-registered verdicts, computed MECHANICALLY from records (HYPOTHESES "Stage 4 Part 3").

Written and tested BEFORE any Part 3 trial (tests/test_prereg_part3.py). Workload: the image classifier. Primary
quantity: Youden's J = DET − FA (LIMITATIONS L39), where
  DET = the unweighted mean over mechanisms of the detection rate on faulty trials (end-to-end), and
  FA  = the share of CONTROL trials (healthy + benign pooled) with detected = true (an empty diagnosis is no alarm).
The crash (channel mismatch) is excluded from every confirmatory quantity; the SILENT mechanisms are leakage and
metric inflation. Confirmatory tests (one Holm family, α = 0.05, over the testable ones):

  H13a  Luna none vs medium, STATIC off:  ΔJ = J(medium) − J(none) > 0, "via false alarms"
  H13b  Luna none vs medium, ReAct off:   ΔJ > 0, "via misses"
  H14   ReAct stats vs off on the silent faults, per condition with headroom (Haiku, Sonnet off, Luna medium)
  H15   Luna medium vs Haiku, off, per mechanism J, pooled over static + ReAct — H9's intersection–union rule
  H16   stats closes the off→rule gap on J, per model (Haiku, Luna medium), static — H10's rule
  H17   Sonnet off: J_silent static > ReAct, off, paired by case (complete agent configurations)

Every threshold is a module constant, so the pre-registration and the code name the same number. Inputs are
attached records (harness/sweep_stats.attach_meta); pilot trials are refused.
"""
from __future__ import annotations

import random

from harness import prereg_part1 as pp1
from harness import sweep_stats as ss
from harness.prereg_part2 import percentile_ci, two_sided_p   # the same rules as Part 2 (ties count half)

ALPHA = 0.05
OFF, STATS, RULE = "off.v2", "stats.v2", "rule.v2"
STATIC, REACT = "static", "react"
CRASH_MECHANISMS = frozenset({"shape_mismatch"})
SILENT_MECHANISMS = frozenset({"data_leakage", "metric_inflation"})
HEADROOM_MAX_UPPER = 0.85     # a unit is eligible only if the LOWER side's J 95% upper bound < this
MIN_MECHANISMS = 2            # per-mechanism tests need at least this many eligible mechanisms
SMALL_MARGIN = 0.15           # REFUTING (shown small): the Δ interval inside (−0.15, +0.15)
H15_SMALL_UPPER = 0.20        # H9's rule: REFUTING iff every Δ_m upper bound < 0.20
H16_MIN_GAP = 0.30            # H10's eligibility: a mechanism's J rule − off gap ≥ 0.30
H16_NULL_F = 0.5
CLAUSE_SHARE = 0.5            # "via false alarms" / "via misses": the component ≥ half of ΔĴ
N_BOOT = 10_000
N_BOOT_HEADROOM = 2_000

# (model_id, ((condition key, value), ...)) — hashable, so a condition can key a dict
HAIKU = ("claude-haiku-4-5-20251001", ())
SONNET_OFF = ("claude-sonnet-5", (("thinking", "disabled"),))
LUNA_MED = ("gpt-5.6-luna", (("effort", "medium"),))
LUNA_NONE = ("gpt-5.6-luna", (("effort", "none"),))
CONDITION_NAMES = {HAIKU: "Haiku 4.5", SONNET_OFF: "Sonnet 5 thinking off", LUNA_MED: "GPT-5.6 Luna medium",
                   LUNA_NONE: "GPT-5.6 Luna none"}
H14_CONDITIONS = (HAIKU, SONNET_OFF, LUNA_MED)     # Luna none excluded by design (its ReAct misses are H13b)
H16_CONDITIONS = (HAIKU, LUNA_MED)


def _matches(r: dict, cond) -> bool:
    model, want = cond[0], dict(cond[1])
    c = r.get("conditions") or {}
    if (r.get("model") or {}).get("model_id") != model:
        return False
    return all(c.get(k) == want.get(k) for k in ("effort", "thinking"))


def _is_alarm(t) -> bool:
    return ((t.get("scores") or {}).get("detection") or {}).get("detected_predicted") is True


class Side:
    """One side of a contrast: per-case (positives, n) counts for faulty trials by mechanism and control trials by
    control type (the control operator), restricted to a condition, agent set and arm."""

    def __init__(self, recs, cond, agents, arm, mechs=None):
        self.f: dict = {}
        self.c: dict = {}
        for r in recs:
            if (r.get("conditions") or {}).get("pilot") or r.get("_exploratory"):
                continue
            if r.get("_agent") not in agents or r.get("_anchor") != arm or not _matches(r, cond):
                continue
            if r.get("_tier") == "control":
                k, n = self.c.setdefault(r["_op"], {}).get(r["case_id"], (0, 0))
                self.c[r["_op"]][r["case_id"]] = (k + _is_alarm(r), n + 1)
                continue
            m = ss.mechanism_of(r["_op"])
            if m in CRASH_MECHANISMS or (mechs is not None and m not in mechs):
                continue
            k, n = self.f.setdefault(m, {}).get(r["case_id"], (0, 0))
            self.f[m][r["case_id"]] = (k + bool(ss._detect_correct(r)), n + 1)

    def empty(self) -> bool:
        return not self.f or not self.c

    def stat(self, fdraw: dict, cdraw: dict) -> tuple[float, float, float]:
        """(J, DET, FA) on drawn cases: DET = mean over the drawn mechanisms; FA pooled over control trials."""
        rates = []
        for m, cases in fdraw.items():
            k = sum(self.f[m][c][0] for c in cases)
            n = sum(self.f[m][c][1] for c in cases)
            rates.append(k / n)
        det = sum(rates) / len(rates)
        k = sum(self.c[t][c][0] for t, cases in cdraw.items() for c in cases)
        n = sum(self.c[t][c][1] for t, cases in cdraw.items() for c in cases)
        fa = k / n
        return det - fa, det, fa


def _strata(a: Side, b: Side | None, mechs):
    """Paired strata: the cases present on BOTH sides, per mechanism and per control type."""
    fs = {m: sorted(set(a.f.get(m, {})) & (set(b.f.get(m, {})) if b else set(a.f.get(m, {})))) for m in sorted(mechs)}
    cs = {t: sorted(set(a.c[t]) & (set(b.c.get(t, {})) if b else set(a.c[t]))) for t in sorted(a.c)}
    return {m: v for m, v in fs.items() if v}, {t: v for t, v in cs.items() if v}


def _draw(rng, strata):
    return {k: [rng.choice(v) for _ in v] for k, v in strata.items()}


def j_interval(side: Side, mechs, seed, n=None) -> dict:
    """J of one side over `mechs` with its 95% percentile interval (case-level bootstrap, stratified)."""
    n = n or N_BOOT_HEADROOM
    fs, cs = _strata(side, None, mechs)
    if not fs or not cs:
        return {"point": None, "lo": None, "hi": None}
    point = side.stat(fs, cs)[0]
    rng = random.Random(seed)
    boots = sorted(side.stat(_draw(rng, fs), _draw(rng, cs))[0] for _ in range(n))
    return {"point": point, "lo": boots[int(0.025 * n)], "hi": boots[int(0.975 * n) - 1]}


def paired(a: Side, b: Side, mechs, seed, n=None) -> dict:
    """Δ = J(b) − J(a) with its components ΔDET = DET(b) − DET(a) and ΔFA = FA(a) − FA(b) (so ΔJ = ΔDET + ΔFA),
    from paired case resamples stratified by mechanism and control type."""
    n = n or N_BOOT
    fs, cs = _strata(a, b, mechs)
    ja, da, fa = a.stat(fs, cs)
    jb, db, fb = b.stat(fs, cs)
    rng = random.Random(seed)
    boots = {"J": [], "DET": [], "FA": []}
    for _ in range(n):
        f, c = _draw(rng, fs), _draw(rng, cs)
        (ja_, da_, fa_), (jb_, db_, fb_) = a.stat(f, c), b.stat(f, c)
        boots["J"].append(jb_ - ja_)
        boots["DET"].append(db_ - da_)
        boots["FA"].append(fa_ - fb_)
    return {"delta": jb - ja, "d_det": db - da, "d_fa": fa - fb, "boots": boots,
            "clusters": {**{m: len(v) for m, v in fs.items()}, "controls": sum(len(v) for v in cs.values())}}


def _headroom_mechs(side: Side, seed) -> dict:
    out = {}
    for m in sorted(side.f):
        ci = j_interval(side, [m], seed)
        out[m] = {**ci, "eligible": ci["hi"] is not None and ci["hi"] < HEADROOM_MAX_UPPER}
    return out


def _delta_test(name, title, lower: Side, upper: Side, mechs, seed, clause=None) -> dict:
    b = paired(lower, upper, mechs, seed)
    lo, hi = percentile_ci(b["boots"]["J"])
    out = {"name": name, "title": title, "kind": "delta", "testable": True, "delta": b["delta"], "lo": lo, "hi": hi,
           "p": two_sided_p(b["boots"]["J"]), "d_det": b["d_det"], "d_fa": b["d_fa"], "clusters": b["clusters"],
           "B": len(b["boots"]["J"]), "mechanisms": sorted(mechs)}
    if clause:
        comp = "FA" if clause == "via false alarms" else "DET"
        clo, chi = percentile_ci(b["boots"][comp])
        point = b["d_fa"] if comp == "FA" else b["d_det"]
        out["clause"] = {"name": clause, "component": comp, "point": point, "lo": clo, "hi": chi,
                         "met": clo > 0 and point >= CLAUSE_SHARE * b["delta"]}
    return out


def _untestable(name, title, reason, **extra):
    return {"name": name, "title": title, "testable": False, "reason": reason, **extra}


def h13(recs, agent: str) -> dict:
    name = "H13a" if agent == STATIC else "H13b"
    clause = "via false alarms" if agent == STATIC else "via misses"
    title = f"GPT-5.6 Luna none vs medium, {agent}, off arm — J lower without reasoning, {clause}"
    lower, upper = Side(recs, LUNA_NONE, {agent}, OFF), Side(recs, LUNA_MED, {agent}, OFF)
    if lower.empty() or upper.empty():
        return _untestable(name, title, "missing: no faulty or control trials for one condition")
    seed = 20261001 if agent == STATIC else 20261002
    hr = _headroom_mechs(lower, seed)
    eligible = [m for m, d in hr.items() if d["eligible"]]
    if len(eligible) < MIN_MECHANISMS:
        return _untestable(name, title, f"{len(eligible)} eligible mechanism(s) < {MIN_MECHANISMS} (headroom rule)",
                           headroom=hr)
    return {**_delta_test(name, title, lower, upper, eligible, seed, clause), "headroom": hr}


def h14(recs) -> dict:
    """{test name: result} — one test per condition whose ReAct off-arm J_silent upper bound is < 0.85."""
    out = {}
    for i, cond in enumerate(H14_CONDITIONS):
        name = f"H14[{CONDITION_NAMES[cond]}]"
        title = f"{CONDITION_NAMES[cond]}: ReAct stats vs off, J on the silent faults"
        off = Side(recs, cond, {REACT}, OFF, SILENT_MECHANISMS)
        st = Side(recs, cond, {REACT}, STATS, SILENT_MECHANISMS)
        if off.empty() or st.empty():
            out[name] = _untestable(name, title, "missing: no ReAct off or stats trials")
            continue
        seed = 20261010 + i
        hr = j_interval(off, SILENT_MECHANISMS & set(off.f), seed)
        if hr["hi"] is None or hr["hi"] >= HEADROOM_MAX_UPPER:
            out[name] = _untestable(name, title, "no headroom: ReAct off-arm J_silent upper bound ≥ "
                                    f"{HEADROOM_MAX_UPPER}", headroom=hr)
            continue
        out[name] = {**_delta_test(name, title, off, st, sorted(SILENT_MECHANISMS & set(off.f)), seed),
                     "headroom": hr}
    return out


def h15(recs) -> dict:
    name, title = "H15", "Luna medium vs Haiku, off arm, J per mechanism, pooled static + ReAct (H9 rule)"
    agents = {STATIC, REACT}
    haiku, luna = Side(recs, HAIKU, agents, OFF), Side(recs, LUNA_MED, agents, OFF)
    if haiku.empty() or luna.empty():
        return _untestable(name, title, "missing: no trials for one condition")
    hr = _headroom_mechs(haiku, 20261020)
    eligible = [m for m, d in hr.items() if d["eligible"]]
    per = {}
    for i, m in enumerate(sorted(hr)):
        b = paired(haiku, luna, [m], 20261021 + i)
        lo, hi = percentile_ci(b["boots"]["J"])
        per[m] = {"delta": b["delta"], "lo": lo, "hi": hi, "p": two_sided_p(b["boots"]["J"])}
    if len(eligible) < MIN_MECHANISMS:
        return _untestable(name, title, f"{len(eligible)} eligible mechanism(s) < {MIN_MECHANISMS} (headroom rule)",
                           headroom=hr, per_mechanism=per)
    return {"name": name, "title": title, "kind": "iu", "testable": True, "eligible": eligible, "headroom": hr,
            "per_mechanism": per, "p": max(per[m]["p"] for m in eligible)}     # the intersection–union p


def h16(recs) -> dict:
    """{test name: result} — H10's rule on J per model, static; f = (J_stats − J_off) / (J_rule − J_off)."""
    out = {}
    for i, cond in enumerate(H16_CONDITIONS):
        name = f"H16[{CONDITION_NAMES[cond]}]"
        title = f"{CONDITION_NAMES[cond]}: stats closes the off→rule gap on J (static; H10 rule)"
        arms = {a: Side(recs, cond, {STATIC}, a) for a in (OFF, STATS, RULE)}
        if any(s.empty() for s in arms.values()):
            out[name] = _untestable(name, title, "missing: an arm has no faulty or control trials")
            continue
        common = set.intersection(*(set(s.f) for s in arms.values()))
        gaps = {}
        for m in sorted(common):
            fs, cs = _strata(arms[OFF], arms[RULE], [m])
            gaps[m] = arms[RULE].stat(fs, cs)[0] - arms[OFF].stat(fs, cs)[0]
        eligible = [m for m, g in gaps.items() if g >= H16_MIN_GAP]
        if not eligible:
            out[name] = _untestable(name, title, f"no mechanism with a J rule − off gap ≥ {H16_MIN_GAP}", gaps=gaps)
            continue
        # paired strata across the three arms (cases present in all three)
        fs = {m: sorted(set.intersection(*(set(s.f.get(m, {})) for s in arms.values()))) for m in eligible}
        cs = {t: sorted(set.intersection(*(set(s.c.get(t, {})) for s in arms.values()))) for t in arms[OFF].c}
        fs, cs = {m: v for m, v in fs.items() if v}, {t: v for t, v in cs.items() if v}

        def f_of(fd, cd):
            j = {a: arms[a].stat(fd, cd)[0] for a in arms}
            den = j[RULE] - j[OFF]
            return None if den == 0 else (j[STATS] - j[OFF]) / den

        f_hat = f_of(fs, cs)
        rng = random.Random(20261030 + i)
        boots = [v for v in (f_of(_draw(rng, fs), _draw(rng, cs)) for _ in range(N_BOOT)) if v is not None]
        below = sum(1 for v in boots if v < H16_NULL_F)
        p = min(1.0, 2 * min(below, len(boots) - below) / len(boots)) if boots else 1.0
        lo, hi = percentile_ci(boots) if boots else (None, None)
        out[name] = {"name": name, "title": title, "kind": "f", "testable": f_hat is not None, "f": f_hat, "lo": lo,
                     "hi": hi, "p": p, "B": len(boots), "eligible": eligible, "gaps": gaps,
                     **({} if f_hat is not None else {"reason": "J rule − off = 0 on the full sample"})}
    return out


def h17(recs) -> dict:
    name = "H17"
    title = ("Sonnet 5 thinking off, off arm: J on the silent faults is higher for the complete STATIC agent "
             "configuration than for the complete ReAct configuration (paired by case)")
    react = Side(recs, SONNET_OFF, {REACT}, OFF, SILENT_MECHANISMS)
    static = Side(recs, SONNET_OFF, {STATIC}, OFF, SILENT_MECHANISMS)
    if react.empty() or static.empty():
        return _untestable(name, title, "missing: no static or ReAct trials")
    mechs = sorted(SILENT_MECHANISMS & set(react.f))
    hr = j_interval(react, mechs, 20261040)
    if hr["hi"] is None or hr["hi"] >= HEADROOM_MAX_UPPER:
        return _untestable(name, title, f"no headroom: ReAct off-arm J_silent upper bound ≥ {HEADROOM_MAX_UPPER}",
                           headroom=hr)
    return {**_delta_test(name, title, react, static, mechs, 20261041), "headroom": hr}


def analyse_all(recs) -> dict:
    out = {"H13a": h13(recs, STATIC), "H13b": h13(recs, REACT)}
    out.update(h14(recs))
    out["H15"] = h15(recs)
    out.update(h16(recs))
    out["H17"] = h17(recs)
    return out


def decide(results: dict) -> dict:
    """ONE Holm family over every testable test (α = 0.05), then each test's verdict."""
    testable = {k: r["p"] for k, r in results.items() if r.get("testable")}
    rejected = pp1._holm(testable, ALPHA) if testable else {}
    out = {}
    for k, r in results.items():
        if not r.get("testable"):
            out[k] = {**r, "verdict": "UNTESTABLE", "why": f"untestable ({r.get('reason')})"}
            continue
        rej = rejected[k]
        kind = r["kind"]
        if kind == "iu":
            per = [r["per_mechanism"][m] for m in r["eligible"]]
            if rej and all(d["lo"] > 0 for d in per):
                v, why = "CONFIRMING", "Holm-rejected (IU p); every eligible Δ_m has its lower bound > 0"
            elif rej and all(d["hi"] < 0 for d in per):
                v, why = "REFUTING (opposite direction)", "Holm-rejected; every eligible Δ_m below 0"
            elif all(d["hi"] < H15_SMALL_UPPER for d in per):
                v, why = "REFUTING (shown small)", f"every eligible Δ_m upper bound < {H15_SMALL_UPPER}"
            else:
                v, why = "INCONCLUSIVE", "neither rule met on every eligible mechanism"
        elif kind == "f":
            if rej and r["f"] > H16_NULL_F:
                v, why = "CONFIRMING", f"Holm-rejected; f̂ > {H16_NULL_F}"
            elif rej and r["f"] < H16_NULL_F:
                v, why = "REFUTING", f"Holm-rejected; f̂ < {H16_NULL_F}"
            else:
                v, why = "INCONCLUSIVE", "not rejected by Holm (or f̂ = 0.5 exactly)"
        else:
            clause = r.get("clause")
            if rej and r["delta"] > 0 and (clause is None or clause["met"]):
                v, why = "CONFIRMING", "Holm-rejected; ΔJ in the declared direction" + (
                    f"; {clause['name']} clause met" if clause else "")
            elif rej and r["delta"] > 0:
                v, why = "CONFIRMING (J only)", f"Holm-rejected; ΔJ > 0, but the '{clause['name']}' clause fails"
            elif rej and r["delta"] < 0:
                v, why = "REFUTING (opposite direction)", "Holm-rejected; ΔJ opposite to the declared direction"
            elif not rej and -SMALL_MARGIN < r["lo"] and r["hi"] < SMALL_MARGIN:
                v, why = "REFUTING (shown small)", f"not rejected; the ΔJ interval lies inside ±{SMALL_MARGIN}"
            else:
                v, why = "INCONCLUSIVE", "not rejected by Holm, and the interval is not inside ±0.15" if not rej \
                    else "Holm-rejected with ΔJ = 0 exactly"
        out[k] = {**r, "verdict": v, "why": why, "holm_rejected": rej, "holm_m": len(testable)}
    return out


def part3_verdicts(recs) -> dict:
    return decide(analyse_all(recs))


def present(recs) -> bool:
    """True iff any record is an image-workload trial of a Part 3 condition (the report renders the section)."""
    return any(str(r.get("_op", "")).startswith(IMAGE_OP_PREFIXES) and
               any(_matches(r, c) for c in CONDITION_NAMES) for r in recs)


IMAGE_OP_PREFIXES = ("silent.pixel_tag_leakage", "silent.label_flip", "silent.decay_unit", "silent.confident_subset",
                     "crash.channel_mismatch", "control.healthy_image", "control.benign_img_")


PART3_SWEEPS = ("stage4_part3_static", "stage4_part3_react")
VERDICTS_DOC = "docs/audits/stage4_part3_verdicts.md"
PER_SWEEP_NOTE = ("The pre-registered Part 3 verdicts span BOTH Part 3 sweeps — H15 pools static and ReAct, H17 compares "
                  "them, H13a / H13b need one each, and all share one Holm family — so they are computed from "
                  f"{' + '.join(PART3_SWEEPS)} together in `{VERDICTS_DOC}` "
                  "(`python -m harness.prereg_part3 --write`), never from one sweep alone.")


def spans_both_protocols(recs) -> bool:
    """True iff the image-workload Part 3 records include BOTH agents (static and ReAct)."""
    agents = {r.get("_agent") for r in recs if str(r.get("_op", "")).startswith(IMAGE_OP_PREFIXES)}
    return {STATIC, REACT} <= agents


def combined_report(root, sweeps=PART3_SWEEPS) -> str:
    """The pre-registered H13a–H17 section computed over the Part 3 sweeps TOGETHER (the locked family), rendered by
    the same report code as every generated report."""
    from harness import report_gen
    recs = []
    for name in sweeps:
        recs += ss.load_from_cases(root, name)
    recs = [r for r in recs if not r.get("_exploratory")]
    counts = {name: sum(1 for r in recs if (r.get("conditions") or {}).get("sweep_name") == name) for name in sweeps}
    head = ["# Stage 4 Part 3 — pre-registered verdicts (computed over both sweeps)", "",
            "> Machine-generated by `python -m harness.prereg_part3 --write` from the trial records of "
            + ", ".join(f"`{n}` ({counts[n]} records)" for n in sweeps)
            + "; do NOT hand-edit. The family, thresholds and rules are the locked ones (docs/HYPOTHESES.md, "
            "\"Stage 4 Part 3 — PRE-REGISTRATION\"; harness/prereg_part3.py).", ""]
    return "\n".join(head + report_gen._prereg_part3_tables(recs)) + "\n"


def main() -> int:
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser(description="Stage 4 Part 3 pre-registered verdicts over both sweeps")
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--write", action="store_true", help=f"write {VERDICTS_DOC} (otherwise print)")
    a = ap.parse_args()
    md = combined_report(a.project_root)
    if a.write:
        out = a.project_root / VERDICTS_DOC
        out.write_text(md)
        print(f"wrote {out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
