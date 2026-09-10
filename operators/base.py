"""Incident operator protocol and data types (spec §4).

All data types are frozen dataclasses so they can be serialised with
``dataclasses.asdict()`` and are immutable after creation (spec §7 integrity).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Any, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MutationRecord:
    """One atomic change made by an operator's ``apply()``."""

    file: str                   # relative path within workspace
    key_path: str               # dot-separated config key, or empty for non-config
    original_value: Any
    mutated_value: Any
    description: str


@dataclass(frozen=True)
class Manifest:
    """Ground-truth record of everything an operator changed."""

    operator_id: str
    layer: Literal["dynamics", "execution"]
    strength: str
    seed: int
    mutations: list[MutationRecord] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceRef:
    """A structural pointer to one piece of observable evidence.

    ``kind`` selects the matching semantics used by the scorer (spec §8.3):
    - config_key:    ``detail`` has ``key_path``
    - metric_window: ``detail`` has ``series``, ``start_epoch``, ``end_epoch``
    - line_range:    ``detail`` has ``artifact_id``, ``start_line``, ``end_line``
    - code_span:     ``detail`` has ``file``, ``start_line``, ``end_line``
    """

    kind: Literal["config_key", "metric_window", "line_range", "code_span"]
    artifact_id: str            # e.g. "config.yaml", "metrics.jsonl"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairSpecSchema:
    """Declarative schema of admissible repairs for an operator.

    The evaluator (spec §7) validates submitted repairs against this schema
    before applying them to a fresh workspace.
    """

    repair_type: Literal["config_patch", "code_patch", "data_fix"]
    allowed_keys: list[str] = field(default_factory=list)
    value_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    allowed_paths: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class IncidentOperator(Protocol):
    """Interface every operator must satisfy (spec §4).

    Each operator ships with unit tests proving:
    (a) the clean run passes verification, and
    (b) the mutated run fails it,
    across 3 seeds, before merge.
    """

    id: str
    layer: Literal["dynamics", "execution"]

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Mutate the workspace copy deterministically under *rng*.

        Returns a :class:`Manifest` recording every change (hidden ground
        truth).  Must only modify files inside *workspace*.
        """
        ...

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs that a correct diagnosis should cite."""
        ...

    def admissible_repairs(self) -> RepairSpecSchema:
        """Schema of valid repairs the evaluator will accept."""
        ...

    def accepted_classes(self) -> frozenset[str]:
        """Set of class names that correctly identify this operator.

        Scoring normalises case and separators (``-``/``_``/`` ``) before
        comparing the agent's predicted class against this set.  Include
        all synonyms an agent might reasonably use to name this fault
        category.
        """
        ...
