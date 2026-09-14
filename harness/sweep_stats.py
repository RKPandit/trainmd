"""Cluster-aware statistics for Sweep-1 primary contrasts (claim-tightening, Stage 0).

Recomputes DERIVED statistics only — never re-scores model outputs. All uncertainty
is a case-level nonparametric bootstrap (resample the unique cases with replacement,
10,000 resamples, 95% percentile interval), because the 324 trials come from only 27
unique cases (6 per faulty operator, 3 controls) and trials within a case are not
independent.

Recovery has TWO endpoints:
  * STRICT   — a valid STRUCTURED repair was submitted and verified (primary).
  * SEMANTIC — strict plus repairs recovered post-hoc from folded output (secondary).
A folded recovery (correction #3, `submission_parse_warning.recovered`) counts for
semantic only; strict is the autonomous-success headline.
"""
from __future__ import annotations

import glob
import random
from collections import defaultdict
from pathlib import Path

import yaml

N_RESAMPLES = 10_000
SEED = 20260913

_POS = {"silent.data_leakage.v1"}
_NEG = {"silent.lr_warmup.v1", "silent.label_corruption.v1"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load(project_root: Path):
    root = project_root
    hc_cache: dict = {}

    def hc(cid):
        if cid not in hc_cache:
            hc_cache[cid] = yaml.safe_load(
                open(root / "cases" / cid / "hidden" / "card.hidden.yaml"))
        return hc_cache[cid]

    recs = []
    for f in sorted(glob.glob(str(root / "results" / "*" / "trials" / "*.yaml"))):
        d = yaml.safe_load(open(f))
        c = d.get("conditions") or {}
        if c.get("sweep_name") != "sweep1" or d.get("trusted"):
            continue
        card = hc(d["case_id"])
        d["_op"] = card.get("operator_id")
        d["_sig_vis"] = card.get("visible_sigma_distance")
        d["_sig_hid"] = card.get("hidden_sigma_distance")
        d["_symptom"] = card.get("symptom_direction")
        recs.append(d)
    return recs


# ---- trial-level accessors ------------------------------------------------

def _detect_correct(r):
    return bool(((r.get("scores") or {}).get("detection") or {}).get("correct"))

def _detected(r):
    return ((r.get("submission") or {}).get("diagnosis") or {}).get("detected")

def _id_correct(r):
    return bool(((r.get("scores") or {}).get("identification") or {}).get("correct"))

def _ev_f1(r):
    e = (r.get("scores") or {}).get("evidence") or {}
    return e.get("f1")

def _recovered(r):
    return ((r.get("scores") or {}).get("recovery") or {}).get("verdict") == "recovered"

def _folded(r):
    return bool(((r.get("submission") or {}).get("submission_parse_warning") or {}).get("recovered"))

def _strict_recovered(r):
    return _recovered(r) and not _folded(r)

def _agent(r):
    return (r.get("conditions") or {}).get("agent_type")

def _anchor(r):
    # Three-arm design (off | numbers | rule); legacy Sweep-1 "on" == "rule".
    # Mapped in analysis only — records are never rewritten (docs/DECISIONS.md).
    a = (r.get("conditions") or {}).get("anchor")
    return "rule" if a == "on" else a


# ---- case-level bootstrap -------------------------------------------------

def _by_case(recs):
    d = defaultdict(list)
    for r in recs:
        d[r["case_id"]].append(r)
    return d


def bootstrap_ci(recs, statistic, n=N_RESAMPLES, seed=SEED):
    """95% percentile CI of `statistic(list_of_trials)` resampling CASES.

    Returns (point, lo, hi, n_cases). None entries from the statistic (empty
    resample cells) are dropped from the interval.
    """
    by_case = _by_case(recs)
    cases = list(by_case)
    point = statistic(recs)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [rng.choice(cases) for _ in cases]
        boot = []
        for c in pick:
            boot.extend(by_case[c])
        v = statistic(boot)
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = vals[int(0.025 * len(vals))] if vals else None
    hi = vals[int(0.975 * len(vals)) - 1] if vals else None
    return {"point": point, "lo": lo, "hi": hi, "n_cases": len(cases), "n_trials": len(recs)}


def _rate(pred):
    def stat(trials):
        xs = [pred(t) for t in trials if pred(t) is not None]
        return (sum(1 for x in xs if x) / len(xs)) if xs else None
    return stat


# ---- primary contrasts ----------------------------------------------------

def h1_anchor_gap(recs):
    """Anchor-off: negative-symptom detection − positive-symptom (leakage) detection."""
    off = [r for r in recs if _anchor(r) == "off" and r["_op"] in (_POS | _NEG)]
    def gap(trials):
        pos = [t for t in trials if t["_op"] in _POS]
        neg = [t for t in trials if t["_op"] in _NEG]
        if not pos or not neg:
            return None
        pr = sum(1 for t in pos if _detect_correct(t)) / len(pos)
        nr = sum(1 for t in neg if _detect_correct(t)) / len(neg)
        return nr - pr
    ci = bootstrap_ci(off, gap)
    pos = [r for r in off if r["_op"] in _POS]
    neg = [r for r in off if r["_op"] in _NEG]
    ci["pos_rate"] = sum(1 for t in pos if _detect_correct(t)) / len(pos)
    ci["neg_rate"] = sum(1 for t in neg if _detect_correct(t)) / len(neg)
    ci["n_cases_pos"] = len({t["case_id"] for t in pos})
    ci["n_cases_neg"] = len({t["case_id"] for t in neg})
    return ci


def h1_matched_sigma(recs):
    """Nearest-|σ_hidden| pairing of each leakage case to a negative-symptom case.

    Reports the mean paired detection gap (neg − leak) anchor-off. Does NOT touch
    the operator-identity confound: each pair is still data_leakage vs lr/label.
    """
    off = [r for r in recs if _anchor(r) == "off"]
    def case_rate(op_set):
        out = {}
        for cid, trials in _by_case([r for r in off if r["_op"] in op_set]).items():
            sig = abs(trials[0]["_sig_hid"]) if trials[0]["_sig_hid"] is not None else None
            rate = sum(1 for t in trials if _detect_correct(t)) / len(trials)
            out[cid] = (sig, rate)
        return out
    leak = case_rate(_POS)
    neg = case_rate(_NEG)
    pairs = []
    for lc, (lsig, lrate) in leak.items():
        best = min(neg.items(), key=lambda kv: abs((kv[1][0] or 0) - (lsig or 0)))
        ncid, (nsig, nrate) = best
        pairs.append({"leak_case": lc, "leak_sigma": round(lsig, 1) if lsig else None,
                      "neg_case": ncid, "neg_sigma": round(nsig, 1) if nsig else None,
                      "leak_detect": round(lrate, 3), "neg_detect": round(nrate, 3),
                      "gap": round(nrate - lrate, 3)})
    mean_gap = sum(p["gap"] for p in pairs) / len(pairs) if pairs else None
    return {"pairs": pairs, "mean_paired_gap": round(mean_gap, 3) if mean_gap is not None else None}


def h6_react_minus_static(recs):
    """Overall ReAct − static evidence F1 on faulty operators (pooled)."""
    faulty = [r for r in recs if r["_op"] in (_POS | _NEG | {"crash.shape_mismatch.v1"})
              and _ev_f1(r) is not None]
    def diff(trials):
        re = [_ev_f1(t) for t in trials if _agent(t) == "react"]
        st = [_ev_f1(t) for t in trials if _agent(t) == "static"]
        if not re or not st:
            return None
        return sum(re) / len(re) - sum(st) / len(st)
    return bootstrap_ci(faulty, diff)


def control_fpr(recs):
    """Detection false-positive rate on anchor=rule controls (legacy "on" maps to
    "rule"), bootstrapped over the (very few) unique control cases — the wide
    interval is the point. The band+rule arm is where false alarms can occur."""
    ctrl_on = [r for r in recs if r["_op"] == "control.healthy.v1" and _anchor(r) == "rule"]
    ci = bootstrap_ci(ctrl_on, _rate(lambda t: _detected(t) is True))
    fp = [r for r in ctrl_on if _detected(r) is True]
    ci["n_fp"] = len(fp)
    ci["fp_cases"] = sorted({r["case_id"] for r in fp})
    return ci


def recovery_endpoints(recs):
    """Per-operator identification, strict recovery, semantic recovery + the two
    dissociation gaps (id − strict, id − semantic) with case-clustered CIs."""
    out = {}
    for op in ("crash.shape_mismatch.v1", "silent.lr_warmup.v1",
               "silent.label_corruption.v1", "silent.data_leakage.v1"):
        rs = [r for r in recs if r["_op"] == op]
        id_rate = _rate(lambda t: _id_correct(t))
        strict = _rate(lambda t: _strict_recovered(t))
        semantic = _rate(lambda t: _recovered(t))
        gap_strict = bootstrap_ci(rs, lambda tr: (id_rate(tr) - strict(tr))
                                  if (id_rate(tr) is not None and strict(tr) is not None) else None)
        gap_sem = bootstrap_ci(rs, lambda tr: (id_rate(tr) - semantic(tr))
                               if (id_rate(tr) is not None and semantic(tr) is not None) else None)
        out[op] = {
            "n_trials": len(rs), "n_cases": len({r["case_id"] for r in rs}),
            "identification": round(id_rate(rs), 4),
            "strict_recovery": round(strict(rs), 4),
            "semantic_recovery": round(semantic(rs), 4),
            "id_minus_strict": gap_strict,
            "id_minus_semantic": gap_sem,
        }
    return out


def compute_all(project_root: Path | None = None) -> dict:
    project_root = Path(project_root).resolve() if project_root else _repo_root()
    recs = _load(project_root)
    return {
        "n_trials": len(recs),
        "n_cases": len({r["case_id"] for r in recs}),
        "method": f"case-level nonparametric bootstrap, {N_RESAMPLES} resamples, 95% percentile",
        "h1_anchor_gap_pooled": h1_anchor_gap(recs),
        "h1_matched_sigma": h1_matched_sigma(recs),
        "h6_react_minus_static": h6_react_minus_static(recs),
        "control_fpr": control_fpr(recs),
        "recovery_endpoints": recovery_endpoints(recs),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compute_all(), indent=2, default=str))
