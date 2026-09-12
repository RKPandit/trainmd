"""Registry-coverage gate for oracle_repair() (spec §4, §7).

Vulnerability class: an operator ships a ground-truth "oracle" repair that is
NOT actually admissible under its own admissible_repairs(), or that equals the
faulty value — so the known-answer gate and recovery oracle would silently
never recover.  This parametrizes over the ENTIRE operator registry so a future
operator cannot dodge the check, and plants a violation to prove it is non-hollow.
"""
from __future__ import annotations

import dataclasses
import shutil
import tempfile
from pathlib import Path
from random import Random

import pytest

from harness.build_case import _OPERATOR_REGISTRY
from harness.evaluator.repair_spec import parse_repair_spec, validate_repair

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


def _verify_from_operator(op) -> dict:
    """A minimal verify dict carrying the operator's admissible_repairs schema."""
    return {"admissible_repairs": dataclasses.asdict(op.admissible_repairs())}


def _assert_oracle_admissible(op) -> None:
    """Raise AssertionError (naming the offending key) if oracle_repair is not
    admissible under the operator's own admissible_repairs()."""
    oracle = op.oracle_repair()
    if oracle is None:  # control tier: no repair is the correct action
        return
    submission = parse_repair_spec(oracle)
    result = validate_repair(submission, _verify_from_operator(op))
    assert result.valid, (
        f"{op.id}: oracle_repair {oracle['patches']} is INADMISSIBLE under its own "
        f"admissible_repairs() — codes={result.reason_codes} details={result.details}"
    )


@pytest.mark.parametrize("operator_id", sorted(_OPERATOR_REGISTRY))
def test_oracle_repair_is_admissible(operator_id):
    """Every operator's oracle_repair validates under its own admissible_repairs()."""
    _assert_oracle_admissible(_OPERATOR_REGISTRY[operator_id]())


@pytest.mark.parametrize("operator_id", sorted(_OPERATOR_REGISTRY))
def test_oracle_repair_is_not_the_faulty_value(operator_id):
    """The oracle repair must differ from every value the operator mutated."""
    op = _OPERATOR_REGISTRY[operator_id]()
    oracle = op.oracle_repair()
    if oracle is None:
        return  # control tier

    ws = Path(tempfile.mkdtemp())
    for fname in ["config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, ws / fname)
    # Any strength is fine for reading the mutated values.
    strength = "moderate"
    manifest = op.apply(ws, Random(0), strength)
    mutated_by_key = {m.key_path: m.mutated_value for m in manifest.mutations}

    for key, oracle_value in oracle["patches"].items():
        if key in mutated_by_key:
            assert oracle_value != mutated_by_key[key], (
                f"{op.id}: oracle_repair for {key!r} equals the faulty value "
                f"{mutated_by_key[key]!r} — 'change nothing' would recover"
            )


# --------------------------------------------------------------------------
# Planted violation — prove the admissibility check is non-hollow
# --------------------------------------------------------------------------

def test_planted_inadmissible_oracle_is_caught():
    """An operator whose oracle_repair uses a disallowed key must be rejected,
    with the check naming the offending key."""
    from operators.silent.lr_warmup import LrWarmupOperator

    class BadOracleOperator(LrWarmupOperator):
        def oracle_repair(self) -> dict:
            # 'training.batch_size' is NOT in lr_warmup's allowed_keys.
            return {"repair_type": "config_patch", "patches": {"training.batch_size": 64}}

    with pytest.raises(AssertionError, match="INADMISSIBLE"):
        _assert_oracle_admissible(BadOracleOperator())
