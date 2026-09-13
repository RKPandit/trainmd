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
    writes the new ``root_token_v1`` result, and refreshes the index line.
    Returns a summary {scanned, rescored, flipped_to_correct, flipped_to_wrong}.
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc re-scoring (disclosed corrections)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("identification", "classify-shape", "reverify-shape"):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
