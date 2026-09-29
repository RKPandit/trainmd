"""Metric-tier operator (image workload): the reported validation top-1 is computed on the model's most-confident
images only — design §2 #5, and its neutral-key variant (closes LIMITATIONS L37 by design).

The workload-1 counterpart is ``silent.metric_inflation.v1``. Here the eval loop reports top-1 over the fraction q
(``eval.confident_fraction``) of validation images with the highest max-softmax probability
(``train.py::_reported_top1``) instead of the full split. Model, optimisation and checkpoint are identical to the
clean run (build guard: bitwise-identical checkpoint to a clean probe); only the reported number moves: visible ABOVE
the band, hidden unchanged. As in workload 1, ``val_loss`` is still computed on the full split.

Strengths (smaller q = stronger inflation; the kept sets are nested prefixes of one confidence ordering), rule-v2
ladder on development seeds 0–5 (docs/audits/part3_calibration.md; DECISIONS 2026-09-29): mild q = 0.85 (worst
seed visible +0.0227 over its bar), moderate 0.80, severe 0.70.

The id's first segment is ``silent`` as in workload 1's ``silent.metric_inflation.v1`` (the layer, not the id,
carries the tier): a ``metric`` segment would appear in every workspace (``metrics.jsonl``) and fail W1.
Identification is the workload-1 metric-inflation concept EXACTLY, alternatives and their vetoes included (author's
decision 2026-09-28; the methods are the ``MetricInflationOperator`` functions themselves).
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
from operators.metric.metric_inflation import MetricInflationOperator

_STRENGTH_Q: dict[str, float] = {"mild": 0.85, "moderate": 0.80, "severe": 0.70}


class ConfidentSubsetOperator:
    """Report validation top-1 on the most-confident fraction of images (image workload)."""

    id: str = "silent.confident_subset.v1"
    layer: Literal["metric"] = "metric"
    WORKLOAD_FAMILY: str = WORKLOAD_FAMILY
    KEY: str = "confident_fraction"          # under ``eval``; the neutral subclass overrides it

    @property
    def CODE_PATH(self):
        # The read of the key + the block it gates, and the subset-accuracy function.
        return (("train.py", "reads", self.KEY), ("train.py", "function", "_reported_top1"))

    @property
    def _knob(self) -> str:
        return f"eval.{self.KEY}"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        check_strength(strength, _STRENGTH_Q)
        q = _STRENGTH_Q[strength]
        muts = edit_config(workspace, {self._knob: q},
                           f"Report validation top-1 on the most-confident {q:.0%} of images instead of the full "
                           f"split ({strength})")
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0, mutations=muts)

    def evidence(self) -> list[EvidenceRef]:
        """The mutated key and the inflated visible series across the run."""
        return [config_key(self._knob), window(VISIBLE_SERIES)]

    def admissible_repairs(self) -> RepairSpecSchema:
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[self._knob],
            allowed_values={self._knob: [1.0]},
            absent_when_clean_keys=[self._knob],
            description=f"Set {self._knob} to 1.0 (the full split), or null to unset it (delete the injected key).",
        )

    accepted_classes = MetricInflationOperator.accepted_classes
    core_tokens = MetricInflationOperator.core_tokens
    core_token_alternatives = MetricInflationOperator.core_token_alternatives
    core_token_alternative_vetoes = MetricInflationOperator.core_token_alternative_vetoes
    off_concept_vetoes = MetricInflationOperator.off_concept_vetoes

    def oracle_repair(self) -> dict:
        return {"repair_type": "config_patch", "patches": {self._knob: None}}

    def build_guard_checks(self, run_output: Path, stats: dict) -> list[str]:
        """The reported symptom: final visible top-1 >= mean + 4σ + 1e-3. The "model untouched" half is the
        checkpoint bitwise-identity check in build_case."""
        v = final_visible(run_output)
        if v is None:
            return ["No epoch-level metrics found"]
        bar = positive_symptom_bar(stats)
        if v < bar:
            return [f"reported {VISIBLE_SERIES}={v:.6f} below margined symptom bar {bar:.6f} (mean + 4·std + 1e-3)"]
        return []


class ConfidentSubsetNeutralOperator(ConfidentSubsetOperator):
    """The same fault under the neutral key ``eval.opt_q`` on the ``image_fmnist_neutral`` family."""

    id: str = "silent.confident_subset_neutral.v1"
    WORKLOAD_FAMILY: str = "image_fmnist_neutral"
    KEY: str = "opt_q"


for _cls in (ConfidentSubsetOperator, ConfidentSubsetNeutralOperator):
    assert isinstance(_cls(), IncidentOperator), f"{_cls.__name__} does not satisfy IncidentOperator"
