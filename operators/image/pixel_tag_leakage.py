"""Silent operator (image workload): label leakage through a pixel tag — design §2 #1 / #2.

The workload-1 counterpart is ``silent.data_leakage.v1`` (a label-derived feature column). Here the leaked signal
is a 4×4 corner patch whose brightness encodes the class label, stamped into the TRAINING and the visible
VALIDATION images (``train.py::_patch_images``); with probability p (``data.corner_tag_noise``) a row's patch shows
a random class instead. The hidden test split is never tagged, so a model that learns the shortcut reads inflated
on validation and degraded on clean test: visible ABOVE the band (positive symptom) AND hidden BELOW tolerance.

Strengths (lower p = stronger leak), rule-v2 ladder on development seeds 0–5 (docs/audits/part3_calibration.md;
DECISIONS 2026-09-29): mild p = 0.20 (worst seed visible +0.0166 over its bar, hidden 0.0585 under its bar),
moderate 0.15, severe 0.05.

Identification is the workload-1 leakage concept EXACTLY (author's decision 2026-09-28): the identification
methods are the ``DataLeakageOperator`` functions themselves, not copies.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.image.common import (
    VISIBLE_SERIES,
    WORKLOAD_FAMILY,
    check_strength,
    config_key,
    edit_config,
    final_visible,
    window,
)
from operators.margins import positive_symptom_bar
from operators.silent.data_leakage import DataLeakageOperator

_STRENGTH_P: dict[str, float] = {"mild": 0.20, "moderate": 0.15, "severe": 0.05}


class PixelTagLeakageOperator:
    """Stamp a label-encoding corner tag into train + validation images (image workload)."""

    id: str = "silent.pixel_tag_leakage.v1"
    layer: Literal["dynamics"] = "dynamics"
    WORKLOAD_FAMILY: str = WORKLOAD_FAMILY
    # The two config keys (under ``data``); the neutral-key subclass overrides only these, ``id`` and the family.
    ENABLE_KEY: str = "corner_tag"
    STRENGTH_KEY: str = "corner_tag_noise"

    @property
    def CODE_PATH(self):
        # The block that reads the enabling key and stamps both visible splits, and the stamping function.
        return (("train.py", "reads", self.ENABLE_KEY), ("train.py", "function", "_patch_images"))

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        check_strength(strength, _STRENGTH_P)
        p = _STRENGTH_P[strength]
        muts = edit_config(workspace, {f"data.{self.ENABLE_KEY}": True, f"data.{self.STRENGTH_KEY}": p},
                           f"Stamp a label-encoding corner patch into train and validation images, "
                           f"disagreement rate {p} ({strength})")
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0, mutations=muts)

    def evidence(self) -> list[EvidenceRef]:
        """Both mutated keys, and the inflated visible series across the run."""
        return [config_key(f"data.{self.ENABLE_KEY}"), config_key(f"data.{self.STRENGTH_KEY}"),
                window(VISIBLE_SERIES)]

    def admissible_repairs(self) -> RepairSpecSchema:
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[f"data.{self.ENABLE_KEY}", f"data.{self.STRENGTH_KEY}"],
            allowed_values={f"data.{self.ENABLE_KEY}": [False]},
            absent_when_clean_keys=[f"data.{self.ENABLE_KEY}", f"data.{self.STRENGTH_KEY}"],
            description=(f"Set data.{self.ENABLE_KEY} to false to stop stamping the patch, or null to unset it "
                         f"(delete the injected key)."),
        )

    accepted_classes = DataLeakageOperator.accepted_classes
    core_tokens = DataLeakageOperator.core_tokens
    off_concept_vetoes = DataLeakageOperator.off_concept_vetoes

    def core_token_alternatives(self) -> list[list[frozenset[str]]]:
        """This operator's OWN terms (author 2026-09-29), derived from its implementation — a corner PATCH / tag
        stamped into the images that ENCODES the class label, i.e. a label shortcut — never from model output:
        {tag, patch, watermark, marker} AND {label, class, target, shortcut, spurious, encod}. The shared
        workload-1 leakage concept is kept as the main spec, its vetoes apply to both."""
        return [[frozenset({"tag", "patch", "watermark", "marker"}),
                 frozenset({"label", "class", "target", "shortcut", "spurious", "encod"})]]

    def oracle_repair(self) -> dict:
        return {"repair_type": "config_patch", "patches": {f"data.{self.ENABLE_KEY}": False}}

    def build_guard_checks(self, run_output: Path, stats: dict) -> list[str]:
        """The misleading symptom: final visible top-1 >= mean + 4σ + 1e-3 (operators/margins.py)."""
        v = final_visible(run_output)
        if v is None:
            return ["No epoch-level metrics found"]
        bar = positive_symptom_bar(stats)
        if v < bar:
            return [f"{VISIBLE_SERIES}={v:.6f} below margined symptom bar {bar:.6f} (mean + 4·std + 1e-3)"]
        return []


class PixelTagLeakageNeutralOperator(PixelTagLeakageOperator):
    """The same fault under neutral key names (``data.opt_t`` / ``data.opt_t_level``) on the
    ``image_fmnist_neutral`` family, whose train.py differs from the descriptive one only in those key strings
    (and ``eval.opt_q``); training is byte-identical (calibration audit, neutral-key twins)."""

    id: str = "silent.pixel_tag_leakage_neutral.v1"
    WORKLOAD_FAMILY: str = "image_fmnist_neutral"
    ENABLE_KEY: str = "opt_t"
    STRENGTH_KEY: str = "opt_t_level"


for _cls in (PixelTagLeakageOperator, PixelTagLeakageNeutralOperator):
    assert isinstance(_cls(), IncidentOperator), f"{_cls.__name__} does not satisfy IncidentOperator"
