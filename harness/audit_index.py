"""Impossible-combination audit over trial records (spec §8).

A NAMED rule list, each with a rationale.  FAIL rules are logically impossible
combinations that indicate a scoring or pipeline bug; INFO rules are worth a
look.  Output: a table (rule | severity | count | sample trial ids | rationale)
→ ``docs/audits/index_<date>.md``.  Nonzero exit on any FAIL.

``assert_clean_for_aggregation`` refuses to aggregate over an index with FAIL
violations unless ``force=True`` — so a broken index cannot silently produce a
headline number.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import yaml

# Operators considered "easy" for the INFO recall-vs-identification heuristic.
_EASY_OPERATORS = {"silent.lr_warmup.v1"}


def _detected(rec: dict) -> bool | None:
    sub = rec.get("submission")
    if not sub:
        return None
    return sub.get("diagnosis", {}).get("detected")


def _evidence_refs(rec: dict) -> list:
    sub = rec.get("submission") or {}
    return sub.get("evidence_refs") or []


def _patches(rec: dict) -> dict:
    sub = rec.get("submission") or {}
    repair = sub.get("repair_spec")
    return (repair or {}).get("patches") or {} if isinstance(repair, dict) else {}


def _scores(rec: dict) -> dict:
    return rec.get("scores") or {}


def _recovery(rec: dict) -> dict:
    return _scores(rec).get("recovery") or {}


# ---- Rule predicates (return True when the rule is VIOLATED) ---------------

def _r1(rec):  # recovered but not detected
    return _recovery(rec).get("verdict") == "recovered" and _detected(rec) is False


def _r2(rec):  # no_submission with a non-null scored axis
    if rec.get("submission") is not None:
        return False
    s = _scores(rec)
    det = (s.get("detection") or {}).get("correct")
    idc = (s.get("identification") or {}).get("correct")
    evf1 = (s.get("evidence") or {}).get("f1") or 0.0
    return det is True or idc is True or evf1 > 0.0


def _r3(rec):  # crash recovered but a repaired rerun did not complete
    if _recovery(rec).get("verdict") != "recovered":
        return False
    if rec.get("scores", {}).get("_tier") == "control":
        return False
    per_seed = _recovery(rec).get("per_seed_hidden_metrics") or []
    return any(s.get("exitcode", 0) != 0 for s in per_seed)


def _r4(rec):  # control: patches submitted but flagged no_unnecessary_repair
    r = _recovery(rec)
    return bool(_patches(rec)) and r.get("no_unnecessary_repair") is True


def _r5(rec):  # detected false but evidence refs non-empty
    return _detected(rec) is False and len(_evidence_refs(rec)) > 0


def _r6(rec):  # identification correct but detected false (INFO)
    return (_scores(rec).get("identification") or {}).get("correct") is True and _detected(rec) is False


def _r7(rec):  # completed LLM trial with zero input tokens
    if rec.get("status") != "completed":
        return False
    if not (rec.get("model") or {}).get("model_id"):
        return False
    return (rec.get("usage") or {}).get("input_tokens", 0) == 0


def _r8(rec):  # estimated cost inconsistent with tokens x price (when priced)
    usage = rec.get("usage") or {}
    cost = usage.get("estimated_cost_usd")
    if cost is None or usage.get("cost_is_estimate") is not False:
        return False
    try:
        from harness.pricing import estimate_cost
        est = estimate_cost(
            (rec.get("model") or {}).get("model_id"),
            usage.get("input_tokens", 0), usage.get("output_tokens", 0),
            usage.get("cached_tokens", 0),
        )
    except Exception:
        return False
    if est is None or est.cost_usd == 0:
        return False
    return abs(cost - est.cost_usd) / est.cost_usd > 0.01


def _r9(rec):  # superseded trial (INFO)
    return rec.get("card_superseded") is True


def _r10(rec):  # recall 1.0 but identification wrong on an easy op (INFO)
    s = _scores(rec)
    recall = (s.get("evidence") or {}).get("recall") or 0.0
    idc = (s.get("identification") or {}).get("correct")
    return recall == 1.0 and idc is False and rec.get("_operator") in _EASY_OPERATORS


@dataclass
class Rule:
    name: str
    severity: str  # FAIL | INFO
    fn: Callable[[dict], bool]
    rationale: str


RULES = [
    Rule("R1_recovered_not_detected", "FAIL", _r1, "fixed it without noticing an incident"),
    Rule("R2_no_submission_scored", "FAIL", _r2, "no submission but an axis was scored correct/non-zero"),
    Rule("R3_crash_recovered_incomplete", "FAIL", _r3, "recovery=recovered but a repaired rerun did not complete"),
    Rule("R4_control_patch_no_intervention", "FAIL", _r4, "control has patches yet no_unnecessary_repair=true"),
    Rule("R5_not_detected_with_evidence", "FAIL", _r5, "detected=false but evidence refs were submitted"),
    Rule("R6_identified_not_detected", "INFO", _r6, "named a fault class but said detected=false"),
    Rule("R7_completed_zero_input_tokens", "FAIL", _r7, "completed LLM trial with input_tokens=0"),
    Rule("R8_cost_price_mismatch", "FAIL", _r8, "estimated_cost != tokens x price within 1%"),
    Rule("R9_superseded_in_results", "INFO", _r9, "trial scored against a superseded build"),
    Rule("R10_recall_full_id_wrong_easy", "INFO", _r10, "full recall but wrong class on an easy operator"),
]


def _load_records(project_root: Path) -> list[dict]:
    records = []
    results = project_root / "results"
    if not results.exists():
        return records
    for tp in sorted(results.glob("*/trials/*.yaml")):
        rec = yaml.safe_load(tp.read_text())
        if not isinstance(rec, dict):
            continue
        # Enrich with tier/operator from the case's hidden card (best-effort).
        cid = rec.get("case_id")
        hc = project_root / "cases" / str(cid) / "hidden" / "card.hidden.yaml"
        if hc.exists():
            card = yaml.safe_load(hc.read_text()) or {}
            rec.setdefault("scores", {})["_tier"] = card.get("layer")
            rec["_operator"] = card.get("operator_id")
        rec["_trial_id"] = rec.get("run_id", tp.stem)
        records.append(rec)
    return records


def run_audit(project_root: Path) -> tuple[list[dict], int]:
    """Return (rows, fail_count).  One row per rule with count + sample ids."""
    records = _load_records(project_root)
    rows = []
    fail_count = 0
    for rule in RULES:
        hits = [r["_trial_id"] for r in records if rule.fn(r)]
        if rule.severity == "FAIL":
            fail_count += len(hits)
        rows.append({
            "rule": rule.name, "severity": rule.severity, "count": len(hits),
            "samples": hits[:3], "rationale": rule.rationale,
        })
    return rows, fail_count


def write_table(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_fail = sum(r["count"] for r in rows if r["severity"] == "FAIL")
    lines = [
        f"# Impossible-combination audit — {date.today().isoformat()}",
        "",
        f"**{total_fail} FAIL violation(s).**",
        "",
        "| rule | severity | count | sample trial ids | rationale |",
        "|------|----------|-------|------------------|-----------|",
    ]
    for r in rows:
        samples = ", ".join(r["samples"]) if r["samples"] else "—"
        lines.append(
            f"| {r['rule']} | {r['severity']} | {r['count']} | {samples} | {r['rationale']} |"
        )
    out_path.write_text("\n".join(lines) + "\n")


def assert_clean_for_aggregation(project_root: Path, force: bool = False) -> None:
    """Refuse to aggregate over an index with FAIL violations unless *force*."""
    _, fail_count = run_audit(project_root)
    if fail_count and not force:
        raise RuntimeError(
            f"audit-index found {fail_count} FAIL violation(s); refusing to aggregate. "
            f"Run `make audit-index`, fix them, or pass force=True."
        )
    if fail_count:
        print(
            f"[audit] WARNING: aggregating over {fail_count} FAIL violation(s) (force=True)",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Impossible-combination audit (spec §8)")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args()
    project_root = args.project_root or Path(__file__).resolve().parent.parent

    rows, fail_count = run_audit(project_root)
    out = project_root / "docs" / "audits" / f"index_{date.today().strftime('%Y%m%d')}.md"
    write_table(rows, out)
    print(out.read_text())
    print(f"\n{fail_count} FAIL violation(s). Audit: {out}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
