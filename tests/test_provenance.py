"""Provenance tests: schema conformance, environment capture, index, crash recovery, cost.

All tests here are fast (no training). They use stub agents on a built case.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case for provenance tests."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("test_provenance")

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


@pytest.fixture()
def trial_record(built_case):
    """Run one stub_oracle trial and return (record, project_root)."""
    case_dir, project_root = built_case
    from agents.stub_agent import StubAgent
    from harness.run_agent import run_trial

    record = run_trial(StubAgent(), case_dir, project_root)
    return record, project_root


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:

    def test_schema_conformance(self, trial_record):
        """Record has all required top-level blocks."""
        record, _ = trial_record
        for key in ("schema_version", "case_id", "agent_name", "run_id",
                     "status", "environment", "model", "usage",
                     "submission", "tool_transcript", "llm_transcript",
                     "scores", "budget"):
            assert key in record, f"Missing key: {key}"

    def test_schema_version(self, trial_record):
        record, _ = trial_record
        assert record["schema_version"] == "1.0"

    def test_status_completed(self, trial_record):
        record, _ = trial_record
        assert record["status"] == "completed"


# ---------------------------------------------------------------------------
# Environment block
# ---------------------------------------------------------------------------

class TestEnvironment:

    def test_git_commit_captured(self, trial_record):
        record, _ = trial_record
        commit = record["environment"]["harness_git_commit"]
        assert commit == "unknown" or re.fullmatch(r"[0-9a-f]{40}", commit)

    def test_git_dirty_flag(self, trial_record):
        record, _ = trial_record
        assert isinstance(record["environment"]["git_dirty"], bool)

    def test_case_card_hash(self, trial_record):
        record, _ = trial_record
        h = record["environment"]["case_card_hash"]
        assert re.fullmatch(r"[0-9a-f]{64}", h)

    def test_uv_lock_hash(self, trial_record):
        record, _ = trial_record
        h = record["environment"]["uv_lock_hash"]
        assert h is None or re.fullmatch(r"[0-9a-f]{64}", h)

    def test_python_version(self, trial_record):
        record, _ = trial_record
        expected_prefix = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert record["environment"]["python_version"].startswith(expected_prefix)

    def test_platform_captured(self, trial_record):
        record, _ = trial_record
        assert isinstance(record["environment"]["platform"], str)
        assert len(record["environment"]["platform"]) > 0

    def test_wall_clock(self, trial_record):
        record, _ = trial_record
        assert record["environment"]["wall_clock_sec"] > 0

    def test_timestamp_utc(self, trial_record):
        record, _ = trial_record
        ts = record["environment"]["timestamp_utc"]
        # Should parse as ISO-8601
        datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# Model block
# ---------------------------------------------------------------------------

class TestModel:

    def test_model_block_null_for_stub(self, trial_record):
        record, _ = trial_record
        model = record["model"]
        for key in ("model_id", "model_version", "provider", "temperature",
                     "top_p", "max_tokens", "stop_reason", "request_seed"):
            assert model[key] is None, f"model.{key} should be None for stub"


# ---------------------------------------------------------------------------
# Usage block
# ---------------------------------------------------------------------------

class TestUsage:

    def test_usage_block_zero_for_stub(self, trial_record):
        record, _ = trial_record
        usage = record["usage"]
        assert usage["llm_calls"] == 0
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["cached_tokens"] == 0
        assert usage["total_tokens"] == 0
        assert usage["estimated_cost_usd"] is None


# ---------------------------------------------------------------------------
# Scores block
# ---------------------------------------------------------------------------

class TestScores:

    def test_scores_embedded(self, trial_record):
        record, _ = trial_record
        scores = record["scores"]
        assert "detection" in scores
        assert "identification" in scores
        assert "evidence" in scores
        assert "safety" in scores

    def test_recovery_pending(self, trial_record):
        record, project_root = trial_record
        assert record["scores"]["recovery"] is None

        # Index line should also show pending
        index_path = project_root / "results" / "index.jsonl"
        assert index_path.exists()
        lines = index_path.read_text().strip().splitlines()
        # Find the line for this run
        for raw in lines:
            entry = json.loads(raw)
            if entry["run_id"] == record["run_id"]:
                assert entry["recovery_verdict"] == "pending"
                break
        else:
            pytest.fail(f"run_id {record['run_id']} not found in index.jsonl")


# ---------------------------------------------------------------------------
# Budget block
# ---------------------------------------------------------------------------

class TestBudget:

    def test_budget_block(self, trial_record):
        record, _ = trial_record
        budget = record["budget"]
        assert "tool_calls_used" in budget
        assert "tool_calls_total" in budget
        assert budget["tool_calls_used"] == 3  # read_config, query_metrics, submit
        assert budget["tool_calls_total"] > 0


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

class TestIndex:

    def test_index_jsonl_appended(self, trial_record):
        record, project_root = trial_record
        index_path = project_root / "results" / "index.jsonl"
        assert index_path.exists()
        lines = index_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        # Each line should be valid JSON
        for raw in lines:
            json.loads(raw)

    def test_index_jsonl_fields(self, trial_record):
        record, project_root = trial_record
        index_path = project_root / "results" / "index.jsonl"
        lines = index_path.read_text().strip().splitlines()
        for raw in lines:
            entry = json.loads(raw)
            if entry["run_id"] == record["run_id"]:
                for key in ("case_id", "agent_name", "run_id", "model_id",
                             "detection_correct", "identification_correct",
                             "evidence_f1", "recovery_verdict",
                             "total_tokens", "estimated_cost_usd",
                             "harness_git_commit", "status", "timestamp_utc"):
                    assert key in entry, f"Missing index field: {key}"
                break
        else:
            pytest.fail(f"run_id {record['run_id']} not found in index.jsonl")


# ---------------------------------------------------------------------------
# Record persistence
# ---------------------------------------------------------------------------

class TestRecordPersistence:

    def test_record_written_to_disk(self, trial_record):
        record, project_root = trial_record
        trials_dir = project_root / "results" / record["case_id"] / "trials"
        path = trials_dir / f"{record['agent_name']}_{record['run_id']}.yaml"
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert loaded["case_id"] == record["case_id"]

    def test_no_overwrite_final(self, trial_record):
        """Writing same run_id twice raises FileExistsError."""
        record, project_root = trial_record
        from harness.provenance import write_record
        with pytest.raises(FileExistsError):
            write_record(project_root, record)


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

class CrashingAgent:
    name = "stub_crasher"

    def run(self, case_dir, tools):
        tools.call("read_config")  # one call before crash
        raise RuntimeError("Simulated agent crash")


class TestCrashRecovery:

    def test_crash_flushes_partial(self, built_case):
        """Agent that raises mid-trial -> record on disk with status='crashed'."""
        case_dir, project_root = built_case
        from harness.run_agent import run_trial

        with pytest.raises(RuntimeError, match="Simulated agent crash"):
            run_trial(CrashingAgent(), case_dir, project_root)

        # Find the crashed record
        trials_dir = project_root / "results"
        crashed_files = list(trials_dir.rglob("stub_crasher_*.yaml"))
        assert len(crashed_files) >= 1
        loaded = yaml.safe_load(crashed_files[-1].read_text())
        assert loaded["status"] == "crashed"
        assert len(loaded["tool_transcript"]) == 1
        assert loaded["tool_transcript"][0]["tool_name"] == "read_config"

    def test_crash_preserves_usage_structure(self, built_case):
        """Crashed record has proper usage block structure."""
        case_dir, project_root = built_case

        trials_dir = project_root / "results"
        crashed_files = list(trials_dir.rglob("stub_crasher_*.yaml"))
        assert len(crashed_files) >= 1
        loaded = yaml.safe_load(crashed_files[-1].read_text())
        usage = loaded["usage"]
        assert "llm_calls" in usage
        assert "input_tokens" in usage
        assert usage["llm_calls"] == 0


# ---------------------------------------------------------------------------
# Cost computation (unit tests — no case needed)
# ---------------------------------------------------------------------------

class TestCostEstimation:

    def test_cost_known_model(self):
        from harness.pricing import estimate_cost
        result = estimate_cost("claude-sonnet-5", 1_000_000, 500_000)
        assert result is not None
        # 1M input * $2/M + 500K output * $10/M = $2 + $5 = $7
        assert abs(result.cost_usd - 7.0) < 0.001
        assert result.is_estimate is True

    def test_cost_with_cached(self):
        from harness.pricing import estimate_cost
        # 1M input, 200K cached, 500K output
        result = estimate_cost(
            "claude-sonnet-5",
            input_tokens=1_000_000,
            output_tokens=500_000,
            cached_tokens=200_000,
        )
        assert result is not None
        # billable_input = 1M - 200K = 800K
        # cost = 800K * $2/M + 500K * $10/M + 200K * $0.20/M
        #      = $1.60 + $5.00 + $0.04 = $6.64
        assert abs(result.cost_usd - 6.64) < 0.001

    def test_cost_unknown_model(self):
        from harness.pricing import estimate_cost
        result = estimate_cost("unknown-model-v99", 1000, 500)
        assert result is None

    def test_cost_null_model(self):
        from harness.pricing import estimate_cost
        result = estimate_cost(None, 1000, 500)
        assert result is None
