"""Cluster-aware statistics for sweep primary contrasts — plan-driven, generic.

Recomputes DERIVED statistics only — never re-scores model outputs. Uncertainty is a case-level
nonparametric bootstrap (resample unique CASES with replacement; trials within a case are not
independent). Everything is derived from the records + per-case metadata + the plan's arm/operator
vocabulary — NO operator list, case count, arm set, or model literal lives here (STAGE3_PLAN §0.3).

Storage is decoupled from analysis: `attach_meta` takes a `case_meta(cid)` callable, so the same
metric code runs over records loaded from `results/` (metadata from the hidden cards) OR from a
sanitized release (metadata from the release's per-case files, no registry) — the external-reviewer
path. Positive/negative symptom sets come from each case's `symptom_direction`, not a hardcoded set.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from pathlib import Path
import random

import yaml

from harness.anchors import normalize_anchor

N_RESAMPLES = 10_000
SEED = 20260913


# --------------------------------------------------------------------------- #
# Loading — records + per-case metadata, decoupled
# --------------------------------------------------------------------------- #

def case_meta_from_cases(root: Path):
    """Return a `case_meta(cid)` reading the hidden card (results/ analysis path)."""
    cache: dict = {}

    def meta(cid: str) -> dict:
        if cid not in cache:
            card = yaml.safe_load((root / "cases" / cid / "hidden" / "card.hidden.yaml").read_text())
            cache[cid] = {
                "operator_id": card.get("operator_id"),
                "tier": card.get("layer"),
                "symptom_direction": card.get("symptom_direction"),
                "visible_sigma_distance": card.get("visible_sigma_distance"),
                "hidden_sigma_distance": card.get("hidden_sigma_distance"),
            }
        return cache[cid]

    return meta


def attach_meta(rec: dict, meta: dict) -> dict:
    """Attach analysis fields (normalizing the anchor exactly once, here at load)."""
    rec["_op"] = meta.get("operator_id")
    rec["_tier"] = meta.get("tier")
    rec["_symptom"] = meta.get("symptom_direction")
    rec["_sig_vis"] = meta.get("visible_sigma_distance")
    rec["_sig_hid"] = meta.get("hidden_sigma_distance")
    rec["_anchor"] = normalize_anchor((rec.get("conditions") or {}).get("anchor"))
    rec["_agent"] = (rec.get("conditions") or {}).get("agent_type")
    return rec


def sweep_is_frozen(root: Path, sweep_name: str) -> bool:
    """True if sweeps/<name>_manifest.yaml declares `frozen: true`.

    A FROZEN historical sweep was run against an earlier reference era; adopting a new reference band
    supersedes every one of its records (a new case_build_id), but those records remain valid under
    THEIR OWN era and must stay reproducible. So the supersession filter is bypassed for a frozen
    sweep — "superseded" means "do not compare to CURRENT cases," not "no longer reproducible."
    Detected from the manifest (not a CLI flag) so a frozen sweep cannot be accidentally regenerated
    as an empty/degraded report. See docs/DECISIONS.md (STAGE3_PLAN §0.5 adoption).
    """
    p = Path(root) / "sweeps" / f"{sweep_name}_manifest.yaml"
    if not p.is_file():
        return False
    return bool((yaml.safe_load(p.read_text()) or {}).get("frozen"))


def load_from_cases(root: Path, sweep_name: str, include_trusted: bool = False) -> list[dict]:
    """Load a sweep's non-trusted trial records from results/, metadata from hidden cards."""
    meta = case_meta_from_cases(root)
    frozen = sweep_is_frozen(root, sweep_name)
    recs = []
    for f in sorted(glob.glob(str(root / "results" / "*" / "trials" / "*.yaml"))):
        d = yaml.safe_load(open(f))
        c = d.get("conditions") or {}
        if c.get("sweep_name") != sweep_name:
            continue
        if d.get("trusted") and not include_trusted:
            continue
        # Scored against a stale build → excluded from aggregation, UNLESS this is a frozen
        # historical sweep (whose records are legitimately all-superseded by a later reference era).
        if d.get("card_superseded") and not frozen:
            continue
        recs.append(attach_meta(d, meta(d["case_id"])))
    return recs


def case_meta_from_release(release_dir: Path):
    """Return a `case_meta(cid)` reading the RELEASE's per-case metadata (no registry, no cases/).

    This is the external-reviewer path: tier/symptom/σ come from results_release/<name>/cases/<cid>.json,
    so the analysis runs with no access to the hidden registry."""
    cache: dict = {}

    def meta(cid: str) -> dict:
        if cid not in cache:
            d = json.loads((release_dir / "cases" / f"{cid}.json").read_text())
            cache[cid] = {k: d.get(k) for k in (
                "operator_id", "tier", "symptom_direction",
                "visible_sigma_distance", "hidden_sigma_distance")}
        return cache[cid]

    return meta


