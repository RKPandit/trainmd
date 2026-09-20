"""Known-answer gate (spec §7, §8) — the pre-sweep centerpiece.

Runs three probe agents over EVERY built case and asserts what MUST be true if
ground truth is correct:

- ORACLE (exact hidden answer): detection ✓, identification ✓, evidence F1 == 1.0,
  and (full mode) recovery == recovered / no_unnecessary_repair.  Any oracle
  deviation means ground truth is wrong for that case — the table names it.
- DEGENERATE (oracle repair, wrong class, no evidence): oracle strictly
  out-scores it on identification and evidence (non-control); on control it is a
  false intervention.
- ALWAYS-BROKEN (untrusted knob-scanner): no evidence anywhere; on controls it
  is a detection false positive (FPR == 1.0).

Output: a table (case | operator | tier | agent | axis | expected | actual |
status | reason) → ``docs/audits/known_answer_<date>.md``.  Exits nonzero on any
FAIL.  ``--fast`` skips recovery reruns; ``--full`` includes them.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from agents.always_broken_agent import _broken_patches
from harness.build_case import _OPERATOR_REGISTRY
from harness.scoring import (
    _score_no_unnecessary_repair,
    score_diagnosis,
    score_recovery,
)


def _oracle_submission(operator_id: str, verify: dict) -> dict:
    """The exactly-correct submission, derived from the OPERATOR (canonical
    source) for evidence + class so drift in the built hidden files surfaces,
    and from the verify FILE for the repair so a corrupted oracle_repair is
    caught by the recovery axis."""
    op = _OPERATOR_REGISTRY[operator_id]()
    accepted = sorted(op.accepted_classes())
    return {
        "diagnosis": {
            "detected": op.layer != "control",
            "operator_class": accepted[0] if accepted else "none",
        },
        "evidence_refs": [dataclasses.asdict(e) for e in op.evidence()],
        "repair_spec": verify.get("oracle_repair"),
    }


@dataclass
class Row:
    case: str
    operator: str
    tier: str
    agent: str
    axis: str
    expected: str
    actual: str
    status: str  # PASS | FAIL
    reason: str


def _diag(submission: dict, case_dir: Path) -> dict:
    return score_diagnosis({"submission": submission, "tool_transcript": []}, case_dir)


def _degenerate_submission(verify: dict) -> dict:
    oracle = verify.get("oracle_repair")
    repair = oracle if oracle is not None else {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}
    return {
        "diagnosis": {"detected": True, "operator_class": "unrelated_fault"},
        "evidence_refs": [],
        "repair_spec": repair,
    }


def _always_broken_submission(case_dir: Path) -> dict:
    resolved = case_dir / "workspace" / "run_output" / "config.resolved.yaml"
    config = yaml.safe_load(resolved.read_text()) if resolved.exists() else {}
    if not isinstance(config, dict):
        config = {}
    patches = _broken_patches(config)
    repair = {"repair_type": "config_patch", "patches": patches} if patches else {"repair_type": "none", "patches": {}}
    return {
        "diagnosis": {"detected": True, "operator_class": "misconfiguration"},
        "evidence_refs": [],
        "repair_spec": repair,
    }


def _recovery_verdict(submission: dict, tier: str, case_dir: Path, project_root: Path, fast: bool) -> str:
    if tier == "control":
        return _score_no_unnecessary_repair(submission)["verdict"]
    if fast:
        return "skipped(fast)"
    return score_recovery(submission, case_dir, project_root)["verdict"]


def _case_meta(case_dir: Path) -> tuple[str, str, str]:
    """(operator_id, strength, tier) for a built case."""
    hc = yaml.safe_load((case_dir / "hidden" / "card.hidden.yaml").read_text())
    return (hc.get("operator_id", "?"), str(hc.get("strength")), hc.get("layer", "dynamics"))


def subset_by_operator_strength(cases: list[tuple[str, str, str]],
                                expected_pairs: set | None = None):
    """Pick ONE case per (operator, strength) + assert design coverage. Pure/testable.

    cases: list of (case_name, operator, strength) for the BUILT cases. Returns
    (selected_names: set, coverage_ok: bool, info: dict). The representative is the
    smallest case_name in each (operator, strength) group. coverage_ok is True iff
    the selected groups cover every (operator, strength) in *expected_pairs* (the
    committed design); a group missing from the build → coverage FAILS. If
    expected_pairs is None it defaults to the pairs present in *cases* (self-check).
    """
    chosen: dict[tuple[str, str], str] = {}
    for name, op, st in sorted(cases):
        chosen.setdefault((op, st), name)
    sel_names = set(chosen.values())
    present_pairs = set(chosen)
    if expected_pairs is None:
        expected_pairs = present_pairs
    expected_pairs = set(expected_pairs)
    missing = expected_pairs - present_pairs
    ok = not missing
    return sel_names, ok, {
        "n_selected": len(sel_names),
        "expected_groups": len(expected_pairs),
        "covered_groups": len(present_pairs & expected_pairs),
        "operators": sorted({op for (op, _st) in expected_pairs}),
        "strengths": sorted({st for (_op, st) in expected_pairs}),
        "missing": sorted(missing),
    }


def run_gate(project_root: Path, fast: bool = True, subset: bool = False) -> list[Row]:
    """Run the gate over every case (or a representative subset); return rows.

    subset=True gates ONE case per (operator, strength) — the smallest case id in
    each group — and appends a coverage row that FAILS unless the selected cases
    cover every operator AND every strength present in the built design. This is
    the certification gate: it exercises each operator at each rung without the
    full ~324-retrain cost, while a coverage guard forbids silently dropping one.
    """
    project_root = Path(project_root).resolve()
    cases_dir = project_root / "cases"
    rows: list[Row] = []

    all_dirs = [cd for cd in sorted(cases_dir.iterdir())
                if cd.is_dir() and cd.name.startswith("case_")]
    meta = {cd: _case_meta(cd) for cd in all_dirs}
    if subset:
        from scripts.build_all_cases import case_design_tuples
        expected_pairs = {(op, st) for op, st, _sd in case_design_tuples()}
        sel_names, cov_ok, cov_info = subset_by_operator_strength(
            [(cd.name, meta[cd][0], meta[cd][1]) for cd in all_dirs], expected_pairs)
        selected = [cd for cd in all_dirs if cd.name in sel_names]
    else:
        selected = all_dirs

    for case_dir in selected:
        hidden = case_dir / "hidden"
        hc = yaml.safe_load((hidden / "card.hidden.yaml").read_text())
        verify = yaml.safe_load((hidden / "verify.yaml").read_text())
        tier = hc.get("layer", "dynamics")
        operator = hc.get("operator_id", "?")
        cid = case_dir.name

        def row(agent, axis, expected, actual, ok, reason=""):
            rows.append(Row(cid, operator, tier, agent, axis, str(expected),
                            str(actual), "PASS" if ok else "FAIL", reason))

        # ---- ORACLE (must be exactly correct) ----------------------------
        osub = _oracle_submission(operator, verify)
        od = _diag(osub, case_dir)
        row("oracle", "detection", True, od["detection"]["correct"],
            od["detection"]["correct"], "oracle must detect per tier")
        row("oracle", "identification", True, od["identification"]["correct"],
            od["identification"]["correct"], "oracle class must be accepted")
        row("oracle", "evidence_f1", 1.0, od["evidence"]["f1"],
            od["evidence"]["f1"] == 1.0, "oracle cites exactly the hidden refs")
        exp_recov = "no_unnecessary_repair" if tier == "control" else "recovered"
        actual_recov = _recovery_verdict(osub, tier, case_dir, project_root, fast)
        recov_ok = actual_recov == exp_recov or actual_recov == "skipped(fast)"
        row("oracle", "recovery", exp_recov, actual_recov, recov_ok,
            "oracle repair must restore reference" if tier != "control" else
            "oracle submits no repair on a control")

        # ---- DEGENERATE (discrimination probe) ---------------------------
        dsub = _degenerate_submission(verify)
        dd = _diag(dsub, case_dir)
        if tier == "control":
            fi = dd["recovery"]["false_intervention"]
            row("degenerate", "false_intervention", True, fi, fi is True,
                "a repair on a healthy run is a false intervention")
        else:
            id_disc = od["identification"]["correct"] and not dd["identification"]["correct"]
            row("degenerate", "identification_discrimination",
                "oracle>degenerate", f"oracle={od['identification']['correct']},deg={dd['identification']['correct']}",
                id_disc, "oracle must out-identify the degenerate")
            ev_disc = od["evidence"]["f1"] > dd["evidence"]["f1"]
            row("degenerate", "evidence_discrimination",
                "oracle>degenerate", f"oracle={od['evidence']['f1']},deg={dd['evidence']['f1']}",
                ev_disc, "oracle must out-evidence the degenerate")

        # ---- ALWAYS-BROKEN (untrusted baseline) --------------------------
        absub = _always_broken_submission(case_dir)
        abd = _diag(absub, case_dir)
        if tier == "control":
            fp = abd["detection"]["detected_predicted"] is True and abd["detection"]["correct"] is False
            row("always_broken", "detection_false_positive", True, fp, fp,
                "controls must catch an always-detect agent")
            # false_intervention reported, NOT asserted (absent-when-clean → no knob to patch)
            row("always_broken", "false_intervention_report", "info",
                abd["recovery"]["false_intervention"], True,
                "INFO: no non-default knob on a clean control")
        else:
            ev0 = abd["evidence"]["f1"] == 0.0
            row("always_broken", "evidence_zero", 0.0, abd["evidence"]["f1"], ev0,
                "always-broken cites no evidence")

    if subset:
        rows.append(Row(
            "SUBSET", "-", "-", "gate", "coverage",
            f"{cov_info['expected_groups']} design groups "
            f"(ops={len(cov_info['operators'])} strengths={cov_info['strengths']})",
            f"{cov_info['n_selected']} cases; covered={cov_info['covered_groups']}"
            + (f"; MISSING={cov_info['missing']}" if cov_info['missing'] else ""),
            "PASS" if cov_ok else "FAIL",
            "one case per (operator,strength) must cover every (operator,strength) in the design",
        ))

    return rows


def write_table(rows: list[Row], out_path: Path, fast: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_fail = sum(1 for r in rows if r.status == "FAIL")
    lines = [
        f"# Known-answer gate — {date.today().isoformat()} ({'fast' if fast else 'full'} mode)",
        "",
        f"{len(rows)} checks, **{n_fail} FAIL**.",
        "",
        "| case | operator | tier | agent | axis | expected | actual | status | reason |",
        "|------|----------|------|-------|------|----------|--------|--------|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r.case} | {r.operator} | {r.tier} | {r.agent} | {r.axis} | "
            f"{r.expected} | {r.actual} | {r.status} | {r.reason} |"
        )
    out_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Known-answer gate (spec §7, §8)")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--full", action="store_true", help="Include recovery reruns")
    parser.add_argument("--fast", action="store_true", help="Skip recovery reruns (default)")
    parser.add_argument("--subset", action="store_true",
                        help="Gate one case per (operator,strength) + assert coverage "
                             "(certification subset; ~15 cases vs all 128)")
    args = parser.parse_args()

    project_root = args.project_root or Path(__file__).resolve().parent.parent
    fast = not args.full  # fast is the default

    rows = run_gate(project_root, fast=fast, subset=args.subset)
    out = project_root / "docs" / "audits" / f"known_answer_{date.today().strftime('%Y%m%d')}.md"
    write_table(rows, out, fast)

    n_fail = sum(1 for r in rows if r.status == "FAIL")
    # Print the table to stdout too.
    print(out.read_text())
    print(f"\n{len(rows)} checks, {n_fail} FAIL. Audit: {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
