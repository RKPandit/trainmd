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

from harness.anchors import arm_key, arm_version, normalize_anchor

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
                # §5.1 band labels — present only on cases rebuilt under the §5.1
                # guard; None on pre-§5.1 (frozen-era) cards → control_fpr falls
                # back to the pooled table (byte-identical for frozen sweeps).
                "band_position_visible": card.get("band_position_visible"),
                "band_position_hidden": card.get("band_position_hidden"),
                "benign_form": card.get("benign_form"),
                # strength × seed — the H8 paired-bootstrap matching key.
                "strength": card.get("strength"),
                "seed": card.get("seed"),
            }
        return cache[cid]

    return meta


# --------------------------------------------------------------------------- #
# Frozen-sweep operator identity (STAGE 4.0.1 methodology, DECISIONS 2026-09-22)
# --------------------------------------------------------------------------- #
#
# LESSON: `case_id` is NOT a stable operator key across rebuilds. A frozen sweep's
# case_ids can be (and were) rebuilt to DIFFERENT operators later, so attributing a
# frozen sweep by today's `cases/*/hidden/` mis-attributes the operator — it did so
# for ~all of Sweeps 1–2 and 67 records of Sweep 3. A record's OWN sealed
# `scores.identification.accepted_classes` (the answer key frozen into the record at
# score time) is the correct, rebuild-proof key. Validated against the released
# operator maps for sweep1+stage2gate: 574 agree, 0 disagree, 2 empty.

def _accepted_class_signatures() -> dict:
    """{frozenset(accepted_classes): operator_id} from the current operator code.

    The two leakage variants share one answer key, so the signature resolves to a
    single canonical CONCEPT operator (fine for identification, which scores the
    concept); split the leakage variants with the frozen per-case map when the arm
    matters. Memoized on first use.
    """
    from operators.registry import all_operator_ids, get_operator
    sig: dict = {}
    for op_id in all_operator_ids():
        sig[frozenset(get_operator(op_id).accepted_classes())] = op_id
    return sig


_ACC_SIG_CACHE: dict = {}


def operator_from_record(rec: dict) -> str | None:
    """The record's TRUE operator from its sealed accepted_classes (rebuild-proof).

    Use this — never today's `cases/` card — to attribute a FROZEN sweep. Returns
    None when the record sealed no answer key (e.g. a null-submission no-op).
    """
    if not _ACC_SIG_CACHE:
        _ACC_SIG_CACHE.update(_accepted_class_signatures())
    acc = frozenset(((rec.get("scores") or {}).get("identification") or {}).get(
        "accepted_classes") or [])
    return _ACC_SIG_CACHE.get(acc) if acc else None


def attach_meta(rec: dict, meta: dict) -> dict:
    """Attach analysis fields (normalizing the anchor exactly once, here at load)."""
    rec["_op"] = meta.get("operator_id")
    rec["_tier"] = meta.get("tier")
    rec["_symptom"] = meta.get("symptom_direction")
    rec["_sig_vis"] = meta.get("visible_sigma_distance")
    rec["_sig_hid"] = meta.get("hidden_sigma_distance")
    rec["_band_vis"] = meta.get("band_position_visible")  # §5.1 (None pre-§5.1)
    rec["_band_hid"] = meta.get("band_position_hidden")
    rec["_benign_form"] = meta.get("benign_form")      # None: not a benign-config control
    rec["_strength"] = meta.get("strength")   # H8 paired-bootstrap key
    rec["_seed"] = meta.get("seed")
    # Arm identity includes the prompt MAJOR version (harness/anchors.py): v1 and v2 arms get
    # distinct keys, so they can never be pooled by any downstream grouping.
    rec["_anchor"] = normalize_anchor((rec.get("conditions") or {}).get("anchor"),
                                      (rec.get("prompt") or {}).get("prompt_version"))
    rec["_agent"] = (rec.get("conditions") or {}).get("agent_type")
    rec["_provider"] = (rec.get("conditions") or {}).get("provider")
    return rec


