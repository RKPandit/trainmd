#!/usr/bin/env python3
"""Stage 4 Part 1 — descriptive follow-up to the hand-read spot check, and the sensitivity analyses
DECLARED BEFORE COMPUTING (DECISIONS 2026-09-26, commit 5e2123e). Nothing here changes a matcher, a
scorer or a pre-registered verdict: every number is reported beside the verdicts as computed.

    python scripts/part1_followup.py          → docs/audits/stage4_part1_followup.md

Reads local results/ + cases/ (the evaluator side; never agent-facing).
"""
from __future__ import annotations

import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import prereg_part1 as pp  # noqa: E402
from harness import sweep_stats as ss  # noqa: E402
from harness.scoring import score_detection, score_identification  # noqa: E402

SWEEP = "stage4_part1"
OUT = ROOT / "docs" / "audits" / "stage4_part1_followup.md"
LR_OP = "silent.lr_warmup.v1"
# Declared definitions (DECISIONS 2026-09-26):
LR_CLASS = re.compile(r"learning.?rate|\blr\b|lr_|step.?size", re.I)
SUBSET_EVAL = re.compile(r"subset|select|confiden|filter|cherry|top.?k|partial.{0,12}(eval|valid)"
                         r"|biased.{0,12}(eval|metric|valid)|(eval|valid|metric).{0,20}(bias|subset|select)", re.I)
WS_RUNAWAY = re.compile(r"[ \t\r\n]{40,}")
GARBLED_KEY = re.compile(r'"[\]\}\[\{,]+"\s*:')
SALV_DET = re.compile(r'"detected"\s*:\s*(true|false)')
SALV_CLS = re.compile(r'"operator_class"\s*:\s*"([^"\\]{0,200})"')


# ------------------------------------------------------------------------------------------ helpers
def prov(r): return r.get("_provider")
def agent(r): return r.get("_agent")
def arm(r): return (r.get("_anchor") or "").split(".")[0]
def cell(r): return (prov(r), agent(r), arm(r))
def faulty(r): return r.get("_tier") != "control"


def submit_call(r):
    """(arguments string, stop_reason, truncated) of the FINAL submit call, or None."""
    last = None
    for turn in r.get("llm_transcript") or []:
        for tc in turn.get("tool_calls") or []:
            if tc.get("name") == "submit":
                last = (tc.get("arguments") if isinstance(tc.get("arguments"), str)
                        else json.dumps(tc.get("arguments")), turn.get("stop_reason"), bool(turn.get("truncated")))
    return last


def patterns(r) -> dict:
    sc = submit_call(r)
    if sc is None:
        return {"no_submit": True}
    args, stop, trunc = sc
    out = {"truncated": stop == "max_tokens" or trunc, "ws_runaway": bool(WS_RUNAWAY.search(args or "")),
           "garbled_key": bool(GARBLED_KEY.search(args or ""))}
    try:
        d = json.loads(args)
        out["json_invalid"] = False
        out["nested_evidence"] = isinstance(d, dict) and isinstance(d.get("diagnosis"), dict) \
            and "evidence_refs" in d["diagnosis"]
    except Exception:
        out["json_invalid"] = True
        out["nested_evidence"] = bool(re.search(r'"diagnosis"\s*:\s*\{[^{}]*"evidence_refs"', args or ""))
    return out


def diag_class(r) -> str:
    return str(((r.get("submission") or {}).get("diagnosis") or {}).get("operator_class") or "")


def patches_lr(r) -> bool:
    rs = (r.get("submission") or {}).get("repair_spec") or {}
    return isinstance(rs, dict) and "training.lr" in (rs.get("patches") or {})


def lr_blame(r) -> bool:
    """Declared definition (sensitivity (a)): the SUBMITTED operator_class names the lr, or the repair
    patches training.lr."""
    return bool(LR_CLASS.search(diag_class(r))) or patches_lr(r)


def lr_blame_salv(r) -> bool:
    """Descriptive count (§3): as lr_blame, plus the SALVAGED operator_class of an empty-diagnosis trial."""
    if lr_blame(r):
        return True
    if not ss.valid_submission(r):
        sv = salvage(r)
        return bool(sv and sv[1] and LR_CLASS.search(sv[1]))
    return False


