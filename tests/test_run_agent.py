"""Agent runner tests (spec §6).

Tests the Agent protocol, run_trial function, and both stub agents.
All tests require a built case but are individually fast.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ---------------------------------------------------------------------------
# Fixture: build one case
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case and return (case_dir, project_root)."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("test_run_agent")

    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml"]:
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


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------

class TestProtocol:

    def test_stub_agent_protocol(self):
        """StubAgent satisfies Agent protocol."""
        from agents.stub_agent import StubAgent
        from harness.run_agent import Agent

        agent = StubAgent()
        assert isinstance(agent, Agent)
        assert agent.name == "stub_oracle"

    def test_stub_degenerate_protocol(self):
        """StubDegenerateAgent satisfies Agent protocol."""
        from agents.stub_degenerate import StubDegenerateAgent
        from harness.run_agent import Agent

        agent = StubDegenerateAgent()
        assert isinstance(agent, Agent)
        assert agent.name == "stub_degenerate"


# ---------------------------------------------------------------------------
# Trial runner tests
# ---------------------------------------------------------------------------

class TestRunTrial:

    def test_produces_record(self, built_case):
        """run_trial returns valid trial record with all fields."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial

        record = run_trial(StubAgent(), case_dir, project_root)

        assert "case_id" in record
        assert "agent_name" in record
        assert record["agent_name"] == "stub_oracle"
        assert "run_id" in record
        assert "submission" in record
        assert "tool_transcript" in record
        assert "budget_used" in record
        assert "budget_total" in record
        assert "tokens_used" in record
        assert record["tokens_used"] == 0

    def test_record_written_to_disk(self, built_case):
        """Trial YAML written to results/<case_id>/trials/."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial

        record = run_trial(StubAgent(), case_dir, project_root)

        trials_dir = project_root / "results" / record["case_id"] / "trials"
        yaml_files = list(trials_dir.glob(f"{record['agent_name']}_{record['run_id']}.yaml"))
        assert len(yaml_files) == 1

        with open(yaml_files[0]) as f:
            loaded = yaml.safe_load(f)
        assert loaded["case_id"] == record["case_id"]
        assert loaded["agent_name"] == "stub_oracle"

    def test_stub_agent_submission(self, built_case):
        """StubAgent submission has correct shape."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial

        record = run_trial(StubAgent(), case_dir, project_root)
        sub = record["submission"]

        assert sub is not None
        assert "diagnosis" in sub
        assert sub["diagnosis"]["detected"] is True
        assert sub["diagnosis"]["operator_class"] == "lr_misconfiguration"
        assert "evidence_refs" in sub
        assert len(sub["evidence_refs"]) == 2
        assert "repair_spec" in sub
        assert sub["repair_spec"]["patches"]["training.lr"] == 0.01

    def test_stub_agent_tool_calls(self, built_case):
        """Transcript has 3 entries (read_config, query_metrics, submit)."""
        case_dir, project_root = built_case
        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial

        record = run_trial(StubAgent(), case_dir, project_root)

        assert record["budget_used"] == 3
        transcript = record["tool_transcript"]
        assert len(transcript) == 3
        assert transcript[0]["tool_name"] == "read_config"
        assert transcript[1]["tool_name"] == "query_metrics"
        assert transcript[2]["tool_name"] == "submit"

    def test_stub_degenerate_submission(self, built_case):
        """StubDegenerateAgent submission has correct shape (empty evidence)."""
        case_dir, project_root = built_case
        from agents.stub_degenerate import StubDegenerateAgent
        from harness.run_agent import run_trial

        record = run_trial(StubDegenerateAgent(), case_dir, project_root)
        sub = record["submission"]

        assert sub is not None
        assert sub["diagnosis"]["detected"] is True
        assert sub["diagnosis"]["operator_class"] == "data_corruption"
        assert sub["evidence_refs"] == []
        assert sub["repair_spec"]["patches"]["training.lr"] == 0.01
        assert record["budget_used"] == 1
