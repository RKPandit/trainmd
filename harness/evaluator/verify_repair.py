"""Recovery verification pipeline (spec §7).

Accepts a repair spec submitted by an agent, validates it against the
case's admissible_repairs, builds a FRESH verification workspace (never
the agent's), reruns training on hidden seeds, and issues a recovery verdict.

Results are written to ``results/<case_id>/<run_id>.yaml`` at the project
root.  The ``hidden/`` directory is immutable ground truth, written once
at case-build time and never modified by the evaluator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint
from harness.evaluator.repair_spec import (
    MALFORMED,
    ValidationResult,
    parse_repair_spec,
    validate_repair,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KNOWN_WORKLOADS = {"tabular_adult"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_nested(d: dict, key_path: str, value: Any) -> None:
    """Set a value in a nested dict using a dot-separated key path.

    >>> d = {"training": {"lr": 0.01}}
    >>> _set_nested(d, "training.lr", 0.1)
    >>> d["training"]["lr"]
    0.1
    """
    keys = key_path.split(".")
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


def _generate_run_id() -> str:
    """Generate a unique run ID from UTC timestamp + 6-char uuid4."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}_{suffix}"


def _make_result(
    case_id: str,
    run_id: str,
    verdict: str,
    reason_codes: list[str],
    details: list[str],
    repair_spec: dict,
    per_seed: list[dict] | None = None,
    compute_sec: float = 0.0,
    integrity: dict | None = None,
    trial_run_id: str | None = None,
) -> dict:
    """Factory for result dicts."""
    result = {
        "case_id": case_id,
        "run_id": run_id,
        "verdict": verdict,
        "reason_codes": reason_codes,
        "details": details,
        "per_seed_hidden_metrics": per_seed or [],
        "compute_spent_sec": round(compute_sec, 2),
        "repair_spec": repair_spec,
        "integrity": integrity or {},
    }
    if trial_run_id is not None:
        result["trial_run_id"] = trial_run_id
    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def verify_repair(
    case_dir: Path,
    repair_spec: dict | Path,
    project_root: Path | None = None,
    trial_run_id: str | None = None,
) -> dict:
    """Run the recovery verification pipeline for one repair submission.

    Args:
        case_dir: Path to the case directory (containing ``card.public.yaml``,
            ``workspace/``, ``hidden/``).
        repair_spec: Either a raw dict or a path to a YAML/JSON file
            containing the repair submission.
        project_root: Project root directory.  Defaults to this file's
            great-grandparent (repo root).
        trial_run_id: If provided, the result file is named
            ``recovery_<trial_run_id>.yaml`` so re-verification overwrites
            in place (idempotent).  The ``trial_run_id`` is also recorded
            in the result dict for traceability.

    Returns:
        Result dict with verdict, per-seed metrics, and integrity info.
        When *trial_run_id* is provided, also written to
        ``results/<case_id>/recovery_<trial_run_id>.yaml``.
        Standalone calls (no *trial_run_id*) return the dict only —
        no file is written, avoiding orphaned results in the trial
        results directory.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent

    case_dir = Path(case_dir).resolve()
    hidden_dir = case_dir / "hidden"

    # ---- Step 1: Load hidden materials -----------------------------------
    with open(hidden_dir / "verify.yaml") as f:
        verify = yaml.safe_load(f)
    with open(hidden_dir / "card.hidden.yaml") as f:
        hidden_card = yaml.safe_load(f)
    with open(case_dir / "card.public.yaml") as f:
        public_card = yaml.safe_load(f)

    case_id = public_card["case_id"]

    # Read workload_name from HIDDEN card only (trusted identity)
    if "workload_name" not in hidden_card:
        raise ValueError(
            "card.hidden.yaml missing 'workload_name' "
            "(case predates trusted workload identity; rebuild with build_case)"
        )
    workload_name = hidden_card["workload_name"]
    if workload_name not in _KNOWN_WORKLOADS:
        raise ValueError(
            f"Unknown workload {workload_name!r}; "
            f"known: {sorted(_KNOWN_WORKLOADS)}"
        )
    if "/" in workload_name or "\\" in workload_name or ".." in workload_name:
        raise ValueError(
            f"Invalid workload_name {workload_name!r}: "
            f"contains path separator"
        )
    workload_dir = project_root / "workloads" / workload_name

    # ---- Step 2: Integrity hash pre-run ----------------------------------
    integrity_files = {
        "verify.yaml": hidden_dir / "verify.yaml",
        "card.hidden.yaml": hidden_dir / "card.hidden.yaml",
        "workload/train.py": workload_dir / "train.py",
        "workload/config.yaml": workload_dir / "config.yaml",
    }
    hashes_before = {name: _hash_file(path) for name, path in integrity_files.items()}

    # ---- Step 3: Parse + validate repair spec ----------------------------
    if isinstance(repair_spec, Path):
        with open(repair_spec) as f:
            if str(repair_spec).endswith(".json"):
                raw = json.load(f)
            else:
                raw = yaml.safe_load(f)
    else:
        raw = repair_spec

    run_id = _generate_run_id()

    try:
        submission = parse_repair_spec(raw)
    except ValueError as e:
        result = _make_result(
            case_id, run_id, "rejected", [MALFORMED], [str(e)], raw,
            trial_run_id=trial_run_id,
        )
        if trial_run_id is not None:
            _write_result(project_root, result, trial_run_id=trial_run_id)
        return result

    validation = validate_repair(submission, verify)
    if not validation.valid:
        result = _make_result(
            case_id, run_id, "rejected",
            validation.reason_codes, validation.details, raw,
            trial_run_id=trial_run_id,
        )
        if trial_run_id is not None:
            _write_result(project_root, result, trial_run_id=trial_run_id)
        return result

    # ---- Step 4: Build FRESH verification workspace ----------------------
    compute_start = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="trainmd_verify_") as tmpdir:
        verify_ws = Path(tmpdir) / "workspace"
        verify_ws.mkdir()

        # Copy clean workload source (NOT the agent's workspace)
        for fname in ["train.py", "config.yaml"]:
            shutil.copy2(workload_dir / fname, verify_ws / fname)

        # Symlink visible data
        (verify_ws / ".data").symlink_to((workload_dir / ".data").resolve())

        # Step 4a: Replay operator mutation from card.hidden.yaml
        config_path = verify_ws / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        for mutation in hidden_card["mutations"]:
            _set_nested(config, mutation["key_path"], mutation["mutated_value"])

        # Step 4b: Apply the repair patch on top
        for key_path, new_value in submission.patches.items():
            _set_nested(config, key_path, new_value)

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # ---- Step 5: Run training on each hidden seed --------------------
        hidden_seeds = verify["hidden_eval_seeds"]
        hidden_data_dir = workload_dir / ".hidden_data"
        per_seed_results: list[dict] = []

        for seed in hidden_seeds:
            seed_output = Path(tmpdir) / f"seed_{seed}"

            run_result = subprocess.run(
                [
                    sys.executable,
                    str(verify_ws / "train.py"),
                    "--config", str(config_path),
                    "--data-dir", str(verify_ws / ".data"),
                    "--output-dir", str(seed_output),
                    "--seed", str(seed),
                ],
                capture_output=True,
                text=True,
            )

            exitcode = run_result.returncode
            metric = None

            if exitcode == 0:
                ckpt_path = seed_output / "checkpoints" / "ckpt_final.pt"
                if ckpt_path.exists():
                    with open(config_path) as f:
                        run_config = yaml.safe_load(f)
                    eval_result = evaluate_checkpoint(
                        ckpt_path, hidden_data_dir, run_config,
                    )
                    metric = eval_result["metric_hidden_test_acc"]

            per_seed_results.append({
                "seed": seed,
                "metric_hidden_test_acc": metric,
                "exitcode": exitcode,
            })

    compute_sec = time.monotonic() - compute_start

    # ---- Step 6: Determine verdict ---------------------------------------
    tolerance = verify["tolerance_lower"]
    all_recovered = all(
        r["exitcode"] == 0
        and r["metric_hidden_test_acc"] is not None
        and r["metric_hidden_test_acc"] >= tolerance
        for r in per_seed_results
    )
    verdict = "recovered" if all_recovered else "not_recovered"

    # ---- Step 7: Integrity hash post-run ---------------------------------
    hashes_after = {
        name: _hash_file(path) for name, path in integrity_files.items()
    }
    for name in integrity_files:
        if hashes_before[name] != hashes_after[name]:
            raise RuntimeError(
                f"{name} was modified during evaluation! "
                f"Before: {hashes_before[name]}, after: {hashes_after[name]}"
            )

    # ---- Step 8: Assemble and write result -------------------------------
    result = _make_result(
        case_id, run_id, verdict,
        reason_codes=[],
        details=[],
        repair_spec=raw,
        per_seed=per_seed_results,
        compute_sec=compute_sec,
        integrity={
            "hashes": hashes_before,
            "hash_verified": True,
        },
        trial_run_id=trial_run_id,
    )
    if trial_run_id is not None:
        _write_result(project_root, result, trial_run_id=trial_run_id)
    return result


def _write_result(
    project_root: Path,
    result: dict,
    trial_run_id: str,
) -> Path:
    """Write recovery result to disk.

    The file is named ``recovery_<trial_run_id>.yaml`` so
    re-verification overwrites in place (idempotent).

    Only called when *trial_run_id* is not None — standalone
    verification calls do not write to disk.
    """
    results_dir = project_root / "results" / result["case_id"]
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = f"recovery_{trial_run_id}.yaml"
    result_path = results_dir / filename
    with open(result_path, "w") as f:
        yaml.dump(result, f, default_flow_style=False, sort_keys=False)
    return result_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a repair submission against a case (spec §7)",
    )
    parser.add_argument(
        "--case", type=Path, required=True,
        help="Path to the case directory",
    )
    parser.add_argument(
        "--spec", type=Path, required=True,
        help="Path to the repair spec YAML/JSON file",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: auto-detect)",
    )
    args = parser.parse_args()

    result = verify_repair(args.case, args.spec, args.project_root)
    print(yaml.dump(result, default_flow_style=False, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
