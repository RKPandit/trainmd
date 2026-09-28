#!/usr/bin/env python3
"""What does the agent add? — non-LLM baselines vs the Stage 4 Part 1 agents on the SAME 200 cases.

Every contestant is scored end-to-end by the standard scorer (`harness.scoring`): an empty or unparseable
diagnosis counts as a MISS on a faulty case, and is never a false alarm on a control (a false alarm is a
stated `detected: true`). Validity — the share of trials with a usable diagnosis — is reported in its own
column, never folded into the primary numbers.

Faulty cases are pooled by distinct fault MECHANISM (`harness.sweep_stats.MECHANISM`): the two leakage
variants are one mechanism, so pooled detection / identification are the unweighted mean over the five
mechanisms, and leakage is not counted twice. CIs: 95% percentile bootstrap over cases (10,000 resamples).

Baselines (harness/baselines.py; read only the agent-visible surface):
  B0 exit code · B1 band detector on the FINAL epoch (uses the public reference band — the same knowledge
  as the stats arm; declared 2026-09-27, the every-epoch rule is in the appendix)
  · B2 config delta (carries declared workload knowledge: the clean resolved config + derived keys)
  · B3 = B1 ∪ B2 · BF form-only comparator (detection only).
B2+ (answer-key knob map) and B4 (reference oracle) are upper bounds, not baselines, and are not rows here.

Scoring reads hidden cards: run in the canonical container
    python scripts/agent_value_table.py [--sweep stage4_part1] [--out docs/audits/agent_value_part1_200.md]
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

BASELINES = [("B0 exit code", "b0"), ("B1 band, final epoch (public band)", "b1"), ("B2 config delta", "b2"),
             ("B3 = B1 ∪ B2", "b3"), ("BF form-only (comparator)", "bform")]
# APPENDIX only: B1's definition before 2026-09-27 (every epoch vs the final-accuracy band) and its union.
APPENDIX = [("B1 every epoch (pre-2026-09-27 definition)", "b1_any"), ("B3 with every-epoch B1", "b3_any")]


def baseline_records(root: Path, name: str) -> list[dict]:
    """One pseudo-trial per built case, shaped like an agent record for the shared statistics."""
    meta = ss.case_meta_from_cases(root)
    out = []
    for cd in sorted((root / "cases").glob("case_*")):
        if not (cd / "card.public.yaml").exists():
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
    if ci["point"] is None:
        return "—"
    return f"{ci['point']:.3f} [{ci['lo']:.3f}, {ci['hi']:.3f}]"


def summarize(recs: list[dict]) -> dict:
    det = ss.bootstrap_ci(recs, _mech_macro(ss._detect_correct))
    idn = ss.bootstrap_ci(recs, _mech_macro(ss._id_correct))
    far = ss.bootstrap_ci(recs, _ctrl_rate(lambda t: ss._detected(t) is True))
    far_h = ss.bootstrap_ci([r for r in recs if r.get("_tier") == "control" and not r.get("_benign_form")],
                            _ctrl_rate(lambda t: ss._detected(t) is True))
    far_b = ss.bootstrap_ci([r for r in recs if r.get("_benign_form")],
                            _ctrl_rate(lambda t: ss._detected(t) is True))
    cost = sum((r.get("usage") or {}).get("estimated_cost_usd") or 0.0 for r in recs) / len(recs)
    valid = sum(1 for r in recs if ss.valid_submission(r)) / len(recs)
    per_mech = {}
    for m in sorted({ss.mechanism_of(r["_op"]) for r in recs if r.get("_tier") != "control"}):
        f = [r for r in recs if r.get("_tier") != "control" and ss.mechanism_of(r["_op"]) == m]
        per_mech[m] = (sum(map(ss._detect_correct, f)) / len(f), sum(map(ss._id_correct, f)) / len(f), len(f))
    return {"det": det, "id": idn, "far": far, "far_h": far_h, "far_b": far_b, "cost": cost, "valid": valid,
            "n": len(recs), "n_cases": len({r["case_id"] for r in recs}), "per_mech": per_mech}


def _main_table(rows):
    L = ["| contestant | trials | cases | detection (faulty, by mechanism) | false alarms (all 92 controls) "
         "| false alarms: healthy (20) | false alarms: benign (72) | identification (faulty, by mechanism) "
         "| valid submissions | $ / trial |", "|" + "---|" * 10]
    for name, s in rows:
        L.append(f"| {name} | {s['n']} | {s['n_cases']} | {_fmt(s['det'])} | {_fmt(s['far'])} | {_fmt(s['far_h'])} "
                 f"| {_fmt(s['far_b'])} | {_fmt(s['id'])} | {s['valid']:.3f} | {s['cost']:.4f} |")
    return L


def render(rows: list[tuple[str, dict]], sweep: str, appendix: list[tuple[str, dict]] = ()) -> str:
    L = [f"# What does the agent add? — baselines vs {sweep} agents on the same 200 cases", "",
         "> Generated by `scripts/agent_value_table.py` in the canonical container; do NOT hand-edit. "
         "End-to-end scoring (an empty diagnosis = a miss; never a false alarm). Faulty cases pooled by "
         "MECHANISM (the two leakage variants = one mechanism; pooled = unweighted mean of 5 mechanisms). "
         "95% case-bootstrap CIs. Identification uses the matcher stored in the records / current scorer "
         "(root_token_v2); regenerate after the scorer is frozen.", ""] + _main_table(rows)
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
    rows = [(label, summarize(baseline_records(root, key))) for label, key in BASELINES]
    agents = [r for r in ss.load_from_cases(root, a.sweep) if not r["_exploratory"]]
    groups = defaultdict(list)
    for r in agents:
        model = (r.get("model") or {}).get("model_id")
        groups[(r["_provider"], model, r["_agent"], r["_anchor"])].append(r)
    for (prov, model, agent, arm) in sorted(groups, key=lambda k: tuple(map(str, k))):
        rows.append((f"{model} · {agent} · {arm}", summarize(groups[(prov, model, agent, arm)])))
    appendix = [(label, summarize(baseline_records(root, key))) for label, key in APPENDIX]
    a.out.write_text(render(rows, a.sweep, appendix))
    print(f"wrote {a.out.relative_to(root) if a.out.is_relative_to(root) else a.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
