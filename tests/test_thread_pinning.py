"""train.py refuses to run without single-threaded math (determinism guard).

Closes the host-run loophole: a bare `python train.py` outside the pinned
container can no longer silently produce non-canonical (unpinned) numbers.
The failure message must be actionable — it prints the exact export line.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TRAIN = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult" / "train.py"
CAPS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"]
EXPORT_LINE = "export " + " ".join(f"{c}=1" for c in CAPS)


def _run(env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(TRAIN), "--seed", "0"],
        capture_output=True, text=True, env=env,
    )


def test_unpinned_env_is_rejected_with_actionable_message():
    env = {c: "1" for c in CAPS}
    env["OMP_NUM_THREADS"] = ""  # unpin one cap
    r = _run(env)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "FATAL" in r.stderr
    assert "OMP_NUM_THREADS" in r.stderr           # names the offending cap
    assert EXPORT_LINE in r.stderr                 # the exact fix, all five caps
    assert "nondeterministic" in r.stderr.lower()  # says WHY


def test_missing_cap_is_rejected():
    env = {c: "1" for c in CAPS}
    del env["VECLIB_MAXIMUM_THREADS"]
    r = _run(env)
    assert r.returncode == 2
    assert "VECLIB_MAXIMUM_THREADS" in r.stderr
    assert EXPORT_LINE in r.stderr


def test_fully_pinned_env_passes_the_guard():
    # All caps set: the guard must NOT fire (any later failure is unrelated —
    # e.g. missing data — but must not be the guard's FATAL message).
    env = {c: "1" for c in CAPS}
    r = _run(env)
    assert "FATAL: training refuses to run" not in r.stderr
