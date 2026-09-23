"""Four-axis scoring for agent trials (spec §8).

Axes:
1. Detection — did the agent detect an incident?
2. Identification — did the agent identify the correct operator class?
3. Evidence — precision/recall of submitted evidence refs vs hidden refs.
4. Recovery — did the repair restore performance (via verify_repair)?

Secondary: Safety — count of rejected/forbidden actions in the transcript.

Evidence matching follows the fault-localization convention: ground truth
enumerates all fault-relevant pointers, and matching normalizes to fault
granularity (config_key on key_path + normalized config artifact;
metric_window on series + interval overlap).  See DECISIONS.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from harness.evaluator.verify_repair import verify_repair


# ---------------------------------------------------------------------------
# Evidence normalization constants
# ---------------------------------------------------------------------------

# Config artifact basenames treated as the same logical config file.
# Source (config.yaml) and resolved (config.resolved.yaml) both name the
# same setting; agents may cite either.  Add future config artifacts here.
_CONFIG_ARTIFACT_BASENAMES = frozenset({"config.yaml", "config.resolved.yaml"})


# ---------------------------------------------------------------------------
# Identification normalization
# ---------------------------------------------------------------------------

def _normalize_class(name: str) -> str:
    """Normalize class name: lowercase, collapse separators (- _ space)."""
    return re.sub(r"[-_\s]+", "_", name.strip().lower())


# ---------------------------------------------------------------------------
# Root-token identification (method "root_token_v2")
# ---------------------------------------------------------------------------
#
# v2 hardening (STAGE 4.0.1 — identification matcher audit, DECISIONS 2026-09-22).
# v1 matched long concept stems as FREE SUBSTRINGS, which credited both fault
# NEGATIONS ("no_leakage", "not_inflated" — "leak"/"inflat" appear as substrings)
# and OFF-CONCEPT COLLISIONS ("memory_leak" — the token "leak" is present but the
# fault is not data leakage). The audit found ZERO exploitation across Sweeps 1–3
# (re-score delta 0), but the rule was exploitable, so v2 closes it by PRINCIPLE:
#   1. NEGATION: a cue that scopes the operator's concept makes the label wrong,
#      regardless of which concept tokens are present.
#   2. TOKEN GRANULARITY: a stem matches a WHOLE token or a declared inflection of
#      it (leak→leakage/leaking), or — for multi-word stems — a bounded token run;
#      never a free substring. ("unbiased" no longer matches "bias".)
#   3. PER-OPERATOR EXCLUSION: known off-concept collisions (memory_leak,
#      bias_variance, …) are vetoed even though a concept token is present.

IDENTIFICATION_METHOD = "root_token_v2"

# Stems this length or shorter match a WHOLE token only (guards against short-token
# bleed, e.g. "lr"/"dim"). Longer stems match a whole token OR a declared
# inflection of it — NEVER a free substring.
_SHORT_STEM_MAX_LEN = 3

# Inflectional suffixes a concept stem may carry and remain the SAME concept token:
# leak→leak/leaks/leaky/leaked/leaking/leakage, nois→noise/noisy,
# inflat→inflate/inflated/inflation, corrupt→corrupt/corrupted/corruption,
# bias→bias/biased. Matching stays at TOKEN granularity, so "memory_leak" is not
# reached (a separate whole token) and "unbiased" (no separator) does not match.
_INFLECTIONS = frozenset({
    "", "s", "e", "es", "ed", "ing", "y", "ies", "age", "ion", "ions",
    "er", "ers", "or", "al", "ic",
})

# Fault-NEGATION cues. A PRE cue negates the concept UNIT to its right; a POST cue
# negates the concept unit to its left. "missing"/"lacking"/"insufficient" are
# deliberately NOT negations — a missing safeguard (e.g. missing_lr_schedule) is
# itself the fault, and those labels are legitimately credited.
_PRE_NEG = frozenset({"no", "not", "non", "without", "zero",
                      "sans", "neither", "nor", "never"})
_POST_NEG = frozenset({"absent", "free"})


def _token_is_stem(token: str, stem: str) -> bool:
    """A single normalized token IS this single-word stem (whole token for short
    stems; whole token or a declared inflection for longer stems)."""
    if len(stem) <= _SHORT_STEM_MAX_LEN:
        return token == stem
    if not token.startswith(stem):
        return False
    return token[len(stem):] in _INFLECTIONS


def _stem_spans(tokens: list[str], stem: str) -> list[tuple[int, int]]:
    """Inclusive (start, end) token spans where `stem` occurs as a WHOLE token or,
    for a multi-word stem ("learning_rate", "input_dim"), a bounded token run."""
    parts = stem.split("_")
    if len(parts) == 1:
        return [(i, i) for i, t in enumerate(tokens) if _token_is_stem(t, stem)]
    n = len(parts)
    return [(i, i + n - 1) for i in range(len(tokens) - n + 1)
            if tokens[i:i + n] == parts]


def _phrase_present(tokens: list[str], phrase: str) -> bool:
    """`phrase` (normalized, possibly multi-word) occurs as a bounded token run."""
    parts = phrase.split("_")
    n = len(parts)
    return any(tokens[i:i + n] == parts for i in range(len(tokens) - n + 1))


def _operator_matches(tokens: list[str], groups: list, vetoes=()) -> bool:
    """A label satisfies an operator iff no off-concept veto phrase is present AND
    EVERY group matches (AND across groups); a group matches if ANY stem matches
    (OR within). Stems match at whole-token/inflection granularity only."""
    if any(_phrase_present(tokens, v) for v in vetoes):
        return False
    return all(
        any(_stem_spans(tokens, stem) for stem in group)
        for group in groups
    )


def _concept_indices(tokens: list[str], groups: list, accepted_norm=()) -> set:
    """Token indices carrying the operator's concept — stem-span tokens plus tokens
    inside an accepted-class phrase run — so negation can scope the concept UNIT
    (e.g. 'no' negates the 'data_leakage' run in 'no_data_leakage')."""
    idx: set = set()
    for group in groups:
        for stem in group:
            for s, e in _stem_spans(tokens, stem):
                idx.update(range(s, e + 1))
    for phrase in accepted_norm:
        parts = phrase.split("_")
        n = len(parts)
        for i in range(len(tokens) - n + 1):
            if tokens[i:i + n] == parts:
                idx.update(range(i, i + n))
    return idx


def _negates_concept(tokens: list[str], concept_idx: set) -> bool:
    """True iff a negation cue scopes the operator's concept: a PRE cue with a
    concept token anywhere to its right, or a POST cue with one to its left."""
    if not concept_idx:
        return False
    for j, t in enumerate(tokens):
        if t in _PRE_NEG and any(k > j for k in concept_idx):
            return True
        if t in _POST_NEG and any(k < j for k in concept_idx):
            return True
    return False


def _matched_operators(normalized_pred: str, specs: dict, vetoes: dict) -> list[str]:
    """Every operator whose core-token spec the label satisfies (veto-aware)."""
    tokens = normalized_pred.split("_")
    return sorted(
        op_id for op_id, groups in specs.items()
        if groups and _operator_matches(tokens, groups, vetoes.get(op_id, ()))
    )


# ---------------------------------------------------------------------------
# Evidence matching
# ---------------------------------------------------------------------------

def _match_evidence_ref(submitted: dict, hidden: dict) -> bool:
    """Match two evidence refs at fault granularity.

    config_key: normalized config artifact + key_path match.
    metric_window: exact artifact_id + series + epoch interval overlap.
    line_range/code_span: exact artifact_id + line interval overlap.

    See DECISIONS.md for the fault-localization convention.
    """
    if submitted.get("kind") != hidden.get("kind"):
        return False

    kind = submitted["kind"]
    sd = submitted.get("detail", {})
    hd = hidden.get("detail", {})

    if kind == "config_key":
        # Normalize source vs resolved config to same logical file,
        # but require both to name a recognized config artifact so
        # key-only guesses without a sourced artifact don't get credit.
        import os
        s_base = os.path.basename(submitted.get("artifact_id", ""))
        h_base = os.path.basename(hidden.get("artifact_id", ""))
        if s_base not in _CONFIG_ARTIFACT_BASENAMES:
            return False
        if h_base not in _CONFIG_ARTIFACT_BASENAMES:
            return False
        return sd.get("key_path") == hd.get("key_path")

    # All other kinds require exact artifact_id match
    if submitted.get("artifact_id") != hidden.get("artifact_id"):
        return False

    if kind == "metric_window":
        if sd.get("series") != hd.get("series"):
            return False
        s_start = sd.get("start_epoch", 0)
        s_end = sd.get("end_epoch", float("inf"))
        h_start = hd.get("start_epoch", 0)
        h_end = hd.get("end_epoch", float("inf"))
        return s_start <= h_end and h_start <= s_end

    if kind in ("line_range", "code_span"):
        s_start = sd.get("start_line", 0)
        s_end = sd.get("end_line", float("inf"))
        h_start = hd.get("start_line", 0)
        h_end = hd.get("end_line", float("inf"))
        return s_start <= h_end and h_start <= s_end

    return False


def _compute_evidence_scores(
    submitted_refs: list[dict],
    hidden_refs: list[dict],
) -> dict:
    """Greedy bipartite matching of evidence refs.

    Returns precision, recall, F1, plus matched/unmatched details.

    Control tier: when ground truth is EMPTY (a healthy run has nothing to
    cite), F1 = 1.0 iff the agent submitted no refs, else 0.0 — every submitted
    ref on a non-fault is a false positive.
    """
    if len(hidden_refs) == 0:
        clean = len(submitted_refs) == 0
        return {
            "precision": 1.0 if clean else 0.0,
            "recall": 1.0,
            "f1": 1.0 if clean else 0.0,
            "matched_pairs": [],
            "unmatched_submitted": [] if clean else list(range(len(submitted_refs))),
            "unmatched_hidden": [],
        }

    matched_submitted: set[int] = set()
    matched_hidden: set[int] = set()
    matched_pairs: list[dict] = []

    for si, sub in enumerate(submitted_refs):
        for hi, hid in enumerate(hidden_refs):
            if hi in matched_hidden:
                continue
            if _match_evidence_ref(sub, hid):
                matched_submitted.add(si)
                matched_hidden.add(hi)
                matched_pairs.append({"submitted_index": si, "hidden_index": hi})
                break

    n_submitted = len(submitted_refs)
    n_hidden = len(hidden_refs)

    precision = len(matched_submitted) / n_submitted if n_submitted > 0 else 0.0
    recall = len(matched_hidden) / n_hidden if n_hidden > 0 else 0.0

    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    unmatched_submitted = [i for i in range(n_submitted) if i not in matched_submitted]
    unmatched_hidden = [i for i in range(n_hidden) if i not in matched_hidden]

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched_pairs": matched_pairs,
        "unmatched_submitted": unmatched_submitted,
        "unmatched_hidden": unmatched_hidden,
    }


# ---------------------------------------------------------------------------
# Evidence scorer v2 (spec §8; DECISIONS 2026-09-13)
#
# Fixes v1's permissiveness: span kinds match by intersection-over-union with a
# width penalty (not "any overlap"); omitted span bounds are MALFORMED, not a
# silent 0..∞; and ground truth is a LIST OF ALTERNATIVE SUFFICIENT SETS (credit
# any one fully; recall = best-matching set; precision = against the union). For
# metric_window, a GT ref tagged match="contain" is a diagnostically-sharp window
# (submitted must lie WITHIN it — rewards precise localization); an untagged /
# match="iou" ref is the full-run window (needs substantial IoU overlap). This
# split (measured, not invented — see scripts/measure_evidence_windows.py) stops
# v2 from rewarding a lazy full-run cite over a sharp one.
# ---------------------------------------------------------------------------

EVIDENCE_SCORER_V1 = "evidence_v1"
EVIDENCE_SCORER_V2 = "evidence_v2"
EVIDENCE_SCORER_V2_1 = "evidence_v2.1"
_IOU_THRESHOLD = 0.5      # min intersection-over-union for a span match
_WIDTH_FACTOR = 3.0       # a submitted span wider than N× the GT span never matches

# Required inclusive-integer bound fields per span kind (omitted → malformed).
_SPAN_BOUNDS = {
    "metric_window": ("start_epoch", "end_epoch"),
    "line_range": ("start_line", "end_line"),
    "code_span": ("start_line", "end_line"),
}


def _span_bounds(ref: dict):
    """(lo, hi) inclusive integer bounds for a span ref, or None if the required
    bounds are missing/invalid — v2 treats that as MALFORMED (no 0..∞ default)."""
    keys = _SPAN_BOUNDS.get(ref.get("kind"))
    if not keys:
        return None
    d = ref.get("detail", {}) or {}
    lo, hi = d.get(keys[0]), d.get(keys[1])
    if not isinstance(lo, int) or not isinstance(hi, int) or isinstance(lo, bool) or isinstance(hi, bool) or lo > hi:
        return None
    return lo, hi


def _iou(a, b) -> float:
    (alo, ahi), (blo, bhi) = a, b
    inter = max(0, min(ahi, bhi) - max(alo, blo) + 1)
    union = (ahi - alo + 1) + (bhi - blo + 1) - inter
    return inter / union if union > 0 else 0.0


def _is_malformed_v2(ref: dict) -> bool:
    """A submitted span ref missing its required bounds is malformed under v2."""
    return ref.get("kind") in _SPAN_BOUNDS and _span_bounds(ref) is None


def _match_ref_v2(sub: dict, hid: dict) -> bool:
    """Match a submitted ref against a hidden ref under v2 semantics."""
    if sub.get("kind") != hid.get("kind"):
        return False
    kind = sub["kind"]
    if kind == "config_key":
        return _match_evidence_ref(sub, hid)  # unchanged: fault-granular
    s, h = _span_bounds(sub), _span_bounds(hid)
    if s is None or h is None:
        return False  # malformed on either side → no match
    if sub.get("artifact_id") != hid.get("artifact_id"):
        return False
    if kind == "metric_window":
        if (sub.get("detail") or {}).get("series") != (hid.get("detail") or {}).get("series"):
            return False
        if (hid.get("detail") or {}).get("match") == "contain":
            return h[0] <= s[0] and s[1] <= h[1]   # sharp: submitted within anomaly
        return _iou(s, h) >= _IOU_THRESHOLD        # full-run: substantial overlap
    # line_range / code_span: IoU + width penalty (a traceback occupies a span).
    if _iou(s, h) < _IOU_THRESHOLD:
        return False
    return (s[1] - s[0] + 1) <= _WIDTH_FACTOR * (h[1] - h[0] + 1)


def _recall_against_set(submitted: list[dict], hidden_set: list[dict]) -> float:
    """Fraction of a hidden set's refs matched by some submitted ref (greedy)."""
    if not hidden_set:
        return 1.0
    matched_hidden, used = set(), set()
    for hi, h in enumerate(hidden_set):
        for si, s in enumerate(submitted):
            if si in used:
                continue
            if _match_ref_v2(s, h):
                matched_hidden.add(hi); used.add(si); break
    return len(matched_hidden) / len(hidden_set)


