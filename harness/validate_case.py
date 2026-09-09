"""Case/artifact validator (spec §5, §7).

Automated structural and consistency checks on built cases, organized into
three categories:

- **WALL** — information-isolation invariants (W1–W3)
- **CONSISTENCY** — cross-file agreement (C1–C8)
- **WELL_FORMEDNESS** — schema completeness (F1–F3)

Usage::

    python -m harness.validate_case --case cases/case_0001
    python -m harness.validate_case --all
    python -m harness.validate_case --all --deep
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class CheckResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    detail: str       # human-readable explanation (empty on pass)
    category: str     # "WALL", "CONSISTENCY", "WELL_FORMEDNESS"


@dataclasses.dataclass
class ValidationReport:
    """Aggregated results for one case."""
    case_id: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        n = len(self.checks)
        n_pass = sum(1 for c in self.checks if c.passed)
        if self.passed:
            return f"{self.case_id}: {n_pass}/{n} passed"
        failed_names = ", ".join(c.name for c in self.failed)
        return f"{self.case_id}: {n_pass}/{n} passed, FAILED: {failed_names}"


# ---------------------------------------------------------------------------
# Forbidden token lists (mirrors tests/test_workspace_isolation.py)
# ---------------------------------------------------------------------------

_BASE_FORBIDDEN_TOKENS = [
    "test_acc", "test_loss", "X_test", "y_test",
    "hidden_test", "hidden_data", "holdout",
]

_CASE_FORBIDDEN_TOKENS = _BASE_FORBIDDEN_TOKENS + [
    "operator_id", "card.hidden", "evidence.yaml", "verify.yaml",
    "tolerance_lower", "recovery_oracle",
]

_PUBLIC_CARD_FORBIDDEN_TOKENS = [
    "lr_warmup", "silent", "dynamics", "operator", "mutation",
    "manifest", "incident", "strength", "severe", "moderate", "mild",
]

_BINARY_EXTENSIONS = frozenset({".pt", ".npy", ".npz"})

_REFERENCE_SEEDS = set(range(10))  # [0..9]

_REQUIRED_FILES = [
    "card.public.yaml",
    "hidden/card.hidden.yaml",
    "hidden/evidence.yaml",
    "hidden/verify.yaml",
    "workspace/train.py",
    "workspace/config.yaml",
    "workspace/run_output/metrics.jsonl",
    "workspace/run_output/logs/stdout.log",
    "workspace/run_output/config.resolved.yaml",
    "workspace/run_output/exitcode",
    "workspace/run_output/checkpoints/ckpt_final.pt",
]

_HIDDEN_CARD_REQUIRED_FIELDS = [
    "case_id", "workload_name", "operator_id", "layer",
    "strength", "seed", "mutations",
]

_VERIFY_REQUIRED_FIELDS = [
    "tolerance_lower", "hidden_eval_seeds", "faulty_value",
    "admissible_repairs",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_text_for_tokens(text: str, tokens: list[str]) -> list[str]:
    """Return list of violations: 'line N contains <token>: <line>'."""
    violations = []
    for i, line in enumerate(text.splitlines(), 1):
        lower = line.lower()
        for token in tokens:
            if token.lower() in lower:
                violations.append(
                    f"line {i} contains '{token}': {line.strip()}"
                )
    return violations


def _load_yaml(path: Path) -> dict | list | None:
    with open(path) as f:
        return yaml.safe_load(f)


def _navigate_config(config: dict, key_path: str):
    """Navigate a nested dict by dot-separated key_path."""
    keys = key_path.split(".")
    current = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


_MISSING = object()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_w1(case_dir: Path, hidden_card: dict) -> CheckResult:
    """W1: workspace_no_hidden_tokens — scan workspace for forbidden tokens."""
    workspace = case_dir / "workspace"
    tokens = list(_CASE_FORBIDDEN_TOKENS)

    # Dynamic tokens from operator_id segments
    operator_id = hidden_card.get("operator_id", "")
    for segment in operator_id.split("."):
        if segment and segment not in ("v1", "v2", "v3"):
            tokens.append(segment)

    violations = []
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in _BINARY_EXTENSIONS:
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        for v in _scan_text_for_tokens(text, tokens):
            violations.append(f"{p.relative_to(workspace)}: {v}")

    if violations:
        detail = f"{len(violations)} violation(s):\n" + "\n".join(violations[:10])
        if len(violations) > 10:
            detail += f"\n... and {len(violations) - 10} more"
        return CheckResult("W1_workspace_no_hidden_tokens", False, detail, "WALL")
    return CheckResult("W1_workspace_no_hidden_tokens", True, "", "WALL")


def _check_w2(case_dir: Path) -> CheckResult:
    """W2: public_card_no_incident_info."""
    card_path = case_dir / "card.public.yaml"
    text = card_path.read_text()
    violations = _scan_text_for_tokens(text, _PUBLIC_CARD_FORBIDDEN_TOKENS)
    if violations:
        detail = "Incident info in card.public.yaml:\n" + "\n".join(violations)
        return CheckResult("W2_public_card_no_incident_info", False, detail, "WALL")
    return CheckResult("W2_public_card_no_incident_info", True, "", "WALL")


def _check_w3(verify: dict) -> CheckResult:
    """W3: hidden_eval_seeds_disjoint — no overlap with reference seeds [0..9]."""
    eval_seeds = set(verify.get("hidden_eval_seeds", []))
    overlap = eval_seeds & _REFERENCE_SEEDS
    if overlap:
        detail = f"Hidden eval seeds overlap reference seeds: {sorted(overlap)}"
        return CheckResult("W3_hidden_eval_seeds_disjoint", False, detail, "WALL")
    return CheckResult("W3_hidden_eval_seeds_disjoint", True, "", "WALL")


def _check_c1(case_dir: Path, public_card: dict, hidden_card: dict) -> CheckResult:
    """C1: case_id_matches_directory."""
    dir_name = case_dir.name
    pub_id = public_card.get("case_id")
    hid_id = hidden_card.get("case_id")
    mismatches = []
    if pub_id != dir_name:
        mismatches.append(f"card.public.yaml={pub_id!r} vs dir={dir_name!r}")
    if hid_id != dir_name:
        mismatches.append(f"card.hidden.yaml={hid_id!r} vs dir={dir_name!r}")
    if pub_id != hid_id:
        mismatches.append(f"card.public.yaml={pub_id!r} vs card.hidden.yaml={hid_id!r}")
    if mismatches:
        detail = "case_id mismatch: " + "; ".join(mismatches)
        return CheckResult("C1_case_id_matches_directory", False, detail, "CONSISTENCY")
    return CheckResult("C1_case_id_matches_directory", True, "", "CONSISTENCY")


def _check_c2(
    public_card: dict, hidden_card: dict, registry: dict, case_id: str,
) -> CheckResult:
    """C2: workload_name_consistent across public card, hidden card, registry."""
    pub_wl = public_card.get("workload_name")
    hid_wl = hidden_card.get("workload_name")
    reg_entry = registry.get(case_id, {})
    reg_wl = reg_entry.get("workload")
    mismatches = []
    if pub_wl != hid_wl:
        mismatches.append(f"public={pub_wl!r} vs hidden={hid_wl!r}")
    if reg_wl is not None and pub_wl != reg_wl:
        mismatches.append(f"public={pub_wl!r} vs registry={reg_wl!r}")
    if mismatches:
        detail = "workload_name mismatch: " + "; ".join(mismatches)
        return CheckResult("C2_workload_name_consistent", False, detail, "CONSISTENCY")
    return CheckResult("C2_workload_name_consistent", True, "", "CONSISTENCY")


def _check_c3(
    registry: dict, case_id: str, hidden_card: dict,
) -> CheckResult:
    """C3: registry_entry_exists and matches hidden card."""
    if case_id not in registry:
        detail = f"{case_id} not found in registry.hidden.yaml"
        return CheckResult("C3_registry_entry_exists", False, detail, "CONSISTENCY")
    entry = registry[case_id]
    mismatches = []
    for reg_key, card_key in [
        ("operator", "operator_id"),
        ("strength", "strength"),
        ("seed", "seed"),
    ]:
        reg_val = entry.get(reg_key)
        card_val = hidden_card.get(card_key)
        if reg_val != card_val:
            mismatches.append(f"{reg_key}: registry={reg_val!r} vs card={card_val!r}")
    if mismatches:
        detail = "Registry mismatch: " + "; ".join(mismatches)
        return CheckResult("C3_registry_entry_exists", False, detail, "CONSISTENCY")
    return CheckResult("C3_registry_entry_exists", True, "", "CONSISTENCY")


def _compute_tolerance(mean: float, std: float) -> float:
    """Recompute tolerance the same way as harness/reference_run.py:131."""
    return round(mean - 2 * std, 6)


def _check_c4(verify: dict, project_root: Path, workload_name: str) -> CheckResult:
    """C4: tolerance_matches_reference — recompute from stats, epsilon compare."""
    stats_path = project_root / "workloads" / workload_name / "reference" / "stats.yaml"
    if not stats_path.exists():
        detail = f"Reference stats not found: {stats_path}"
        return CheckResult("C4_tolerance_matches_reference", False, detail, "CONSISTENCY")

    stats = _load_yaml(stats_path)
    test_stats = stats.get("metric_hidden_test_acc", {})
    mean = test_stats.get("mean")
    std = test_stats.get("std")
    if mean is None or std is None:
        detail = "Reference stats missing mean or std for metric_hidden_test_acc"
        return CheckResult("C4_tolerance_matches_reference", False, detail, "CONSISTENCY")

    expected = _compute_tolerance(mean, std)
    actual = verify.get("tolerance_lower")
    if actual is None:
        detail = "verify.yaml missing tolerance_lower"
        return CheckResult("C4_tolerance_matches_reference", False, detail, "CONSISTENCY")

    if abs(actual - expected) > 1e-9:
        detail = (
            f"tolerance_lower={actual} != round(mean - 2*std, 6)={expected} "
            f"(mean={mean}, std={std}). "
            f"Note: tolerance formula is duplicated in reference_run.py with no shared utility."
        )
        return CheckResult("C4_tolerance_matches_reference", False, detail, "CONSISTENCY")
    return CheckResult("C4_tolerance_matches_reference", True, "", "CONSISTENCY")


def _check_c5(verify: dict) -> CheckResult:
    """C5: faulty_value_below_tolerance."""
    faulty = verify.get("faulty_value")
    tolerance = verify.get("tolerance_lower")
    if faulty is None or tolerance is None:
        detail = "verify.yaml missing faulty_value or tolerance_lower"
        return CheckResult("C5_faulty_value_below_tolerance", False, detail, "CONSISTENCY")
    if faulty >= tolerance:
        detail = f"faulty_value={faulty} >= tolerance_lower={tolerance}"
        return CheckResult("C5_faulty_value_below_tolerance", False, detail, "CONSISTENCY")
    return CheckResult("C5_faulty_value_below_tolerance", True, "", "CONSISTENCY")


def _check_c6(case_dir: Path, hidden_card: dict) -> CheckResult:
    """C6: mutations_applied_in_config (deep check)."""
    resolved_path = case_dir / "workspace" / "run_output" / "config.resolved.yaml"
    if not resolved_path.exists():
        detail = "config.resolved.yaml not found"
        return CheckResult("C6_mutations_applied_in_config", False, detail, "CONSISTENCY")

    resolved = _load_yaml(resolved_path)
    mutations = hidden_card.get("mutations", [])
    mismatches = []
    for mut in mutations:
        key_path = mut.get("key_path", "")
        expected = mut.get("mutated_value")
        actual = _navigate_config(resolved, key_path)
        if actual is _MISSING:
            mismatches.append(f"{key_path}: not found in resolved config")
        elif actual != expected:
            mismatches.append(f"{key_path}: expected={expected!r}, actual={actual!r}")

    if mismatches:
        detail = "Mutation mismatch in resolved config:\n" + "\n".join(mismatches)
        return CheckResult("C6_mutations_applied_in_config", False, detail, "CONSISTENCY")
    return CheckResult("C6_mutations_applied_in_config", True, "", "CONSISTENCY")


def _check_c7(case_id: str, project_root: Path) -> CheckResult:
    """C7: index_matches_record — verify index.jsonl matches trial records."""
    from harness.provenance import _index_line

    trials_dir = project_root / "results" / case_id / "trials"
    if not trials_dir.exists() or not any(trials_dir.iterdir()):
        return CheckResult("C7_index_matches_record", True, "skipped: no trials", "CONSISTENCY")

    index_path = project_root / "results" / "index.jsonl"
    if not index_path.exists():
        # Trials exist but no index — that's a drift
        detail = "Trial records exist but results/index.jsonl is missing"
        return CheckResult("C7_index_matches_record", False, detail, "CONSISTENCY")

    # Parse index into run_id -> entry map
    index_by_run_id: dict[str, dict] = {}
    for raw in index_path.read_text().splitlines():
        if not raw.strip():
            continue
        entry = json.loads(raw)
        index_by_run_id[entry["run_id"]] = entry

    mismatches = []
    for trial_path in sorted(trials_dir.glob("*.yaml")):
        record = _load_yaml(trial_path)
        if record is None:
            continue
        run_id = record.get("run_id")
        if run_id is None:
            continue
        # Only check trials for this case
        if record.get("case_id") != case_id:
            continue

        if run_id not in index_by_run_id:
            mismatches.append(f"run_id={run_id}: missing from index.jsonl")
            continue

        expected = _index_line(record)
        actual = index_by_run_id[run_id]

        for field in ("detection_correct", "identification_correct", "evidence_f1", "recovery_verdict"):
            if expected.get(field) != actual.get(field):
                mismatches.append(
                    f"run_id={run_id} field={field}: "
                    f"record→{expected.get(field)!r} vs index→{actual.get(field)!r}"
                )

    if mismatches:
        detail = "Index drift:\n" + "\n".join(mismatches)
        return CheckResult("C7_index_matches_record", False, detail, "CONSISTENCY")
    return CheckResult("C7_index_matches_record", True, "", "CONSISTENCY")


def _check_c8(case_id: str, project_root: Path) -> CheckResult:
    """C8: recovery_files_linked — recovery files reference existing trials."""
    results_dir = project_root / "results" / case_id
    if not results_dir.exists():
        return CheckResult("C8_recovery_files_linked", True, "skipped: no results", "CONSISTENCY")

    recovery_files = list(results_dir.glob("recovery_*.yaml"))
    if not recovery_files:
        return CheckResult("C8_recovery_files_linked", True, "skipped: no recovery files", "CONSISTENCY")

    # Collect existing trial run_ids
    trials_dir = results_dir / "trials"
    trial_run_ids: set[str] = set()
    if trials_dir.exists():
        for trial_path in trials_dir.glob("*.yaml"):
            record = _load_yaml(trial_path)
            if record and "run_id" in record:
                trial_run_ids.add(record["run_id"])

    mismatches = []
    for rf in recovery_files:
        content = _load_yaml(rf)
        if content is None:
            mismatches.append(f"{rf.name}: could not parse YAML")
            continue
        trial_run_id = content.get("trial_run_id")
        if trial_run_id is None:
            mismatches.append(f"{rf.name}: missing trial_run_id field")
            continue
        if trial_run_id not in trial_run_ids:
            mismatches.append(
                f"{rf.name}: trial_run_id={trial_run_id!r} has no matching trial record"
            )

    if mismatches:
        detail = "Orphaned recovery files:\n" + "\n".join(mismatches)
        return CheckResult("C8_recovery_files_linked", False, detail, "CONSISTENCY")
    return CheckResult("C8_recovery_files_linked", True, "", "CONSISTENCY")


def _check_f1(case_dir: Path) -> CheckResult:
    """F1: required_files_exist."""
    missing = []
    for rel in _REQUIRED_FILES:
        if not (case_dir / rel).exists():
            missing.append(rel)
    if missing:
        detail = "Missing files: " + ", ".join(missing)
        return CheckResult("F1_required_files_exist", False, detail, "WELL_FORMEDNESS")
    return CheckResult("F1_required_files_exist", True, "", "WELL_FORMEDNESS")


def _check_f2(hidden_card: dict) -> CheckResult:
    """F2: hidden_card_required_fields."""
    missing = [f for f in _HIDDEN_CARD_REQUIRED_FIELDS if f not in hidden_card]
    if missing:
        detail = f"card.hidden.yaml missing fields: {missing}"
        return CheckResult("F2_hidden_card_required_fields", False, detail, "WELL_FORMEDNESS")

    mutations = hidden_card.get("mutations")
    if not isinstance(mutations, list) or len(mutations) < 1:
        detail = "card.hidden.yaml mutations must be a non-empty list"
        return CheckResult("F2_hidden_card_required_fields", False, detail, "WELL_FORMEDNESS")

    return CheckResult("F2_hidden_card_required_fields", True, "", "WELL_FORMEDNESS")


def _check_f3(verify: dict) -> CheckResult:
    """F3: verify_yaml_required_fields."""
    missing = [f for f in _VERIFY_REQUIRED_FIELDS if f not in verify]
    if missing:
        detail = f"verify.yaml missing fields: {missing}"
        return CheckResult("F3_verify_yaml_required_fields", False, detail, "WELL_FORMEDNESS")

    # Type checks
    issues = []
    if not isinstance(verify.get("tolerance_lower"), (int, float)):
        issues.append("tolerance_lower must be a number")
    if not isinstance(verify.get("faulty_value"), (int, float)):
        issues.append("faulty_value must be a number")
    seeds = verify.get("hidden_eval_seeds")
    if not isinstance(seeds, list) or not all(isinstance(s, int) for s in seeds):
        issues.append("hidden_eval_seeds must be a list of ints")
    repairs = verify.get("admissible_repairs")
    if not isinstance(repairs, dict):
        issues.append("admissible_repairs must be a dict")
    else:
        for key in ("repair_type", "allowed_keys", "value_ranges"):
            if key not in repairs:
                issues.append(f"admissible_repairs missing '{key}'")

    if issues:
        detail = "verify.yaml schema issues: " + "; ".join(issues)
        return CheckResult("F3_verify_yaml_required_fields", False, detail, "WELL_FORMEDNESS")
    return CheckResult("F3_verify_yaml_required_fields", True, "", "WELL_FORMEDNESS")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_case(
    case_dir: Path,
    project_root: Path | None = None,
    deep: bool = False,
) -> ValidationReport:
    """Run all checks on one case directory.

    Args:
        case_dir: Path to the case directory (e.g. ``cases/case_0001``).
        project_root: Project root.  Defaults to this file's grandparent.
        deep: If True, run C6 (mutation verification in resolved config).

    Returns:
        :class:`ValidationReport` with all check results.
    """
    case_dir = Path(case_dir).resolve()
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    project_root = Path(project_root).resolve()

    case_id = case_dir.name

    # Load required YAML files (F1 catches missing files, but we need them
    # for other checks — run F1 first and bail early if critical files missing)
    checks: list[CheckResult] = []

    f1 = _check_f1(case_dir)
    checks.append(f1)

    # If critical files are missing, we can't run most checks
    public_card_path = case_dir / "card.public.yaml"
    hidden_card_path = case_dir / "hidden" / "card.hidden.yaml"
    verify_path = case_dir / "hidden" / "verify.yaml"

    if not all(p.exists() for p in (public_card_path, hidden_card_path, verify_path)):
        # Can't run further checks without these files
        return ValidationReport(case_id, checks)

    public_card = _load_yaml(public_card_path)
    hidden_card = _load_yaml(hidden_card_path)
    verify = _load_yaml(verify_path)

    # Load registry
    registry_path = project_root / "cases" / "registry.hidden.yaml"
    registry = {}
    if registry_path.exists():
        registry = _load_yaml(registry_path) or {}

    workload_name = hidden_card.get("workload_name", "")

    # WELL_FORMEDNESS
    checks.append(_check_f2(hidden_card))
    checks.append(_check_f3(verify))

    # WALL
    checks.append(_check_w1(case_dir, hidden_card))
    checks.append(_check_w2(case_dir))
    checks.append(_check_w3(verify))

    # CONSISTENCY
    checks.append(_check_c1(case_dir, public_card, hidden_card))
    checks.append(_check_c2(public_card, hidden_card, registry, case_id))
    checks.append(_check_c3(registry, case_id, hidden_card))
    checks.append(_check_c4(verify, project_root, workload_name))
    checks.append(_check_c5(verify))

    if deep:
        checks.append(_check_c6(case_dir, hidden_card))

    checks.append(_check_c7(case_id, project_root))
    checks.append(_check_c8(case_id, project_root))

    return ValidationReport(case_id, checks)


def validate_all(
    project_root: Path | None = None,
    deep: bool = False,
) -> list[ValidationReport]:
    """Run all checks on every ``case_NNNN`` under ``cases/``."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    project_root = Path(project_root).resolve()

    cases_dir = project_root / "cases"
    reports = []
    for case_dir in sorted(cases_dir.iterdir()):
        if case_dir.is_dir() and case_dir.name.startswith("case_"):
            report = validate_case(case_dir, project_root, deep=deep)
            reports.append(report)
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate case/artifact invariants (spec §5, §7)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--case", type=Path,
        help="Path to a single case directory to validate",
    )
    group.add_argument(
        "--all", action="store_true", dest="validate_all",
        help="Validate all cases under cases/",
    )
    parser.add_argument(
        "--deep", action="store_true", default=False,
        help="Run deep checks (C6: verify mutations in resolved config)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: auto-detect)",
    )
    args = parser.parse_args()

    if args.validate_all:
        reports = validate_all(args.project_root, deep=args.deep)
    else:
        report = validate_case(args.case, args.project_root, deep=args.deep)
        reports = [report]

    # Print results
    all_passed = True
    for report in reports:
        print(report.summary())
        if not report.passed:
            all_passed = False
            for check in report.failed:
                print(f"  [{check.category}] {check.name}:")
                for line in check.detail.splitlines():
                    print(f"    {line}")

    if not reports:
        print("No cases found.")
        return 1

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
