"""Healthy control operator — a genuinely non-faulty run (spec §4, §8).

A THIRD tier alongside dynamics (silent) and execution (crash): the control
tier injects NO fault.  It exists to measure the false-positive behaviour of an
agent — a submitted diagnosis or repair on a healthy run is a scored *false
intervention*.  The agent is told healthy runs exist but not the base rate.

Ground truth for a control:
- ``apply()`` is a no-op returning an empty-mutation Manifest (the workspace is
  left clean; the run must genuinely pass tolerance at build time).
- ``evidence() == []`` — there is nothing to cite; any submitted ref is a false
  positive.
- ``admissible_repairs()`` allows NO repair (``repair_type="none"``).
- ``oracle_repair() is None`` — the correct action is *no repair*.

Isolation: the control's public card is shape-identical to a faulty case; no
field, value, or comment reveals "control"/"healthy" (enforced by W1/W2).
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

from operators.base import (
    EvidenceRef,
    IncidentOperator,
    Manifest,
    RepairSpecSchema,
)


class HealthyControlOperator:
    """No-op control: a healthy run with no incident.

    Implements :class:`IncidentOperator` with ``layer="control"``.
    """

    id: str = "control.healthy.v1"
    layer: Literal["control"] = "control"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """No-op: leave the workspace clean and record zero mutations.

        *strength* is accepted for interface uniformity but ignored — the
        control has a single effective behaviour (do nothing).
        """
        return Manifest(
            operator_id=self.id,
            layer=self.layer,
            strength=strength,
            seed=0,
            mutations=[],
        )

    def evidence(self) -> list[EvidenceRef]:
        """No fault → nothing to cite.  Any submitted ref is a false positive."""
        return []

    def admissible_repairs(self) -> RepairSpecSchema:
        """No repair is admissible on a healthy run."""
        return RepairSpecSchema(
            repair_type="none",
            allowed_keys=[],
            description="Healthy run — no repair should be submitted.",
        )

    def accepted_classes(self) -> frozenset[str]:
        """Labels that correctly identify a non-fault."""
        return frozenset({
            "none", "healthy", "no_incident", "no_fault", "nothing_wrong",
        })

    def oracle_repair(self) -> None:
        """The correct action on a control is no repair."""
        return None


# Verify protocol conformance at import time.
assert isinstance(HealthyControlOperator(), IncidentOperator), (
    "HealthyControlOperator does not satisfy IncidentOperator protocol"
)