def compute_evidence_scores_v2(submitted_refs: list[dict], hidden_sets: list[list[dict]]) -> dict:
    """Evidence P/R/F1 under v2 against ALTERNATIVE sufficient sets.

    recall = best-matching set; precision = submitted refs matching the UNION of
    all sets / n_submitted; malformed submitted span refs are counted and count
    as false positives. Control (no non-empty set): F1=1.0 iff no refs submitted.
    """
    submitted = list(submitted_refs or [])
    malformed = sum(1 for r in submitted if _is_malformed_v2(r))
    non_empty = [st for st in (hidden_sets or []) if st]

    if not non_empty:  # control / no fault
        clean = len(submitted) == 0
        return {"precision": 1.0 if clean else 0.0, "recall": 1.0,
                "f1": 1.0 if clean else 0.0, "malformed_refs": malformed,
                "best_set_index": None, "scorer_version": EVIDENCE_SCORER_V2}

    recalls = [_recall_against_set(submitted, st) for st in hidden_sets]
    best = max(range(len(hidden_sets)), key=lambda i: recalls[i])
    recall = recalls[best]

    union: list[dict] = [h for st in hidden_sets for h in st]
    matched_sub = sum(1 for s in submitted if any(_match_ref_v2(s, h) for h in union))
    precision = matched_sub / len(submitted) if submitted else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "malformed_refs": malformed,
            "best_set_index": best, "scorer_version": EVIDENCE_SCORER_V2}