# --------------------------------------------------------------------------- #
# ONE trial per cell (dedup)
# --------------------------------------------------------------------------- #

# A cell = one scheduled trial slot. Its identity is the case + the condition
# labels the runner varies. Retries/aborted attempts write extra records for the
# SAME cell; the report must count each cell once.
_DEDUP_EXCLUDE_STATUS = {"crashed", "partial", "failed"}


def _cell_key(r: dict) -> tuple:
    c = r.get("conditions") or {}
    return (r.get("case_id"), c.get("agent_type"), c.get("anchor"),
            c.get("repeat_index"), c.get("provider"))


def _rec_ts(r: dict) -> tuple:
    return (((r.get("environment") or {}).get("timestamp_utc") or ""), r.get("run_id") or "")


def dedup_one_per_cell(recs: list[dict]) -> list[dict]:
    """Keep the LATEST SUCCESSFUL record per cell; drop failed/crashed/partial.

    Rule: exclude any record whose status is crashed/partial/failed; among the
    rest for a cell key, keep the one with the greatest (timestamp, run_id).
    First-appearance order of each kept key is preserved, so a clean sweep (one
    record per cell, already) is returned unchanged — the frozen release reports
    stay byte-identical, and the results-path and release-path reports match."""
    chosen: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in recs:
        if r.get("status") in _DEDUP_EXCLUDE_STATUS:
            continue
        k = _cell_key(r)
        if k not in chosen:
            chosen[k] = r
            order.append(k)
        elif _rec_ts(r) >= _rec_ts(chosen[k]):
            chosen[k] = r
    return [chosen[k] for k in order]


def dedup_audit(recs: list[dict]) -> dict:
    """Provenance for the dedup: per cell with >1 record, the statuses seen and
    which record was kept. Reported alongside the numbers (not in the machine
    report, so from_cases/from_release stay byte-identical)."""
    from collections import Counter
    groups: dict[tuple, list] = defaultdict(list)
    for r in recs:
        groups[_cell_key(r)].append(r)
    kept = {_cell_key(r): r for r in dedup_one_per_cell(recs)}
    multi = []
    for k, group in groups.items():
        if len(group) > 1:
            kr = kept.get(k)
            multi.append({
                "cell": k,
                "n_records": len(group),
                "statuses": dict(Counter(g.get("status") for g in group)),
                "kept_run_id": kr.get("run_id") if kr else None,
                "kept_status": kr.get("status") if kr else "(none — all excluded)",
            })
    excluded = [r for r in recs if r.get("status") in _DEDUP_EXCLUDE_STATUS]
    return {
        "n_records_in": len(recs),
        "n_cells_out": len(kept),
        "n_cells_multi_record": len(multi),
        "n_excluded_records": len(excluded),
        "excluded_status_counts": dict(Counter(r.get("status") for r in excluded)),
        "multi": sorted(multi, key=lambda m: m["cell"]),
    }


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
    return dedup_one_per_cell(recs)


def case_meta_from_release(release_dir: Path):
    """Return a `case_meta(cid)` reading the RELEASE's per-case metadata (no registry, no cases/).

    This is the external-reviewer path: tier/symptom/σ come from results_release/<name>/cases/<cid>.json,
    so the analysis runs with no access to the hidden registry."""
    cache: dict = {}

    def meta(cid: str) -> dict:
        if cid not in cache:
            d = json.loads((release_dir / "cases" / f"{cid}.json").read_text())
            # Per-case metadata holds ONLY the visible band label, and nothing hidden-band is read
            # here — so this path cannot produce (or be edited to inject) a hidden-band
            # stratification. (Per-trial scores may hold the hidden band position; they are not
            # read for stratification. See the release's FIELD_INVENTORY.json.)
            cache[cid] = {k: d.get(k) for k in (
                "operator_id", "tier", "symptom_direction",
                "visible_sigma_distance", "hidden_sigma_distance",
                "band_position_visible", "benign_form",
                "strength", "seed")}
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
    return dedup_one_per_cell(recs)


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

