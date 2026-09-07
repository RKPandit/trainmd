"""Silent operator: pathologically high initial learning rate (spec §4).

Motivation: LR misconfiguration is one of the most common silent degradation
causes observed in large-scale cluster studies (Jeon et al., "Analysis of
Large-Scale Multi-Tenant GPU Clusters for DNN Training Workloads", ATC 2019).
A model trains to completion with finite metrics but converges to a
significantly worse optimum when the learning rate is too high.

This operator overwrites ``training.lr`` in the workspace ``config.yaml``
with an absolute value that causes silent accuracy degradation without
crashing or producing NaN (the silent-layer invariant).

Strength mapping (absolute LR values, reference is 0.01):
- mild:     0.1   (10x reference) — varied degradation, reliably below tolerance
- moderate: 0.2   (20x reference) — mostly baseline collapse
- severe:   0.5   (50x reference) — fully collapsed, still completes

Empirically verified on 10 seeds (macOS ARM) and 3 seeds (Linux x86_64 CI):
all strengths produce exitcode=0, finite metrics, and acc < tolerance_lower.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

import yaml

from operators.base import (
    EvidenceRef,
    IncidentOperator,
    Manifest,
    MutationRecord,
    RepairSpecSchema,
)

# Absolute LR values per strength tier.  These are NOT multipliers.
_STRENGTH_LR: dict[str, float] = {
    "mild": 0.1,
    "moderate": 0.2,
    "severe": 0.5,
}


class LrWarmupOperator:
    """Inject a pathologically high initial learning rate.

    Implements :class:`IncidentOperator` (spec §4).
    Layer: dynamics (silent tier — runs complete, metrics finite, accuracy
    degraded below tolerance).
    """

    id: str = "silent.lr_warmup.v1"
    layer: Literal["dynamics"] = "dynamics"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Overwrite ``training.lr`` in workspace config.yaml.

        Args:
            workspace: Root of the workspace copy.
            rng: Seeded RNG (accepted but unused — mutation is deterministic).
            strength: One of ``mild``, ``moderate``, ``severe``.

        Returns:
            :class:`Manifest` recording the LR mutation.

        Raises:
            ValueError: If *strength* is not a recognised tier.
        """
        if strength not in _STRENGTH_LR:
            raise ValueError(
                f"Unknown strength {strength!r}; expected one of {sorted(_STRENGTH_LR)}"
            )

        config_path = workspace / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        original_lr = config["training"]["lr"]
        mutated_lr = _STRENGTH_LR[strength]
        config["training"]["lr"] = mutated_lr

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return Manifest(
            operator_id=self.id,
            layer=self.layer,
            strength=strength,
            seed=0,  # deterministic — seed unused
            mutations=[
                MutationRecord(
                    file="config.yaml",
                    key_path="training.lr",
                    original_value=original_lr,
                    mutated_value=mutated_lr,
                    description=(
                        f"Set training.lr from {original_lr} to {mutated_lr} "
                        f"({strength} strength, "
                        f"{mutated_lr / original_lr:.0f}x reference)"
                    ),
                )
            ],
        )

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs for this operator.

        A correct diagnosis should cite:
        1. The config key ``training.lr`` (the root cause).
        2. Early-epoch train_loss anomaly in metrics.jsonl (the observable
           symptom — high LR causes elevated initial loss).
        """
        return [
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": "training.lr"},
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    "series": "train_loss",
                    "start_epoch": 0,
                    "end_epoch": 4,
                },
            ),
        ]

    def admissible_repairs(self) -> RepairSpecSchema:
        """Schema of valid repairs.

        The repair range [0.001, 0.02] includes the reference value (0.01)
        and is capped well below the mildest faulty value (0.1) so that
        "change nothing" is never an admissible repair.
        """
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=["training.lr"],
            value_ranges={"training.lr": (0.001, 0.02)},
            description=(
                "Patch training.lr to a value in [0.001, 0.02]. "
                "The reference value is 0.01."
            ),
        )


# Verify protocol conformance at import time.
assert isinstance(LrWarmupOperator(), IncidentOperator), (
    "LrWarmupOperator does not satisfy IncidentOperator protocol"
)