# ---------------------------------------------------------------------------
# Evidence v2.1 — one-to-one (bipartite) matching (STAGE3_PLAN §0.4)
# ---------------------------------------------------------------------------

def _edge_weight(sub: dict, hid: dict):
    """(edge_bool, weight) for a submitted×GT pair under the EXISTING v2 pair rule.

    weight = IoU for spans, 1.0 for a config_key match — used only as the tie-break after match COUNT.
    """
    if not _match_ref_v2(sub, hid):
        return False, 0.0
    if sub.get("kind") == "config_key":
        return True, 1.0
    s, h = _span_bounds(sub), _span_bounds(hid)
    return True, (_iou(s, h) if (s is not None and h is not None) else 1.0)


def _best_matching(submitted: list[dict], gt: list[dict]) -> tuple[int, float]:
    """Maximum-cardinality one-to-one matching (each submitted ref ↔ at most one GT ref and vice
    versa). Maximize match COUNT, break ties by total IoU, then deterministically by the smallest
    (gt_index, sub_index) assignment tuple — so the score cannot depend on submitted-ref order.

    GT sufficient sets in this benchmark are tiny (≤~3 refs), so an exact enumerator is used (no
    dependency; exact control over count→IoU→index that neither linear_sum_assignment nor
    Hopcroft-Karp gives directly). A guard raises for a pathologically large set.
    """
    if len(gt) > 6:
        raise ValueError(f"evidence v2.1 exact matcher: |GT|={len(gt)} too large; "
                         "use scipy.optimize.linear_sum_assignment for big sets")
    edges = []  # edges[j] = [(sub_index, iou), ...] for gt[j]
    for h in gt:
        row = []
        for i, s in enumerate(submitted):
            ok, w = _edge_weight(s, h)
            if ok:
                row.append((i, w))
        edges.append(row)

    best = {"count": -1, "iou": -1.0, "idxs": None}

    def rec(j, used, count, iou, idxs):
        if j == len(gt):
            better = (count > best["count"]
                      or (count == best["count"] and iou > best["iou"] + 1e-12)
                      or (count == best["count"] and abs(iou - best["iou"]) <= 1e-12
                          and (best["idxs"] is None or idxs < best["idxs"])))
            if better:
                best["count"], best["iou"], best["idxs"] = count, iou, idxs
            return
        rec(j + 1, used, count, iou, idxs + (-1,))              # leave gt[j] unmatched
        for i, w in edges[j]:                                    # or match to an unused submitted ref
            if i not in used:
                rec(j + 1, used | {i}, count + 1, iou + w, idxs + (i,))

    rec(0, frozenset(), 0, 0.0, ())
    return best["count"], best["iou"]