def hidden_card(cid, _cache={}):
    if cid not in _cache:
        _cache[cid] = yaml.safe_load((ROOT / "cases" / cid / "hidden" / "card.hidden.yaml").read_text())
    return _cache[cid]


def salvage_args(args: str):
    """(detected, operator_class) recovered from a raw submit-argument string, or None. Recovered ONLY
    when the prefix contains BOTH a complete `"detected": true|false` and a complete, closed
    `"operator_class": "<label>"` inside the diagnosis object (before anything else is parsed);
    a prefix cut before the label closes, or text that is not a submit object, is not recovered."""
    if not isinstance(args, str) or not args.lstrip().startswith("{"):
        return None
    d = re.search(r'"diagnosis"\s*:\s*\{', args)
    if not d:
        return None
    body = args[d.end():]
    m, c = SALV_DET.search(body), SALV_CLS.search(body)
    if not (m and c):
        return None
    return m.group(1) == "true", c.group(1)


def salvage(r):
    """(detected, operator_class) recovered from the final submit call's raw arguments, or None."""
    sc = submit_call(r)
    return None if sc is None else salvage_args(sc[0])


def salvaged_scores(r):
    s = salvage(r)
    if s is None:
        return None
    sub = {"diagnosis": {"detected": s[0], "operator_class": s[1]}}
    card = hidden_card(r["case_id"])
    return score_detection(sub, card)["correct"], score_identification(sub, card)["correct"]