def load_from_release(release_dir: Path) -> list[dict]:
    """Load a sweep's trial records from a sanitized release (JSON), metadata from the release."""
    release_dir = Path(release_dir)
    meta = case_meta_from_release(release_dir)
    recs = []
    for f in sorted((release_dir / "trials").glob("*.json")):
        d = json.loads(f.read_text())
        recs.append(attach_meta(d, meta(d["case_id"])))
    return recs


# --------------------------------------------------------------------------- #
# Trial-level accessors
# --------------------------------------------------------------------------- #

def _detect_correct(r):
    return bool(((r.get("scores") or {}).get("detection") or {}).get("correct"))

def _detected(r):
    return ((r.get("submission") or {}).get("diagnosis") or {}).get("detected")

def _id_correct(r):
    return bool(((r.get("scores") or {}).get("identification") or {}).get("correct"))

def _ev_f1(r):
    return ((r.get("scores") or {}).get("evidence") or {}).get("f1")

def _recovered(r):
    return ((r.get("scores") or {}).get("recovery") or {}).get("verdict") == "recovered"

def _folded(r):
    return bool(((r.get("submission") or {}).get("submission_parse_warning") or {}).get("recovered"))

def _strict_recovered(r):
    return _recovered(r) and not _folded(r)


# --------------------------------------------------------------------------- #
# Derived operator/arm sets (from the data — never hardcoded)
# --------------------------------------------------------------------------- #

def positive_ops(recs) -> set[str]:
    return {r["_op"] for r in recs if r.get("_symptom") == "positive"}

def negative_ops(recs) -> set[str]:
    return {r["_op"] for r in recs if r.get("_symptom") == "negative"}

def faulty_ops(recs) -> list[str]:
    return sorted({r["_op"] for r in recs if r.get("_tier") != "control" and r["_op"]})

def control_ops(recs) -> list[str]:
    return sorted({r["_op"] for r in recs if r.get("_tier") == "control" and r["_op"]})

def arms_present(recs) -> list[str]:
    return sorted({r["_anchor"] for r in recs if r.get("_anchor") is not None})

def agents_present(recs) -> list[str]:
    return sorted({r["_agent"] for r in recs if r.get("_agent") is not None})


# --------------------------------------------------------------------------- #
# Case-level bootstrap
# --------------------------------------------------------------------------- #

def _by_case(recs):
    d = defaultdict(list)
    for r in recs:
        d[r["case_id"]].append(r)
    return d


def bootstrap_ci(recs, statistic, n=N_RESAMPLES, seed=SEED):
    """95% percentile CI of `statistic(list_of_trials)` resampling CASES (None cells dropped)."""
    by_case = _by_case(recs)
    cases = sorted(by_case)  # deterministic order so results-path and release-path CIs are byte-identical
    point = statistic(recs)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [rng.choice(cases) for _ in cases]
        boot = [t for c in pick for t in by_case[c]]
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


def _detect_rate(trials):
    return _rate(_detect_correct)(trials)


# --------------------------------------------------------------------------- #
# Metrics — generic over whatever operators/arms/agents are present
# --------------------------------------------------------------------------- #

def h1_anchor_gap(recs):
    """Anchor-off: negative-symptom detection − positive-symptom detection (symptom-derived)."""
    pos_ops, neg_ops = positive_ops(recs), negative_ops(recs)
    off = [r for r in recs if r["_anchor"] == "off" and r["_op"] in (pos_ops | neg_ops)]

    def gap(trials):
        pos = [t for t in trials if t["_op"] in pos_ops]
        neg = [t for t in trials if t["_op"] in neg_ops]
        if not pos or not neg:
            return None
        return (sum(1 for t in neg if _detect_correct(t)) / len(neg)
                - sum(1 for t in pos if _detect_correct(t)) / len(pos))

    ci = bootstrap_ci(off, gap)
    pos = [r for r in off if r["_op"] in pos_ops]
    neg = [r for r in off if r["_op"] in neg_ops]
    ci["pos_rate"] = (sum(1 for t in pos if _detect_correct(t)) / len(pos)) if pos else None
    ci["neg_rate"] = (sum(1 for t in neg if _detect_correct(t)) / len(neg)) if neg else None
    ci["n_cases_pos"] = len({t["case_id"] for t in pos})
    ci["n_cases_neg"] = len({t["case_id"] for t in neg})
    ci["positive_ops"] = sorted(pos_ops)
    ci["negative_ops"] = sorted(neg_ops)
    return ci


