"""Healthy control operator — protocol shape (spec §4, §8).

The control tier declares NO fault: empty mutations, empty evidence, no
admissible repair, and a null oracle_repair.  If any of these drift, the scorer
would credit or penalise a phantom fault on a healthy run.
"""
from __future__ import annotations

from pathlib import Path
from random import Random

from operators.base import IncidentOperator
from operators.control.healthy import HealthyControlOperator


def test_layer_is_control():
    assert HealthyControlOperator().layer == "control"


def test_satisfies_protocol():
    assert isinstance(HealthyControlOperator(), IncidentOperator)


def test_apply_is_noop_empty_manifest(tmp_path):
    m = HealthyControlOperator().apply(tmp_path, Random(0), "mild")
    assert m.operator_id == "control.healthy.v1"
    assert m.layer == "control"
    assert m.mutations == []


def test_evidence_is_empty():
    assert HealthyControlOperator().evidence() == []


def test_no_admissible_repair():
    schema = HealthyControlOperator().admissible_repairs()
    assert schema.repair_type == "none"
    assert schema.allowed_keys == []


def test_oracle_repair_is_none():
    assert HealthyControlOperator().oracle_repair() is None


def test_accepted_classes_include_none():
    accepted = HealthyControlOperator().accepted_classes()
    assert "none" in accepted
    assert "healthy" in accepted
