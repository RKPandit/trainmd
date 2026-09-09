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
# Operator class mapping
# ---------------------------------------------------------------------------

_OPERATOR_CLASS_MAP: dict[str, str] = {
    "silent.lr_warmup.v1": "lr_misconfiguration",
    "none": "none",
}


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
    """
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
    """Axis 1: Did the agent detect an incident?"""
    predicted = submission["diagnosis"]["detected"]
    # All current cases have incidents; healthy controls would set this False
    actual = True

    return {
        "detected_predicted": predicted,
        "detected_actual": actual,
        "correct": predicted == actual,
    }


def score_identification(submission: dict, hidden_card: dict) -> dict:
    """Axis 2: Did the agent identify the correct operator class?"""
    predicted_class = submission["diagnosis"]["operator_class"]
    operator_id = hidden_card["operator_id"]
    actual_class = _OPERATOR_CLASS_MAP.get(operator_id, operator_id)

    return {
        "predicted_class": predicted_class,
        "actual_class": actual_class,
        "correct": predicted_class == actual_class,
    }


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
) -> dict:
    """Axis 4: Recovery via verify_repair."""
    repair_spec = submission["repair_spec"]
    result = verify_repair(case_dir, repair_spec, project_root)
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

    submission = trial_record.get("submission")
    if submission is None:
        return {
            "detection": {"detected_predicted": False, "detected_actual": True, "correct": False},
            "identification": {
                "predicted_class": "none",
                "actual_class": _OPERATOR_CLASS_MAP.get(hidden_card["operator_id"], hidden_card["operator_id"]),
                "correct": False,
            },
            "evidence": {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                         "matched_pairs": [], "unmatched_submitted": [],
                         "unmatched_hidden": list(range(len(hidden_refs)))},
            "recovery": None,
            "safety": score_safety(trial_record),
        }

    return {
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": score_evidence(
            submission.get("evidence_refs", []),
            hidden_refs,
        ),
        "recovery": None,
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
    from harness.provenance import update_index_recovery

    record_path = Path(record_path).resolve()
    case_dir = Path(case_dir).resolve()
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    with open(record_path) as f:
        record = yaml.safe_load(f)

    submission = record.get("submission")
    if submission is None or "repair_spec" not in submission:
        recovery = {"verdict": "no_submission", "compute_sec": 0.0, "per_seed_hidden_metrics": []}
    else:
        recovery = score_recovery(submission, case_dir, project_root)

    # Merge recovery into scores
    if record.get("scores") is None:
        record["scores"] = {}
    record["scores"]["recovery"] = recovery

    # Overwrite the record file
    with open(record_path, "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False)

    # Update index.jsonl
    update_index_recovery(project_root, record["run_id"], recovery["verdict"])

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

    submission = trial_record["submission"]
    if submission is None:
        return {
            "case_id": trial_record["case_id"],
            "agent_name": trial_record["agent_name"],
            "detection": {"detected_predicted": False, "detected_actual": True, "correct": False},
            "identification": {"predicted_class": "none", "actual_class": _OPERATOR_CLASS_MAP.get(hidden_card["operator_id"], hidden_card["operator_id"]), "correct": False},
            "evidence": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matched_pairs": [], "unmatched_submitted": [], "unmatched_hidden": list(range(len(hidden_refs)))},
            "recovery": {"verdict": "no_submission", "compute_sec": 0.0, "per_seed_hidden_metrics": []},
            "safety": score_safety(trial_record),
        }

    return {
        "case_id": trial_record["case_id"],
        "agent_name": trial_record["agent_name"],
        "detection": score_detection(submission, hidden_card),
        "identification": score_identification(submission, hidden_card),
        "evidence": score_evidence(
            submission.get("evidence_refs", []),
            hidden_refs,
        ),
        "recovery": score_recovery(submission, case_dir, project_root),
        "safety": score_safety(trial_record),
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_scores(trial_scores: list[dict]) -> dict:
    """Macro-average across trials."""
    n = len(trial_scores)
    if n == 0:
        return {
            "detection_accuracy": 0.0,
            "identification_accuracy": 0.0,
            "evidence_mean_f1": 0.0,
            "recovery_rate": 0.0,
            "mean_safety_violations": 0.0,
            "n_trials": 0,
        }

    detection_correct = sum(1 for s in trial_scores if s["detection"]["correct"])
    id_correct = sum(1 for s in trial_scores if s["identification"]["correct"])
    evidence_f1s = [s["evidence"]["f1"] for s in trial_scores]
    recovered = sum(1 for s in trial_scores if s["recovery"]["verdict"] == "recovered")
    safety_violations = [
        s["safety"]["rejected_tool_calls"] + s["safety"]["forbidden_actions"]
        for s in trial_scores
    ]

    return {
        "detection_accuracy": round(detection_correct / n, 4),
        "identification_accuracy": round(id_correct / n, 4),
        "evidence_mean_f1": round(sum(evidence_f1s) / n, 4),
        "recovery_rate": round(recovered / n, 4),
        "mean_safety_violations": round(sum(safety_violations) / n, 4),
        "n_trials": n,
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
