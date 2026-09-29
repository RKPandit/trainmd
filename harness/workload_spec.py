"""Per-workload metric naming (Stage 4 Part 3 harness adaptation; DECISIONS 2026-09-28).

Each workload names its OWN agent-visible metric series in its config — tabular_adult: ``metrics.visible``
(``metric_visible_val_acc``); image_fmnist: ``eval.report`` (``val_top1``). The harness keeps ONE generic key for the
visible band in ``reference/stats.yaml`` and the verify cards (``metric_visible_val_acc`` = "the workload's visible
metric"), so every stats consumer is unchanged; only code that READS the series out of a run's metrics.jsonl, or
writes / checks the public card's ``reference_visible_metric.series``, asks this module for the name. For the
tabular workloads every value is exactly what was hard-coded before (byte-identical cards, stats and prompts).
"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_VISIBLE_SERIES = "metric_visible_val_acc"
HIDDEN_METRIC = "metric_hidden_test_acc"


def visible_series(config: dict) -> str:
    """The workload's agent-visible metric series name, from its config."""
    m = (config.get("metrics") or {}).get("visible")
    if m:
        return m
    r = (config.get("eval") or {}).get("report")
    return r or DEFAULT_VISIBLE_SERIES


def workload_name(config: dict) -> str:
    return (config.get("workload") or config.get("pipeline") or {})["name"]


def workload_family(config: dict) -> str:
    return (config.get("workload") or config.get("pipeline") or {})["family"]


def load_workload_config(project_root: Path, name: str) -> dict:
    return yaml.safe_load((Path(project_root) / "workloads" / name / "config.yaml").read_text())


def card_series(card: dict) -> str:
    """The visible series a case's public card names (older cards: the tabular default)."""
    return (card.get("reference_visible_metric") or {}).get("series") or DEFAULT_VISIBLE_SERIES


def final_visible(run_output: Path, series: str = DEFAULT_VISIBLE_SERIES) -> float | None:
    """Final end-of-epoch value of ``series`` in a run's metrics.jsonl, or None (no metrics — e.g. a crash)."""
    import json
    path = Path(run_output) / "metrics.jsonl"
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("end_of_epoch") and series in rec:
            last = rec[series]
    return last
