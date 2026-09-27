"""root_token_v3 (DECISIONS 2026-09-27): metric_inflation's mechanism-level alternative concept —
EVALUATION ON A SELECTED SUBSET of the validation data — derived from the operator's mechanism, requiring
BOTH a subset-selection term and an evaluation / metric context term.
"""
from __future__ import annotations

import pytest

from harness.scoring import score_identification
from operators.registry import all_operator_ids, get_operator

MI = "silent.metric_inflation.v1"


def _card(op_id):
    return {"operator_id": op_id, "accepted_classes": sorted(get_operator(op_id).accepted_classes())}


def ok(label, op_id=MI) -> bool:
    return score_identification({"diagnosis": {"operator_class": label}}, _card(op_id))["correct"]


@pytest.mark.parametrize("label", [
    "confidence_subset_metric_reporting",      # A07, A13 (second human audit: rated correct)
    "confidence_selected_eval_subset",         # A26
])
def test_audit_disagreement_labels_now_pass(label):
    assert ok(label)


@pytest.mark.parametrize("op_id", all_operator_ids())
def test_every_accepted_class_still_passes(op_id):
    for label in get_operator(op_id).accepted_classes():
        assert ok(label, op_id), (op_id, label)


@pytest.mark.parametrize("label", ["inflated_validation_accuracy", "biased_evaluation_metric",
                                   "cherry_picked_eval", "metric_inflation_via_subset"])
def test_previous_concept_labels_still_pass(label):
    assert ok(label)


@pytest.mark.parametrize("label", [
    "training_subset_selection", "feature_selection_bug", "data_filtering_error",
    "subset_sampling_error", "confidence_subset_filtering", "label_subset_noise", "subset", "selection",
])
def test_non_evaluation_subset_labels_fail(label):
    assert not ok(label)


@pytest.mark.parametrize("label", ["no_subset_evaluation", "not_filtered_validation_metric",
                                   "evaluation_subset_absent", "non_selected_eval_subset"])
def test_negation_still_applies_to_the_alternative(label):
    assert not ok(label)


@pytest.mark.parametrize("label", ["bias_variance_subset_evaluation", "inductive_bias_eval_subset"])
def test_vetoes_still_apply_to_the_alternative(label):
    assert not ok(label)


def test_uniqueness_still_rejects_a_two_concept_label():
    # names leakage AND a validation subset → two distinct concepts → rejected for either operator
    assert not ok("validation_subset_leakage", MI)
    assert not ok("validation_subset_leakage", "silent.data_leakage.v1")


def test_other_operators_unaffected():
    assert ok("label_noise_subset", "silent.label_corruption.v1")          # no evaluation context
    assert ok("excessive_learning_rate", "silent.lr_warmup.v1")
    assert ok("input_dimension_mismatch", "crash.shape_mismatch.v1")