def compute_evidence_scores_v2_1(submitted_refs: list[dict], hidden_sets: list[list[dict]]) -> dict:
    """Evidence P/R/F1 under v2.1: ONE-TO-ONE matching against each alternative sufficient set, best F1.

    recall = matched / |GT of the best-matching set|. precision = matched / |submitted|, where the
    denominator is the FULL submission INCLUDING malformed refs (a malformed ref is a wasted citation,
    not a free one — a scoring decision). A submission covering multiple sets is matched against ONE
    set and pays precision for the rest (the anti-shotgun property). Control: F1=1.0 iff no refs.
    """
    submitted = list(submitted_refs or [])
    malformed = sum(1 for r in submitted if _is_malformed_v2(r))
    non_empty = [st for st in (hidden_sets or []) if st]
    if not non_empty:  # control / no fault
        clean = len(submitted) == 0
        return {"precision": 1.0 if clean else 0.0, "recall": 1.0, "f1": 1.0 if clean else 0.0,
                "malformed_refs": malformed, "best_set_index": None, "matched": 0,
                "scorer_version": EVIDENCE_SCORER_V2_1}

    best = None  # (f1, recall, set_index, precision, matched)
    for idx, st in enumerate(hidden_sets):
        if not st:
            continue
        matched, _iou = _best_matching(submitted, st)
        recall = matched / len(st)
        precision = matched / len(submitted) if submitted else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        cand = (round(f1, 9), round(recall, 9), -idx, precision, matched, idx)
        if best is None or cand[:3] > best[:3]:  # best F1, then recall, then lowest set index
            best = cand
    _f1, _r, _negidx, precision, matched, set_index = best
    recall = matched / len(hidden_sets[set_index])
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "malformed_refs": malformed, "best_set_index": set_index, "matched": matched,
            "scorer_version": EVIDENCE_SCORER_V2_1}


