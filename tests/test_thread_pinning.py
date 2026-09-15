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


def _run(cap_values: dict) -> subprocess.CompletedProcess:
    # Strip ALL caps from the inherited env, then set exactly the ones the test
    # provides — so a cap omitted here is genuinely unset (not shadowed by an
    # ambient value from the shell / container).
    env = {k: v for k, v in os.environ.items() if k not in CAPS}
    env.update(cap_values)
    return subprocess.run(
        [sys.executable, str(TRAIN), "--seed", "0"],
        capture_output=True, text=True, env=env,
    )


def test_unpinned_env_is_rejected_with_actionable_message():
    r = _run({c: "1" for c in CAPS if c != "OMP_NUM_THREADS"})  # OMP unset
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "FATAL" in r.stderr
    assert "OMP_NUM_THREADS" in r.stderr           # names the offending cap
    assert EXPORT_LINE in r.stderr                 # the exact fix, all five caps
    assert "nondeterministic" in r.stderr.lower()  # says WHY


def test_missing_cap_is_rejected():
    r = _run({c: "1" for c in CAPS if c != "VECLIB_MAXIMUM_THREADS"})  # VECLIB unset
    assert r.returncode == 2
    assert "VECLIB_MAXIMUM_THREADS" in r.stderr
    assert EXPORT_LINE in r.stderr


def test_not_one_is_rejected():
    r = _run({**{c: "1" for c in CAPS}, "OMP_NUM_THREADS": "4"})  # set but != 1
    assert r.returncode == 2
    assert "OMP_NUM_THREADS" in r.stderr


def test_fully_pinned_env_passes_the_guard():
    # All caps = 1: the guard must NOT fire (any later failure is unrelated —
    # e.g. missing data — but must not be the guard's FATAL message).
    r = _run({c: "1" for c in CAPS})
    assert "FATAL: training refuses to run" not in r.stderr


# --------------------------------------------------------------------------
# Spawn side: the harness helper that harness paths pass as subprocess env.
# The CHECK side (train.py) and the SPAWN side (harness.thread_pins) must agree.
# --------------------------------------------------------------------------


def test_spawn_caps_match_train_guard_caps():
    """harness.thread_pins.THREAD_CAPS must equal train.py's _THREAD_CAPS.

    If these drift, the spawn side pins a different set than the guard checks and
    the guard fires again — silently reintroducing the Stage-2 verify bug.
    """
    from harness.thread_pins import THREAD_CAPS
    from workloads.tabular_adult.train import _THREAD_CAPS

    assert tuple(THREAD_CAPS) == tuple(_THREAD_CAPS)
    assert set(THREAD_CAPS) == set(CAPS)


def test_pinned_thread_env_sets_all_five_over_an_unpinned_base():
    """pinned_thread_env re-pins every cap even when the base env has them unset
    or wrong — this is what makes a spawn work from a bare/unpinned parent."""
    from harness.thread_pins import pinned_thread_env

    base = {"OMP_NUM_THREADS": "8", "PATH": "/usr/bin"}  # unpinned + unrelated key
    env = pinned_thread_env(base)
    for c in CAPS:
        assert env[c] == "1", c
    assert env["PATH"] == "/usr/bin"  # unrelated keys preserved
    assert base["OMP_NUM_THREADS"] == "8"  # caller's dict not mutated
