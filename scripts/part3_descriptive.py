#!/usr/bin/env python3
"""Stage 4 Part 3 descriptive tables · DESCRIPTIVE ONLY (no verdicts): code opening, compliance, control false
alarms by form and band position (docs/audits/stage4_part3_descriptive.md).

    python scripts/part3_descriptive.py      (after: make export-release NAME=stage4_part3_static / _react)

Reads ONLY the local releases ``results_release/stage4_part3_{static,react}/`` (one trial per cell, pilots
excluded, by ``load_from_release``) — no cases/, results/ or registry. Prints the markdown tables to stdout."""
import collections
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.report_gen import condition_of  # noqa: E402
from harness.sweep_stats import load_from_release, mechanism_of  # noqa: E402

for _n in ("stage4_part3_static", "stage4_part3_react"):
    if not (ROOT / "results_release" / _n / "trials").is_dir():
        raise SystemExit(f"part3_descriptive: no local release results_release/{_n}/ — run make export-release NAME={_n}")
S = load_from_release(ROOT / "results_release" / "stage4_part3_static")
R = load_from_release(ROOT / "results_release" / "stage4_part3_react")
ALL = S + R
COND_ORDER = sorted({condition_of(r) for r in ALL})
SHORT = {c: c.replace("claude-haiku-4-5-20251001", "claude-haiku-4.5").replace(" (effort=", " [").replace(
    " (thinking=disabled)", " [thinking off]").replace(", strict)", " strict]") for c in COND_ORDER}
ARM = {"off.v2": "off", "stats.v2": "stats", "rule.v2": "rule"}


def det(r):
    return bool(((r.get("scores") or {}).get("detection") or {}).get("detected_predicted"))


def ident(r):
    return bool(((r.get("scores") or {}).get("identification") or {}).get("correct"))


def is_ctrl(r):
    return (r["_op"] or "").startswith("control.")


def frac(k, n):
    return f"{k}/{n} ({k / n:.2f})" if n else "—"


def rate(xs):
    return f"{sum(xs) / len(xs):.2f}" if xs else "—"


def tools(r):
    return r.get("tool_transcript") or []


def opened(r, path):
    return any(t.get("tool_name") == "read_code" and str((t.get("arguments") or {}).get("path", "")).lstrip("./")
               == path and (t.get("result") or {}).get("status") == "ok" for t in tools(r))


def opened_config(r):
    return any(t.get("tool_name") in ("read_config", "diff_config") or (
        t.get("tool_name") == "read_code" and "config" in str((t.get("arguments") or {}).get("path", "")))
        for t in tools(r))


def static_case_det(recs):
    """Static detection per case = mean over its repeats; returned as {case: mean}."""
    by = collections.defaultdict(list)
    for r in recs:
        by[r["case_id"]].append(det(r))
    return {c: sum(v) / len(v) for c, v in by.items()}


out = []
p = out.append

# ---------------------------------------------------------------- 1. code opening
for arm in ("off.v2", "stats.v2"):
    p(f"\n### 1{'a' if arm == 'off.v2' else 'b'}. `{ARM[arm]}` arm — faulty cases present in both sweeps\n")
    p("| condition | mechanism | n cases | static det | ReAct det | ReAct opened train.py | opened config | "
      "ReAct det, train.py opened | ReAct det, not opened |")
    p("|---|---|---|---|---|---|---|---|---|")
    for c in COND_ORDER:
        rows_all = {"s": [], "r": [], "o": [], "cfg": [], "do": [], "dn": []}
        mechs = sorted({mechanism_of(r["_op"]) for r in R if not is_ctrl(r)})
        for m in mechs + ["**all silent**"]:
            def keep(r):
                if is_ctrl(r) or condition_of(r) != c or r["_anchor"] != arm:
                    return False
                mm = mechanism_of(r["_op"])
                return mm == m if m in mechs else mm != "shape_mismatch"
            rr = [r for r in R if keep(r)]
            sd = static_case_det([r for r in S if keep(r)])
            rr = [r for r in rr if r["case_id"] in sd]
            if not rr:
                continue
            o = [r for r in rr if opened(r, "train.py")]
            no = [r for r in rr if not opened(r, "train.py")]
            p(f"| {SHORT[c]} | {m} | {len(rr)} | {rate([sd[r['case_id']] for r in rr])} | {rate([det(r) for r in rr])} | "
              f"{rate([opened(r, 'train.py') for r in rr])} | {rate([opened_config(r) for r in rr])} | "
              f"{rate([det(r) for r in o])} (n={len(o)}) | {rate([det(r) for r in no])} (n={len(no)}) |")

# ReAct opening of train.py on CONTROLS, and false alarms by opening
p("\n### 1c. ReAct controls — opening `train.py` and false alarms\n")
p("| condition | arm | n controls | opened train.py | FA, opened | FA, not opened |")
p("|---|---|---|---|---|---|")
for c in COND_ORDER:
    for arm in ("off.v2", "stats.v2"):
        rr = [r for r in R if is_ctrl(r) and condition_of(r) == c and r["_anchor"] == arm]
        o = [r for r in rr if opened(r, "train.py")]
        no = [r for r in rr if not opened(r, "train.py")]
        p(f"| {SHORT[c]} | {ARM[arm]} | {len(rr)} | {rate([opened(r, 'train.py') for r in rr])} | "
          f"{frac(sum(map(det, o)), len(o))} | {frac(sum(map(det, no)), len(no))} |")

