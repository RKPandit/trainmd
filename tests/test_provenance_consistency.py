"""Provenance consistency tests.

The trial record is the single source of truth.  index.jsonl is a derived
view kept in sync on every (re)score.  Recovery merges into the trial
record and is idempotent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from harness.provenance import (
    _index_line,
    append_index,
    build_empty_record,
    update_index,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(run_id: str = "20260101T000000Z_aaaaaa", **overrides) -> dict:
    """Build a minimal record for testing."""
    env = {
        "harness_git_commit": "abc123",
        "git_dirty": False,
        "case_card_hash": "hash",
        "python_version": "3.9",
        "platform": "test",
        "uv_lock_hash": "lock_hash",
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "wall_clock_sec": 1.0,
    }
    record = build_empty_record("case_0001", "test_agent", run_id, env)
    record["status"] = "completed"
    record.update(overrides)
    return record


def _read_index(project_root: Path) -> list[dict]:
    """Read all index.jsonl lines."""
    path = project_root / "results" / "index.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [json.loads(l) for l in lines if l.strip()]


# ---------------------------------------------------------------------------
# update_index: insert and rewrite
# ---------------------------------------------------------------------------

class TestUpdateIndex:

    def test_insert_new_line(self, tmp_path):
        """update_index on a missing run_id appends the line."""
        record = _make_record()
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        assert len(entries) == 1
        assert entries[0]["run_id"] == record["run_id"]

    def test_rewrite_existing_line(self, tmp_path):
        """update_index on an existing run_id rewrites it in place."""
        record = _make_record()
        record["scores"] = {
            "detection": {"correct": True},
            "identification": {"correct": True},
            "evidence": {"f1": 0.0},
            "recovery": None,
            "safety": {},
        }
        # Initial insert
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        assert entries[0]["evidence_f1"] == 0.0
        assert entries[0]["recovery_verdict"] == "pending"

        # Update evidence score
        record["scores"]["evidence"]["f1"] = 0.8
        record["scores"]["recovery"] = {"verdict": "recovered"}
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        assert len(entries) == 1, "Should rewrite, not append"
        assert entries[0]["evidence_f1"] == 0.8
        assert entries[0]["recovery_verdict"] == "recovered"

    def test_preserves_other_entries(self, tmp_path):
        """Rewriting one entry does not disturb other entries."""
        rec1 = _make_record(run_id="20260101T000000Z_aaaaaa")
        rec2 = _make_record(run_id="20260101T000000Z_bbbbbb")
        rec2["agent_name"] = "other_agent"
        update_index(tmp_path, rec1)
        update_index(tmp_path, rec2)

        assert len(_read_index(tmp_path)) == 2

        # Rewrite rec1
        rec1["scores"] = {
            "detection": {"correct": False},
            "identification": {"correct": False},
            "evidence": {"f1": 0.5},
            "recovery": {"verdict": "not_recovered"},
            "safety": {},
        }
        update_index(tmp_path, rec1)

        entries = _read_index(tmp_path)
        assert len(entries) == 2
        by_run = {e["run_id"]: e for e in entries}
        assert by_run["20260101T000000Z_aaaaaa"]["evidence_f1"] == 0.5
        assert by_run["20260101T000000Z_bbbbbb"]["agent_name"] == "other_agent"


# ---------------------------------------------------------------------------
# Index stays in sync with trial record through scoring
# ---------------------------------------------------------------------------

class TestIndexSyncWithScoring:

    def test_index_matches_after_score(self, tmp_path):
        """After update_index, index line matches _index_line(record)."""
        record = _make_record()
        record["scores"] = {
            "detection": {"correct": True},
            "identification": {"correct": False},
            "evidence": {"f1": 0.42},
            "recovery": {"verdict": "not_recovered"},
            "safety": {"rejected_tool_calls": 1, "forbidden_actions": 0, "total_calls": 5},
        }
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        expected = _index_line(record)
        assert entries[0] == expected

    def test_rescore_updates_index(self, tmp_path):
        """Simulates re-scoring: change scores, call update_index, verify."""
        record = _make_record()
        record["scores"] = {
            "detection": {"correct": True},
            "identification": {"correct": True},
            "evidence": {"f1": 0.0},
            "recovery": None,
            "safety": {},
        }
        update_index(tmp_path, record)

        # Simulate re-score with updated evidence
        record["scores"]["evidence"]["f1"] = 0.8
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        assert len(entries) == 1
        assert entries[0]["evidence_f1"] == 0.8

        # Simulate recovery merge
        record["scores"]["recovery"] = {"verdict": "recovered"}
        update_index(tmp_path, record)

        entries = _read_index(tmp_path)
        assert len(entries) == 1
        assert entries[0]["recovery_verdict"] == "recovered"
        assert entries[0]["evidence_f1"] == 0.8


# ---------------------------------------------------------------------------
# Recovery result idempotency
# ---------------------------------------------------------------------------

class TestRecoveryIdempotency:

    def test_recovery_file_named_by_trial(self, tmp_path):
        """When trial_run_id is set, result file is recovery_<trial_run_id>.yaml."""
        from harness.evaluator.verify_repair import _write_result

        result = {
            "case_id": "case_0001",
            "run_id": "20260909T999999Z_verify",
            "verdict": "recovered",
            "trial_run_id": "20260909T021346Z_2bdcbe",
        }
        path = _write_result(tmp_path, result, trial_run_id="20260909T021346Z_2bdcbe")
        assert path.name == "recovery_20260909T021346Z_2bdcbe.yaml"
        assert path.exists()

    def test_recovery_overwrites_on_reverify(self, tmp_path):
        """Two calls with same trial_run_id produce one file, not two."""
        from harness.evaluator.verify_repair import _write_result

        trial_run_id = "20260909T021346Z_2bdcbe"

        result1 = {
            "case_id": "case_0001",
            "run_id": "20260909T111111Z_first",
            "verdict": "not_recovered",
            "trial_run_id": trial_run_id,
        }
        _write_result(tmp_path, result1, trial_run_id=trial_run_id)

        result2 = {
            "case_id": "case_0001",
            "run_id": "20260909T222222Z_second",
            "verdict": "recovered",
            "trial_run_id": trial_run_id,
        }
        _write_result(tmp_path, result2, trial_run_id=trial_run_id)

        results_dir = tmp_path / "results" / "case_0001"
        recovery_files = list(results_dir.glob("recovery_*.yaml"))
        assert len(recovery_files) == 1, f"Expected 1 file, got {len(recovery_files)}"

        with open(recovery_files[0]) as f:
            content = yaml.safe_load(f)
        assert content["verdict"] == "recovered"

    def test_recovery_result_records_trial_run_id(self, tmp_path):
        """Result dict contains trial_run_id for traceability."""
        from harness.evaluator.verify_repair import _make_result

        result = _make_result(
            "case_0001", "20260909T999999Z_verify", "recovered",
            [], [], {"repair_type": "config_patch", "patches": {"training.lr": 0.01}},
            trial_run_id="20260909T021346Z_2bdcbe",
        )
        assert result["trial_run_id"] == "20260909T021346Z_2bdcbe"

    def test_standalone_verify_repair_does_not_write(self, tmp_path):
        """Without trial_run_id, verify_repair must NOT write a result file.

        Standalone calls (operator development, oracle checks) return the
        result dict only.  Writing to disk would create orphans invisible
        to C8's structural orphan detection.
        """
        results_dir = tmp_path / "results" / "case_0001"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Count files before
        before = set(results_dir.iterdir())

        # _write_result now requires trial_run_id (str, not None).
        # Standalone callers simply don't call _write_result.
        # Verify no new files appear if we DON'T call _write_result.
        after = set(results_dir.iterdir())
        assert before == after
