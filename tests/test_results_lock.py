"""results/ locks (DECISIONS 2026-09-27 — after a rescore and a running pilot raced on results/index.jsonl).

Proves: while another live process holds the sweep lock, every writer refuses (record write, index append,
index update, the rescore / rebuild scripts); the holder itself may write; a dead-pid lock on this host is
stale; a lock from another host is treated as live; concurrent index updates from separate processes leave a
valid index holding every row; a sweep phase holds the lock while it runs and releases it after.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from harness import results_lock as rl
from harness.provenance import append_index, update_index, write_record

ROOT = Path(__file__).resolve().parent.parent


def _write_lock(root: Path, pid: int, host: str | None = None, sweep: str = "other"):
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / ".sweep.lock").write_text(json.dumps(
        {"pid": pid, "host": host or socket.gethostname(), "sweep": sweep, "phase": "agents", "since": "t"}))


@pytest.fixture
def live_other_pid():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p.pid
    p.kill()
    p.wait()


def _record(run_id: str, case_id: str = "case_0001") -> dict:
    return {"run_id": run_id, "case_id": case_id, "agent_name": "react", "status": "complete",
            "environment": {"timestamp_utc": "2026-09-27T00:00:00Z"},
            "conditions": {"sweep_name": "s"}, "scores": {}, "submission": None}


def test_no_lock_allows_writes(tmp_path):
    rl.assert_can_write(tmp_path)
    append_index(tmp_path, _record("r1"))
    assert (tmp_path / "results" / "index.jsonl").read_text().count("\n") == 1


def test_another_live_holder_blocks_every_writer(tmp_path, live_other_pid):
    _write_lock(tmp_path, live_other_pid)
    with pytest.raises(rl.ResultsLocked, match="other"):
        rl.assert_can_write(tmp_path)
    with pytest.raises(rl.ResultsLocked):
        write_record(tmp_path, _record("r1"))
    with pytest.raises(rl.ResultsLocked):
        append_index(tmp_path, _record("r1"))
    with pytest.raises(rl.ResultsLocked):
        update_index(tmp_path, _record("r1"))
    with pytest.raises(rl.ResultsLocked):
        with rl.sweep_lock(tmp_path, "mine", "agents"):
            pass
    assert not (tmp_path / "results" / "index.jsonl").exists()
    assert not list((tmp_path / "results").glob("*/trials/*"))


def test_rebuild_script_refuses_under_a_live_lock(tmp_path, live_other_pid):
    _write_lock(tmp_path, live_other_pid)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_index.py"), "--project-root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "ResultsLocked" in r.stderr
    assert not (tmp_path / "results" / "index.jsonl").exists()


def test_the_holder_itself_may_write(tmp_path):
    with rl.sweep_lock(tmp_path, "mine", "agents") as info:
        assert rl.holder(tmp_path)["pid"] == os.getpid() == info["pid"]
        write_record(tmp_path, _record("r1"))
        update_index(tmp_path, _record("r1"))
    assert not (tmp_path / "results" / ".sweep.lock").exists()           # released
    rl.assert_can_write(tmp_path)


def test_dead_pid_lock_on_this_host_is_stale(tmp_path):
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    _write_lock(tmp_path, p.pid)
    assert rl.holder(tmp_path) is None
    rl.assert_can_write(tmp_path)
    with rl.sweep_lock(tmp_path, "mine", "verify"):                       # a stale lock is replaced
        assert rl.holder(tmp_path)["sweep"] == "mine"


def test_lock_from_another_host_is_treated_as_live(tmp_path):
    _write_lock(tmp_path, 1, host="some-container-host")
    with pytest.raises(rl.ResultsLocked):
        rl.assert_can_write(tmp_path)


def test_unreadable_lock_is_treated_as_live(tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / ".sweep.lock").write_text("{not json")
    with pytest.raises(rl.ResultsLocked):
        rl.assert_can_write(tmp_path)


def _hammer(root: str, worker: int, n: int):
    for i in range(n):
        update_index(Path(root), _record(f"w{worker}_r{i}"))


def test_concurrent_index_updates_from_separate_processes_keep_every_row(tmp_path):
    workers, n = 4, 40
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_hammer, args=(str(tmp_path), w, n)) for w in range(workers)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    lines = (tmp_path / "results" / "index.jsonl").read_text().splitlines()
    ids = [json.loads(ln)["run_id"] for ln in lines]                     # every line parses (no torn / NUL line)
    assert sorted(ids) == sorted(f"w{w}_r{i}" for w in range(workers) for i in range(n))


def test_update_index_replaces_in_place_atomically(tmp_path):
    update_index(tmp_path, _record("r1"))
    update_index(tmp_path, _record("r2"))
    rec = _record("r1")
    rec["environment"]["timestamp_utc"] = "2026-09-28T00:00:00Z"
    update_index(tmp_path, rec)
    rows = [json.loads(ln) for ln in (tmp_path / "results" / "index.jsonl").read_text().splitlines()]
    assert [r["run_id"] for r in rows].count("r1") == 1 and len(rows) == 2
    assert next(r for r in rows if r["run_id"] == "r1")["timestamp_utc"] == "2026-09-28T00:00:00Z"
    assert not list((tmp_path / "results").glob(".index.jsonl.*.tmp"))  # no temp file left behind


def test_sweep_phases_hold_and_release_the_lock(tmp_path, monkeypatch):
    from harness import sweep
    seen = {}

    def fake_agents(project_root, name, max_cost_usd, **kw):
        seen["agents"] = rl.holder(project_root)
        return {"ok": True}

    def fake_verify(project_root, name, *, recovery_fn=None):
        seen["verify"] = rl.holder(project_root)
        return {"ok": True}

    monkeypatch.setattr(sweep, "_run_agents", fake_agents)
    monkeypatch.setattr(sweep, "_run_verify", fake_verify)
    assert sweep.run_agents(tmp_path, "s", 1.0) == {"ok": True}
    assert sweep.run_verify(tmp_path, "s") == {"ok": True}
    assert seen["agents"]["sweep"] == "s" and seen["agents"]["phase"] == "agents"
    assert seen["agents"]["pid"] == os.getpid()
    assert seen["verify"]["phase"] == "verify"
    assert rl.holder(tmp_path) is None


def test_sweep_phase_releases_the_lock_on_error(tmp_path, monkeypatch):
    from harness import sweep

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(sweep, "_run_agents", boom)
    with pytest.raises(RuntimeError):
        sweep.run_agents(tmp_path, "s", 1.0)
    assert rl.holder(tmp_path) is None


def test_second_sweep_refuses_to_start_while_one_runs(tmp_path, live_other_pid):
    from harness import sweep
    _write_lock(tmp_path, live_other_pid, sweep="stage4_part2_pilot")
    with pytest.raises(rl.ResultsLocked, match="stage4_part2_pilot"):
        sweep.run_agents(tmp_path, "s", 1.0)
