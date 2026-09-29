"""Silent operator (image workload): training labels replaced by their look-alike class — design §2 #3.

The workload-1 counterpart is ``silent.label_corruption.v1``. Here a fixed fraction f (``data.flip_fraction``) of
TRAINING labels is replaced by its confusable partner class (T-shirt↔Shirt, Pullover↔Coat, Sneaker↔Ankle boot,
Dress↔Trouser, Bag↔Sandal — ``train.py::_swap_partner_labels``). The rows are a prefix of one permutation fixed by
the split's name, never the training seed, so a larger f contains a smaller one and the evaluator's hidden-seed
reruns see the same labels. Validation and test labels stay clean: visible AND hidden degrade (negative symptom).

Strengths, rule-v2 ladder on development seeds 0–5 (docs/audits/part3_calibration.md; DECISIONS 2026-09-29):
mild f = 0.25 (worst seed hidden 0.0313 under its bar), moderate 0.35, severe 0.45.

Identification is the workload-1 label-corruption concept EXACTLY (author's decision 2026-09-28; its methods are
the ``LabelCorruptionOperator`` functions themselves). Consequence recorded for the spec review: a label naming a
"swap" without a corruption word (``label_swap``) does not satisfy that concept.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.image.common import VISIBLE_SERIES, WORKLOAD_FAMILY, check_strength, config_key, edit_config, window
from operators.silent.label_corruption import LabelCorruptionOperator

_STRENGTH_F: dict[str, float] = {"mild": 0.25, "moderate": 0.35, "severe": 0.45}
_KEY = "data.flip_fraction"


class LabelFlipOperator:
    """Replace a nested fraction of training labels with their look-alike partner class (image workload)."""

    id: str = "silent.label_flip.v1"
    layer: Literal["dynamics"] = "dynamics"
    WORKLOAD_FAMILY: str = WORKLOAD_FAMILY
    # The read of data.flip_fraction + the block it gates, and the function that picks and replaces the labels.
    CODE_PATH = (("train.py", "reads", "flip_fraction"), ("train.py", "function", "_swap_partner_labels"))

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        check_strength(strength, _STRENGTH_F)
        f = _STRENGTH_F[strength]
        muts = edit_config(workspace, {_KEY: f},
                           f"Replace {f:.0%} of training labels with their look-alike class ({strength})")
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0, mutations=muts)

    def evidence(self) -> list[EvidenceRef]:
        """The mutated key; training loss raised and visible top-1 degraded across the run."""
        return [config_key(_KEY), window("train_loss"), window(VISIBLE_SERIES)]

    def admissible_repairs(self) -> RepairSpecSchema:
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[_KEY],
            value_ranges={_KEY: (0.0, 0.02)},
            absent_when_clean_keys=[_KEY],
            description=f"Patch {_KEY} to a value in [0.0, 0.02] (reference: absent, i.e. 0), or null to unset it.",
        )

    accepted_classes = LabelCorruptionOperator.accepted_classes
    core_tokens = LabelCorruptionOperator.core_tokens

    def oracle_repair(self) -> dict:
        return {"repair_type": "config_patch", "patches": {_KEY: 0.0}}


assert isinstance(LabelFlipOperator(), IncidentOperator), "LabelFlipOperator does not satisfy IncidentOperator"