# ---------------------------------------------------------------- 2. compliance
p("\n### 2. Compliance, per condition × agent (all trials, one per cell)\n")
p("| condition | agent | n | submit not called | submit unparsed | ended without submit | detected not stated | "
  "incomplete LLM calls | missing fields | ignored fields | malformed evidence refs | correct dx, no repair |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in COND_ORDER:
    for agent, recs in (("static", S), ("react", R)):
        rr = [r for r in recs if condition_of(r) == c]
        comp = [r.get("completion") or {} for r in rr]
        n = len(rr)
        nsub = sum(not x.get("submit_called") for x in comp)
        unp = sum(bool(x.get("submit_called")) and not x.get("submit_parsed") for x in comp)
        ews = sum(r.get("termination_reason") == "ended_without_submit" for r in rr)
        dns = sum(((r.get("submission") or {}).get("diagnosis") or {}).get("detected") is None for r in rr)
        inc = sum((x.get("incomplete_calls") or 0) > 0 for x in comp)
        mis = sum(bool((r.get("compliance") or {}).get("missing_fields")) for r in rr)
        ign = sum(bool((r.get("compliance") or {}).get("ignored_fields")) for r in rr)
        mal = sum((((r.get("scores") or {}).get("evidence") or {}).get("malformed_refs") or 0) > 0 for r in rr)
        cdx = [r for r in rr if not is_ctrl(r) and det(r) and ident(r)]
        nrep = sum(not (r.get("submission") or {}).get("repair_spec") for r in cdx)
        p(f"| {SHORT[c]} | {agent} | {n} | {frac(nsub, n)} | {frac(unp, n)} | {frac(ews, n)} | {frac(dns, n)} | "
          f"{frac(inc, n)} | {frac(mis, n)} | {frac(ign, n)} | {frac(mal, n)} | {frac(nrep, len(cdx))} |")
term = collections.Counter((condition_of(r), r["conditions"].get("agent_type"), r.get("termination_reason")) for r in ALL)
p("\nTermination reasons: " + "; ".join(f"{SHORT[c]} {a}: {t} {n}" for (c, a, t), n in sorted(term.items())
                                         if t != "submitted"))
mf = collections.Counter(f for r in ALL for f in (r.get("compliance") or {}).get("missing_fields") or [])
ig = collections.Counter(f for r in ALL for f in (r.get("compliance") or {}).get("ignored_fields") or [])
p(f"\nMissing-field names: {dict(mf.most_common())}; ignored-field names: {dict(ig.most_common())}")

# ---------------------------------------------------------------- 3. control false alarms by form and band
FORMS = [("healthy", lambda r: r["_benign_form"] is None),
         ("benign, value changed", lambda r: r["_benign_form"] == "changed"),
         ("benign, key added", lambda r: r["_benign_form"] == "added")]
p("\n### 3a. Control false alarms by control form, per condition × agent × arm\n")
p("| condition | agent | arm | healthy | benign, value changed | benign, key added | all controls | "
  "faulty det (non-crash) | J |")
p("|---|---|---|---|---|---|---|---|---|")
for c in COND_ORDER:
    for agent, recs in (("static", S), ("react", R)):
        for arm in ("off.v2", "stats.v2", "rule.v2"):
            rr = [r for r in recs if condition_of(r) == c and r["_anchor"] == arm]
            if not rr:
                continue
            ctl = [r for r in rr if is_ctrl(r)]
            cells = [frac(sum(det(r) for r in ctl if f(r)), sum(1 for r in ctl if f(r))) for _n, f in FORMS]
            fl = [r for r in rr if not is_ctrl(r) and mechanism_of(r["_op"]) != "shape_mismatch"]
            fa = sum(map(det, ctl)) / len(ctl)
            dt = sum(map(det, fl)) / len(fl)
            p(f"| {SHORT[c]} | {agent} | {ARM[arm]} | " + " | ".join(cells) +
              f" | {frac(sum(map(det, ctl)), len(ctl))} | {dt:.2f} | {dt - fa:+.2f} |")

p("\n### 3b. Control false alarms by benign TYPE (all conditions and arms pooled), per agent\n")
types = sorted({r["_op"] for r in ALL if is_ctrl(r)})
p("| control type | static | react |")
p("|---|---|---|")
for t in types:
    cells = []
    for recs in (S, R):
        rr = [r for r in recs if r["_op"] == t]
        cells.append(frac(sum(map(det, rr)), len(rr)))
    p(f"| `{t}` | " + " | ".join(cells) + " |")

p("\n### 3c. Control false alarms by visible band position, per condition × agent × arm\n")
p("| condition | agent | arm | in band | below band (out of band) |")
p("|---|---|---|---|---|")
for c in COND_ORDER:
    for agent, recs in (("static", S), ("react", R)):
        for arm in ("off.v2", "stats.v2", "rule.v2"):
            ctl = [r for r in recs if condition_of(r) == c and r["_anchor"] == arm and is_ctrl(r)]
            if not ctl:
                continue
            ib = [r for r in ctl if r["_band_vis"] == "in_band"]
            ob = [r for r in ctl if r["_band_vis"] != "in_band"]
            p(f"| {SHORT[c]} | {agent} | {ARM[arm]} | {frac(sum(map(det, ib)), len(ib))} | "
              f"{frac(sum(map(det, ob)), len(ob))} |")
oob = sorted({r["case_id"] for r in ALL if is_ctrl(r) and r["_band_vis"] != "in_band"})
p(f"\nOut-of-band controls: {', '.join(oob)} "
  f"({', '.join(sorted({r['_op'] for r in ALL if r['case_id'] in oob}))}).")
print("\n".join(out))