def _hidden_evidence_sets(hidden_card: dict, hidden_refs: list[dict]) -> list[list[dict]]:
    """Resolve alternative sufficient sets from the OPERATOR (single source of
    truth); fall back to a single set = the sealed evidence.yaml list."""
    import dataclasses
    try:
        from operators.registry import get_operator
        op = get_operator(hidden_card.get("operator_id", ""))
        if hasattr(op, "evidence_sets"):
            return [[dataclasses.asdict(e) for e in st] for st in op.evidence_sets()]
        return [[dataclasses.asdict(e) for e in op.evidence()]]
    except Exception:
        return [list(hidden_refs)] if hidden_refs else []


def _evidence_triple(submitted_refs, hidden_refs, hidden_card):
    """Return (v2_1, v2, v1): **v2.1 (bipartite one-to-one) is PRIMARY** (STAGE3_PLAN §0.4);
    v2 and v1 are retained beside it for audit/disclosure (v2's union rule over-credited
    duplicates/shotgun — corrected by v2.1; Sweep 1 was originally reported under v1)."""
    sets = _hidden_evidence_sets(hidden_card, hidden_refs)
    v1 = _compute_evidence_scores(submitted_refs, hidden_refs)
    v1["scorer_version"] = EVIDENCE_SCORER_V1
    v2 = compute_evidence_scores_v2(submitted_refs, sets)
    v2_1 = compute_evidence_scores_v2_1(submitted_refs, sets)
    return v2_1, v2, v1


# ---------------------------------------------------------------------------
# Individual axis scorers
# ---------------------------------------------------------------------------

def _diagnosis(submission: dict) -> dict:
    """The submission's diagnosis as a dict — missing / non-dict scores as EMPTY ({})."""
    diag = submission.get("diagnosis")
    return diag if isinstance(diag, dict) else {}


def _evidence_refs(submission: dict) -> list:
    """The submission's evidence refs — missing / null / non-list scores as EMPTY ([])."""
    refs = submission.get("evidence_refs")
    return refs if isinstance(refs, list) else []


def score_detection(submission: dict, hidden_card: dict) -> dict:
    """Axis 1: Did the agent detect an incident?

    Tier-aware: control-tier cases are healthy, so the correct ``detected`` is
    False; a control that the agent flags as faulty is a detection false
    positive.

    A missing (or null) ``detected`` scores as EMPTY: no answer, incorrect on
    every tier — like a non-submission, it is never a correct healthy call.
    """
    predicted = _diagnosis(submission).get("detected")
    actual = hidden_card.get("layer", "dynamics") != "control"

    result = {
        "detected_predicted": predicted,
        "detected_actual": actual,
        "correct": predicted is not None and predicted == actual,
    }
    if predicted is None:
        result["missing_field"] = True
    return result


def _score_no_unnecessary_repair(submission: dict | None) -> dict:
    """Control-tier 'recovery' axis: the correct action is NO repair.

    Correct iff no patches were submitted (repair_spec None, or repair_type
    'none', or empty patches).  A submitted repair is a false intervention.
    """
    repair = (submission or {}).get("repair_spec") if submission else None
    patches = repair.get("patches") if isinstance(repair, dict) else None
    submitted_repair = bool(patches)
    return {
        "verdict": "false_intervention" if submitted_repair else "no_unnecessary_repair",
        "no_unnecessary_repair": not submitted_repair,
        "false_intervention": submitted_repair,
        "compute_sec": 0.0,
        "per_seed_hidden_metrics": [],
    }


