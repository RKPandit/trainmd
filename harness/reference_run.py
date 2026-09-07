"""Reference-run protocol: run K seeded training jobs and compute aggregate
statistics for a workload.

Per harness_spec_v0.1.md §3:
  1. Run the clean config on K=10 seeds; record final hidden-metric values,
     per-epoch curves, wall-time, and peak memory.
  2. Commit reference/stats.yaml: mean, std, empirical min/max of the hidden
     metric; tolerance bands are mean - 2*std on the *hidden test metric*.
  3. Reference runs are re-executed in CI monthly and on any dependency change;
     drift beyond tolerance fails CI and blocks case generation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml


def _read_epoch_metrics(metrics_path: Path) -> list[dict]:
    """Read end-of-epoch records from a metrics.jsonl file."""
    epochs = []
    with open(metrics_path) as f:
        for line in f:
            record = json.loads(line)
            if record.get("end_of_epoch"):
                epochs.append(record)
    return epochs


def run_reference(workload_dir: Path, num_seeds: int = 10) -> dict:
    """Execute K seeded runs and compute reference statistics.

    Returns the stats dict that is written to stats.yaml.
    """
    import subprocess

    config_path = workload_dir / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    data_dir = workload_dir / ".data"
    reference_dir = workload_dir / "reference"
    runs_dir = reference_dir / "runs"
    reference_dir.mkdir(parents=True, exist_ok=True)

    seeds = config["reference"]["seeds"][:num_seeds]
    all_results: list[dict] = []

    for seed in seeds:
        seed_dir = runs_dir / f"seed_{seed}"
        print(f"\n{'=' * 60}")
        print(f"Reference run: seed={seed}")
        print(f"{'=' * 60}")

        result = subprocess.run(
            [
                sys.executable,
                str(workload_dir / "train.py"),
                "--config", str(config_path),
                "--data-dir", str(data_dir),
                "--output-dir", str(seed_dir),
                "--seed", str(seed),
            ],
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Training failed for seed {seed} (exit code {result.returncode})"
            )

        epoch_metrics = _read_epoch_metrics(seed_dir / "metrics.jsonl")
        final = epoch_metrics[-1]

        all_results.append({
            "seed": seed,
            "metric_visible_val_acc": final["metric_visible_val_acc"],
            "metric_hidden_test_acc": final["metric_hidden_test_acc"],
            "wall_time_sec": round(
                sum(m["epoch_time_sec"] for m in epoch_metrics), 3,
            ),
            "peak_memory_mb": final["peak_memory_mb"],
            "epochs": [
                {
                    "epoch": m["epoch"],
                    "train_loss": m["train_loss"],
                    "metric_visible_val_acc": m["metric_visible_val_acc"],
                    "metric_hidden_test_acc": m["metric_hidden_test_acc"],
                }
                for m in epoch_metrics
            ],
        })

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------
    val_accs = np.array([r["metric_visible_val_acc"] for r in all_results])
    test_accs = np.array([r["metric_hidden_test_acc"] for r in all_results])
    wall_times = np.array([r["wall_time_sec"] for r in all_results])
    peak_mems = np.array([r["peak_memory_mb"] for r in all_results])

    stats: dict = {
        "workload": config["workload"]["name"],
        "num_seeds": num_seeds,
        "metric_visible_val_acc": {
            "mean": round(float(val_accs.mean()), 6),
            "std": round(float(val_accs.std()), 6),
            "min": round(float(val_accs.min()), 6),
            "max": round(float(val_accs.max()), 6),
        },
        "metric_hidden_test_acc": {
            "mean": round(float(test_accs.mean()), 6),
            "std": round(float(test_accs.std()), 6),
            "min": round(float(test_accs.min()), 6),
            "max": round(float(test_accs.max()), 6),
            # Recovery tolerance (spec §3): hidden metric >= mean - 2*std
            "tolerance_lower": round(
                float(test_accs.mean() - 2 * test_accs.std()), 6,
            ),
        },
        "wall_time_sec": {
            "mean": round(float(wall_times.mean()), 2),
            "std": round(float(wall_times.std()), 2),
        },
        "peak_memory_mb": {
            "max": round(float(peak_mems.max()), 2),
        },
        "per_seed": all_results,
    }

    # ------------------------------------------------------------------
    # Write stats.yaml
    # ------------------------------------------------------------------
    stats_path = reference_dir / "stats.yaml"
    with open(stats_path, "w") as f:
        yaml.dump(stats, f, default_flow_style=False, sort_keys=False)

    print(f"\n{'=' * 60}")
    print(f"Reference stats written to {stats_path}")
    vs = stats["metric_visible_val_acc"]
    ts = stats["metric_hidden_test_acc"]
    print(f"  val_acc:  {vs['mean']:.6f} +/- {vs['std']:.6f}")
    print(f"  test_acc: {ts['mean']:.6f} +/- {ts['std']:.6f}")
    print(f"  tolerance_lower (test_acc): {ts['tolerance_lower']:.6f}")
    print(f"{'=' * 60}")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run reference protocol for a workload",
    )
    parser.add_argument(
        "--workload-dir", type=Path, required=True,
        help="Path to the workload directory",
    )
    parser.add_argument(
        "--num-seeds", type=int, default=10,
        help="Number of seeds to run (default: 10)",
    )
    args = parser.parse_args()
    run_reference(args.workload_dir, args.num_seeds)
