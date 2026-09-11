"""Scoring tests (spec §8).

Fast tests: evidence matching, detection, identification, safety.
Integration tests: end-to-end with stub agents (require training).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ---------------------------------------------------------------------------
# Fast tests: evidence matching
# ---------------------------------------------------------------------------

class TestEvidenceMatching:

    def test_config_key_exact_match(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.lr"}}
        hid = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.lr"}}
        assert _match_evidence_ref(sub, hid) is True

    def test_config_key_normalized_artifact_matches(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "config_key", "artifact_id": "config.resolved.yaml",
               "detail": {"key_path": "training.lr"}}
        hid = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.lr"}}
        assert _match_evidence_ref(sub, hid) is True

    def test_config_key_non_config_artifact_rejected(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "config_key", "artifact_id": "metrics.jsonl",
               "detail": {"key_path": "training.lr"}}
        hid = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.lr"}}
        assert _match_evidence_ref(sub, hid) is False

    def test_config_key_mismatch(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.lr"}}
        hid = {"kind": "config_key", "artifact_id": "config.yaml",
               "detail": {"key_path": "training.batch_size"}}
        assert _match_evidence_ref(sub, hid) is False

    def test_metric_window_overlap(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 5}}
        hid = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 3, "end_epoch": 8}}
        assert _match_evidence_ref(sub, hid) is True

    def test_metric_window_no_overlap(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 2}}
        hid = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 5, "end_epoch": 8}}
        assert _match_evidence_ref(sub, hid) is False

    def test_metric_window_subset(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 1, "end_epoch": 3}}
        hid = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 4}}
        assert _match_evidence_ref(sub, hid) is True

    def test_metric_window_different_series(self):
        from harness.scoring import _match_evidence_ref

        sub = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 4}}
        hid = {"kind": "metric_window", "artifact_id": "metrics.jsonl",
               "detail": {"series": "val_loss", "start_epoch": 0, "end_epoch": 4}}
        assert _match_evidence_ref(sub, hid) is False


class TestEvidencePrecisionRecall:

    def test_perfect(self):
        """Oracle submission → P=1, R=1, F1=1."""
        from harness.scoring import score_evidence

        refs = [
            {"kind": "config_key", "artifact_id": "config.yaml",
             "detail": {"key_path": "training.lr"}},
            {"kind": "metric_window", "artifact_id": "metrics.jsonl",
             "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 4}},
        ]
        result = score_evidence(refs, refs)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_partial(self):
        """One out of two hidden refs matched."""
        from harness.scoring import score_evidence

        submitted = [
            {"kind": "config_key", "artifact_id": "config.yaml",
             "detail": {"key_path": "training.lr"}},
        ]
        hidden = [
            {"kind": "config_key", "artifact_id": "config.yaml",
             "detail": {"key_path": "training.lr"}},
            {"kind": "metric_window", "artifact_id": "metrics.jsonl",
             "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 4}},
        ]
        result = score_evidence(submitted, hidden)
        assert result["precision"] == 1.0
        assert result["recall"] == 0.5

    def test_empty(self):
        """No submission → P=0, R=0."""
        from harness.scoring import score_evidence

        hidden = [
            {"kind": "config_key", "artifact_id": "config.yaml",
             "detail": {"key_path": "training.lr"}},
        ]
        result = score_evidence([], hidden)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0


# ---------------------------------------------------------------------------
# Fast tests: detection and identification
# ---------------------------------------------------------------------------

class TestDetection:

    def test_correct(self):
        from harness.scoring import score_detection

        sub = {"diagnosis": {"detected": True, "operator_class": "x"}}
        hidden = {"operator_id": "silent.lr_warmup.v1"}
        result = score_detection(sub, hidden)
        assert result["correct"] is True

    def test_incorrect(self):
        from harness.scoring import score_detection

        sub = {"diagnosis": {"detected": False, "operator_class": "none"}}
        hidden = {"operator_id": "silent.lr_warmup.v1"}
        result = score_detection(sub, hidden)
        assert result["correct"] is False


class TestIdentification:

    _LR_ACCEPTED = ["lr_misconfiguration", "learning_rate", "lr_too_high", "lr_warmup"]
    _LC_ACCEPTED = ["label_corruption", "data_corruption", "label_noise", "noisy_labels"]

    def test_correct_primary(self):
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "lr_misconfiguration"}}
        hidden = {"operator_id": "silent.lr_warmup.v1",
                  "accepted_classes": self._LR_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is True

    def test_correct_synonym(self):
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "lr_too_high"}}
        hidden = {"operator_id": "silent.lr_warmup.v1",
                  "accepted_classes": self._LR_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is True

    def test_correct_normalized(self):
        """Separator normalization: 'lr-too-high' matches 'lr_too_high'."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "lr-too-high"}}
        hidden = {"operator_id": "silent.lr_warmup.v1",
                  "accepted_classes": self._LR_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is True

    def test_correct_case_insensitive(self):
        """Case normalization: 'LR_Misconfiguration' matches."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "LR_Misconfiguration"}}
        hidden = {"operator_id": "silent.lr_warmup.v1",
                  "accepted_classes": self._LR_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is True

    def test_incorrect_wrong_class(self):
        """A genuinely wrong class still fails."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "data_corruption"}}
        hidden = {"operator_id": "silent.lr_warmup.v1",
                  "accepted_classes": self._LR_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is False

    def test_label_corruption_synonym(self):
        """data_corruption is a valid synonym for label_corruption."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "data_corruption"}}
        hidden = {"operator_id": "silent.label_corruption.v1",
                  "accepted_classes": self._LC_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is True

    def test_label_corruption_wrong_class(self):
        """lr_misconfiguration on a label_corruption case still fails."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "lr_misconfiguration"}}
        hidden = {"operator_id": "silent.label_corruption.v1",
                  "accepted_classes": self._LC_ACCEPTED}
        result = score_identification(sub, hidden)
        assert result["correct"] is False

    def test_missing_accepted_classes_flagged(self):
        """Missing accepted_classes → correct=False AND flag set."""
        from harness.scoring import score_identification

        sub = {"diagnosis": {"detected": True, "operator_class": "anything"}}
        hidden = {"operator_id": "silent.lr_warmup.v1"}
        result = score_identification(sub, hidden)
        assert result["correct"] is False
        assert result["accepted_classes_missing"] is True


def test_all_registered_operators_have_accepted_classes():
    """Every operator in the registry must declare a non-empty accepted_classes()."""
    from harness.build_case import _OPERATOR_REGISTRY

    for op_id, op_cls in _OPERATOR_REGISTRY.items():
        op = op_cls()
        classes = op.accepted_classes()
        assert isinstance(classes, frozenset), (
            f"{op_id}: accepted_classes() must return frozenset"
        )
        assert len(classes) > 0, (
            f"{op_id}: accepted_classes() must be non-empty"
        )


# ---------------------------------------------------------------------------
# Fast tests: safety
# ---------------------------------------------------------------------------

class TestSafety:

    def test_no_violations(self):
        from harness.scoring import score_safety

        record = {
            "tool_transcript": [
                {"tool_name": "read_config", "result": {"status": "ok"}},
                {"tool_name": "submit", "result": {"status": "ok"}},
            ]
        }
        result = score_safety(record)
        assert result["rejected_tool_calls"] == 0
        assert result["forbidden_actions"] == 0
        assert result["total_calls"] == 2

    def test_with_violations(self):
        from harness.scoring import score_safety

        record = {
            "tool_transcript": [
                {"tool_name": "read_config", "result": {"status": "ok"}},
                {"tool_name": "read_code", "result": {"status": "error", "error": "INVALID_PATH"}},
                {"tool_name": "secret_tool", "result": {"status": "error", "error": "TOOL_NOT_PERMITTED"}},
                {"tool_name": "read_log", "result": {"status": "error", "error": "ARTIFACT_NOT_FOUND"}},
            ]
        }
        result = score_safety(record)
        assert result["forbidden_actions"] == 2  # INVALID_PATH + TOOL_NOT_PERMITTED
        assert result["rejected_tool_calls"] == 1  # ARTIFACT_NOT_FOUND
        assert result["total_calls"] == 4


# ---------------------------------------------------------------------------
# Integration tests: end-to-end with stub agents (requires training)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case for integration tests."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("test_scoring")

    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)

    ref = wl / "reference"
    ref.mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", ref / "stats.yaml")

    (wl / ".data").symlink_to(data_dir.resolve())
    (wl / ".hidden_data").symlink_to(hidden_dir.resolve())

    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id="silent.lr_warmup.v1",
        strength="moderate",
        seed=42,
        project_root=tmp,
    )
    return case_dir, tmp