def score_identification(submission: dict, hidden_card: dict) -> dict:
    """Axis 2: Did the agent identify the correct operator class?

    Two-path match (method ``root_token_v2``), both normalised (lowercase,
    separators→``_``):

    1. EXACT path — normalized predicted ∈ the operator's ``accepted_classes``
       (authoritative; not subject to the v2 negation gate).
    2. TOKEN path — the label satisfies the target operator's principled
       ``core_tokens`` at whole-token/inflection granularity (never a free
       substring), is NOT an off-concept veto, does NOT negate the concept, AND
       the target is the UNIQUE operator it satisfies (a
       label naming two faults, e.g. ``lr_and_leakage``, matches two operators
       and is rejected; ``none`` on a faulty case matches only control and is
       rejected).

    Token spec + absent-when-clean semantics are resolved from the operator
    CODE at score time (single source of truth), so the result records
    ``method`` and ``token_spec_sha256`` for reproducibility.
    """
    from operators.registry import (
        core_token_specs,
        core_token_vetoes,
        token_spec_sha256,
    )

    predicted_class = _diagnosis(submission).get("operator_class")
    accepted = hidden_card.get("accepted_classes", [])
    operator_id = hidden_card.get("operator_id")
    if not isinstance(predicted_class, str) or not predicted_class.strip():
        # Missing / null / blank class scores as EMPTY: names no fault, never correct.
        return {
            "predicted_class": "",
            "accepted_classes": accepted,
            "method": IDENTIFICATION_METHOD,
            "token_spec_sha256": token_spec_sha256(),
            "matched_operators": [],
            "negated": False,
            "match_path": "none",
            "missing_field": True,
            "correct": False,
        }
    normalized_predicted = _normalize_class(predicted_class)
    tokens = normalized_predicted.split("_")

    result: dict = {
        "predicted_class": predicted_class,
        "accepted_classes": accepted,
        "method": IDENTIFICATION_METHOD,
        "token_spec_sha256": token_spec_sha256(),
    }

    # Path 1: exact membership (preserves oracle + hand-listed synonyms).
    normalized_accepted = {_normalize_class(c) for c in accepted}
    exact = normalized_predicted in normalized_accepted

    # Path 2: principled root-token match with single-CONCEPT uniqueness.
    # Uniqueness is over DISTINCT token specs (concepts), not operator ids: two
    # operators that ARE the same concept — e.g. data_leakage + data_leakage_neutral,
    # both core_tokens {leak} — must not defeat each other's identification, since a
    # label naming "leakage" correctly names the concept for either. Every existing
    # operator has a pairwise-distinct spec, so this is a NO-OP for them (frozen-sweep
    # delta = 0); it only lets concept-synonym operators coexist. A genuinely
    # ambiguous label (e.g. "lr_and_leakage") still matches two DIFFERENT specs and is
    # rejected. See docs/DECISIONS.md 2026-09-18.
    specs = core_token_specs()
    vetoes = core_token_vetoes()
    matched = _matched_operators(normalized_predicted, specs, vetoes)
    result["matched_operators"] = matched
    matched_specs = {tuple(tuple(g) for g in specs[m]) for m in matched}

    # v2 negation gate — applies to the TOKEN (generalization) path ONLY. A cue
    # that scopes THIS operator's concept makes a GENERALIZED label a
    # non-identification regardless of the concept tokens present (no_leakage,
    # not_inflated, leakage_absent). It never overrides the EXACT path: an
    # accepted_classes entry is an authoritative hand-declared answer, and some
    # faults are legitimately NAMED with a negation ("no_fault"/"no_incident" for
    # the control, "non_representative_evaluation" for metric inflation). Scoped to
    # the target operator so "missing_lr_schedule" (a missing safeguard = the
    # fault) is still credited. See docs/DECISIONS.md 2026-09-22.
    target_groups = specs.get(operator_id) or []
    concept_idx = _concept_indices(tokens, target_groups, normalized_accepted)
    negated = _negates_concept(tokens, concept_idx)
    result["negated"] = negated

    token_correct = (
        operator_id in matched and len(matched_specs) == 1 and not negated
    )

    if exact:
        result["match_path"] = "exact"
    elif token_correct:
        result["match_path"] = "token"
    else:
        result["match_path"] = "none"

    if not accepted:
        result["accepted_classes_missing"] = True

    result["correct"] = bool(exact or token_correct)
    return result


def score_evidence(
    submission_refs: list[dict],
    hidden_refs: list[dict],
) -> dict:
    """Axis 3: Precision/recall of submitted evidence refs."""
    return _compute_evidence_scores(submission_refs, hidden_refs)


def score_recovery(
    submission: dict,
    case_dir: Path,
    project_root: Path | None = None,
    trial_run_id: str | None = None,
) -> dict:
    """Axis 4: Recovery via verify_repair."""
    repair_spec = submission.get("repair_spec")    # missing → None → rejected (MALFORMED)
    result = verify_repair(
        case_dir, repair_spec, project_root, trial_run_id=trial_run_id,
    )
    return {
        "verdict": result["verdict"],
        "compute_sec": result["compute_spent_sec"],
        "per_seed_hidden_metrics": result["per_seed_hidden_metrics"],
    }


def score_safety(trial_record: dict) -> dict:
    """Secondary: count rejected/forbidden actions in transcript."""
    transcript = trial_record.get("tool_transcript", [])
    total_calls = len(transcript)
    rejected = 0
    forbidden = 0

    for entry in transcript:
        result = entry.get("result", {})
        if result.get("status") == "error":
            error_code = result.get("error", "")
            if error_code in ("PATH_TRAVERSAL", "INVALID_PATH", "TOOL_NOT_PERMITTED"):
                forbidden += 1
            else:
                rejected += 1

    return {
        "rejected_tool_calls": rejected,
        "forbidden_actions": forbidden,
        "total_calls": total_calls,
    }


# ---------------------------------------------------------------------------
# Diagnosis-only scoring (free axes — no training)
# ---------------------------------------------------------------------------

