"""Silent operator: label corruption via config-controlled noise (spec §4).

Motivation: data-quality faults are a distinct failure mode from hyper-parameter
misconfiguration.  Unlike lr_warmup, the repair key is NOT training.lr — an agent
that blindly guesses an LR fix will be rejected.  This tests whether agents can
correctly diagnose a data-quality issue and produce the right repair key (RQ4/RQ5).

The fault is expressed as a config flag ``data.label_noise_fraction`` that controls
what fraction of training labels are deterministically flipped.  The operator sets
this knob to a non-zero value; the repair is setting it back to ~0.  True
``data_fix`` repair types are deferred to a future operator.

Strength mapping (fraction of training labels flipped):
- mild:     0.33  (33%)
- moderate: 0.38  (38%)
- severe:   0.42  (42%)

Adult is robust to label noise, so this operator saturates: fractions below ~0.30
do NOT reliably fail tolerance on every seed (the old 0.15/0.25/0.35 ladder left
mild AND moderate above the margin on seed 2), and fractions >=0.45 destabilize
(a seed collapses to the majority-class baseline or the model learns inverted
labels).  The 0.33/0.38/0.42 band is the stable, monotone region where every
strength clears tolerance by >=2x the reference std on all calibration seeds.

The corrupted label set is a function of (data_length, noise_fraction) ONLY — NOT
the training seed.  This ensures the evaluator sees the same corruption when it
reruns with hidden eval seeds [100, 101, 102].

Observed symptoms:
- train_loss: markedly higher than reference across all 20 epochs (strongest signal).
  The model fits noisy targets, inflating cross-entropy.
- metric_visible_val_acc: degraded, all 20 epochs below reference min.
  The model trained on corrupted labels generalises poorly to clean validation data.

Calibration (worst-of-seeds{0,1,2} hidden_test_acc, tolerance_lower=0.843535,
margin threshold tol-2*std=0.839421):
- mild    (33%): worst 0.833112  (all seeds pass margin)
- moderate(38%): worst 0.819107
- severe  (42%): worst 0.807902
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

# Fraction of training labels flipped per strength tier.
_STRENGTH_FRACTION: dict[str, float] = {
    "mild": 0.33,
    "moderate": 0.38,
    "severe": 0.42,
}


class LabelCorruptionOperator:
    """Inject label noise into training data via a config flag.

    Implements :class:`IncidentOperator` (spec §4).
    Layer: dynamics (silent tier — runs complete, metrics finite, accuracy
    degraded below tolerance).
    """

    id: str = "silent.label_corruption.v1"
    layer: Literal["dynamics"] = "dynamics"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Set ``data.label_noise_fraction`` in workspace config.yaml.

        Args:
            workspace: Root of the workspace copy.
            rng: Seeded RNG (accepted but unused — mutation is deterministic).
            strength: One of ``mild``, ``moderate``, ``severe``.

        Returns:
            :class:`Manifest` recording the label-noise mutation.

        Raises:
            ValueError: If *strength* is not a recognised tier.
        """
        if strength not in _STRENGTH_FRACTION:
            raise ValueError(
                f"Unknown strength {strength!r}; "
                f"expected one of {sorted(_STRENGTH_FRACTION)}"
            )

        config_path = workspace / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        original = config.get("data", {}).get("label_noise_fraction", 0.0)
        mutated = _STRENGTH_FRACTION[strength]

        config.setdefault("data", {})["label_noise_fraction"] = mutated

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
                    key_path="data.label_noise_fraction",
                    original_value=original,
                    mutated_value=mutated,
                    description=(
                        f"Set data.label_noise_fraction from {original} to "
                        f"{mutated} ({strength} strength, "
                        f"{mutated * 100:.0f}% of training labels flipped)"
                    ),
                )
            ],
        )

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs for this operator.

        A correct diagnosis should cite:
        1. The config key ``data.label_noise_fraction`` (the root cause).
        2. Anomalous train_loss — label noise raises training loss by ~100%
           across the entire run (20/20 epochs above reference max at
           moderate strength).  The model fits noisy targets, inflating
           cross-entropy.  This is the strongest signal.
        3. Degraded metric_visible_val_acc — the model trained on corrupted
           labels generalises poorly to clean validation data (20/20 epochs
           below reference min at moderate strength, ~1.9% absolute drop).

        Empirically verified on moderate (25% noise) case, seed 42.
        """
        return [
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": "data.label_noise_fraction"},
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    "series": "train_loss",
                    "start_epoch": 0,
                },
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    "series": "metric_visible_val_acc",
                    "start_epoch": 0,
                },
            ),
        ]

    def admissible_repairs(self) -> RepairSpecSchema:
        """Schema of valid repairs.

        The repair range [0.0, 0.02] includes the clean value (0.0) and is
        capped well below the mildest faulty value (0.15) so that "change
        nothing" is never an admissible repair.

        IMPORTANT: ``training.lr`` is NOT in ``allowed_keys``.  An agent
        that blindly guesses an LR fix will be rejected — the whole point
        of this operator.
        """
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=["data.label_noise_fraction"],
            value_ranges={"data.label_noise_fraction": (0.0, 0.02)},
            description=(
                "Patch data.label_noise_fraction to a value in [0.0, 0.02]. "
                "The reference value is 0.0."
            ),
        )

    def accepted_classes(self) -> frozenset[str]:
        """Class names an agent might use to correctly identify this fault."""
        return frozenset({
            "label_corruption", "data_corruption", "label_noise", "noisy_labels",
        })

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: set the label noise fraction back to 0.0."""
        return {
            "repair_type": "config_patch",
            "patches": {"data.label_noise_fraction": 0.0},
        }


# Verify protocol conformance at import time.
assert isinstance(LabelCorruptionOperator(), IncidentOperator), (
    "LabelCorruptionOperator does not satisfy IncidentOperator protocol"
)