def prompt_majors_present(recs) -> list[int]:
    return sorted({arm_version(a) for a in arms_present(recs)})

def _single_major(recs) -> int | None:
    """The one prompt major version the records span, or None if they mix versions (a contrast
    across arms of different versions is never computed implicitly)."""
    majors = prompt_majors_present(recs)
    return majors[0] if len(majors) == 1 else None

def _mid_arm(major: int) -> str:
    return "numbers" if major == 1 else "stats"

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


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p) — exact, stdlib only."""
    from math import comb
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1−alpha) Clopper–Pearson interval for k events in n independent units.

    lo solves P(X >= k) = alpha/2, hi solves P(X <= k) = alpha/2 (bisection on the exact binomial
    CDF; no scipy). lo = 0 when k = 0 and hi = 1 when k = n."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, n > 0 (got k={k}, n={n})")

    def solve(f, target):          # f increasing in p on [0, 1]; find p with f(p) = target
        a, b = 0.0, 1.0
        for _ in range(100):
            m = (a + b) / 2
            a, b = (m, b) if f(m) < target else (a, m)
        return (a + b) / 2

    lo = 0.0 if k == 0 else solve(lambda p: 1 - _binom_cdf(k - 1, n, p), alpha / 2)
    hi = 1.0 if k == n else solve(lambda p: 1 - _binom_cdf(k, n, p), 1 - alpha / 2)
    return lo, hi


def zero_event_upper(n, alpha=0.05, two_sided=True):
    """Exact Clopper–Pearson upper limit for 0 events in n independent units (closed form).

    Callers pass the number of UNIQUE CASES (clusters) as n, never the trial count: trials within
    a case are correlated, and every other interval here clusters by case.
      two_sided=True  (TABLES):  1 − (alpha/2)^(1/n) — the upper limit of the two-sided (1−alpha)
                                 interval [0, U]; 3 cases ⇒ 0.708, 19 ⇒ 0.176, 20 ⇒ 0.168.
      two_sided=False (PROSE ceilings only, labelled one-sided): 1 − alpha^(1/n); 20 ⇒ 0.139.
    Correction #6 (2026-09-23): a zero-event stratum's bootstrap percentile CI is a false-precision
    [0, 0]; tables carry the exact interval instead. The point estimate stays 0.0."""
    if not n or n <= 0:
        return None
    return 1.0 - (alpha / 2 if two_sided else alpha) ** (1.0 / n)


def _mark_zero_event(ci):
    """If a RATE CI observed zero events, replace its degenerate [0, 0] with the exact two-sided
    95% Clopper–Pearson interval over its number of UNIQUE CASES — the cluster unit of the
    case-clustered bootstrap it replaces. Rows with 1–2 events are flagged `low_count`: the
    percentile bootstrap understates uncertainty there (LIMITATIONS L30). Mutates and returns ci."""
    n_fp = ci.get("n_fp")
    if n_fp == 0 and ci.get("n_cases"):
        ci["zero_event_cp"] = True
        ci["point"] = 0.0
        ci["lo"] = 0.0
        ci["hi"] = round(zero_event_upper(ci["n_cases"], two_sided=True), 6)
    elif n_fp in (1, 2):
        ci["low_count"] = True
    return ci


def _detect_rate(trials):
    return _rate(_detect_correct)(trials)


# --------------------------------------------------------------------------- #
# Metrics — generic over whatever operators/arms/agents are present
# --------------------------------------------------------------------------- #

def h1_anchor_gap(recs):
    """Anchor-off: negative-symptom detection − positive-symptom detection (symptom-derived)."""
    pos_ops, neg_ops = positive_ops(recs), negative_ops(recs)
    major = _single_major(recs)
    off_arm = arm_key("off", major) if major else None   # mixed versions: no implicit pooling
    off = [r for r in recs if r["_anchor"] == off_arm and r["_op"] in (pos_ops | neg_ops)]

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
    major = _single_major(recs)
    off_arm = arm_key("off", major) if major else None   # mixed versions: no implicit pooling
    off = [r for r in recs if r["_anchor"] == off_arm]

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


def ratio_gap_closed(recs, low_arm=None, mid_arm=None, high_arm=None):
    """Pre-registered but never-computed statistic (STAGE3_PLAN §0.3.4): per operator, the
    FRACTION of the low->high detection gap closed by the mid arm = (mid-low)/(high-low),
    with a case-clustered bootstrap of the RATIO. Degenerate gap (high≈low) -> flagged.

    Default arms are the records' own prompt version's off→mid→rule (v1 off/numbers/rule, v2
    off.v2/stats.v2/rule.v2); records mixing prompt versions are not available (never pooled).
    """
    arms = set(arms_present(recs))
    if low_arm is None or mid_arm is None or high_arm is None:
        major = _single_major(recs)
        if major is None:
            return {"available": False,
                    "reason": f"records mix prompt versions {prompt_majors_present(recs)}; "
                              "arms of different versions are never pooled — analyze separately"}
        low_arm = low_arm or arm_key("off", major)
        mid_arm = mid_arm or arm_key(_mid_arm(major), major)
        high_arm = high_arm or arm_key("rule", major)
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
        _mark_zero_event(ci)          # zero-event → exact CP over cases; 1–2 events flagged
        per_arm[arm] = ci
    out = {"available": True, "per_arm": per_arm}

    # Benign-configuration controls (STAGE4 4.0.6): FP rate SEPARATELY by edit form — healthy
    # (no edit), changed-value, new-key — per arm. Only when benign controls are present, so sweeps
    # without them render byte-identically.
    if any(r.get("_benign_form") for r in ctrl_all):
        forms = {}
        for form, keep in (("healthy (no edit)", lambda r: not r.get("_benign_form")),
                           ("benign: changed value", lambda r: r.get("_benign_form") == "changed"),
                           ("benign: new key", lambda r: r.get("_benign_form") == "added")):
            forms[form] = {}
            for arm in arms_present(ctrl_all):
                sub = [r for r in ctrl_all if r["_anchor"] == arm and keep(r)]
                if not sub:
                    continue
                ci = bootstrap_ci(sub, fp_pred)
                fp = [r for r in sub if _detected(r) is True]
                ci["n_fp"], ci["fp_cases"] = len(fp), sorted({r["case_id"] for r in fp})
                _mark_zero_event(ci)
                forms[form][arm] = ci
        out["by_benign_form"] = forms

    # §5.1: stratify each arm into in_band vs out-of-band (below_band ∪ above_band).
    # A pooled control FPR must never stand alone; the out-of-band rate is the honest
    # false-positive measurement (the hard healthy case). Gated on the EXPLICIT band
    # label being present on every control record: it exists only on cases rebuilt
    # under the §5.1 guard, so frozen pre-§5.1 sweeps omit these and render the pooled
    # table byte-identically.
    #
    # The STRATIFICATION KEY is the VISIBLE band position (`_band_vis`), by MECHANISM:
    # a control false positive is a visible-metric event — the agent reads
    # metric_visible_val_acc, compares it to its band, and flags. The HIDDEN breakdown
    # (`_band_hid`) is reported ALONGSIDE only as a case-quality label (the agent never
    # sees it). Both metrics are equally platform-sensitive native-vs-emulated, so
    # robustness is NOT the basis; the guard (platform_guard) ensures native-only
    # artifacts. See LIMITATIONS / DECISIONS 2026-09-16.
    def _by_band(key):
        breakdown = {}
        for arm in arms_present(ctrl_all):
            ctrl = [r for r in ctrl_all if r["_anchor"] == arm]
            strata = {}
            for name, keep in (
                ("in_band", lambda r, k=key: r[k] == "in_band"),
                ("out_of_band", lambda r, k=key: r[k] in ("below_band", "above_band")),
            ):
                sub = [r for r in ctrl if keep(r)]
                if not sub:
                    strata[name] = {"available": False, "n_cases": 0, "n_trials": 0}
                    continue
                ci = bootstrap_ci(sub, fp_pred)
                fp = [r for r in sub if _detected(r) is True]
                ci["available"] = True
                ci["n_fp"] = len(fp)
                ci["fp_cases"] = sorted({r["case_id"] for r in fp})
                _mark_zero_event(ci)  # zero-event → exact CP over cases; 1–2 events flagged
                strata[name] = ci
            breakdown[arm] = strata
        return breakdown

    if all(r.get("_band_vis") is not None for r in ctrl_all):
        out["by_band"] = _by_band("_band_vis")          # PRIMARY key (visible, by mechanism)
        out["stratified"] = True
        out["stratify_key"] = "visible_band_position"
        if all(r.get("_band_hid") is not None for r in ctrl_all):
            out["by_band_hidden"] = _by_band("_band_hid")   # alongside: case-quality label
    else:
        out["stratified"] = False

    # mid − rule difference (the specificity contrast), WITHIN each prompt version present
    # (v1 numbers − rule; v2 stats.v2 − rule.v2) — never across versions.
    diffs = []
    for major in prompt_majors_present(ctrl_all):
        mid, high = arm_key(_mid_arm(major), major), arm_key("rule", major)
        if mid not in per_arm or high not in per_arm:
            continue
        pair = [r for r in ctrl_all if r["_anchor"] in (mid, high)]

        def diff(trials, mid=mid, high=high):
            n = [t for t in trials if t["_anchor"] == mid]
            r = [t for t in trials if t["_anchor"] == high]
            if not n or not r:
                return None
            return (sum(1 for t in n if _detected(t) is True) / len(n)
                    - sum(1 for t in r if _detected(t) is True) / len(r))
        diffs.append({"mid_arm": mid, "high_arm": high, **bootstrap_ci(pair, diff)})
    if diffs:
        out["mid_minus_rule"] = diffs
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


# --------------------------------------------------------------------------- #
# Provider dimension (H7) + H8 neutral-vs-descriptive identification
# --------------------------------------------------------------------------- #

def providers_present(recs) -> list[str]:
    return sorted({r["_provider"] for r in recs if r.get("_provider")})


# The H8 pair. Named here (not a config literal elsewhere) because this metric IS
# the neutral-key ablation; it self-reports unavailable when the pair is absent.
_H8_DESCRIPTIVE = "silent.data_leakage.v1"
_H8_NEUTRAL = "silent.data_leakage_neutral.v1"
_H8_CONFIRM = 0.15
_H8_REFUTE = 0.30


def _h8_verdict(point, lo, hi):
    """Pre-registered EQUIVALENCE test on Δ = neutral − descriptive identification.

    Confirming requires the ENTIRE 95% CI to sit inside the equivalence interval
    (lo > −0.15 AND hi < +0.15) — a CI that merely straddles 0 but crosses ±0.15
    is INCONCLUSIVE, not confirming. Refuting requires a large gap AND the CI to
    exclude 0 (point < −0.30 and hi < 0). Everything else is inconclusive."""
    if point is None or lo is None or hi is None:
        return "n/a"
    if lo > -_H8_CONFIRM and hi < _H8_CONFIRM:
        return "confirming (no substantial gap)"
    if point < -_H8_REFUTE and hi < 0:
        return "refuting (name-reading)"
    return "inconclusive"


def h8_identification_contrast(recs):
    """Δ = neutral − descriptive IDENTIFICATION, per anchor arm, per provider (and
    pooled), case-clustered 95% CI, judged against the pre-registered thresholds."""
    ops = set(faulty_ops(recs))
    if not {_H8_DESCRIPTIVE, _H8_NEUTRAL} <= ops:
        return {"available": False,
                "reason": f"needs both {_H8_DESCRIPTIVE} + {_H8_NEUTRAL}; present {sorted(ops)}"}
    pair = [r for r in recs if r["_op"] in (_H8_DESCRIPTIVE, _H8_NEUTRAL)]
    arms = arms_present(pair)
    provs = providers_present(pair)
    facets = ([("pooled", pair)] + [(p, [r for r in pair if r["_provider"] == p]) for p in provs]
              if len(provs) > 1 else [("pooled", pair)])

    def gap(trials):
        neut = [_id_correct(t) for t in trials if t["_op"] == _H8_NEUTRAL]
        desc = [_id_correct(t) for t in trials if t["_op"] == _H8_DESCRIPTIVE]
        if not neut or not desc:
            return None
        return sum(neut) / len(neut) - sum(desc) / len(desc)

    out = {"available": True, "confirming_bound": _H8_CONFIRM, "refuting_bound": _H8_REFUTE,
           "descriptive_op": _H8_DESCRIPTIVE, "neutral_op": _H8_NEUTRAL,
           "arms": arms, "providers": provs, "rows": []}
    for fname, fsub in facets:
        for arm in arms:
            rs = [r for r in fsub if r["_anchor"] == arm]
            ci = bootstrap_ci(rs, gap)
            neut = [r for r in rs if r["_op"] == _H8_NEUTRAL]
            desc = [r for r in rs if r["_op"] == _H8_DESCRIPTIVE]
            ci["neutral_id"] = _rate(_id_correct)(neut)
            ci["descriptive_id"] = _rate(_id_correct)(desc)
            ci["n_cases_neutral"] = len({r["case_id"] for r in neut})
            ci["n_cases_descriptive"] = len({r["case_id"] for r in desc})
            ci["verdict"] = _h8_verdict(ci["point"], ci.get("lo"), ci.get("hi"))
            out["rows"].append({"provider": fname, "arm": arm, **ci})
    return out


def _h8_paired_gap_ci(pair_recs, n=N_RESAMPLES, seed=SEED):
    """PAIRED bootstrap of Δ = neutral − descriptive identification (STAGE 4.0.2).

    The neutral and descriptive variants are the SAME injected fault under two
    config-key namings, built at matched (strength, seed). Resampling the two arms
    independently (the unpaired ``bootstrap_ci``) ignores that pairing and inflates
    the CI. Here the resampling UNIT is a matched (strength, seed) PAIR — the
    descriptive case and the neutral case are resampled TOGETHER — so shared
    case-difficulty cancels and the CI reflects the within-pair contrast the
    ablation is about. Only (strength, seed) cells present for BOTH variants
    contribute. The point estimate is unchanged from the unpaired contrast; only
    the interval differs.
    """
    units = defaultdict(lambda: {"neut": [], "desc": []})
    for r in pair_recs:
        key = (r.get("_strength"), r.get("_seed"))
        if r["_op"] == _H8_NEUTRAL:
            units[key]["neut"].append(r)
        elif r["_op"] == _H8_DESCRIPTIVE:
            units[key]["desc"].append(r)
    keys = sorted(k for k, u in units.items() if u["neut"] and u["desc"])

    def gap_over(sel_keys):
        neut = [x for k in sel_keys for x in map(_id_correct, units[k]["neut"]) if x is not None]
        desc = [x for k in sel_keys for x in map(_id_correct, units[k]["desc"]) if x is not None]
        if not neut or not desc:
            return None
        return sum(neut) / len(neut) - sum(desc) / len(desc)

    point = gap_over(keys) if keys else None
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [rng.choice(keys) for _ in keys] if keys else []
        v = gap_over(pick)
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = vals[int(0.025 * len(vals))] if vals else None
    hi = vals[int(0.975 * len(vals)) - 1] if vals else None
    return {"point": point, "lo": lo, "hi": hi, "n_pairs": len(keys),
            "n_trials": len(pair_recs)}


def h8_identification_contrast_paired(recs):
    """H8 identification contrast with the PAIRED bootstrap (STAGE 4.0.2).

    Same point estimate and pre-registered equivalence verdict as
    :func:`h8_identification_contrast`, but the CI resamples matched (strength,
    seed) PAIRS together (see :func:`_h8_paired_gap_ci`). Self-reports unavailable
    when the pair, or the strength×seed matching key, is absent.
    """
    ops = set(faulty_ops(recs))
    if not {_H8_DESCRIPTIVE, _H8_NEUTRAL} <= ops:
        return {"available": False,
                "reason": f"needs both {_H8_DESCRIPTIVE} + {_H8_NEUTRAL}; present {sorted(ops)}"}
    pair = [r for r in recs if r["_op"] in (_H8_DESCRIPTIVE, _H8_NEUTRAL)]
    if all(r.get("_strength") is None or r.get("_seed") is None for r in pair):
        return {"available": False, "reason": "no strength×seed on cases → cannot pair"}
    arms = arms_present(pair)
    provs = providers_present(pair)
    facets = ([("pooled", pair)] + [(p, [r for r in pair if r["_provider"] == p]) for p in provs]
              if len(provs) > 1 else [("pooled", pair)])

    out = {"available": True, "method": f"PAIRED (strength×seed) case-level bootstrap, "
           f"{N_RESAMPLES} resamples, 95% percentile, seed {SEED}",
           "confirming_bound": _H8_CONFIRM, "refuting_bound": _H8_REFUTE,
           "descriptive_op": _H8_DESCRIPTIVE, "neutral_op": _H8_NEUTRAL,
           "arms": arms, "providers": provs, "rows": []}
    for fname, fsub in facets:
        for arm in arms:
            rs = [r for r in fsub if r["_anchor"] == arm]
            ci = _h8_paired_gap_ci(rs)
            neut = [r for r in rs if r["_op"] == _H8_NEUTRAL]
            desc = [r for r in rs if r["_op"] == _H8_DESCRIPTIVE]
            ci["neutral_id"] = _rate(_id_correct)(neut)
            ci["descriptive_id"] = _rate(_id_correct)(desc)
            ci["verdict"] = _h8_verdict(ci["point"], ci.get("lo"), ci.get("hi"))
            out["rows"].append({"provider": fname, "arm": arm, **ci})
    return out


def h8_secondary_detection_recovery(recs):
    """Pre-registered H8 secondary: detection + semantic recovery per VARIANT, per
    anchor arm, per provider (pooled when single). Expected UNCHANGED between the
    two variants (same fault) — a difference flags an instrument problem."""
    ops = set(faulty_ops(recs))
    if not {_H8_DESCRIPTIVE, _H8_NEUTRAL} <= ops:
        return {"available": False, "reason": "needs both variants"}
    pair = [r for r in recs if r["_op"] in (_H8_DESCRIPTIVE, _H8_NEUTRAL)]
    arms = arms_present(pair)
    provs = providers_present(pair)
    facets = ([("pooled", pair)] + [(p, [r for r in pair if r["_provider"] == p]) for p in provs]
              if len(provs) > 1 else [("pooled", pair)])
    rows = []
    for fname, fsub in facets:
        for variant, op in (("descriptive", _H8_DESCRIPTIVE), ("neutral", _H8_NEUTRAL)):
            for arm in arms:
                rs = [r for r in fsub if r["_op"] == op and r["_anchor"] == arm]
                rows.append({
                    "provider": fname, "variant": variant, "arm": arm,
                    "detection": _detect_rate(rs), "recovery": _rate(_recovered)(rs),
                    "n_trials": len(rs), "n_cases": len({r["case_id"] for r in rs}),
                })
    return {"available": True, "arms": arms, "providers": provs, "rows": rows}


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
    "h8_identification_contrast": h8_identification_contrast,
    "h8_identification_contrast_paired": h8_identification_contrast_paired,
    "h8_secondary_detection_recovery": h8_secondary_detection_recovery,
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
