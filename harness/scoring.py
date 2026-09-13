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
# Root-token identification (method "root_token_v1")
# ---------------------------------------------------------------------------

IDENTIFICATION_METHOD = "root_token_v1"

# Stems this length or shorter match a WHOLE token only (guards against
# substring bleed, e.g. "lr"/"dim"); longer stems match as a substring so
# "leak"⊂"leakage" and "nois"⊂"noisy".
_SHORT_STEM_MAX_LEN = 3


def _stem_matches(stem: str, tokens: set[str], normalized_full: str) -> bool:
    if len(stem) <= _SHORT_STEM_MAX_LEN:
        return stem in tokens
    return stem in normalized_full


def _operator_matches(normalized_pred: str, groups: list) -> bool:
    """A normalized label satisfies an operator iff EVERY group matches
    (AND across groups); a group matches if ANY stem matches (OR within)."""
    tokens = set(normalized_pred.split("_"))
    return all(
        any(_stem_matches(stem, tokens, normalized_pred) for stem in group)
        for group in groups
    )


def _matched_operators(normalized_pred: str, specs: dict) -> list[str]:
    """Every operator whose core-token spec the label satisfies."""
    return sorted(
        op_id for op_id, groups in specs.items()
        if groups and _operator_matches(normalized_pred, groups)
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
# Individual axis scorers
# ---------------------------------------------------------------------------

def score_detection(submission: dict, hidden_card: dict) -> dict:
    """Axis 1: Did the agent detect an incident?

    Tier-aware: control-tier cases are healthy, so the correct ``detected`` is
    False; a control that the agent flags as faulty is a detection false
    positive.
    """
    predicted = submission["diagnosis"]["detected"]
    actual = hidden_card.get("layer", "dynamics") != "control"

    return {
        "detected_predicted": predicted,
        "detected_actual": actual,
        "correct": predicted == actual,
    }


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

    Two-path match (method ``root_token_v1``), both normalised (lowercase,
    separators→``_``):

    1. EXACT path — normalized predicted ∈ the operator's ``accepted_classes``.
    2. TOKEN path — the label satisfies the target operator's principled
       ``core_tokens`` AND the target is the UNIQUE operator it satisfies (a
       label naming two faults, e.g. ``lr_and_leakage``, matches two operators
       and is rejected; ``none`` on a faulty case matches only control and is
       rejected).

    Token spec + absent-when-clean semantics are resolved from the operator
    CODE at score time (single source of truth), so the result records
    ``method`` and ``token_spec_sha256`` for reproducibility.
    """
    from operators.registry import core_token_specs, token_spec_sha256

    predicted_class = submission["diagnosis"]["operator_class"]
    accepted = hidden_card.get("accepted_classes", [])
    operator_id = hidden_card.get("operator_id")
    normalized_predicted = _normalize_class(predicted_class)

    result: dict = {
        "predicted_class": predicted_class,
        "accepted_classes": accepted,
        "method": IDENTIFICATION_METHOD,
        "token_spec_sha256": token_spec_sha256(),
    }

    # Path 1: exact membership (preserves oracle + hand-listed synonyms).
    normalized_accepted = {_normalize_class(c) for c in accepted}
    exact = normalized_predicted in normalized_accepted

    # Path 2: principled root-token match with single-operator uniqueness.
    specs = core_token_specs()
    matched = _matched_operators(normalized_predicted, specs)
    result["matched_operators"] = matched
    token_correct = (
        operator_id in matched and len(matched) == 1
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
    repair_spec = submission["repair_spec"]
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
    submission = trial_record.get("submission")
    if submission is None:
        # No answer. A non-submission is never a correct healthy call, so
        # detection stays incorrect even on controls. No repair was submitted,
        # so the control recovery axis records no false intervention.
        return {
            "tier": tier,
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

    return {
        "tier": tier,
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": score_evidence(
            submission.get("evidence_refs", []),
            hidden_refs,
        ),
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
    return {
        "case_id": trial_record["case_id"],
        "agent_name": trial_record["agent_name"],
        "tier": tier,
        "trusted": trusted,
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": score_evidence(
            submission.get("evidence_refs", []),
            hidden_refs,
        ),
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
        "false_intervention_rate": 0.0,
        "mean_safety_violations": 0.0,
        "n_trials": 0,
        "n_controls": 0,
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

    return {
        "detection_accuracy": round(detection_correct / n, 4),
        "identification_accuracy": round(id_correct / n, 4),
        "evidence_mean_f1": round(sum(evidence_f1s) / n, 4),
        "recovery_rate": round(recovered / len(faulty), 4) if faulty else 0.0,
        "detection_false_positive_rate_on_controls": (
            round(fp_controls / len(controls), 4) if controls else 0.0
        ),
        "false_intervention_rate": (
            round(false_interventions / len(controls), 4) if controls else 0.0
        ),
        "mean_safety_violations": round(sum(safety_violations) / n, 4),
        "n_trials": n,
        "n_controls": len(controls),
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
