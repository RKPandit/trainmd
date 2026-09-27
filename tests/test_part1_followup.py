"""The salvage parser in scripts/part1_followup.py produces reported (descriptive) numbers, so it is tested:
a whitespace-truncated prefix is recovered; a prefix cut before operator_class closes is NOT; garbage is NOT."""
from __future__ import annotations

from scripts.part1_followup import salvage_args

WS = "\t\t\t\n " * 400


def test_whitespace_truncated_prefix_is_recovered():
    args = ('{"diagnosis":{"detected":true,"operator_class":"input_dimension_mismatch","},"' + WS)
    assert salvage_args(args) == (True, "input_dimension_mismatch")
    assert salvage_args('{"diagnosis": {"detected": false, "operator_class": "none"' + WS) == (False, "none")


def test_prefix_cut_before_operator_class_is_not_recovered():
    assert salvage_args('{"diagnosis":{"detected":true,' + WS) is None
    assert salvage_args('{"diagnosis":{"detected":true,"operator_class":"input_dimen') is None   # label unclosed
    assert salvage_args('{"diagnosis":{"detected":true,"operator_class":') is None


def test_garbage_is_not_recovered():
    for junk in ("", WS, "not json at all", "}}}]]]", '"detected": true, "operator_class": "x"',  # no object
                 '{"evidence_refs": [], "detected": true, "operator_class": "x"}',             # no diagnosis
                 None, 123):
        assert salvage_args(junk) is None