def h1_matched_sigma(recs):
    """Nearest-|σ_hidden| pairing of each positive-symptom case to a negative-symptom case; mean
    paired detection gap (neg − pos) anchor-off. Does NOT touch the operator-identity confound."""
    pos_ops, neg_ops = positive_ops(recs), negative_ops(recs)
    off = [r for r in recs if r["_anchor"] == "off"]

    def case_rate(op_set):
        out = {}
        for cid, trials in _by_case([r for r in off if r["_op"] in op_set]).items():
            sig = abs(trials[0]["_sig_hid"]) if trials[0]["_sig_hid"] is not None else None
            out[cid] = (sig, sum(1 for t in trials if _detect_correct(t)) / len(trials))
        return out

    pos, neg = case_rate(pos_ops), case_rate(neg_ops)
    pairs = []
    for lc, (lsig, lrate) in pos.items():
        if not neg:
            break
        ncid, (nsig, nrate) = min(neg.items(), key=lambda kv: abs((kv[1][0] or 0) - (lsig or 0)))
        pairs.append({"pos_case": lc, "neg_case": ncid, "gap": round(nrate - lrate, 3)})
    mean_gap = sum(p["gap"] for p in pairs) / len(pairs) if pairs else None
    return {"pairs": pairs, "mean_paired_gap": round(mean_gap, 3) if mean_gap is not None else None}


def detection_by_operator_arm(recs):
    """Detection rate (point + case-clustered CI) per faulty operator × arm present."""
    out = {}
    for op in faulty_ops(recs):
        out[op] = {}
        for arm in arms_present(recs):
            rs = [r for r in recs if r["_op"] == op and r["_anchor"] == arm]
            if rs:
                out[op][arm] = bootstrap_ci(rs, _detect_rate)
    return out


def ratio_gap_closed(recs, low_arm="off", mid_arm="numbers", high_arm="rule"):
    """Pre-registered but never-computed statistic (STAGE3_PLAN §0.3.4): per operator, the
    FRACTION of the low->high detection gap closed by the mid arm = (mid-low)/(high-low),
    with a case-clustered bootstrap of the RATIO. Degenerate gap (high≈low) -> flagged.
    """
    arms = set(arms_present(recs))
    if not {low_arm, mid_arm, high_arm} <= arms:
        return {"available": False, "reason": f"needs arms {low_arm}/{mid_arm}/{high_arm}; present {sorted(arms)}"}
    out = {"available": True, "low_arm": low_arm, "mid_arm": mid_arm, "high_arm": high_arm,
           "method": f"case-level bootstrap of the ratio, {N_RESAMPLES} resamples, seed {SEED}", "operators": {}}
    for op in faulty_ops(recs):
        rs = [r for r in recs if r["_op"] == op and r["_anchor"] in (low_arm, mid_arm, high_arm)]

        def ratio(trials):
            def rate(arm):
                xs = [r for r in trials if r["_anchor"] == arm]
                return (sum(1 for t in xs if _detect_correct(t)) / len(xs)) if xs else None
            lo, mid, hi = rate(low_arm), rate(mid_arm), rate(high_arm)
            if lo is None or mid is None or hi is None:
                return None
            gap = hi - lo
            if abs(gap) < 1e-9:
                return None  # degenerate: no gap to close
            return (mid - lo) / gap

        ci = bootstrap_ci(rs, ratio)
        # point-estimate arm rates for context
        def r_arm(arm):
            xs = [r for r in rs if r["_anchor"] == arm]
            return round(sum(1 for t in xs if _detect_correct(t)) / len(xs), 4) if xs else None
        lo, mid, hi = r_arm(low_arm), r_arm(mid_arm), r_arm(high_arm)
        degenerate = lo is not None and hi is not None and abs(hi - lo) < 1e-9
        out["operators"][op] = {
            f"detect_{low_arm}": lo, f"detect_{mid_arm}": mid, f"detect_{high_arm}": hi,
            "gap_low_high": round((hi - lo), 4) if (lo is not None and hi is not None) else None,
            "fraction_closed_by_mid": ci, "degenerate_gap": degenerate,
        }
    return out


def h6_react_minus_static(recs):
    """Overall (ReAct − static) evidence F1 on faulty operators, pooled (if both agents present)."""
    ags = set(agents_present(recs))
    if not {"react", "static"} <= ags:
        return {"available": False, "reason": f"needs react+static; present {sorted(ags)}"}
    faulty = [r for r in recs if r.get("_tier") != "control" and _ev_f1(r) is not None]

    def diff(trials):
        re = [_ev_f1(t) for t in trials if t["_agent"] == "react"]
        st = [_ev_f1(t) for t in trials if t["_agent"] == "static"]
        if not re or not st:
            return None
        return sum(re) / len(re) - sum(st) / len(st)

    ci = bootstrap_ci(faulty, diff)
    ci["available"] = True
    return ci


