"""Post-hoc re-scoring utilities (disclosed corrections; spec §8, DECISIONS.md).

Two corrections applied AFTER Sweep 1 results, both principle-based and
resolved from operator code (never string-chasing):

* ``identification`` — re-score the free axis with method ``root_token_v1``
  (root-token match + single-operator uniqueness).  The prior membership
  result is preserved as ``scores.identification_original`` and each new
  result records ``method`` + ``token_spec_sha256`` for reproducibility.

* ``recovery`` (shape unset) — re-verify trials whose repair was an
  unexpressible-but-correct ``null`` unset, now that the evaluator supports it.

Everything here is idempotent and touches only trial records + the index —
never HYPOTHESES, ground truth, or the operators.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from harness.scoring import score_identification, score_recovery_standalone


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _trial_records(project_root: Path):
    """Yield (record_path, record dict) for every stored trial."""
    for rp in sorted((project_root / "results").glob("*/trials/*.yaml")):
        with open(rp) as f:
            yield rp, yaml.safe_load(f)


def _hidden_card(project_root: Path, case_id: str) -> dict:
    p = project_root / "cases" / str(case_id) / "hidden" / "card.hidden.yaml"
    with open(p) as f:
        return yaml.safe_load(f)


def _is_sweep1_contestant(record: dict) -> bool:
    """A real Sweep-1 contestant trial (not a trusted probe / other sweep)."""
    if record.get("trusted"):
        return False
    return (record.get("conditions") or {}).get("sweep_name") == "sweep1"


# ---------------------------------------------------------------------------
# Identification re-score (root_token_v1)
# ---------------------------------------------------------------------------

def rescore_identification(project_root: Path | None = None) -> dict:
    """Re-score identification in place for every submitting trial.

    Preserves the original result as ``scores.identification_original`` (once),
    writes the new ``root_token_v2`` result, and refreshes the index line.
    Returns a summary {scanned, rescored, flipped_to_correct, flipped_to_wrong}.

    CAUTION — this reads the CURRENT ``cases/<cid>/hidden`` card, so it is valid
    ONLY while a case_id still maps to the operator it was scored under. For a
    FROZEN sweep whose case_ids may have been rebuilt to other operators, do NOT
    use this; attribute by the record's sealed ``accepted_classes`` instead (see
    ``scripts/audit_stage4_identification.py`` and
    ``harness.sweep_stats.operator_from_record``; DECISIONS 2026-09-22).
    """
    from harness.provenance import update_index

    project_root = Path(project_root).resolve() if project_root else _repo_root()
    scanned = rescored = flipped_true = flipped_false = 0

    for rp, record in _trial_records(project_root):
        scanned += 1
        submission = record.get("submission")
        if not submission or not (submission.get("diagnosis") or {}).get("operator_class"):
            continue  # no class submitted (e.g. max_turns) → nothing to re-score

        scores = record.setdefault("scores", {})
        old = scores.get("identification") or {}
        hidden_card = _hidden_card(project_root, record["case_id"])
        new = score_identification(submission, hidden_card)

        # Preserve the pre-correction result exactly once.
        if "identification_original" not in scores:
            scores["identification_original"] = old
        scores["identification"] = new
        rescored += 1

        was = bool(old.get("correct"))
        now = bool(new.get("correct"))
        if now and not was:
            flipped_true += 1
        elif was and not now:
            flipped_false += 1

        with open(rp, "w") as f:
            yaml.dump(record, f, default_flow_style=False, sort_keys=False)
        update_index(project_root, record)

    return {
        "scanned": scanned,
        "rescored": rescored,
        "flipped_to_correct": flipped_true,
        "flipped_to_wrong": flipped_false,
    }


# ---------------------------------------------------------------------------
# Shape recovery re-verify (unset) + repair split (amendment A)
# ---------------------------------------------------------------------------

def _patches(record: dict) -> dict | None:
    sub = record.get("submission") or {}
    spec = sub.get("repair_spec")
    if not isinstance(spec, dict):
        return None
    patches = spec.get("patches")
    return patches if isinstance(patches, dict) else None


def classify_shape_repairs(project_root: Path | None = None,
                           operator_id: str = "crash.shape_mismatch.v1") -> dict:
    """Split shape trials by the shape of their submitted repair.

    Categories (amendment A):
      recovered_value        — already recovered (e.g. input_dim=105).
      unexpressible_correct  — patches {model.input_dim: null}; correct-in-spirit
                               unset, re-verifiable now.
      no_repair              — no usable repair proposed (empty/malformed/other):
                               a genuine model failure that stands as not-recovered.
    """
    project_root = Path(project_root).resolve() if project_root else _repo_root()
    out = {"recovered_value": [], "unexpressible_correct": [], "no_repair": [], "other": []}
    key = "model.input_dim"

    for rp, record in _trial_records(project_root):
        if not _is_sweep1_contestant(record):
            continue
        hc = _hidden_card(project_root, record["case_id"])
        if hc.get("operator_id") != operator_id:
            continue
        verdict = ((record.get("scores") or {}).get("recovery") or {}).get("verdict")
        patches = _patches(record)
        rid = record.get("run_id")
        if verdict == "recovered":
            out["recovered_value"].append(rid)
        elif patches is not None and key in patches and patches[key] is None and len(patches) == 1:
            out["unexpressible_correct"].append((rid, str(rp)))
        elif not patches:
            out["no_repair"].append(rid)
        else:
            out["other"].append((rid, patches))
    return out


def reverify_unexpressible(project_root: Path | None = None,
                           operator_id: str = "crash.shape_mismatch.v1") -> dict:
    """Re-verify only the unexpressible-but-correct (null unset) shape trials.

    The 25 already-recovered and the genuine no-repair failures are left
    untouched — the split is reported by :func:`classify_shape_repairs`.
    """
    project_root = Path(project_root).resolve() if project_root else _repo_root()
    split = classify_shape_repairs(project_root, operator_id)
    results = {"reverified": 0, "now_recovered": 0, "still_rejected": 0, "run_ids": []}

    for rid, rp in split["unexpressible_correct"]:
        rp = Path(rp)
        case_id = yaml.safe_load(open(rp))["case_id"]
        case_dir = project_root / "cases" / case_id
        record = score_recovery_standalone(rp, case_dir, project_root)
        verdict = ((record.get("scores") or {}).get("recovery") or {}).get("verdict")
        results["reverified"] += 1
        results["run_ids"].append((rid, verdict))
        if verdict == "recovered":
            results["now_recovered"] += 1
        else:
            results["still_rejected"] += 1
    return results


# ---------------------------------------------------------------------------
# Correction #3 — recover MODEL-folded repair_spec (parser_fix_v1)
# ---------------------------------------------------------------------------

def _short(op):
    return {"silent.lr_warmup.v1": "lr_warmup", "silent.label_corruption.v1": "label_corruption",
            "silent.data_leakage.v1": "data_leakage", "crash.shape_mismatch.v1": "shape_mismatch",
            "control.healthy.v1": "control"}.get(op, op)


def _response_text(record: dict) -> str:
    return "\n".join((m.get("response_text") or "")
                     for m in (record.get("llm_transcript") or []))


def scan_folded_repairs(project_root: Path | None = None) -> dict:
    """Classify every sweep-1 submission by folded-repair status.

    Reports structured-vs-recovered rates and the folding rate, split by
    (operator, agent, anchor).  Read-only.
    """
    from harness.submission_repair import recover_folded_repair_spec

    project_root = Path(project_root).resolve() if project_root else _repo_root()
    from collections import Counter
    reasons = Counter()
    recovered_by = Counter()
    structured_by = Counter()
    resp_only = 0
    total = 0
    for _rp, rec in _trial_records(project_root):
        if not _is_sweep1_contestant(rec):
            continue
        total += 1
        sub = rec.get("submission") or {}
        fold = recover_folded_repair_spec(sub)
        reasons[fold.reason] += 1
        key = (_short(_hidden_card(project_root, rec["case_id"]).get("operator_id")),
               (rec.get("conditions") or {}).get("agent_type"),
               (rec.get("conditions") or {}).get("anchor"))
        if fold.reason == "already_structured":
            structured_by[key] += 1
        elif fold.reason == "recovered":
            recovered_by[key] += 1
        # repair mentioned only in reasoning text, not in the submit arguments
        if fold.reason in ("none",):
            rt = _response_text(rec)
            if ('name="repair_spec"' in rt) or ('"repair_type"' in rt):
                resp_only += 1
    return {"total": total, "reasons": dict(reasons),
            "recovered_by": {"/".join(map(str, k)): v for k, v in sorted(recovered_by.items())},
            "structured_by_total": sum(structured_by.values()),
            "response_text_only": resp_only}


def reparse_folded(project_root: Path | None = None) -> dict:
    """Recover folded repair_specs on stored records (method parser_fix_v1).

    For each sweep-1 record, run the strict extractor on the STORED structured
    submission.  On a clean single-object recovery, preserve submission_original
    (once), set the recovered repair_spec, and flag submission_parse_warning.
    Also flags (without changing repair_spec) ambiguous / unparseable folds.
    Returns counts.  Recovery does NOT bypass validation — recovered specs are
    re-verified via the normal evaluator path by reverify_recovered().
    """
    from harness.provenance import update_index
    from harness.submission_repair import recover_folded_repair_spec
    import copy

    project_root = Path(project_root).resolve() if project_root else _repo_root()
    out = {"recovered": 0, "flagged_only": 0, "recovered_run_ids": []}
    for rp, rec in _trial_records(project_root):
        if not _is_sweep1_contestant(rec):
            continue
        sub = rec.get("submission")
        if not isinstance(sub, dict):
            continue
        fold = recover_folded_repair_spec(sub)
        if not fold.warning:
            continue
        if "submission_original" not in rec:
            rec["submission_original"] = copy.deepcopy(sub)
        warn = {"folded": True, "recovered": fold.spec is not None,
                "reason": fold.reason, "method": "parser_fix_v1"}
        sub["submission_parse_warning"] = warn
        if fold.spec is not None:
            sub["repair_spec"] = fold.spec
            out["recovered"] += 1
            out["recovered_run_ids"].append(rec.get("run_id"))
        else:
            out["flagged_only"] += 1
        with open(rp, "w") as f:
            yaml.dump(rec, f, default_flow_style=False, sort_keys=False)
        update_index(project_root, rec)
    return out


def reverify_recovered(project_root: Path | None = None) -> dict:
    """Re-verify recovery (free) for records whose repair_spec was just recovered.

    Non-control records carrying a parser_fix_v1 recovery with a repair_spec.
    """
    project_root = Path(project_root).resolve() if project_root else _repo_root()
    out = {"reverified": 0, "now_recovered": 0, "rejected": 0, "results": []}
    for rp, rec in _trial_records(project_root):
        if not _is_sweep1_contestant(rec):
            continue
        warn = (rec.get("submission") or {}).get("submission_parse_warning") or {}
        if not (warn.get("method") == "parser_fix_v1" and warn.get("recovered")):
            continue
        if _hidden_card(project_root, rec["case_id"]).get("operator_id") == "control.healthy.v1":
            continue
        case_dir = project_root / "cases" / rec["case_id"]
        rec2 = score_recovery_standalone(rp, case_dir, project_root)
        verdict = ((rec2.get("scores") or {}).get("recovery") or {}).get("verdict")
        out["reverified"] += 1
        out["results"].append((rec.get("run_id"), _short(_hidden_card(project_root, rec["case_id"]).get("operator_id")), verdict))
        if verdict == "recovered":
            out["now_recovered"] += 1
        else:
            out["rejected"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc re-scoring (disclosed corrections)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("identification", "classify-shape", "reverify-shape",
                 "scan-folded", "reparse-folded", "reverify-recovered"):
        p = sub.add_parser(name)
        p.add_argument("--project-root", type=Path, default=None)
    args = ap.parse_args()

    if args.cmd == "identification":
        print(rescore_identification(args.project_root))
    elif args.cmd == "classify-shape":
        split = classify_shape_repairs(args.project_root)
        for k, v in split.items():
            print(f"{k}: {len(v)}")
    elif args.cmd == "reverify-shape":
        print(reverify_unexpressible(args.project_root))
    elif args.cmd == "scan-folded":
        import json as _json
        print(_json.dumps(scan_folded_repairs(args.project_root), indent=2))
    elif args.cmd == "reparse-folded":
        print(reparse_folded(args.project_root))
    elif args.cmd == "reverify-recovered":
        print(reverify_recovered(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Evidence re-score v1 → v2 (disclosed measurement change; DECISIONS 2026-09-13)
# ---------------------------------------------------------------------------

def _hidden_evidence_refs(project_root: Path, case_id: str) -> list:
    p = project_root / "cases" / str(case_id) / "hidden" / "evidence.yaml"
    if not p.exists():
        return []
    with open(p) as f:
        return yaml.safe_load(f) or []


def rescore_evidence_v2(project_root: Path | None = None, write: bool = False) -> dict:
    """Re-score every Sweep-1 contestant's evidence under v2, preserving v1.

    Returns a per-operator report: n, mean evidence F1 under v1 and v2, the delta,
    and — specifically — how many submitted metric_window refs changed match
    STATUS between v1 (any-overlap) and v2 (containment), so we can see whether
    the metric_window rule (not the span/IoU rule) drove the change. With
    ``write=True`` it also stores ``scores.evidence`` (v2, primary) +
    ``scores.evidence_v1`` (preserved) back into each record and updates the index.
    """
    from collections import defaultdict

    from harness.scoring import (
        EVIDENCE_SCORER_V1,
        _hidden_evidence_sets,
        _match_evidence_ref,
        _match_ref_v2,
        compute_evidence_scores_v2,
    )

    project_root = project_root or _repo_root()
    agg = defaultdict(lambda: {"n": 0, "f1_v1": 0.0, "f1_v2": 0.0,
                               "mw_refs": 0, "mw_v1_only": 0, "mw_v2_only": 0})
    for rp, rec in _trial_records(project_root):
        if not _is_sweep1_contestant(rec):
            continue
        scores = rec.get("scores") or {}
        ev = scores.get("evidence")
        if ev is None:
            continue
        case_id = rec["case_id"]
        if not (project_root / "cases" / str(case_id) / "hidden" / "card.hidden.yaml").exists():
            agg["_skipped_missing_case"]["n"] += 1
            continue
        hcard = _hidden_card(project_root, case_id)
        op = rec.get("_operator") or hcard.get("operator_id")
        submitted = ((rec.get("submission") or {}).get("evidence_refs")) or []
        sealed = _hidden_evidence_refs(project_root, case_id)
        sets = _hidden_evidence_sets(hcard, sealed)
        v2 = compute_evidence_scores_v2(submitted, sets)

        d = agg[op]
        d["n"] += 1
        d["f1_v1"] += ev.get("f1", 0.0)
        d["f1_v2"] += v2["f1"]

        # metric_window match-status flips, isolated from the span/IoU rule.
        gt_mw = [h for st in sets for h in st if h.get("kind") == "metric_window"]
        sealed_mw = [h for h in sealed if h.get("kind") == "metric_window"]
        for s in submitted:
            if s.get("kind") != "metric_window":
                continue
            d["mw_refs"] += 1
            v1m = any(_match_evidence_ref(s, h) for h in sealed_mw)
            v2m = any(_match_ref_v2(s, h) for h in gt_mw)
            if v1m and not v2m:
                d["mw_v1_only"] += 1
            elif v2m and not v1m:
                d["mw_v2_only"] += 1

        if write:
            from harness.provenance import update_index
            scores["evidence_v1"] = {**ev, "scorer_version": EVIDENCE_SCORER_V1}
            scores["evidence"] = v2
            rec["scores"] = scores
            with open(rp, "w") as f:
                yaml.safe_dump(rec, f, sort_keys=False)
            try:
                update_index(project_root, rec)
            except Exception:
                pass

    report = {}
    if agg.get("_skipped_missing_case", {}).get("n"):
        report["_skipped_missing_case"] = agg["_skipped_missing_case"]["n"]
    for op, d in sorted(agg.items()):
        if op.startswith("_"):
            continue
        n = d["n"] or 1
        report[op] = {
            "n": d["n"],
            "evidence_f1_v1": round(d["f1_v1"] / n, 4),
            "evidence_f1_v2": round(d["f1_v2"] / n, 4),
            "delta_v1_to_v2": round((d["f1_v2"] - d["f1_v1"]) / n, 4),
            "metric_window_refs": d["mw_refs"],
            "mw_matched_v1_only": d["mw_v1_only"],   # credited under v1, dropped by v2
            "mw_matched_v2_only": d["mw_v2_only"],   # newly credited by v2 (e.g. sharp cites)
        }
    return report