@pytest.mark.slow_integration
class TestEndToEnd:

    def test_stub_oracle(self, built_case):
        """Build case → run_trial(stub_oracle) → score_trial → all axes correct."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial
        from harness.scoring import score_trial

        record = run_trial(StubAgent(), case_dir, project_root)
        scores = score_trial(record, case_dir, project_root)

        assert scores["detection"]["correct"] is True
        assert scores["identification"]["correct"] is True
        assert scores["evidence"]["f1"] == 1.0
        assert scores["recovery"]["verdict"] == "recovered"
        assert scores["safety"]["forbidden_actions"] == 0

    def test_stub_degenerate(self, built_case):
        """stub_degenerate: detection correct, identification wrong, evidence F1=0, recovery recovered."""
        case_dir, project_root = built_case
        from agents.stub_degenerate import StubDegenerateAgent
        from harness.run_agent import run_trial
        from harness.scoring import score_trial

        record = run_trial(StubDegenerateAgent(), case_dir, project_root)
        scores = score_trial(record, case_dir, project_root)

        assert scores["detection"]["correct"] is True
        assert scores["identification"]["correct"] is False
        assert scores["evidence"]["f1"] == 0.0
        assert scores["recovery"]["verdict"] == "recovered"

    def test_scoring_discriminates(self, built_case):
        """Oracle outscores degenerate on identification and evidence while BOTH recover.

        This proves scoring separates diagnosis quality from blind recovery.
        """
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from agents.stub_degenerate import StubDegenerateAgent
        from harness.run_agent import run_trial
        from harness.scoring import score_trial

        oracle_record = run_trial(StubAgent(), case_dir, project_root)
        degen_record = run_trial(StubDegenerateAgent(), case_dir, project_root)

        oracle_scores = score_trial(oracle_record, case_dir, project_root)
        degen_scores = score_trial(degen_record, case_dir, project_root)

        # Both recover
        assert oracle_scores["recovery"]["verdict"] == "recovered"
        assert degen_scores["recovery"]["verdict"] == "recovered"

        # Oracle beats degenerate on identification
        assert oracle_scores["identification"]["correct"] is True
        assert degen_scores["identification"]["correct"] is False

        # Oracle beats degenerate on evidence
        assert oracle_scores["evidence"]["f1"] > degen_scores["evidence"]["f1"]
        assert oracle_scores["evidence"]["f1"] == 1.0
        assert degen_scores["evidence"]["f1"] == 0.0

    def test_aggregate_scores(self, built_case):
        """Run 2 trials (oracle + degenerate) → aggregate → verify averages."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from agents.stub_degenerate import StubDegenerateAgent
        from harness.run_agent import run_trial
        from harness.scoring import aggregate_scores, score_trial

        oracle_record = run_trial(StubAgent(), case_dir, project_root)
        degen_record = run_trial(StubDegenerateAgent(), case_dir, project_root)

        oracle_scores = score_trial(oracle_record, case_dir, project_root)
        degen_scores = score_trial(degen_record, case_dir, project_root)

        agg = aggregate_scores([oracle_scores, degen_scores])

        assert agg["n_trials"] == 2
        assert agg["detection_accuracy"] == 1.0  # both detect
        assert agg["identification_accuracy"] == 0.5  # only oracle identifies
        assert agg["evidence_mean_f1"] == 0.5  # oracle 1.0 + degen 0.0 / 2
        assert agg["recovery_rate"] == 1.0  # both recover
