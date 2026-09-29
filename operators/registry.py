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
from operators.control.benign import BENIGN_OPERATORS
from operators.control.healthy import HealthyControlOperator
from operators.crash.shape_mismatch import ShapeMismatchOperator
from operators.image.channel_mismatch import ChannelMismatchOperator
from operators.image.confident_subset import ConfidentSubsetNeutralOperator, ConfidentSubsetOperator
from operators.image.controls import IMAGE_BENIGN_OPERATORS, ImageHealthyControlOperator
from operators.image.decay_unit import DecayUnitOperator
from operators.image.label_flip import LabelFlipOperator
from operators.image.pixel_tag_leakage import PixelTagLeakageNeutralOperator, PixelTagLeakageOperator
from operators.metric.metric_inflation import MetricInflationOperator
from operators.silent.data_leakage import DataLeakageOperator
from operators.silent.data_leakage_neutral import DataLeakageNeutralOperator
from operators.silent.label_corruption import LabelCorruptionOperator
from operators.silent.lr_warmup import LrWarmupOperator

OPERATOR_REGISTRY: dict[str, type] = {
    "silent.lr_warmup.v1": LrWarmupOperator,
    "silent.label_corruption.v1": LabelCorruptionOperator,
    "silent.data_leakage.v1": DataLeakageOperator,
    "silent.data_leakage_neutral.v1": DataLeakageNeutralOperator,
    "silent.metric_inflation.v1": MetricInflationOperator,
    "crash.shape_mismatch.v1": ShapeMismatchOperator,
    "control.healthy.v1": HealthyControlOperator,
    # Benign-configuration controls (STAGE4 4.0.6): healthy runs with one qualified routine change.
    **{cls.id: cls for cls in BENIGN_OPERATORS},
    # Part 3 image workload (workload group image_fmnist; design docs/PART3_DESIGN_DRAFT.md).
    "silent.pixel_tag_leakage.v1": PixelTagLeakageOperator,
    "silent.pixel_tag_leakage_neutral.v1": PixelTagLeakageNeutralOperator,
    "silent.label_flip.v1": LabelFlipOperator,
    "silent.decay_unit.v1": DecayUnitOperator,
    "silent.confident_subset.v1": ConfidentSubsetOperator,
    "silent.confident_subset_neutral.v1": ConfidentSubsetNeutralOperator,
    "crash.channel_mismatch.v1": ChannelMismatchOperator,
    "control.healthy_image.v1": ImageHealthyControlOperator,
    **{cls.id: cls for cls in IMAGE_BENIGN_OPERATORS},
}
for _op_id, _cls in OPERATOR_REGISTRY.items():
    assert _cls.id == _op_id, f"registry key {_op_id!r} != {_cls.__name__}.id {_cls.id!r}"


def get_operator(operator_id: str) -> IncidentOperator:
    """Instantiate an operator by ID."""
    if operator_id not in OPERATOR_REGISTRY:
        raise ValueError(
            f"Unknown operator {operator_id!r}; "
            f"known: {sorted(OPERATOR_REGISTRY)}"
        )
    return OPERATOR_REGISTRY[operator_id]()


# WORKLOAD GROUPS (Part 3, DECISIONS 2026-09-29). An operator belongs to the group of the workload family whose
# train.py reads its keys (``WORKLOAD_FAMILY``, default tabular_adult), with the neutral-key family folded into its
# descriptive twin. Every enumeration below is SCOPED to one group and defaults to workload 1, so everything that
# existed before the image operators — identification uniqueness, token_spec_sha256, the frozen evidence spec,
# the sweep planners, the case design — sees exactly the operator set it saw before (byte-identical; pinned by
# tests/test_workload1_spec_identity.py). A label is judged only against the concepts of its OWN workload.
DEFAULT_GROUP = "tabular_adult"
WORKLOAD_GROUPS = ("tabular_adult", "image_fmnist")


def workload_group(operator_id: str) -> str:
    """The workload group an operator's cases run on (``tabular_adult`` | ``image_fmnist``)."""
    family = getattr(OPERATOR_REGISTRY[operator_id], "WORKLOAD_FAMILY", DEFAULT_GROUP)
    return family.removesuffix("_neutral")


