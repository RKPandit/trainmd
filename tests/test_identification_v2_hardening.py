"""STAGE 4.0.1 — root_token_v2 identification hardening.

The v1 rule matched long concept stems as FREE SUBSTRINGS, so fault NEGATIONS
("no_leakage") and OFF-CONCEPT collisions ("memory_leak") scored CORRECT. v2
closes this by principle: negation detection, whole-token/declared-inflection
matching (never a free substring), and a per-operator off-concept veto list.

Guarantees under test:
  * the external reviewer's three labels FAIL,
  * ~20 adversarial negations / off-concept strings per operator FAIL,
  * EVERY accepted_classes entry PASSES (exact path) — and the oracle label
    (accepted[0]) with it,
  * the previously-passing token-path synonyms (correction #1) still PASS.
"""
from __future__ import annotations

import pytest

from harness.scoring import score_identification
from operators.registry import all_operator_ids, get_operator


def _score(pred: str, op_id: str, accepted) -> bool:
    return score_identification(
        {"diagnosis": {"detected": True, "operator_class": pred}},
        {"operator_id": op_id, "accepted_classes": list(accepted)},
    )["correct"]


# The single concept word each operator's fault centers on, for generating
# negation adversaries. (label_corruption needs the LABEL concept word too.)
_CONCEPT_WORD = {
    "silent.lr_warmup.v1": "learning_rate",
    "silent.label_corruption.v1": "label_noise",
    "silent.data_leakage.v1": "leakage",
    "silent.data_leakage_neutral.v1": "leakage",
    "silent.metric_inflation.v1": "inflation",
    "crash.shape_mismatch.v1": "shape_mismatch",
    "control.healthy.v1": "none",
}


def _negation_adversaries(concept: str) -> list[str]:
    return [
        f"no_{concept}", f"not_{concept}", f"non_{concept}",
        f"without_{concept}", f"zero_{concept}", f"{concept}_absent",
        f"{concept}_free", f"no_evidence_{concept}"[:60], f"no_sign_of_{concept}",
        f"neither_{concept}_nor_drift",
    ]


# Off-concept collisions per concept token (whole token present, wrong fault).
_OFF_CONCEPT = {
    "silent.data_leakage.v1": [
        "memory_leak", "memory_leakage", "gpu_memory_leak", "ram_leak",
        "vram_leak", "resource_leak", "gradient_leak", "buffer_leak",
        "socket_leak", "connection_leak", "file_handle_leak", "fd_leak",
    ],
    "silent.data_leakage_neutral.v1": [
        "memory_leak", "gpu_leak", "resource_leak", "gradient_leak",
    ],
    "silent.metric_inflation.v1": [
        "inductive_bias", "bias_variance", "bias_variance_tradeoff",
        "weight_bias", "bias_term", "bias_unit", "bias_node",
        "bias_initialization", "bias_gradient",
    ],
}


class TestReviewerFlaggedLabels:
    """The exact strings the external reviewer flagged must be scored WRONG."""

    _DL = "silent.data_leakage.v1"
    _DL_ACC = ["data_leakage", "feature_leakage", "target_leakage", "label_leakage"]

    def test_no_leakage_fails(self):
        assert _score("no_leakage", self._DL, self._DL_ACC) is False

    def test_memory_leak_fails(self):
        assert _score("memory_leak", self._DL, self._DL_ACC) is False

    def test_leakage_absent_fails(self):
        assert _score("leakage_absent", self._DL, self._DL_ACC) is False


class TestNegationAdversaries:
    def test_every_faulty_operator_rejects_negations(self):
        failures = []
        for op_id in all_operator_ids():
            if get_operator(op_id).layer == "control":
                continue  # "none"/negations are the CORRECT answer on any control (healthy or benign)
            acc = list(get_operator(op_id).accepted_classes())
            for adv in _negation_adversaries(_CONCEPT_WORD[op_id]):
                if _score(adv, op_id, acc):
                    failures.append((op_id, adv))
        assert not failures, f"negations scored correct: {failures}"


class TestOffConceptVetoes:
    def test_every_off_concept_collision_rejected(self):
        failures = []
        for op_id, advs in _OFF_CONCEPT.items():
            acc = list(get_operator(op_id).accepted_classes())
            for adv in advs:
                if _score(adv, op_id, acc):
                    failures.append((op_id, adv))
        assert not failures, f"off-concept collisions scored correct: {failures}"


class TestAcceptedAndOraclePass:
    def test_every_accepted_class_passes_exact(self):
        failures = []
        for op_id in all_operator_ids():
            acc = list(get_operator(op_id).accepted_classes())
            for entry in acc:
                if not _score(entry, op_id, acc):
                    failures.append((op_id, entry))
        assert not failures, f"accepted_classes entries that no longer pass: {failures}"

    def test_oracle_label_passes(self):
        # oracle_agent submits sorted(accepted_classes)[0].
        for op_id in all_operator_ids():
            acc = sorted(get_operator(op_id).accepted_classes())
            if not acc:
                continue
            assert _score(acc[0], op_id, acc), (op_id, acc[0])


class TestCorrection1SynonymsStillPass:
    """Token-path synonyms credited under correction #1 must remain credited."""

    CASES = [
        ("missing_lr_schedule", "silent.lr_warmup.v1"),
        ("high_learning_rate_without_decay", "silent.lr_warmup.v1"),
        ("excessive_learning_rate", "silent.lr_warmup.v1"),
        ("noisy_label_data", "silent.label_corruption.v1"),
        ("excessive_label_noise", "silent.label_corruption.v1"),
        ("label_derived_feature_leakage", "silent.data_leakage.v1"),
        ("label_leaking_aux_feature", "silent.data_leakage.v1"),
        ("magic_feature_leak", "silent.data_leakage_neutral.v1"),
        ("input_dimension_mismatch", "crash.shape_mismatch.v1"),
        ("config_input_dim_mismatch", "crash.shape_mismatch.v1"),
        ("eval_subset_fraction_inflation", "silent.metric_inflation.v1"),
        ("subset_accuracy_inflation", "silent.metric_inflation.v1"),
    ]

    @pytest.mark.parametrize("pred,op_id", CASES)
    def test_synonym_passes(self, pred, op_id):
        acc = list(get_operator(op_id).accepted_classes())
        assert _score(pred, op_id, acc) is True


class TestRequiredGuaranteesPreserved:
    _LR = ("silent.lr_warmup.v1", ["lr_misconfiguration", "learning_rate", "lr_too_high"])
    _CTRL = ("control.healthy.v1", ["none", "healthy", "no_incident", "no_fault", "nothing_wrong"])

    def test_none_on_faulty_fails(self):
        assert _score("none", *self._LR) is False

    def test_none_on_control_passes(self):
        assert _score("none", *self._CTRL) is True

    def test_short_stem_no_substring_bleed(self):
        # 'controller' must not match lr_warmup via a stray 'lr'.
        assert _score("controller_error", *self._LR) is False

    def test_two_fault_label_rejected(self):
        assert _score("lr_and_leakage", "silent.data_leakage.v1",
                      ["data_leakage", "leaky_feature"]) is False