def control_fpr(recs):
    """Detection false-positive rate on controls, PER ARM present + the numbers−rule difference
    (if both arms exist), each bootstrapped over the control cases (wide by construction)."""
    ctrl_all = [r for r in recs if r.get("_tier") == "control"]
    if not ctrl_all:
        return {"available": False, "reason": "no control trials"}
    fp_pred = _rate(lambda t: _detected(t) is True)
    per_arm = {}
    for arm in arms_present(ctrl_all):
        ctrl = [r for r in ctrl_all if r["_anchor"] == arm]
        ci = bootstrap_ci(ctrl, fp_pred)
        fp = [r for r in ctrl if _detected(r) is True]
        ci["n_fp"] = len(fp)
        ci["fp_cases"] = sorted({r["case_id"] for r in fp})
        per_arm[arm] = ci
    out = {"available": True, "per_arm": per_arm}
    # numbers − rule difference (the specificity contrast), if both arms present
    if "numbers" in per_arm and "rule" in per_arm:
        num = [r for r in ctrl_all if r["_anchor"] == "numbers"]
        rul = [r for r in ctrl_all if r["_anchor"] == "rule"]

        def diff(trials):
            n = [t for t in trials if t["_anchor"] == "numbers"]
            r = [t for t in trials if t["_anchor"] == "rule"]
            if not n or not r:
                return None
            return (sum(1 for t in n if _detected(t) is True) / len(n)
                    - sum(1 for t in r if _detected(t) is True) / len(r))
        out["numbers_minus_rule"] = bootstrap_ci(num + rul, diff)
    return out


def recovery_endpoints(recs):
    """Per faulty operator: identification, strict & semantic recovery + the id−strict / id−semantic
    dissociation gaps with case-clustered CIs. Iterates whatever faulty operators are present."""
    out = {}
    for op in faulty_ops(recs):
        rs = [r for r in recs if r["_op"] == op]
        id_rate, strict, semantic = _rate(_id_correct), _rate(_strict_recovered), _rate(_recovered)
        gap_strict = bootstrap_ci(rs, lambda tr: (id_rate(tr) - strict(tr))
                                  if (id_rate(tr) is not None and strict(tr) is not None) else None)
        gap_sem = bootstrap_ci(rs, lambda tr: (id_rate(tr) - semantic(tr))
                               if (id_rate(tr) is not None and semantic(tr) is not None) else None)
        out[op] = {
            "n_trials": len(rs), "n_cases": len({r["case_id"] for r in rs}),
            "identification": round(id_rate(rs), 4) if id_rate(rs) is not None else None,
            "strict_recovery": round(strict(rs), 4) if strict(rs) is not None else None,
            "semantic_recovery": round(semantic(rs), 4) if semantic(rs) is not None else None,
            "id_minus_strict": gap_strict, "id_minus_semantic": gap_sem,
        }
    return out


# Metric registry (STAGE3_PLAN §0.3.3): a plan may declare `metrics: [names]` in its header to
# select which of these run; absent -> all applicable (each metric self-reports "not available"
# when the design lacks the arms/agents it needs). Output key == registry name.
METRICS = {
    "h1_anchor_gap_pooled": h1_anchor_gap,
    "detection_by_operator_arm": detection_by_operator_arm,
    "ratio_gap_closed": ratio_gap_closed,
    "h6_react_minus_static": h6_react_minus_static,
    "control_fpr": control_fpr,
    "recovery_endpoints": recovery_endpoints,
}


def compute_all(recs, metrics=None) -> dict:
    """Generic contrast bundle over already-loaded+attached records.

    `metrics`: list of registry names to compute (default: all). A plan declares its set via
    `header.metrics`; report_gen passes it through. Nothing here is operator/arm/model-specific.
    """
    names = metrics or list(METRICS)
    out = {
        "n_trials": len(recs),
        "n_cases": len({r["case_id"] for r in recs}),
        "method": f"case-level nonparametric bootstrap, {N_RESAMPLES} resamples, 95% percentile, seed {SEED}",
        "operators_faulty": faulty_ops(recs),
        "operators_control": control_ops(recs),
        "arms": arms_present(recs),
        "agents": agents_present(recs),
    }
    for name in names:
        if name not in METRICS:
            raise KeyError(f"unknown metric {name!r}; registered: {sorted(METRICS)}")
        out[name] = METRICS[name](recs)
    return out