def score_diagnosis(trial_record: dict, case_dir: Path) -> dict:
    """Score the three free axes plus safety.  No recovery (no training).

    This is called inline by :func:`~harness.run_agent.run_trial` to score
    detection, identification, and evidence immediately after the agent
    finishes — these are pure comparisons against hidden ground truth with
    zero compute cost.

    Returns a scores dict with ``recovery: None`` (pending).
    """
    case_dir = Path(case_dir).resolve()
    hidden_dir = case_dir / "hidden"

    with open(hidden_dir / "card.hidden.yaml") as f:
        hidden_card = yaml.safe_load(f)
    with open(hidden_dir / "evidence.yaml") as f:
        hidden_refs = yaml.safe_load(f) or []

    tier = hidden_card.get("layer", "dynamics")
    is_control = tier == "control"
    # §5.1: carry band position onto the scored record so control FPR can be
    # stratified (in_band vs out-of-band). The STRATIFICATION KEY is the VISIBLE
    # band position, chosen on MECHANISM: a control false positive occurs when the
    # agent reads metric_visible_val_acc, compares it to the band it was given, and
    # flags the run — a visible-metric event end to end. The HIDDEN band position is
    # ground-truth model quality the agent never sees (no causal path to the
    # outcome), so it is carried alongside only as a case-quality label. (Both
    # metrics are equally platform-sensitive native-vs-emulated — see LIMITATIONS;
    # robustness is NOT the basis for this choice.) Absent (None) on pre-§5.1 cases.
    band_position = hidden_card.get("band_position_visible")
    band_position_hidden = hidden_card.get("band_position_hidden")
    submission = trial_record.get("submission")
    if submission is None:
        # No answer. A non-submission is never a correct healthy call, so
        # detection stays incorrect even on controls. No repair was submitted,
        # so the control recovery axis records no false intervention.
        return {
            "tier": tier,
            "band_position": band_position,                     # VISIBLE — the key (mechanism)
            "band_position_hidden": band_position_hidden,       # alongside: case-quality label
            "detection": {
                "detected_predicted": False,
                "detected_actual": not is_control,
                "correct": False,
            },
            "identification": {
                "predicted_class": "none",
                "accepted_classes": hidden_card.get("accepted_classes", []),
                "correct": False,
            },
            "evidence": {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                         "matched_pairs": [], "unmatched_submitted": [],
                         "unmatched_hidden": list(range(len(hidden_refs)))},
            "recovery": _score_no_unnecessary_repair(None) if is_control else None,
            "safety": score_safety(trial_record),
        }

    _ev21, _ev2, _ev1 = _evidence_triple(_evidence_refs(submission), hidden_refs, hidden_card)
    return {
        "tier": tier,
        "band_position": band_position,                     # VISIBLE — the key (mechanism)
        "band_position_hidden": band_position_hidden,       # alongside: case-quality label
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": _ev21,       # v2.1 (bipartite one-to-one) primary — STAGE3_PLAN §0.4
        "evidence_v2": _ev2,     # retained for audit (v2 over-credited duplicates/shotgun)
        "evidence_v1": _ev1,     # retained for audit (Sweep 1 was originally reported under v1)
        # Control 'recovery' is the free no_unnecessary_repair axis; faulty
        # tiers leave recovery pending (verify_repair runs later).
        "recovery": _score_no_unnecessary_repair(submission) if is_control else None,
        "safety": score_safety(trial_record),
    }


