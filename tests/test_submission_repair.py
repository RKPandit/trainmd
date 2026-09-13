"""Tests for folded-repair recovery (post-hoc correction #3).

Recovery is strict: exactly one complete {repair_type, patches} JSON object,
never partial reconstruction or key scraping, and never overriding a
well-formed structured repair_spec.
"""
from __future__ import annotations

from harness.submission_repair import recover_folded_repair_spec

VALID = {"repair_type": "config_patch", "patches": {"model.input_dim": 105}}
NOISE = "lorem ipsum " * 45  # ~500 chars of noise


def _args(repair_spec=None, rationale=""):
    return {"diagnosis": {"detected": True, "operator_class": "x"},
            "evidence_refs": [], "repair_spec": repair_spec,
            "confidence": None, "rationale": rationale}


class TestStructuredWins:
    def test_wellformed_structured_never_overridden(self):
        # rationale carries tags/XML/JSON/noise AND a structured spec is present.
        rat = (f"reason </rationale> </repair_spec> <parameter name=\"repair_spec\">"
               f'{{"repair_type": "config_patch", "patches": {{"model.input_dim": 999}}}} '
               f"{NOISE}")
        fold = recover_folded_repair_spec(_args(repair_spec=VALID, rationale=rat))
        assert fold.spec is None
        assert fold.warning is False
        assert fold.reason == "already_structured"

    def test_explicit_no_repair_not_overridden(self):
        none_spec = {"repair_type": "none", "patches": {}}
        rat = '<parameter name="repair_spec">{"repair_type":"config_patch","patches":{"a":1}}'
        fold = recover_folded_repair_spec(_args(repair_spec=none_spec, rationale=rat))
        assert fold.spec is None and fold.reason == "already_structured"


class TestRecovery:
    def test_recovers_single_folded_envelope(self):
        rat = ('The input_dim is wrong.</anionale>\n<parameter name="repair_spec">\n'
               '{\n  "repair_type": "config_patch",\n  "patches": {\n    "model.input_dim": null\n  }\n}\n')
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec == {"repair_type": "config_patch", "patches": {"model.input_dim": None}}
        assert fold.warning is True and fold.reason == "recovered"

    def test_recovers_with_surrounding_noise_and_tags(self):
        rat = (NOISE + ' </rationale> ```json {"repair_type": "config_patch", '
               '"patches": {"data.include_aux_feature": false}} ``` ' + NOISE)
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec == {"repair_type": "config_patch",
                             "patches": {"data.include_aux_feature": False}}
        assert fold.reason == "recovered"


class TestStrictNonRecovery:
    def test_ambiguous_multiple_not_recovered(self):
        rat = ('{"repair_type":"config_patch","patches":{"model.input_dim":105}} '
               'and also {"repair_type":"config_patch","patches":{"model.input_dim":50}}')
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec is None
        assert fold.warning is True and fold.reason == "ambiguous_multiple"

    def test_marker_without_parseable_object_flags_only(self):
        rat = "I would set repair_type config_patch and patch model.input_dim to 105"
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec is None
        assert fold.warning is True and fold.reason == "folded_unparseable"

    def test_prose_mentioning_knob_no_marker_not_recovered(self):
        rat = "The input_dim should be 105 (derived from data)."
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec is None
        assert fold.warning is False and fold.reason == "none"

    def test_incomplete_object_not_scraped(self):
        # has repair_type but patches is not a dict -> not a valid repair object.
        rat = '{"repair_type": "config_patch", "patches": "model.input_dim=105"}'
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=rat))
        assert fold.spec is None and fold.reason == "folded_unparseable"

    def test_duplicate_identical_object_is_single_candidate(self):
        obj = '{"repair_type":"config_patch","patches":{"model.input_dim":105}}'
        fold = recover_folded_repair_spec(_args(repair_spec=None, rationale=f"{obj} restated: {obj}"))
        assert fold.spec == {"repair_type": "config_patch", "patches": {"model.input_dim": 105}}
        assert fold.reason == "recovered"