def all_operator_ids(group: str | None = DEFAULT_GROUP) -> list[str]:
    """Registered operator ids in *group* (default: workload 1); ``group=None`` returns every workload's."""
    if group is not None and group not in WORKLOAD_GROUPS:
        raise ValueError(f"unknown workload group {group!r}; known: {WORKLOAD_GROUPS}")
    return sorted(o for o in OPERATOR_REGISTRY if group is None or workload_group(o) == group)


def core_token_specs(group: str = DEFAULT_GROUP) -> dict[str, list[list[str]]]:
    """Every operator's core-token spec, canonicalized (sorted groups).

    Shape: ``{operator_id: [group, ...]}`` where each *group* is a sorted list
    of stems.  A label satisfies an operator iff EVERY group is matched (AND
    across groups, OR within a group).  Used by identification scoring for the
    single-operator uniqueness guard, and hashed for the per-record audit trail.
    """
    spec: dict[str, list[list[str]]] = {}
    for op_id in all_operator_ids(group):
        op = get_operator(op_id)
        spec[op_id] = [sorted(group) for group in op.core_tokens()]
    return spec


def core_token_alternatives(group: str = DEFAULT_GROUP) -> dict[str, list[list[list[str]]]]:
    """Every operator's ALTERNATIVE concept specs (root_token_v3), canonicalized. Shape:
    ``{operator_id: [[group, ...], ...]}`` — the label satisfies the operator if it satisfies the main
    ``core_tokens`` spec OR any alternative (each AND-across-groups). Operators without alternatives map
    to ``[]``."""
    out: dict = {}
    for op_id in all_operator_ids(group):
        alts = getattr(get_operator(op_id), "core_token_alternatives", lambda: [])()
        out[op_id] = [[sorted(g) for g in alt] for alt in alts]
    return out


def core_token_alternative_vetoes(group: str = DEFAULT_GROUP) -> dict[str, list[str]]:
    """Every operator's ALTERNATIVE-ONLY veto stems (root_token_v3), sorted: a label naming one of them cannot
    satisfy an alternative spec (it still can the main spec). Operators without any map to ``[]``."""
    return {op_id: sorted(getattr(get_operator(op_id), "core_token_alternative_vetoes", lambda: frozenset())())
            for op_id in all_operator_ids(group)}


def core_token_vetoes(group: str = DEFAULT_GROUP) -> dict[str, list[str]]:
    """Every operator's OFF-CONCEPT veto phrases, canonicalized (sorted).

    Shape: ``{operator_id: [phrase, ...]}``.  A label that contains a veto phrase
    as a bounded token run does NOT satisfy that operator via the token path
    (root_token_v2), even if a concept token is present (e.g. ``memory_leak`` for
    the ``leak`` concept).  Resolved from the operator code and hashed into the
    per-record audit trail alongside the token spec.
    """
    out: dict[str, list[str]] = {}
    for op_id in all_operator_ids(group):
        op = get_operator(op_id)
        vetoes = getattr(op, "off_concept_vetoes", lambda: frozenset())()
        out[op_id] = sorted(vetoes)
    return out


def token_spec_sha256(group: str = DEFAULT_GROUP) -> str:
    """Stable sha256 over the full multi-operator identification spec.

    Recorded on each re-scored identification result so a score is reproducible:
    the digest changes iff any operator's core tokens OR off-concept vetoes change
    (the two inputs to the root_token_v2 token path). Scoped to one workload group
    (default workload 1, whose digest is unchanged by adding another workload).
    """
    alts, alt_vetoes = core_token_alternatives(group), core_token_alternative_vetoes(group)
    blob = json.dumps(
        {"tokens": core_token_specs(group), "vetoes": core_token_vetoes(group),
         **({"alternatives": alts} if any(alts.values()) else {}),
         **({"alternative_vetoes": alt_vetoes} if any(alt_vetoes.values()) else {})},
        sort_keys=True,
    ).encode()
    return hashlib.sha256(blob).hexdigest()