def f(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def rate(xs, pred):
    return (sum(1 for t in xs if pred(t)) / len(xs)) if xs else None


def table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


# ------------------------------------------------------------------------------------------ main
def main() -> int:
    recs = ss.load_from_cases(ROOT, SWEEP)
    conf = [r for r in recs if not r.get("_exploratory")]
    fault = [r for r in conf if faulty(r)]
    L = ["# Stage 4 Part 1 — spot-check follow-up (DESCRIPTIVE) and declared sensitivity analyses", "",
         "> Generated by `scripts/part1_followup.py` from the local records — do NOT hand-edit. Nothing here "
         "changes a matcher, a scorer or a pre-registered verdict. The sensitivity analyses (§4) were DECLARED "
         "before computing (DECISIONS 2026-09-26, commit 5e2123e).", "",
         f"Confirmatory trials analysed (one per cell): **{len(conf)}** ({len(fault)} faulty, "
         f"{len(conf) - len(fault)} control).", ""]

    # ---- 1a. output degeneration patterns -------------------------------------------------------
    by = defaultdict(list)
    for r in conf:
        by[cell(r)].append(r)
    keys = ("truncated", "ws_runaway", "garbled_key", "nested_evidence", "json_invalid", "no_submit")
    rows = []
    for k in sorted(by, key=lambda x: tuple(map(str, x))):
        ts = by[k]
        pats = [patterns(t) for t in ts]
        empty = [t for t in ts if not ss.valid_submission(t)]
        rows.append(list(k) + [len(ts), len(empty)] + [sum(1 for p in pats if p.get(x)) for x in keys])
    L += ["## 1a. Submit-argument degeneration — counts per provider × agent × arm (all confirmatory trials)", "",
          "Patterns on the FINAL submit call's raw arguments (not exclusive): **truncated** (the submit turn hit "
          "max_tokens), **ws_runaway** (a run of ≥ 40 whitespace characters), **garbled_key** (a punctuation-only "
          "JSON key such as `\"},\":`), **nested_evidence** (`evidence_refs` inside `diagnosis`), **json_invalid** "
          "(arguments do not parse), **no_submit** (no submit call). *Empty diagnosis* as in the report's "
          "valid-submission view.", ""]
    L += table(["provider", "agent", "arm", "trials", "empty diagnosis"] + list(keys), rows) + [""]
    empty_all = [t for t in conf if not ss.valid_submission(t)]
    pe = [patterns(t) for t in empty_all]
    L += [f"Among all **{len(empty_all)}** empty-diagnosis trials: ws_runaway {sum(1 for p in pe if p.get('ws_runaway'))}, "
          f"truncated {sum(1 for p in pe if p.get('truncated'))}, garbled_key {sum(1 for p in pe if p.get('garbled_key'))}, "
          f"nested_evidence {sum(1 for p in pe if p.get('nested_evidence'))}, json_invalid "
          f"{sum(1 for p in pe if p.get('json_invalid'))}, no_submit {sum(1 for p in pe if p.get('no_submit'))}.", ""]

    # garbled keys that leave the diagnosis intact but swallow later fields into it
    g_valid = [t for t in conf if (patterns(t).get("garbled_key") and ss.valid_submission(t))]
    sub = lambda t: t.get("submission") or {}
    lost_ev = sum(1 for t in g_valid if not sub(t).get("evidence_refs"))
    lost_rep = sum(1 for t in g_valid if faulty(t) and not sub(t).get("repair_spec"))
    g_fault = sum(1 for t in g_valid if faulty(t))
    L += [f"**Garbled keys that keep the diagnosis:** {len(g_valid)} valid submissions contain a punctuation-only "
          "key inside `diagnosis` (e.g. `\"operator_class\": \"…\", \"},\": [], \"repair_spec\": {…}`), which "
          "swallows the fields after it into the diagnosis object: detection and identification survive, but the "
          f"top-level `evidence_refs` is empty in {lost_ev} of them and `repair_spec` is missing in {lost_rep} of "
          f"the {g_fault} faulty ones — so they score evidence F1 0 and no repair (end-to-end).", ""]

    # ---- 1b. salvage -----------------------------------------------------------------------------
    rows = []
    fby = defaultdict(list)
    for r in fault:
        fby[cell(r)].append(r)
    tot = defaultdict(int)
    for k in sorted(fby, key=lambda x: tuple(map(str, x))):
        ts = fby[k]
        empty = [t for t in ts if not ss.valid_submission(t)]
        salv = {id(t): salvaged_scores(t) for t in empty}
        n_s = sum(1 for v in salv.values() if v is not None)
        det_rec = rate(ts, ss._detect_correct)
        id_rec = rate(ts, ss._id_correct)
        det_s = rate(ts, lambda t: (salv[id(t)][0] if salv.get(id(t)) else ss._detect_correct(t)))
        id_s = rate(ts, lambda t: (salv[id(t)][1] if salv.get(id(t)) else ss._id_correct(t)))
        rows.append(list(k) + [len(ts), len(empty), n_s, f(det_rec), f(det_s), f(id_rec), f(id_s)])
        tot["empty"] += len(empty); tot["salv"] += n_s
    L += ["## 1b. Salvage analysis — DESCRIPTIVE ONLY (verdicts stay as computed)", "",
          "For each empty-diagnosis FAULTY trial, `detected` and `operator_class` are recovered from the valid "
          "prefix of the final submit call's raw arguments and scored with the unchanged detection / "
          "identification scorers. *Salvaged* rates replace only those trials; every other trial keeps its "
          "recorded score.", ""]
    L += table(["provider", "agent", "arm", "faulty trials", "empty diagnosis", "salvageable",
                "detection recorded", "detection salvaged", "identification recorded", "identification salvaged"],
               rows) + ["", f"Salvageable: **{tot['salv']} of {tot['empty']}** empty-diagnosis faulty trials.", ""]

    # ---- 1c. strict mode -------------------------------------------------------------------------
    from harness.llm.openai_client import to_responses_tools
    from agents.llm_agent import TOOLS_SCHEMA
    L += ["## 1c. OpenAI tool schemas — strict mode", ""]
    try:
        tools = to_responses_tools(TOOLS_SCHEMA)
        strict = [t.get("name") for t in tools if t.get("strict") is True]
        L += [f"The Responses-API tools sent in Part 1 declare `strict: true` on **{len(strict)} of {len(tools)}** "
              "tools (`harness/llm/openai_client.py::to_responses_tools` emits type / name / description / "
              "parameters only), so the model's function-call arguments were NOT constrained to the schema — "
              "which is what lets them degenerate as in §1a.", ""]
    except Exception as e:  # pragma: no cover
        L += [f"_(could not introspect the tool schema: {e})_", ""]

    # ---- 2. metric_inflation labels ----------------------------------------------------------------
    mi_wrong = [r for r in fault if r.get("_op") == "silent.metric_inflation.v1" and not ss._id_correct(r)
                and diag_class(r)]
    hits = [r for r in mi_wrong if SUBSET_EVAL.search(diag_class(r))]
    lab = defaultdict(int)
    for r in hits:
        lab[diag_class(r)] += 1
    byp = defaultdict(lambda: [0, 0])
    for r in mi_wrong:
        byp[prov(r)][1] += 1
        byp[prov(r)][0] += bool(SUBSET_EVAL.search(diag_class(r)))
    L += ["## 2. metric_inflation — labels scored wrong that describe a selected / subset / confidence-filtered "
          "evaluation (matcher NOT changed)", "",
          f"Pattern (declared): `{SUBSET_EVAL.pattern}`. Of **{len(mi_wrong)}** metric_inflation trials with a label "
          f"scored wrong, **{len(hits)}** name such a mechanism — "
          + ", ".join(f"{p} {a}/{b}" for p, (a, b) in sorted(byp.items())) + ". The second human audit "
          "adjudicates; any matcher change would be derived from the operator's mechanism, not these labels.", ""]
    L += table(["label (scored wrong)", "trials"], sorted(lab.items(), key=lambda kv: -kv[1])[:25]) + [""]

    # ---- 3. learning-rate red herring --------------------------------------------------------------
    def lr_rows(pool):
        g = defaultdict(list)
        for r in pool:
            g[(prov(r), arm(r))].append(r)
        return [[p, a, len(ts), sum(1 for t in ts if lr_blame(t)), f(rate(ts, lr_blame)),
                 sum(1 for t in ts if lr_blame_salv(t)), f(rate(ts, lr_blame_salv))]
                for (p, a), ts in sorted(g.items())]
    nonlr = [r for r in fault if r.get("_op") != LR_OP]
    healthy = [r for r in conf if r.get("_op") == "control.healthy.v1"]
    benign = [r for r in conf if (r.get("_op") or "").startswith("control.benign_") and r["_op"] != "control.benign_lr005.v1"]
    benign_lr = [r for r in conf if r.get("_op") == "control.benign_lr005.v1"]
    L += ["## 3. Learning-rate blame where the learning rate is not the fault", "",
          f"*Blames the learning rate* (declared) = `operator_class` matches `{LR_CLASS.pattern}` OR the repair "
          "patches `training.lr`. The clean configuration is lr = 0.01 with Adam.", "",
          f"**Non-lr FAULTY trials:** {sum(1 for r in nonlr if lr_blame(r))} of {len(nonlr)} "
          f"({f(rate(nonlr, lr_blame))}) from submitted diagnoses; **{sum(1 for r in nonlr if lr_blame_salv(r))} "
          f"of {len(nonlr)} ({f(rate(nonlr, lr_blame_salv))}) including the SALVAGED diagnoses** of empty-diagnosis "
          "trials (§1b). lr_warmup cases are excluded — naming the learning rate there is the correct answer "
          "(e.g. case_0074, lr_warmup, salvaged `excessive_adam_learning_rate`).", ""]
    L += table(["provider", "arm", "trials", "lr blame (submitted)", "rate", "incl. salvaged", "rate"],
               lr_rows(nonlr)) + [""]

    # ---- 4. sensitivity ----------------------------------------------------------------------------
    def with_det(pool, fn):
        out = []
        for r in pool:
            r2 = copy.copy(r)
            v = fn(r)
            if v is not None:
                r2["scores"] = {**(r.get("scores") or {}), "detection": {**((r.get("scores") or {}).get("detection") or {}),
                                                                         "correct": v}}
            out.append(r2)
        return out

    base9, base10 = pp.h9_verdict(conf), pp.h10_verdict(conf)
    a_recs = with_det(conf, lambda r: False if (faulty(r) and r.get("_op") != LR_OP and lr_blame(r)) else None)
    a9, a10 = pp.h9_verdict(a_recs), pp.h10_verdict(a_recs)
    luna_empty = lambda r: faulty(r) and prov(r) == "openai" and not ss.valid_submission(r)
    inc = with_det(conf, lambda r: (salvaged_scores(r) or (None,))[0] if luna_empty(r) else None)
    exc = [r for r in conf if not luna_empty(r)]
    i9, e9 = pp.h9_verdict(inc), pp.h9_verdict(exc)

    def h9_row(label, v):
        ops = v["operators"]
        cells = []
        for op in pp.H9_NON_LEAKAGE:
            d = ops.get(op, {})
            if "delta" in d:
                cells.append(f"{op.split('.')[1]}: {f(d['delta']['point'])} [{f(d['delta']['lo'])}, "
                             f"{f(d['delta']['hi'])}] ({d['status'].replace('_', ' ')})")
        return [label, f"**{v['verdict']}**", "; ".join(cells)]

    def h10_row(label, v):
        return [label] + [f"**{v['models'][m]['verdict']}**" + (f" f = {f(v['models'][m]['f']['point'])} "
                          f"[{f(v['models'][m]['f']['lo'])}, {f(v['models'][m]['f']['hi'])}]"
                          if 'f' in v['models'][m] else "") for m in (pp.REF_PROVIDER, pp.CMP_PROVIDER)]
    n_a = sum(1 for r in conf if faulty(r) and r.get("_op") != LR_OP and lr_blame(r))
    L += ["## 4. Sensitivity analyses (DECLARED BEFORE COMPUTING — the pre-registered verdicts stand)", "",
          f"(a) {n_a} faulty non-lr trials whose diagnosis blames the learning rate are counted as MISSES. "
          f"(b, H9 only) Luna's {sum(1 for r in conf if luna_empty(r))} empty-diagnosis faulty trials use their "
          "salvaged detection (*included*), or are dropped (*excluded*).", ""]
    L += table(["H9 reading", "verdict", "decision-carrying operators: Δ Luna − Haiku [95% CI]"],
               [h9_row("pre-registered (as computed)", base9), h9_row("(a) lr blame on non-lr = miss", a9),
                h9_row("(b) Luna salvaged detections included", i9),
                h9_row("(b) Luna empty diagnoses excluded", e9)]) + [""]
    L += table(["H10 reading", "Haiku", "Luna"],
               [h10_row("pre-registered (as computed)", base10), h10_row("(a) lr blame on non-lr = miss", a10)]) + [""]
    flag_lr = lambda r: (((r.get("submission") or {}).get("diagnosis") or {}).get("detected") is True
                         and bool(LR_CLASS.search(diag_class(r)))) or patches_lr(r)

    def flag_lr_salv(r):
        """flag_lr, plus an empty-diagnosis control whose SALVAGED diagnosis flags an lr incident."""
        if flag_lr(r):
            return True
        sv = None if ss.valid_submission(r) else salvage(r)
        return bool(sv and sv[0] is True and sv[1] and LR_CLASS.search(sv[1]))

    def ctrl_rows(pool):
        g = defaultdict(list)
        for r in pool:
            g[(prov(r), arm(r))].append(r)
        return [[p, a, len(ts), sum(1 for t in ts if flag_lr(t)), f(rate(ts, flag_lr))] for (p, a), ts in sorted(g.items())]
    L += ["### Control-based check — agents flagging or patching the learning rate on HEALTHY and BENIGN controls", "",
          "*Flags or patches the lr* = reports an incident whose class names the learning rate, OR patches "
          "`training.lr`. If agents flagged runs because lr = 0.01 looks wrong, it would show up here.", "",
          f"Healthy controls: {sum(1 for r in healthy if flag_lr(r))} of {len(healthy)}; benign controls (lr "
          f"unchanged): {sum(1 for r in benign if flag_lr(r))} of {len(benign)}; benign lr 0.01 → 0.005 (the lr "
          f"legitimately changed): {sum(1 for r in benign_lr if flag_lr(r))} of {len(benign_lr)}. Including salvaged "
          f"diagnoses of empty-diagnosis controls: healthy {sum(1 for r in healthy if flag_lr_salv(r))} of "
          f"{len(healthy)}, benign {sum(1 for r in benign if flag_lr_salv(r))} of {len(benign)}.", ""]
    L += ["Healthy + benign (lr unchanged):", ""] + table(["provider", "arm", "trials", "flags/patches lr", "rate"],
                                                           ctrl_rows(healthy + benign)) + [""]
    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
