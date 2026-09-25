"""A crash can never leave a trial record the index doesn't know about.

run_trial writes a "partial" crash-checkpoint record before the agent runs. A process KILLED mid-trial
(no `finally`, no exception handling — e.g. SIGKILL, OOM, os._exit) used to leave that record without an
index.jsonl row: H8's case_0041 checkpoint then failed validate-all C7 and blocked Part 1's sweep
preconditions. The checkpoint's index row is now written together with the record. This test kills a
real trial mid-run in a subprocess and asserts record and index agree.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / "tests" / "fixtures" / "cases_public" / "case_0001"


def _records(root: Path) -> dict[str, dict]:
    return {r["run_id"]: r for r in (yaml.safe_load(p.read_text())
                                     for p in (root / "results").glob("*/trials/*.yaml"))}


def _index(root: Path) -> dict[str, dict]:
    p = root / "results" / "index.jsonl"
    return {e["run_id"]: e for e in (json.loads(l) for l in p.read_text().splitlines() if l.strip())}


def test_process_killed_mid_trial_leaves_record_and_index_in_agreement(tmp_path):
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from harness.run_agent import run_trial

        class Killer:
            name = "killer_agent"
            def run(self, case_dir, tools):
                tools.call("list_files")      # do some work, then die hard: no finally runs
                os._exit(9)

        run_trial(Killer(), Path({str(CASE)!r}), project_root=Path({str(tmp_path)!r}))
    """)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 9, proc.stderr[-2000:]
    records, index = _records(tmp_path), _index(tmp_path)
    assert len(records) == 1, "the crash checkpoint record must exist"
    (run_id, rec), = records.items()
    assert rec["status"] == "partial"
    assert set(index) == set(records), "every record on disk must have an index row"
    assert index[run_id]["status"] == "partial"


def test_completed_trial_rewrites_its_checkpoint_row_not_duplicates(tmp_path):
    from harness.run_agent import run_trial

    class Quiet:
        name = "quiet_agent"

        def run(self, case_dir, tools):
            tools.call("list_files")

    run_trial(Quiet(), CASE, project_root=tmp_path, score=False)
    lines = [l for l in (tmp_path / "results" / "index.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1                                   # one row per record, rewritten in place
    assert json.loads(lines[0])["status"] == "completed"
    assert set(_index(tmp_path)) == set(_records(tmp_path))
