"""Tool layer tests (spec §6).

Tests cover: paging, metrics queries, config reading, code reading,
file listing, submit, budget exhaustion, path traversal security,
legitimate hidden-named files, and transcript logging.

All tests require a built case (which runs training once) but are
individually fast — they just read the produced artifacts.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ---------------------------------------------------------------------------
# Fixture: build one case, create ToolContext
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case and return (case_dir, project_root)."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("test_tools")

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


@pytest.fixture
def ctx(built_case):
    """Create a fresh ToolContext for each test."""
    case_dir, _ = built_case
    from harness.tools.tool_context import ToolContext
    from harness.tools.tools import register_all_tools

    tc = ToolContext(case_dir)
    register_all_tools(tc)
    return tc


# ---------------------------------------------------------------------------
# read_log tests
# ---------------------------------------------------------------------------

class TestReadLog:

    def test_basic(self, ctx):
        """Read first 50 lines of stdout.log."""
        result = ctx.call("read_log", artifact_id="logs/stdout.log")
        assert result["status"] == "ok"
        assert len(result["lines"]) > 0
        assert result["start_line"] == 1
        assert result["total_lines"] > 0

    def test_paging(self, ctx):
        """Read specific line range."""
        result = ctx.call("read_log", artifact_id="logs/stdout.log",
                          start_line=2, end_line=5)
        assert result["status"] == "ok"
        assert result["start_line"] == 2
        assert result["end_line"] <= 5
        assert len(result["lines"]) <= 4

    def test_page_cap(self, ctx):
        """Request 200 lines, get capped to 50."""
        result = ctx.call("read_log", artifact_id="logs/stdout.log",
                          start_line=1, end_line=200)
        assert result["status"] == "ok"
        assert result["end_line"] <= 50

    def test_beyond_eof(self, ctx):
        """Request past end, get clamped."""
        result = ctx.call("read_log", artifact_id="logs/stdout.log",
                          start_line=9999, end_line=10050)
        assert result["status"] == "ok"
        assert len(result["lines"]) == 0 or result["start_line"] <= result["total_lines"]

    def test_invalid_artifact(self, ctx):
        """Non-existent artifact → ARTIFACT_NOT_FOUND."""
        result = ctx.call("read_log", artifact_id="logs/nonexistent.log")
        assert result["status"] == "error"
        assert result["error"] == "ARTIFACT_NOT_FOUND"


# ---------------------------------------------------------------------------
# query_metrics tests
# ---------------------------------------------------------------------------

class TestQueryMetrics:

    def test_full_series(self, ctx):
        """Get all epochs of train_loss."""
        result = ctx.call("query_metrics", series="train_loss")
        assert result["status"] == "ok"
        assert result["series"] == "train_loss"
        assert len(result["values"]) > 0
        assert all("epoch" in v and "value" in v for v in result["values"])

    def test_window(self, ctx):
        """Filter epoch range."""
        result = ctx.call("query_metrics", series="train_loss",
                          start_epoch=0, end_epoch=2)
        assert result["status"] == "ok"
        for v in result["values"]:
            assert 0 <= v["epoch"] <= 2

    def test_agg_mean(self, ctx):
        """Aggregate mean over full series."""
        result = ctx.call("query_metrics", series="train_loss", agg="mean")
        assert result["status"] == "ok"
        assert result["agg"] == "mean"
        assert isinstance(result["value"], float)

    def test_agg_last(self, ctx):
        """Get last value."""
        result = ctx.call("query_metrics", series="train_loss", agg="last")
        assert result["status"] == "ok"
        assert result["agg"] == "last"
        assert isinstance(result["value"], float)

    def test_invalid_series(self, ctx):
        """Unknown series name → error."""
        result = ctx.call("query_metrics", series="nonexistent_metric")
        assert result["status"] == "error"
        assert result["error"] == "INVALID_ARGUMENTS"


# ---------------------------------------------------------------------------
# read_config tests
# ---------------------------------------------------------------------------

class TestReadConfig:

    def test_full(self, ctx):
        """Full config returned."""
        result = ctx.call("read_config")
        assert result["status"] == "ok"
        assert isinstance(result["value"], dict)
        assert result["key_path"] is None

    def test_key_path(self, ctx):
        """Specific nested key."""
        result = ctx.call("read_config", key_path="training")
        assert result["status"] == "ok"
        assert result["key_path"] == "training"
        assert isinstance(result["value"], dict)

    def test_invalid_path(self, ctx):
        """Non-existent key_path → error."""
        result = ctx.call("read_config", key_path="nonexistent.deep.key")
        assert result["status"] == "error"
        assert result["error"] == "INVALID_ARGUMENTS"


# ---------------------------------------------------------------------------
# read_code tests
# ---------------------------------------------------------------------------

class TestReadCode:

    def test_basic(self, ctx):
        """Read train.py first page."""
        result = ctx.call("read_code", path="train.py")
        assert result["status"] == "ok"
        assert result["path"] == "train.py"
        assert len(result["lines"]) > 0
        assert result["total_lines"] > 0

    def test_paging(self, ctx):
        """Read specific line range."""
        result = ctx.call("read_code", path="train.py",
                          start_line=5, end_line=10)
        assert result["status"] == "ok"
        assert result["start_line"] == 5
        assert result["end_line"] <= 10


# ---------------------------------------------------------------------------
# list_files tests
# ---------------------------------------------------------------------------

class TestListFiles:

    def test_list_files(self, ctx):
        """List workspace contents."""
        result = ctx.call("list_files")
        assert result["status"] == "ok"
        files = result["files"]
        assert "train.py" in files
        assert "config.yaml" in files
        # .data/ should appear as a directory entry
        assert ".data/" in files


# ---------------------------------------------------------------------------
# submit tests
# ---------------------------------------------------------------------------

class TestSubmit:

    def test_basic(self, ctx):
        """Valid submission accepted."""
        result = ctx.call("submit",
            diagnosis={"detected": True, "operator_class": "test"},
            evidence_refs=[],
            repair_spec={"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
        )
        assert result["status"] == "ok"
        assert result["submitted"] is True
        assert ctx.submission is not None

    def test_twice(self, ctx):
        """Second submission rejected (max_submissions=1)."""
        # First submission
        ctx.call("submit",
            diagnosis={"detected": True, "operator_class": "test"},
            evidence_refs=[],
            repair_spec={"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
        )
        # Second submission → rejected
        result = ctx.call("submit",
            diagnosis={"detected": True, "operator_class": "test"},
            evidence_refs=[],
            repair_spec={"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
        )
        assert result["status"] == "error"
        assert result["error"] == "SUBMISSION_LIMIT_REACHED"


# ---------------------------------------------------------------------------
# Budget tests
# ---------------------------------------------------------------------------

class TestBudget:

    def test_exhaustion(self, built_case):
        """Exhaust max_tool_calls, next call rejected."""
        case_dir, _ = built_case
        from harness.tools.tool_context import ToolContext
        from harness.tools.tools import register_all_tools

        tc = ToolContext(case_dir)
        register_all_tools(tc)

        # Exhaust budget by making max_tool_calls calls
        for _ in range(tc.budget_total):
            tc.call("read_config")

        assert tc.budget_remaining == 0
        result = tc.call("read_config")
        assert result["status"] == "error"
        assert result["error"] == "BUDGET_EXHAUSTED"

    def test_counts_errors(self, built_case):
        """Failed calls still decrement budget."""
        case_dir, _ = built_case
        from harness.tools.tool_context import ToolContext
        from harness.tools.tools import register_all_tools

        tc = ToolContext(case_dir)
        register_all_tools(tc)

        initial = tc.budget_remaining
        # Call a non-permitted tool (if any) or use a bad artifact
        tc.call("read_log", artifact_id="nonexistent.log")
        assert tc.budget_remaining == initial - 1


# ---------------------------------------------------------------------------
# Path security tests
# ---------------------------------------------------------------------------

class TestPathSecurity:

    def test_traversal_dotdot(self, ctx):
        """../hidden/verify.yaml → rejected."""
        result = ctx.call("read_code", path="../hidden/verify.yaml")
        assert result["status"] == "error"
        assert result["error"] == "INVALID_PATH"

    def test_traversal_absolute(self, ctx):
        """Absolute path → rejected."""
        result = ctx.call("read_code", path="/etc/passwd")
        assert result["status"] == "error"
        assert result["error"] == "INVALID_PATH"

    def test_outside_workspace(self, ctx):
        """../../etc/passwd → rejected."""
        result = ctx.call("read_code", path="../../etc/passwd")
        assert result["status"] == "error"
        assert result["error"] == "INVALID_PATH"

    def test_symlink_escape(self, built_case):
        """Symlink pointing outside workspace → rejected."""
        case_dir, _ = built_case
        from harness.tools.tool_context import ToolContext
        from harness.tools.tools import register_all_tools

        tc = ToolContext(case_dir)
        register_all_tools(tc)

        # Create a symlink inside workspace pointing outside
        workspace = case_dir / "workspace"
        escape_link = workspace / "escape_link"
        escape_link.symlink_to("/tmp")

        try:
            result = tc.call("read_code", path="escape_link")
            # Could be INVALID_PATH (if resolve escapes) or ARTIFACT_NOT_FOUND
            # The key is that it does NOT return actual content from /tmp
            assert result["status"] == "error"
        finally:
            escape_link.unlink()

    def test_legitimate_hidden_name(self, built_case):
        """A file named hidden_layers.txt inside workspace IS allowed."""
        case_dir, _ = built_case
        from harness.tools.tool_context import ToolContext
        from harness.tools.tools import register_all_tools

        tc = ToolContext(case_dir)
        register_all_tools(tc)

        # Create a legitimate file with "hidden" in the name
        workspace = case_dir / "workspace"
        legit_file = workspace / "hidden_layers.txt"
        legit_file.write_text("layer1: 128\nlayer2: 64\n")

        try:
            result = tc.call("read_code", path="hidden_layers.txt")
            assert result["status"] == "ok"
            assert "layer1: 128" in result["lines"][0]
        finally:
            legit_file.unlink()

    def test_tool_not_permitted(self, built_case):
        """Call a tool not in permitted_tools → rejected."""
        case_dir, _ = built_case
        from harness.tools.tool_context import ToolContext
        from harness.tools.tools import register_all_tools

        tc = ToolContext(case_dir)
        register_all_tools(tc)

        # "secret_tool" is not in permitted_tools
        result = tc.call("secret_tool")
        assert result["status"] == "error"
        assert result["error"] == "TOOL_NOT_PERMITTED"


# ---------------------------------------------------------------------------
# Deferred tool tests
# ---------------------------------------------------------------------------

class TestDeferredTools:

    def test_diff_config_not_available(self, ctx):
        result = ctx.call("diff_config")
        assert result["status"] == "error"
        assert result["error"] == "TOOL_NOT_AVAILABLE"

    def test_run_training_not_available(self, ctx):
        result = ctx.call("run_training")
        assert result["status"] == "error"
        assert result["error"] == "TOOL_NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# Transcript logging test
# ---------------------------------------------------------------------------

class TestTranscript:

    def test_call_transcript(self, ctx):
        """Verify transcript records all calls with indices."""
        ctx.call("read_config")
        ctx.call("list_files")
        ctx.call("read_config", key_path="training")

        transcript = ctx.transcript
        assert len(transcript) == 3
        assert transcript[0]["index"] == 0
        assert transcript[0]["tool_name"] == "read_config"
        assert transcript[1]["index"] == 1
        assert transcript[1]["tool_name"] == "list_files"
        assert transcript[2]["index"] == 2
        assert transcript[2]["tool_name"] == "read_config"
        assert transcript[2]["arguments"]["key_path"] == "training"

        # All entries have timestamps
        for entry in transcript:
            assert "timestamp" in entry
            assert isinstance(entry["timestamp"], float)
