"""Lightweight operator registry (id → operator instance).

Torch-free and import-cheap: the scoring and evaluator paths resolve an
operator's *identification token spec* and *absent-when-clean keys* from the
operator code at (re)score time, so ground truth has a single source (the
operator), never a copy baked into a sealed card.  ``build_case`` re-exports
this map so there is exactly one registry in the codebase.

See docs/DECISIONS.md: "post-hoc corrections resolve from the operator".
"""
from __future__ import annotations

import hashlib
import json

from operators.base import IncidentOperator
from operators.control.healthy import HealthyControlOperator
from operators.crash.shape_mismatch import ShapeMismatchOperator
from operators.silent.data_leakage import DataLeakageOperator
from operators.silent.label_corruption import LabelCorruptionOperator
from operators.silent.lr_warmup import LrWarmupOperator

OPERATOR_REGISTRY: dict[str, type] = {
    "silent.lr_warmup.v1": LrWarmupOperator,
    "silent.label_corruption.v1": LabelCorruptionOperator,
    "silent.data_leakage.v1": DataLeakageOperator,
    "crash.shape_mismatch.v1": ShapeMismatchOperator,
    "control.healthy.v1": HealthyControlOperator,
}


def get_operator(operator_id: str) -> IncidentOperator:
    """Instantiate an operator by ID."""
    if operator_id not in OPERATOR_REGISTRY:
        raise ValueError(
            f"Unknown operator {operator_id!r}; "
            f"known: {sorted(OPERATOR_REGISTRY)}"
        )
    return OPERATOR_REGISTRY[operator_id]()


def all_operator_ids() -> list[str]:
    return sorted(OPERATOR_REGISTRY)


def core_token_specs() -> dict[str, list[list[str]]]:
    """Every operator's core-token spec, canonicalized (sorted groups).

    Shape: ``{operator_id: [group, ...]}`` where each *group* is a sorted list
    of stems.  A label satisfies an operator iff EVERY group is matched (AND
    across groups, OR within a group).  Used by identification scoring for the
    single-operator uniqueness guard, and hashed for the per-record audit trail.
    """
    spec: dict[str, list[list[str]]] = {}
    for op_id in all_operator_ids():
        op = get_operator(op_id)
        spec[op_id] = [sorted(group) for group in op.core_tokens()]
    return spec


def token_spec_sha256() -> str:
    """Stable sha256 over the full multi-operator token spec.

    Recorded on each re-scored identification result so a score is reproducible:
    the digest changes iff any operator's core tokens change.
    """
    blob = json.dumps(core_token_specs(), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()
