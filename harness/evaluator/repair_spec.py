"""Repair submission schema and validator (spec §7).

The evaluator validates every repair spec before executing any training runs.
Invalid specs are rejected with machine-readable reason codes (spec §8 item 5:
rate of attempted forbidden actions per case).

v1 supports ``repair_type="config_patch"`` only: a dict of
``{key_path: new_value}`` pairs that modify the training config.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepairSubmission:
    """A parsed repair spec ready for validation."""

    repair_type: Literal["config_patch"]
    patches: dict[str, Any]  # key_path → new_value


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a repair spec against admissible_repairs."""

    valid: bool
    reason_codes: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Reason codes (spec §8 item 5)
# ---------------------------------------------------------------------------

KEY_NOT_ALLOWED = "KEY_NOT_ALLOWED"
VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
VALUE_TYPE_INVALID = "VALUE_TYPE_INVALID"
REPAIR_TYPE_UNSUPPORTED = "REPAIR_TYPE_UNSUPPORTED"
MALFORMED = "MALFORMED"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_ALLOWED_TOP_KEYS = {"repair_type", "patches"}


def parse_repair_spec(raw: Any) -> RepairSubmission:
    """Parse a raw dict into a :class:`RepairSubmission`.

    Strict structural parsing — rejects extra fields, empty patches,
    non-string keys, and wrong types.  Does NOT validate values against
    the operator's admissible_repairs; that is :func:`validate_repair`'s job.

    Raises:
        ValueError: On any structural issue.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Repair spec must be a dict, got {type(raw).__name__}")

    # Required keys
    if "repair_type" not in raw:
        raise ValueError("Missing required field 'repair_type'")
    if "patches" not in raw:
        raise ValueError("Missing required field 'patches'")

    # No extra keys
    extra = set(raw.keys()) - _ALLOWED_TOP_KEYS
    if extra:
        raise ValueError(f"Unexpected fields: {sorted(extra)}")

    repair_type = raw["repair_type"]
    if not isinstance(repair_type, str):
        raise ValueError(
            f"'repair_type' must be a string, got {type(repair_type).__name__}"
        )

    patches = raw["patches"]
    if not isinstance(patches, dict):
        raise ValueError(
            f"'patches' must be a dict, got {type(patches).__name__}"
        )
    if len(patches) == 0:
        raise ValueError("'patches' must not be empty")

    for key in patches:
        if not isinstance(key, str):
            raise ValueError(f"Patch key must be a string, got {type(key).__name__}")

    # repair_type is validated semantically by validate_repair, not here —
    # but we can still construct the submission with any string and let
    # validate_repair reject unsupported types.  For the frozen dataclass
    # Literal type, we accept any string here and let the validator check.
    return RepairSubmission(repair_type=repair_type, patches=dict(patches))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_repair(
    spec: RepairSubmission,
    verify: dict,
) -> ValidationResult:
    """Validate a parsed repair spec against a case's admissible_repairs.

    The ``verify`` dict is the loaded ``hidden/verify.yaml``.  Its
    ``admissible_repairs`` section has the shape produced by
    ``build_case.py`` (after ``_to_yaml_safe`` round-trip):

    .. code-block:: yaml

        admissible_repairs:
          repair_type: config_patch
          allowed_keys: [training.lr]
          value_ranges:
            training.lr: [0.001, 0.02]

    All violations are accumulated (no short-circuit) so the result
    gives a complete picture of what went wrong.
    """
    admissible = verify["admissible_repairs"]
    codes: list[str] = []
    details: list[str] = []

    # Check repair type
    if spec.repair_type != admissible["repair_type"]:
        codes.append(REPAIR_TYPE_UNSUPPORTED)
        details.append(
            f"repair_type {spec.repair_type!r} not supported; "
            f"expected {admissible['repair_type']!r}"
        )

    allowed_keys = set(admissible.get("allowed_keys", []))
    value_ranges = admissible.get("value_ranges", {})
    allowed_values = admissible.get("allowed_values", {})

    for key, value in spec.patches.items():
        # Key allowed?
        if key not in allowed_keys:
            codes.append(KEY_NOT_ALLOWED)
            details.append(
                f"Key {key!r} not in allowed_keys {sorted(allowed_keys)}"
            )
            continue  # skip value check for disallowed keys

        # Value check: numeric range (value_ranges) or discrete set (allowed_values)
        if key in value_ranges:
            # Reject bool explicitly (bool is a subclass of int in Python)
            if isinstance(value, bool):
                codes.append(VALUE_TYPE_INVALID)
                details.append(
                    f"Value for {key!r} must be numeric, "
                    f"got bool: {value!r}"
                )
                continue

            if not isinstance(value, (int, float)):
                codes.append(VALUE_TYPE_INVALID)
                details.append(
                    f"Value for {key!r} must be numeric, "
                    f"got {type(value).__name__}: {value!r}"
                )
                continue  # skip range check

            # Reject non-finite floats (NaN, inf, -inf)
            if not math.isfinite(value):
                codes.append(VALUE_OUT_OF_RANGE)
                details.append(
                    f"Value {value} for {key!r} is not finite"
                )
                continue

            lo, hi = value_ranges[key]
            if value < lo or value > hi:
                codes.append(VALUE_OUT_OF_RANGE)
                details.append(
                    f"Value {value} for {key!r} outside range [{lo}, {hi}]"
                )

        elif key in allowed_values:
            # Type-safe membership: Python treats 0 == False and
            # 0.0 == False, so ``0 in [False]`` is True.  Require
            # matching type AND value to prevent type confusion.
            expected = allowed_values[key]
            type_match = any(
                value is v or (type(value) is type(v) and value == v)
                for v in expected
            )
            if not type_match:
                codes.append(VALUE_OUT_OF_RANGE)
                details.append(
                    f"Value {value!r} (type {type(value).__name__}) for "
                    f"{key!r} not in allowed set {expected}"
                )

    return ValidationResult(
        valid=len(codes) == 0,
        reason_codes=codes,
        details=details,
    )
