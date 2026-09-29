"""Shared pieces of the image operators: the visible series, the evidence window, and the config edit.

Torch-free (the registry is imported on the scoring path)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from operators.base import EvidenceRef, MutationRecord

WORKLOAD_FAMILY = "image_fmnist"
# The image workload's agent-visible metric series (workloads/image_fmnist/config.yaml: eval.report) and its last
# epoch index (sched.epochs = 8). Every image fault's symptom is present across the whole run, so its metric
# evidence is one CONTAINMENT window over epochs 0..7, as workload 1's [0, 19].
VISIBLE_SERIES = "val_top1"
LAST_EPOCH = 7


def window(series: str) -> EvidenceRef:
    return EvidenceRef(kind="metric_window", artifact_id="metrics.jsonl",
                       detail={"series": series, "start_epoch": 0, "end_epoch": LAST_EPOCH, "match": "contain"})


def config_key(key_path: str) -> EvidenceRef:
    return EvidenceRef(kind="config_key", artifact_id="config.yaml", detail={"key_path": key_path})


def edit_config(workspace: Path, edits: dict, description: str) -> list[MutationRecord]:
    """Set each ``key.path: value`` in the workspace ``config.yaml`` (creating sections), in order."""
    path = workspace / "config.yaml"
    config = yaml.safe_load(path.read_text())
    records = []
    for key_path, value in edits.items():
        node = config
        *parents, leaf = key_path.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        original = node.get(leaf)
        node[leaf] = value
        records.append(MutationRecord(file="config.yaml", key_path=key_path, original_value=original,
                                      mutated_value=value, description=description))
    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
    return records


def final_visible(run_output: Path) -> float | None:
    """Final end-of-epoch ``val_top1`` of a run (None: no epoch rows)."""
    rows = [json.loads(ln) for ln in (run_output / "metrics.jsonl").read_text().splitlines() if ln.strip()]
    epochs = [r for r in rows if r.get("end_of_epoch")]
    return epochs[-1].get(VISIBLE_SERIES) if epochs else None


def check_strength(strength: str, ladder: dict) -> None:
    if strength not in ladder:
        raise ValueError(f"Unknown strength {strength!r}; expected one of {sorted(ladder)}")
