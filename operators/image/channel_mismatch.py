"""Crash operator (image workload): the network's input-channel count disagrees with the grayscale data — design
§2 #6.

The workload-1 counterpart is ``crash.shape_mismatch.v1``. Here ``net.in_ch`` is set to c ≠ 1, so the first
convolution is built for c channels and the first forward pass raises::

    RuntimeError: Given groups=1, weight of size [16, c, 3, 3], expected input[128, 1, 28, 28] to have c channels,
    but got 1 channels instead

Strengths (every rung crashes; the value is the strength, as the tabular input_dim): mild c = 2, moderate 3,
severe 4 (18/18 crashes with a traceback on development seeds; docs/audits/part3_calibration.md). Only c = 1 runs.

Identification is the workload-1 shape-mismatch concept EXACTLY (author's decision 2026-09-28; the methods are the
``ShapeMismatchOperator`` functions themselves), PLUS its own implementation-derived input-channel alternatives
(author 2026-09-29), so ``channel_mismatch`` is credited.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.crash.shape_mismatch import ShapeMismatchOperator
from operators.image.common import WORKLOAD_FAMILY, check_strength, config_key, edit_config

_STRENGTH_CH: dict[str, int] = {"mild": 2, "moderate": 3, "severe": 4}
_KEY = "net.in_ch"


class ChannelMismatchOperator:
    """Build the first convolution for the wrong number of input channels (image workload)."""

    id: str = "crash.channel_mismatch.v1"
    layer: Literal["execution"] = "execution"
    WORKLOAD_FAMILY: str = WORKLOAD_FAMILY
    # The model construction that consumes net.in_ch.
    CODE_PATH = (("train.py", "reads", "in_ch"),)
    # What the fault itself produces (evidence v2.3, resolved per case from its own log).
    CRASH_OUTPUT = ("logs/stdout.log",)

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        check_strength(strength, _STRENGTH_CH)
        c = _STRENGTH_CH[strength]
        muts = edit_config(workspace, {_KEY: c},
                           f"Set net.in_ch to {c} ({strength}); the images have 1 channel, so the first "
                           f"convolution fails")
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0, mutations=muts)

    def evidence(self) -> list[EvidenceRef]:
        """The mutated key and the error report + traceback in the run log: line 2 is ``[ERROR] Training
        failed:``, line 37 the ``RuntimeError: Given groups=1, …`` line — the same on every strength and seed
        (same code path, same pinned torch); asserted against real crash logs in tests/test_image_operators.py."""
        return [config_key(_KEY),
                EvidenceRef(kind="line_range", artifact_id="logs/stdout.log",
                            detail={"start_line": 2, "end_line": 37})]

    def admissible_repairs(self) -> RepairSpecSchema:
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[_KEY],
            value_ranges={_KEY: (1, 1)},
            description="Patch net.in_ch to 1 (the images are grayscale).",
        )

    accepted_classes = ShapeMismatchOperator.accepted_classes
    core_tokens = ShapeMismatchOperator.core_tokens

    def core_token_alternatives(self) -> list[list[frozenset[str]]]:
        """This operator's OWN terms (author 2026-09-29), derived from its implementation — ``net.in_ch``, the
        first convolution's input-channel count, disagrees with the 1-channel images — never from model output:
        (a) a term naming the convolution's input channels itself; (b) ``channel`` AND a disagreement / count
        term (a bare "channel" — e.g. channel normalisation — does not name the fault). The shared workload-1
        shape concept above is kept as the main spec."""
        return [
            [frozenset({"in_ch", "in_channel", "in_channels", "input_channel", "input_channels", "conv_input"})],
            [frozenset({"channel"}), frozenset({"mismatch", "wrong", "incorrect", "invalid", "misconfigur",
                                                "inconsistent", "disagree", "count", "number"})],
        ]

    def oracle_repair(self) -> dict:
        return {"repair_type": "config_patch", "patches": {_KEY: 1}}


assert isinstance(ChannelMismatchOperator(), IncidentOperator), \
    "ChannelMismatchOperator does not satisfy IncidentOperator"