def score_recovery_standalone(
    record_path: Path,
    case_dir: Path,
    project_root: Path | None = None,
) -> dict:
    """Load a saved trial record, run verify_repair, merge verdict back.

    1. Load record from YAML.
    2. Extract ``submission.repair_spec``.
    3. Call :func:`verify_repair`.
    4. Merge recovery scores into ``record["scores"]["recovery"]``.
    5. Overwrite the record file.
    6. Update ``index.jsonl`` recovery_verdict.
    7. Return the updated record.
    """
    from harness.provenance import mark_card_superseded, update_index

    record_path = Path(record_path).resolve()
    case_dir = Path(case_dir).resolve()
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    with open(record_path) as f:
        record = yaml.safe_load(f)

    submission = record.get("submission")
    trial_run_id = record.get("run_id")
    if submission is None or "repair_spec" not in submission:
        recovery = {"verdict": "no_submission", "compute_sec": 0.0, "per_seed_hidden_metrics": []}
    else:
        recovery = score_recovery(
            submission, case_dir, project_root, trial_run_id=trial_run_id,
        )

    # Merge recovery into scores
    if record.get("scores") is None:
        record["scores"] = {}
    record["scores"]["recovery"] = recovery

    # Flag whether this trial was scored against a stale case build.
    mark_card_superseded(record, case_dir)

    # Overwrite the record file
    with open(record_path, "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False)

    # Update index.jsonl from full record state
    update_index(project_root, record)

    return record


# ---------------------------------------------------------------------------
# Trial-level scoring (all axes including recovery)
# ---------------------------------------------------------------------------

def score_trial(
    trial_record: dict,
    case_dir: Path,
    project_root: Path | None = None,
) -> dict:
    """Score one trial against hidden ground truth.

    Returns per-trial scores across all four axes plus safety.
    """
    case_dir = Path(case_dir).resolve()
    hidden_dir = case_dir / "hidden"

    with open(hidden_dir / "card.hidden.yaml") as f:
        hidden_card = yaml.safe_load(f)
    with open(hidden_dir / "evidence.yaml") as f:
        hidden_refs = yaml.safe_load(f) or []

    tier = hidden_card.get("layer", "dynamics")
    is_control = tier == "control"
    trusted = trial_record.get("trusted", False)
    submission = trial_record["submission"]
    if submission is None:
        return {
            "case_id": trial_record["case_id"],
            "agent_name": trial_record["agent_name"],
            "tier": tier,
            "trusted": trusted,
            "detection": {"detected_predicted": False, "detected_actual": not is_control, "correct": False},
            "identification": {"predicted_class": "none", "accepted_classes": hidden_card.get("accepted_classes", []), "correct": False},
            "evidence": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matched_pairs": [], "unmatched_submitted": [], "unmatched_hidden": list(range(len(hidden_refs)))},
            "recovery": _score_no_unnecessary_repair(None) if is_control else {"verdict": "no_submission", "compute_sec": 0.0, "per_seed_hidden_metrics": []},
            "safety": score_safety(trial_record),
        }

    # Controls never run verify_repair — their 'recovery' axis is the free
    # no_unnecessary_repair check; a submitted repair is a false intervention.
    recovery = (
        _score_no_unnecessary_repair(submission)
        if is_control
        else score_recovery(submission, case_dir, project_root)
    )
    _ev21, _ev2, _ev1 = _evidence_triple(_evidence_refs(submission), hidden_refs, hidden_card)
    return {
        "case_id": trial_record["case_id"],
        "agent_name": trial_record["agent_name"],
        "tier": tier,
        "trusted": trusted,
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": _ev21,       # v2.1 (bipartite one-to-one) primary — STAGE3_PLAN §0.4
        "evidence_v2": _ev2,     # retained for audit
        "evidence_v1": _ev1,     # retained for audit
        "recovery": recovery,
        "safety": score_safety(trial_record),
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_scores(trial_scores: list[dict]) -> dict:
    """Macro-average across trials.

    Trusted probe-agent trials (``trusted: true``) are EXCLUDED — they read
    hidden ground truth directly and are never contestants.  Recovery rate is
    computed over non-control trials only; control-tier behaviour is reported
    separately as a detection false-positive rate and a false-intervention rate.
    """
    n_total = len(trial_scores)
    scored = [s for s in trial_scores if not s.get("trusted", False)]
    n_excluded = n_total - len(scored)
    if n_excluded:
        print(
            f"[aggregate] excluded {n_excluded} trusted trial(s) from aggregation",
            file=sys.stderr,
        )

    n = len(scored)
    empty = {
        "detection_accuracy": 0.0,
        "identification_accuracy": 0.0,
        "evidence_mean_f1": 0.0,
        "recovery_rate": 0.0,
        "detection_false_positive_rate_on_controls": 0.0,
        "detection_false_positive_rate_on_controls_in_band": None,
        "detection_false_positive_rate_on_controls_out_of_band": None,
        "false_intervention_rate": 0.0,
        "mean_safety_violations": 0.0,
        "n_trials": 0,
        "n_controls": 0,
        "n_controls_in_band": 0,
        "n_controls_out_of_band": 0,
        "n_controls_unlabeled": 0,
        "n_excluded_trusted": n_excluded,
    }
    if n == 0:
        return empty

    faulty = [s for s in scored if s.get("tier", "dynamics") != "control"]
    controls = [s for s in scored if s.get("tier", "dynamics") == "control"]

    detection_correct = sum(1 for s in scored if s["detection"]["correct"])
    id_correct = sum(1 for s in scored if s["identification"]["correct"])
    evidence_f1s = [s["evidence"]["f1"] for s in scored]
    recovered = sum(
        1 for s in faulty if (s.get("recovery") or {}).get("verdict") == "recovered"
    )
    safety_violations = [
        s["safety"]["rejected_tool_calls"] + s["safety"]["forbidden_actions"]
        for s in scored
    ]
    fp_controls = sum(
        1 for s in controls if s["detection"]["detected_predicted"] is True
    )
    false_interventions = sum(
        1 for s in controls if (s.get("recovery") or {}).get("false_intervention") is True
    )

    # §5.1: stratify control FPR by VISIBLE band position (the key by mechanism;
    # `band_position` is the visible label — see score_diagnosis). A pooled control
    # FPR must never stand alone — the in-band / out-of-band split is where the
    # false-positive honesty lives (an out-of-band healthy run is the hard case).
    # Controls without a band label (pre-§5.1 builds) fall into `unlabeled` and
    # only the pooled rate is meaningful.
    def _fpr(subset):
        if not subset:
            return None
        fp = sum(1 for s in subset if s["detection"]["detected_predicted"] is True)
        return round(fp / len(subset), 4)

    ctrl_in = [s for s in controls if s.get("band_position") == "in_band"]
    ctrl_out = [s for s in controls
                if s.get("band_position") in ("below_band", "above_band")]
    ctrl_unlabeled = [s for s in controls if s.get("band_position") is None]

    return {
        "detection_accuracy": round(detection_correct / n, 4),
        "identification_accuracy": round(id_correct / n, 4),
        "evidence_mean_f1": round(sum(evidence_f1s) / n, 4),
        "recovery_rate": round(recovered / len(faulty), 4) if faulty else 0.0,
        "detection_false_positive_rate_on_controls": (
            round(fp_controls / len(controls), 4) if controls else 0.0
        ),
        # Stratified (None when that stratum is empty). Reported alongside the
        # pooled rate, never in place of it.
        "detection_false_positive_rate_on_controls_in_band": _fpr(ctrl_in),
        "detection_false_positive_rate_on_controls_out_of_band": _fpr(ctrl_out),
        "false_intervention_rate": (
            round(false_interventions / len(controls), 4) if controls else 0.0
        ),
        "mean_safety_violations": round(sum(safety_violations) / n, 4),
        "n_trials": n,
        "n_controls": len(controls),
        "n_controls_in_band": len(ctrl_in),
        "n_controls_out_of_band": len(ctrl_out),
        "n_controls_unlabeled": len(ctrl_unlabeled),
        "n_excluded_trusted": n_excluded,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score an agent trial against a case (spec §8)",
    )
    parser.add_argument(
        "--case", type=Path, required=True,
        help="Path to the case directory",
    )
    parser.add_argument(
        "--trial", type=Path, required=True,
        help="Path to the trial record YAML file",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: auto-detect)",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Run standalone recovery verification on a saved trial record",
    )
    args = parser.parse_args()

    if args.verify:
        record = score_recovery_standalone(
            args.trial, args.case, args.project_root,
        )
        print(yaml.dump(record["scores"]["recovery"],
                        default_flow_style=False, sort_keys=False))
        return 0

    with open(args.trial) as f:
        trial_record = yaml.safe_load(f)

    scores = score_trial(trial_record, args.case, args.project_root)
    print(yaml.dump(scores, default_flow_style=False, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
