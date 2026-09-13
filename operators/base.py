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
    layer: Literal["dynamics", "execution", "control"]
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

    repair_type: Literal["config_patch", "code_patch", "data_fix", "none"]
    allowed_keys: list[str] = field(default_factory=list)
    value_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    allowed_values: dict[str, list[Any]] = field(default_factory=dict)
    allowed_paths: list[str] = field(default_factory=list)
    # Keys that are ABSENT in the clean config (the operator injects them).  A
    # repair patch of ``null`` on such a key is an "unset" directive: the
    # evaluator deletes the key so the workload derives its clean default,
    # which is oracle-equivalent to restoring the reference value.  ``null`` on
    # any other key stays a VALUE_TYPE_INVALID rejection.
    absent_when_clean_keys: list[str] = field(default_factory=list)
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
    layer: Literal["dynamics", "execution", "control"]

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
        category.  This is the EXACT-match path; the token path below is the
        principled generalisation.
        """
        ...

    def core_tokens(self) -> list[frozenset[str]]:
        """Root-token spec for principled identification (``root_token_v1``).

        A list of *groups*; a normalised predicted class satisfies this
        operator iff EVERY group is matched (AND across groups), where a group
        is matched if ANY of its stems matches (OR within a group).  Stems of
        length ≤ 3 (e.g. ``lr``, ``dim``) match a whole token only; longer
        stems (e.g. ``leak``, ``nois``) match as a substring, so
        ``leak``⊂``leakage`` and ``nois``⊂``noisy``.

        Defined from the fault's MEANING, never by copying observed model
        output.  Identification is credited only when the target operator is
        the UNIQUE operator matched (a label naming two faults matches two
        operators and is rejected).  See docs/DECISIONS.md.
        """
        ...

    def oracle_repair(self) -> dict | None:
        """The repair that restores the reference behaviour (hidden ground truth).

        Returns a ``RepairSubmission``-shaped dict
        ``{"repair_type": ..., "patches": {...}}`` — the known-good fix for this
        fault (e.g. ``{"repair_type": "config_patch", "patches": {"training.lr": 0.01}}``).
        Must be admissible under :meth:`admissible_repairs` and must NOT be the
        faulty value.  Returns ``None`` for the healthy control tier, where the
        correct action is *no repair*.
        """
        ...
