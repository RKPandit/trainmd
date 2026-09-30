#!/usr/bin/env python3
"""What does the agent add? — non-LLM baselines vs a sweep's agents on the SAME cases (any workload).

Every contestant is scored end-to-end by the standard scorer (`harness.scoring`): an empty or unparseable
diagnosis counts as a MISS on a faulty case, and is never a false alarm on a control (a false alarm is a
stated `detected: true`). Validity — the share of trials with a usable diagnosis — is its own column.

Rows: the baselines, then one row per FULL agent condition — model + its settings (effort / thinking / strict
tools, `report_gen.condition_of`) × agent × anchor arm — never pooled across settings (external review
2026-09-30). Columns: detection, false alarms (all controls, healthy, benign), Youden's J = detection − false
alarms, identification, evidence F1, repair (verified recovery; baselines are not verified), validity, cost.
Faulty cases are pooled by distinct fault MECHANISM (`harness.sweep_stats.MECHANISM`, workload-aware): the
unweighted mean over mechanisms. CIs: 95% percentile bootstrap over cases (10,000 resamples); a rate at exactly
0 or 1 carries the main report's exact Clopper–Pearson interval over its unique cases instead of a degenerate
[0, 0] / [1, 1]. Case counts are read from the data, never hard-coded (workload 1: 200 cases, 92 controls;
image: 230, 104).

Baselines (harness/baselines.py; read only the agent-visible surface):
  B0 exit code · B1 band detector on the FINAL epoch (the public reference band — the stats arm's knowledge)
  · B0 ∨ B1 (nonzero exit OR final metric outside the band; computed per case from its own outputs)
  · B2 config delta (declared workload knowledge: the clean resolved config of the case's OWN workload)
  · B3 = B1 ∪ B2 · BF form-only comparator (detection only).
B2+ and B4 are upper bounds, not baselines, and are not rows here.

Scoring reads hidden cards: run in the canonical container
    python scripts/agent_value_table.py --sweep stage4_part1 --out docs/audits/agent_value_part1_200.md
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import baselines as B  # noqa: E402
from harness import sweep_stats as ss  # noqa: E402

BASELINES = [("B0 exit code", "b0"), ("B1 band, final epoch (public band)", "b1"),
             ("B0 ∨ B1 (nonzero exit or final metric outside the band)", "b01"), ("B2 config delta", "b2"),
             ("B3 = B1 ∪ B2", "b3"), ("BF form-only (comparator)", "bform")]
# APPENDIX only: B1's definition before 2026-09-27 (every epoch vs the final-accuracy band) and its union.
APPENDIX = [("B1 every epoch (pre-2026-09-27 definition)", "b1_any"), ("B3 with every-epoch B1", "b3_any")]


def baseline_records(root: Path, name: str, case_ids=None) -> list[dict]:
    """One pseudo-trial per built case (restricted to `case_ids`, the sweep's own cases, when given), shaped like
    an agent record for the shared statistics."""
    meta = ss.case_meta_from_cases(root)
    out = []
    for cd in sorted((root / "cases").glob("case_*")):
        if not (cd / "card.public.yaml").exists() or (case_ids is not None and cd.name not in case_ids):
            continue
        sub, scores = B.score_baseline(cd, name, project_root=root)
        rec = {"case_id": cd.name, "submission": sub, "scores": scores, "conditions": {},
               "usage": {"estimated_cost_usd": 0.0}, "compliance": {"missing_fields": []}}
        out.append(ss.attach_meta(rec, meta(cd.name)))
    return out


def _mech_macro(pred):
    """Mean over mechanisms of the per-mechanism rate of `pred` among faulty trials (None if none)."""
    def stat(trials):
        by = defaultdict(list)
        for t in trials:
            if t.get("_tier") != "control":
                by[ss.mechanism_of(t["_op"])].append(pred(t))
        rates = [sum(v) / len(v) for v in by.values() if v]
        return sum(rates) / len(rates) if rates else None
    return stat


def _ctrl_rate(pred):
    def stat(trials):
        c = [t for t in trials if t.get("_tier") == "control"]
        return sum(1 for t in c if pred(t)) / len(c) if c else None
    return stat


def _fmt(ci) -> str:
    if ci is None or ci["point"] is None:
        return "—"
    mark = "\u2020" if ci.get("exact") else "\u2021" if ci.get("exact_macro") else ""
    if not mark and ci["lo"] == ci["hi"]:
        return f"{ci['point']:.3f} (no case-level variation)"   # e.g. a deterministic baseline's evidence F1
    return f"{ci['point']:.3f} [{ci['lo']:.3f}, {ci['hi']:.3f}]" + mark


def _ci(trials, stat):
    """Case-bootstrap CI; at a rate of exactly 0 or 1 the exact Clopper–Pearson interval over the unique cases
    (the main report's treatment — the bootstrap is degenerate there). `trials` must be the stat's own subset."""
    ci = ss.bootstrap_ci(trials, stat)
    p, k = ci["point"], ci["n_cases"]
    if p is not None and k and p in (0.0, 1.0):
        lo, hi = ss.clopper_pearson(round(p * k), k)
        ci.update(lo=lo, hi=hi, exact=True)
    return ci


def _macro_ci(faulty, pred):
    """CI of a by-mechanism rate. When the case bootstrap is DEGENERATE (lo == hi — deterministic contestants such
    as the baselines, where every mechanism's rate is 0 or 1), each mechanism's rate gets the exact Clopper–Pearson
    interval over its unique cases (the main report's zero-event treatment) and the pooled interval is the MEAN of
    those exact limits (marked \u2021)."""
    ci = _ci(faulty, _mech_macro(pred))
    if ci["point"] is None or ci.get("exact") or ci["lo"] != ci["hi"]:
        return ci
    by = defaultdict(lambda: defaultdict(list))
    for t in faulty:
        by[ss.mechanism_of(t["_op"])][t["case_id"]].append(bool(pred(t)))
    los, his = [], []
    for cases in by.values():
        n = len(cases)
        k = sum(1 for v in cases.values() if all(v))
        if 0 < k < n and not all(len(set(v)) == 1 for v in cases.values()):
            return ci                                   # not a per-case-deterministic 0/1 stratum: keep bootstrap
        lo, hi = ss.clopper_pearson(k, n)
        los.append(lo)
        his.append(hi)
    ci.update(lo=sum(los) / len(los), hi=sum(his) / len(his), exact_macro=True)
    return ci


def _j(trials):
    d = _mech_macro(ss._detect_correct)(trials)
    f = _ctrl_rate(lambda t: ss._detected(t) is True)(trials)
    return None if d is None or f is None else d - f


def summarize(recs: list[dict], verified_repair: bool = True) -> dict:
    faulty = [r for r in recs if r.get("_tier") != "control"]
    ctrl = [r for r in recs if r.get("_tier") == "control"]
    alarm = _ctrl_rate(lambda t: ss._detected(t) is True)
    per_mech = {}
    for m in sorted({ss.mechanism_of(r["_op"]) for r in faulty}):
        f = [r for r in faulty if ss.mechanism_of(r["_op"]) == m]
        per_mech[m] = (sum(map(ss._detect_correct, f)) / len(f), sum(map(ss._id_correct, f)) / len(f), len(f))
    det = _macro_ci(faulty, ss._detect_correct) if faulty else None
    far = _ci(ctrl, alarm) if ctrl else None
    j = ss.bootstrap_ci(recs, _j) if faulty and ctrl else None
    if j and j["point"] is not None and j["lo"] == j["hi"] and (det.get("exact") or det.get("exact_macro")
                                                               or far.get("exact")):
        # degenerate bootstrap (deterministic contestant): J's interval from its parts' exact limits
        j.update(lo=det["lo"] - far["hi"], hi=det["hi"] - far["lo"], exact_macro=True)
    return {
        "det": det,
        "id": _macro_ci(faulty, ss._id_correct) if faulty else None,
        "ev": ss.bootstrap_ci(faulty, _mech_macro(lambda t: ss._ev_f1(t) or 0.0)) if faulty else None,
        "rep": (_ci(faulty, _mech_macro(ss._recovered)) if faulty and verified_repair else None),
        "far": far,
        "far_h": _ci([r for r in ctrl if not r.get("_benign_form")], alarm),
        "far_b": _ci([r for r in ctrl if r.get("_benign_form")], alarm),
        "j": j,
        "cost": sum((r.get("usage") or {}).get("estimated_cost_usd") or 0.0 for r in recs) / len(recs),
        "valid": sum(1 for r in recs if ss.valid_submission(r)) / len(recs),
        "n": len(recs), "n_cases": len({r["case_id"] for r in recs}),
        "n_ctrl": len({r["case_id"] for r in ctrl}),
        "n_healthy": len({r["case_id"] for r in ctrl if not r.get("_benign_form")}),
        "n_benign": len({r["case_id"] for r in ctrl if r.get("_benign_form")}),
        "per_mech": per_mech}


def _main_table(rows):
    s0 = rows[0][1] if rows else {"n_ctrl": "?", "n_healthy": "?", "n_benign": "?"}
    L = [f"| contestant | trials | cases | detection (faulty, by mechanism) | false alarms (all {s0['n_ctrl']} controls) "
         f"| false alarms: healthy ({s0['n_healthy']}) | false alarms: benign ({s0['n_benign']}) | J = detection − "
         "false alarms | identification (by mechanism) | evidence F1 (by mechanism) | repair: verified recovery "
         "| valid submissions | $ / trial |", "|" + "---|" * 13]
    for name, s in rows:
        L.append(f"| {name} | {s['n']} | {s['n_cases']} | {_fmt(s['det'])} | {_fmt(s['far'])} | {_fmt(s['far_h'])} "
                 f"| {_fmt(s['far_b'])} | {_fmt(s['j'])} | {_fmt(s['id'])} | {_fmt(s['ev'])} "
                 f"| {_fmt(s['rep']) if s['rep'] is not None else 'not verified'} | {s['valid']:.3f} "
                 f"| {s['cost']:.4f} |")
    return L


def render(rows: list[tuple[str, dict]], sweep: str, appendix: list[tuple[str, dict]] = ()) -> str:
    n_cases = rows[0][1]["n_cases"] if rows else "?"
    n_mech = len({m for _, s in rows for m in s["per_mech"]})
    L = [f"# What does the agent add? — baselines vs {sweep} agents on the same {n_cases} cases", "",
         "> Generated by `scripts/agent_value_table.py` in the canonical container; do NOT hand-edit. "
         "End-to-end scoring (an empty diagnosis = a miss; never a false alarm). Faulty cases pooled by "
         f"MECHANISM (variants of one mechanism pooled; pooled = unweighted mean of {n_mech} mechanisms). One row per "
         "FULL condition (model + settings) × agent × arm. 95% case-bootstrap CIs; \u2020 = a rate of exactly 0 "
         "or 1, shown with the exact Clopper–Pearson interval over its unique cases; \u2021 = a by-mechanism rate "
         "whose bootstrap is degenerate (each mechanism 0 or 1 — deterministic baselines): the mean of the "
         "per-mechanism exact limits (for J: detection's exact limits minus the false-alarm rate's); a value "
         "marked 'no case-level variation' is constant across cases, so no case interval exists. Identification is the verdict "
         "stored in each record (the frozen scorer); baselines are scored live by the same frozen scorer. Repair = "
         "verified recovery (agents only; baseline repairs are not trained).", ""] + _main_table(rows)
    mechs = sorted({m for _, s in rows for m in s["per_mech"]})
    L += ["", "## By mechanism — detection / identification (point; trials)", "",
          "| contestant | " + " | ".join(mechs) + " |", "|" + "---|" * (len(mechs) + 1)]
    for name, s in rows:
        L.append(f"| {name} | " + " | ".join(
            f"{s['per_mech'][m][0]:.2f} / {s['per_mech'][m][1]:.2f} ({s['per_mech'][m][2]})" if m in s["per_mech"]
            else "—" for m in mechs) + " |")
    L += ["", "**Reading this table.** B0, B1 and BF state no fault class, so their identification is 0 by "
          "construction. B1 compares the visible metric with the PUBLIC reference band — the knowledge the "
          "stats / rule arms are given — so it is the fair floor for those arms, not for `off`. B2 carries "
          "declared workload knowledge (the clean resolved config and which keys are derived) and flags every "
          "config change, so its false-alarm rate on benign controls is the cost of that policy. Cost excludes "
          "the free training run every contestant reads. Agent rows exclude the exploratory no-passback arm "
          "and pilot trials; one trial per scheduled cell."]
    if appendix:
        L += ["", "## Appendix — B1 on EVERY epoch (its definition before 2026-09-27)", "",
              "Until 2026-09-27 B1 flagged a run if ANY epoch's visible accuracy left the band; the band describes "
              "the reference runs' FINAL accuracy (±2σ, σ ≈ 0.002), so ordinary epoch-to-epoch fluctuation of a "
              "healthy run triggers it. Final-epoch B1 is the declared baseline (DECISIONS 2026-09-27); these rows "
              "are shown for the record only.", ""] + _main_table(appendix)
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", default="stage4_part1")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "audits" / "agent_value_part1_200.md")
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.project_root
    from harness.report_gen import condition_of
    agents = [r for r in ss.load_from_cases(root, a.sweep) if not r["_exploratory"]]
    case_ids = {r["case_id"] for r in agents}          # the sweep's own cases (its workload), never all of cases/
    rows = [(label, summarize(baseline_records(root, key, case_ids), verified_repair=False))
            for label, key in BASELINES]
    groups = defaultdict(list)
    for r in agents:
        groups[(condition_of(r), r["_agent"], r["_anchor"])].append(r)     # the FULL condition
    for (cond, agent, arm) in sorted(groups, key=lambda k: tuple(map(str, k))):
        rows.append((f"{cond} · {agent} · {arm}", summarize(groups[(cond, agent, arm)])))
    appendix = [(label, summarize(baseline_records(root, key, case_ids), verified_repair=False))
                for label, key in APPENDIX]
    a.out.write_text(render(rows, a.sweep, appendix))
    print(f"wrote {a.out.relative_to(root) if a.out.is_relative_to(root) else a.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
