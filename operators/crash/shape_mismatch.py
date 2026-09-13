"""Crash operator: shape mismatch via wrong input dimension (spec §4).

Motivation: this is the first execution-tier (crash) operator.  Unlike silent
operators that produce completed-but-bad training runs, this operator causes the
training job to FAIL on the first forward pass with a RuntimeError.  This exercises
build guard inversion, null faulty_value, log-based evidence, and absent-checkpoint
handling in the harness.

The fault: set ``model.input_dim`` in config to a wrong value.  The MLP is
constructed with ``Linear(wrong_dim, 64)`` but the Adult dataset has 105 features,
so the first ``model(xb)`` call crashes with::

    RuntimeError: mat1 and mat2 shapes cannot be multiplied (256x105 and Nx64)

Strength mapping (correct value is 105):
- mild:     50  (roughly half — less obviously wrong)
- moderate: 10  (one-tenth — clear mismatch)
- severe:    1  (single feature — gross mismatch)

All strengths crash identically (binary outcome), but the error messages differ in
reported dimensions.  Recovery is also binary: only exactly 105 completes
successfully.  All other in-range values crash.  This is a fundamental property
of the fault — nn.Linear requires exact dimension match.
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

# Wrong input_dim per strength tier.  Correct value is 105 (from data).
_STRENGTH_DIM: dict[str, int] = {
    "mild": 50,
    "moderate": 10,
    "severe": 1,
}


class ShapeMismatchOperator:
    """Inject a dimension mismatch that crashes training on first batch.

    Implements :class:`IncidentOperator` (spec §4).
    Layer: execution (crash tier — job fails with non-zero exitcode,
    no checkpoint produced).
    """

    id: str = "crash.shape_mismatch.v1"
    layer: Literal["execution"] = "execution"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Set ``model.input_dim`` in workspace config.yaml to a wrong value.

        Args:
            workspace: Root of the workspace copy.
            rng: Seeded RNG (accepted but unused — mutation is deterministic).
            strength: One of ``mild``, ``moderate``, ``severe``.

        Returns:
            :class:`Manifest` recording the input_dim mutation.

        Raises:
            ValueError: If *strength* is not a recognised tier.
        """
        if strength not in _STRENGTH_DIM:
            raise ValueError(
                f"Unknown strength {strength!r}; "
                f"expected one of {sorted(_STRENGTH_DIM)}"
            )

        config_path = workspace / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Key absent in clean config — original_value is None.
        original = config.get("model", {}).get("input_dim")
        mutated = _STRENGTH_DIM[strength]

        config.setdefault("model", {})["input_dim"] = mutated

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
                    key_path="model.input_dim",
                    original_value=original,
                    mutated_value=mutated,
                    description=(
                        f"Set model.input_dim from {original} to "
                        f"{mutated} ({strength} strength); data has 105 "
                        f"features so Linear({mutated}, 64) will crash"
                    ),
                )
            ],
        )

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs for this operator.

        A correct diagnosis should cite:
        1. The config key ``model.input_dim`` (the root cause).
        2. The traceback in ``logs/stdout.log`` lines 2-24 showing the
           RuntimeError with shape mismatch details.

        Line range [2, 24] determined empirically: line 2 is ``[ERROR]
        Training failed:``, line 24 is ``RuntimeError: mat1 and mat2
        shapes cannot be multiplied``.  Stable across all strengths
        and seeds (same code paths, same PyTorch version).
        """
        return [
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": "model.input_dim"},
            ),
            EvidenceRef(
                kind="line_range",
                artifact_id="logs/stdout.log",
                detail={
                    "start_line": 2,
                    "end_line": 24,
                },
            ),
        ]

    def admissible_repairs(self) -> RepairSpecSchema:
        """Schema of valid repairs.

        The repair range [90, 120] includes the correct value (105) and
        excludes all faulty values (1, 10, 50 — all below 90).  Recovery
        is binary: only exactly 105 completes.  All other values crash
        with shape mismatch (nn.Linear requires exact dimension match).
        """
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=["model.input_dim"],
            value_ranges={"model.input_dim": (90, 120)},
            # Absent in clean config; unset ≡ letting the model derive 105.
            absent_when_clean_keys=["model.input_dim"],
            description=(
                "Patch model.input_dim to a value in [90, 120] (correct 105, "
                "derived from data), or null to unset it (delete the injected "
                "override so the model derives the dimension). "
                "Only 105 — or unset — avoids shape mismatch."
            ),
        )

    def accepted_classes(self) -> frozenset[str]:
        """Class names whose core meaning is a shape/dimension mismatch.

        Defined by principle (the fault's core concept), not by expanding
        to match observed model outputs.  See DECISIONS.md.
        """
        return frozenset({
            "shape_mismatch", "dimension_mismatch", "data_shape_mismatch",
            "input_dim_mismatch", "tensor_shape_error", "model_shape_error",
            "shape_error", "dimension_error",
        })

    def core_tokens(self) -> list[frozenset[str]]:
        """Concept = a shape/dimension mismatch."""
        return [frozenset({"shape", "dimension", "dim", "input_dim"})]

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: set input_dim to the correct value (105)."""
        return {"repair_type": "config_patch", "patches": {"model.input_dim": 105}}


# Verify protocol conformance at import time.
assert isinstance(ShapeMismatchOperator(), IncidentOperator), (
    "ShapeMismatchOperator does not satisfy IncidentOperator protocol"
)
