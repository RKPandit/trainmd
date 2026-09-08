"""Case generation pipeline (spec §5).

``build_case.py --workload W --operator O --strength S --seed N`` produces a
case directory under ``cases/`` containing:

- ``card.public.yaml``: opaque case_id, workload family, permitted tools,
  permitted edit paths, agent budget, artifact inventory.  NO incident info.
- ``workspace/``: mutated copy of the workload source + produced artifacts
  of ONE faulty run (logs, metrics.jsonl, resolved config, checkpoints).
- ``hidden/``: ground-truth card, structural evidence, recovery oracle params.
  NEVER shipped to the agent (spec §7).

Case IDs are opaque sequential identifiers (``case_0001``, ``case_0002``, etc.).
A hidden-side registry ``cases/registry.hidden.yaml`` maps each case_id to its
generation parameters.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from random import Random

import yaml

from operators.base import IncidentOperator, Manifest


def _to_yaml_safe(obj):
    """Recursively convert tuples to lists for yaml.safe_load round-trip."""
    if isinstance(obj, dict):
        return {k: _to_yaml_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_yaml_safe(item) for item in obj]
    return obj
from operators.silent.lr_warmup import LrWarmupOperator


# ---------------------------------------------------------------------------
# Operator registry
# ---------------------------------------------------------------------------

_OPERATOR_REGISTRY: dict[str, type] = {
    "silent.lr_warmup.v1": LrWarmupOperator,
}


def _get_operator(operator_id: str) -> IncidentOperator:
    """Instantiate an operator by ID."""
    if operator_id not in _OPERATOR_REGISTRY:
        raise ValueError(
            f"Unknown operator {operator_id!r}; "
            f"known: {sorted(_OPERATOR_REGISTRY)}"
        )
    return _OPERATOR_REGISTRY[operator_id]()


# ---------------------------------------------------------------------------
# Case ID management
# ---------------------------------------------------------------------------

def _next_case_id(registry_path: Path) -> str:
    """Return the next sequential case ID (``case_NNNN``)."""
    if registry_path.exists():
        with open(registry_path) as f:
            registry = yaml.safe_load(f) or {}
        existing = [k for k in registry if k.startswith("case_")]
        if existing:
            max_num = max(int(k.split("_")[1]) for k in existing)
            return f"case_{max_num + 1:04d}"
    return "case_0001"


def _append_registry(registry_path: Path, case_id: str, entry: dict) -> None:
    """Append a case entry to the hidden registry."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        with open(registry_path) as f:
            registry = yaml.safe_load(f) or {}
    else:
        registry = {}
    registry[case_id] = entry
    with open(registry_path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

def build_case(
    workload_name: str,
    operator_id: str,
    strength: str,
    seed: int,
    project_root: Path | None = None,
) -> Path:
    """Build one case instance.

    Args:
        workload_name: Name of the workload (e.g. ``tabular_adult``).
        operator_id: Operator ID (e.g. ``silent.lr_warmup.v1``).
        strength: One of ``mild``, ``moderate``, ``severe``.
        seed: RNG seed for the operator and training run.
        project_root: Project root directory.  Defaults to this file's
            grandparent (i.e. the repo root).

    Returns:
        Path to the created case directory.

    Raises:
        RuntimeError: If the faulty run violates silent-layer invariants
            (crash, NaN metrics, missing checkpoint) or if the hidden test
            accuracy is not below tolerance.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    workload_dir = project_root / "workloads" / workload_name
    cases_dir = project_root / "cases"
    registry_path = cases_dir / "registry.hidden.yaml"

    # ---- assign opaque case ID -------------------------------------------
    case_id = _next_case_id(registry_path)
    case_dir = cases_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    workspace = case_dir / "workspace"
    hidden = case_dir / "hidden"
    workspace.mkdir()
    hidden.mkdir()

    # ---- copy workload source to workspace --------------------------------
    for fname in ["train.py", "config.yaml"]:
        shutil.copy2(workload_dir / fname, workspace / fname)

    # Symlink visible data (matches Docker mount model; spec §2)
    data_src = workload_dir / ".data"
    data_link = workspace / ".data"
    data_link.symlink_to(data_src.resolve())

    # ---- apply operator mutation ------------------------------------------
    op = _get_operator(operator_id)
    rng = Random(seed)
    manifest = op.apply(workspace, rng, strength)

    # ---- run faulty training ----------------------------------------------
    with open(workspace / "config.yaml") as f:
        config = yaml.safe_load(f)

    run_output = workspace / "run_output"
    result = subprocess.run(
        [
            sys.executable,
            str(workspace / "train.py"),
            "--config", str(workspace / "config.yaml"),
            "--data-dir", str(data_link),
            "--output-dir", str(run_output),
            "--seed", str(seed),
        ],
        capture_output=True,
        text=True,
    )

    # ---- silent-layer build-time guards -----------------------------------
    if op.layer == "dynamics":
        # Guard 1: run must complete
        if result.returncode != 0:
            shutil.rmtree(case_dir)
            raise RuntimeError(
                f"Faulty run crashed (exitcode={result.returncode}); "
                f"silent operators must produce completed runs.\n"
                f"stderr: {result.stderr[-500:]}"
            )

        # Guard 2: checkpoint must exist
        ckpt_path = run_output / "checkpoints" / "ckpt_final.pt"
        if not ckpt_path.exists():
            shutil.rmtree(case_dir)
            raise RuntimeError(
                "Checkpoint missing after faulty run; "
                "silent operators must produce valid checkpoints."
            )

        # Guard 3: all metrics must be finite
        metrics_path = run_output / "metrics.jsonl"
        with open(metrics_path) as f:
            for line in f:
                rec = json.loads(line)
                for v in rec.values():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        shutil.rmtree(case_dir)
                        raise RuntimeError(
                            "Faulty run produced NaN/Inf metrics; "
                            "silent operators must produce finite metrics."
                        )

    # ---- evaluate checkpoint (hidden metric) ------------------------------
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint

    hidden_data_dir = workload_dir / ".hidden_data"
    ckpt_path = run_output / "checkpoints" / "ckpt_final.pt"
    eval_result = evaluate_checkpoint(ckpt_path, hidden_data_dir, config)
    hidden_acc = eval_result["metric_hidden_test_acc"]

    # Load tolerance from reference stats
    stats_path = workload_dir / "reference" / "stats.yaml"
    with open(stats_path) as f:
        stats = yaml.safe_load(f)
    tolerance_lower = stats["metric_hidden_test_acc"]["tolerance_lower"]

    if hidden_acc >= tolerance_lower:
        shutil.rmtree(case_dir)
        raise RuntimeError(
            f"Faulty run acc={hidden_acc:.6f} >= tolerance={tolerance_lower:.6f}; "
            f"operator must reliably degrade accuracy below tolerance."
        )

    # ---- read workload family from config ---------------------------------
    with open(workload_dir / "config.yaml") as f:
        workload_config = yaml.safe_load(f)
    workload_family = workload_config["workload"]["family"]

    # ---- write card.public.yaml (NO incident info) ------------------------
    public_card = {
        "case_id": case_id,
        "workload_family": workload_family,
        "workload_name": workload_name,
        "permitted_tools": [
            "read_log", "query_metrics", "read_config", "diff_config",
            "read_code", "list_files", "run_training", "submit",
        ],
        "permitted_edit_paths": ["workspace/config.yaml"],
        "agent_budget": {
            "max_tool_calls": 40,
            "max_reruns": 2,
            "max_rerun_steps_fraction": 0.25,
            "max_submissions": 1,
        },
        "artifact_inventory": [
            "workspace/run_output/metrics.jsonl",
            "workspace/run_output/logs/stdout.log",
            "workspace/run_output/config.resolved.yaml",
            "workspace/run_output/checkpoints/ckpt_final.pt",
            "workspace/run_output/exitcode",
            "workspace/config.yaml",
            "workspace/train.py",
        ],
    }
    with open(case_dir / "card.public.yaml", "w") as f:
        yaml.dump(public_card, f, default_flow_style=False, sort_keys=False)

    # ---- write hidden/card.hidden.yaml ------------------------------------
    hidden_card = {
        "case_id": case_id,
        "workload_name": workload_name,
        "operator_id": manifest.operator_id,
        "layer": manifest.layer,
        "strength": manifest.strength,
        "seed": seed,
        "mutations": [dataclasses.asdict(m) for m in manifest.mutations],
    }
    with open(hidden / "card.hidden.yaml", "w") as f:
        yaml.dump(hidden_card, f, default_flow_style=False, sort_keys=False)

    # ---- write hidden/evidence.yaml ---------------------------------------
    evidence_refs = [dataclasses.asdict(e) for e in op.evidence()]
    with open(hidden / "evidence.yaml", "w") as f:
        yaml.dump(evidence_refs, f, default_flow_style=False, sort_keys=False)

    # ---- write hidden/verify.yaml -----------------------------------------
    # Hidden eval seeds never overlap reference seeds [0-9]
    verify = {
        "tolerance_lower": tolerance_lower,
        "hidden_eval_seeds": [100, 101, 102],
        "faulty_value": hidden_acc,
        "reference_metric_mean": stats["metric_hidden_test_acc"]["mean"],
        "reference_metric_std": stats["metric_hidden_test_acc"]["std"],
        "admissible_repairs": _to_yaml_safe(dataclasses.asdict(op.admissible_repairs())),
    }
    with open(hidden / "verify.yaml", "w") as f:
        yaml.dump(verify, f, default_flow_style=False, sort_keys=False)

    # ---- append to registry -----------------------------------------------
    _append_registry(registry_path, case_id, {
        "workload": workload_name,
        "operator": operator_id,
        "strength": strength,
        "seed": seed,
    })

    print(f"Case {case_id} built at {case_dir}")
    print(f"  operator={operator_id}  strength={strength}  seed={seed}")
    print(f"  hidden_acc={hidden_acc:.6f}  tolerance={tolerance_lower:.6f}")

    return case_dir


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a case instance (spec §5)",
    )
    parser.add_argument(
        "--workload", type=str, required=True,
        help="Workload name (e.g. tabular_adult)",
    )
    parser.add_argument(
        "--operator", type=str, required=True,
        help="Operator ID (e.g. silent.lr_warmup.v1)",
    )
    parser.add_argument(
        "--strength", type=str, required=True,
        choices=["mild", "moderate", "severe"],
        help="Incident strength tier",
    )
    parser.add_argument(
        "--seed", type=int, required=True,
        help="RNG seed for operator and training",
    )
    args = parser.parse_args()

    build_case(args.workload, args.operator, args.strength, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
