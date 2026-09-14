"""Silent operator: pathologically high initial learning rate (spec §4).

Motivation: LR misconfiguration is one of the most common silent degradation
causes observed in large-scale cluster studies (Jeon et al., "Analysis of
Large-Scale Multi-Tenant GPU Clusters for DNN Training Workloads", ATC 2019).
A model trains to completion with finite metrics but converges to a
significantly worse optimum when the learning rate is too high.

This operator overwrites ``training.lr`` in the workspace ``config.yaml``
with an absolute value that causes silent accuracy degradation without
crashing or producing NaN (the silent-layer invariant).

The degradation is BIMODAL, not graded (finding 2026-09-14;
scripts/calibrate_lr_warmup.py): at a given lr each seed either COLLAPSES to the
majority-class baseline (metric_hidden_test_acc = 0.756008, ~44σ below tolerance)
or trains ~normally (~0.83) — a coin flip near the LR-stability boundary whose
collapse PROBABILITY rises with lr, and which is also microarch-sensitive (the
same (lr, seed) can flip between microarchitectures — this is why the old graded
"mild" flaked on an Intel runner). So the three strengths are three points of
INCREASING COLLAPSE PROBABILITY, NOT three graded effect sizes; a valid built case
is one where the run actually failed tolerance (the build guard enforces
acc < tolerance_lower), and its σ-magnitude is ~baseline when collapsed, not set by
strength.

Strength = injected learning rate (absolute; reference 0.01; repair range caps a
faulty value > 0.02). Measured collapse rate to the exact baseline (5 seeds,
emulated amd64):
- mild:     0.1  → 0/5 full collapse (unstable strong dips ~0.82–0.84; produces
                    valid faulty cases at some seeds — e.g. the sealed 42/43 dips —
                    but seed/microarch-dependent; the rung that flaked in CI)
- moderate: 0.2  → 4/5 collapse
- severe:   0.5  → 5/5 collapse (rate reaches 1.0; lr 1.0 also 5/5; at lr 0.3 one
                    seed fell BELOW the majority baseline, 0.684 — anti-learned)

This operator therefore contributes DETECTION data, not σ-magnitude data: H2's
σ-axis rests on label_corruption (stably graded, S7). See docs/FINDINGS (per-lr
collapse table), docs/LIMITATIONS L1 (rewritten), docs/DECISIONS 2026-09-14.
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
        2. Anomalous train_loss across the run — a too-high LR corrupts the
           entire training trajectory, not just a warmup window.
        3. Degraded metric_visible_val_acc across the run — the fault
           observably corrupts validation accuracy as well as training loss.

        Both series are anomalous over the WHOLE run (val_acc measured outside
        the healthy band on all seeds at every epoch —
        scripts/measure_evidence_windows.py), so the evidence-v2 ground truth is
        a CONTAINMENT window [0, 19] (epochs 0..19; config.training.epochs = 20)
        per series: any in-run localization is credited, out-of-run/unbounded is
        not. No narrower sharp sub-window exists to declare.
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
                    "end_epoch": 19,
                    "match": "contain",
                },
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    "series": "metric_visible_val_acc",
                    "start_epoch": 0,
                    "end_epoch": 19,
                    "match": "contain",
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

    def accepted_classes(self) -> frozenset[str]:
        """Class names an agent might use to correctly identify this fault."""
        return frozenset({
            "lr_misconfiguration", "learning_rate", "lr_too_high", "lr_warmup",
        })

    def core_tokens(self) -> list[frozenset[str]]:
        """Concept = the learning rate.  Any label naming it qualifies."""
        return [frozenset({"learning_rate", "lr"})]

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: reset the learning rate to 0.01."""
        return {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}


# Verify protocol conformance at import time.
assert isinstance(LrWarmupOperator(), IncidentOperator), (
    "LrWarmupOperator does not satisfy IncidentOperator protocol"
)
