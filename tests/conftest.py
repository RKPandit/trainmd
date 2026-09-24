"""Test-session configuration.

The canonical-platform guard (harness.platform_guard) refuses case/reference
builds under emulation so NON-CANONICAL artifacts are never produced. But the
test suite legitimately builds EPHEMERAL fixtures (tmp_path) via build_case, and
"emulation stays fine for tests". So we enable the loud, explicit override for the
whole test session: fixtures build under emulation, while committed-artifact paths
(scripts/build_all_cases.py, docker-reference, sweeps) — which do NOT set this —
stay guarded. On native CI the guard is a no-op anyway.
"""
import inspect
import os

import pytest


def pytest_configure(config):  # noqa: ARG001
    os.environ.setdefault("TRAINMD_ALLOW_NONCANONICAL_BUILD", "1")
    _REFERENCE_SNAPSHOT.update(_reference_hashes())


# ---- Committed reference files must be UNCHANGED by any test (DECISIONS 2026-09-23) -------------
# The only path that may write a committed reference is explicit reference generation
# (`make docker-reference`, CI reference-repro). A job once wrote THROUGH the neutral workload's
# symlinked reference; this session-level check fails the run if any test modified one.
import hashlib  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_REPO = _Path(__file__).resolve().parent.parent
_REFERENCE_SNAPSHOT: dict[str, str] = {}


def _reference_hashes() -> dict[str, str]:
    out = {}
    if not (_REPO / "workloads").is_dir():       # e.g. a pytester sandbox copy of this conftest
        return out
    for wl in sorted((_REPO / "workloads").iterdir()):
        ref = wl / "reference"
        if not ref.is_dir():
            continue
        for f in sorted(ref.glob("*")):          # top level only: runs/ is regenerated, gitignored
            if f.is_file():
                out[os.path.realpath(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def changed_reference_files() -> list[str]:
    now = _reference_hashes()
    keys = set(_REFERENCE_SNAPSHOT) | set(now)
    return sorted(str(_Path(k).relative_to(_REPO)) if k.startswith(str(_REPO)) else k
                  for k in keys if _REFERENCE_SNAPSHOT.get(k) != now.get(k))


def _fail_if_references_changed(session) -> None:
    """Called from the single pytest_sessionfinish below (a second hook definition in this module
    would silently REPLACE the first)."""
    changed = changed_reference_files()
    if changed:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            tr.write_line("FAIL: the test session MODIFIED committed reference file(s) — only explicit "
                          "reference generation may write them:\n  " + "\n  ".join(changed), red=True)
        session.exitstatus = 1


# A test is "slow" iff it TRAINS — builds a case, runs train.py, or verifies a
# repair (which retrains) — directly in its body or via a training fixture. Marked
# automatically at collection so the fast lane (`-m "not slow_integration"`, run on
# every push) never trains, and a NEW training test cannot silently sneak into it.
# The slow lane (`-m slow_integration`, run on PRs to main + nightly) trains.
_TRAIN_SOURCE_PATTERNS = (
    "_run_training", "build_case(", "verify_repair(", "score_recovery(",
    "_train_variant", "_train(", "_setup_tmp_workload", "reference_run",
)
_TRAIN_FIXTURES = {"built_case", "trained_output"}


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for item in items:
        trains = bool(set(getattr(item, "fixturenames", [])) & _TRAIN_FIXTURES)
        if not trains:
            fn = getattr(item, "function", None)
            try:
                src = inspect.getsource(fn) if fn is not None else ""
            except (OSError, TypeError):
                src = ""
            trains = any(p in src for p in _TRAIN_SOURCE_PATTERNS)
        if trains:
            item.add_marker(pytest.mark.slow_integration)


# ---- No test FILE may skip every one of its tests (CI; DECISIONS 2026-09-23) -------------------
# Three test groups were found silently skipping in CI (the gate tests 2026-09-20, R8's vacuous pass,
# and tests/test_static_agent.py — 15/15 skipped because CI builds no cases). With
# `--fail-on-all-skipped-file` (set by `make docker-test-fast` / `docker-test` / `docker-test-slow`),
# the session FAILS if any test file that ran at least one test had all of them skipped, or was
# skipped whole at collection. Deselected tests (markers) are not "run" and do not count.
from collections import defaultdict as _defaultdict  # noqa: E402

_FILE_OUTCOMES: dict[str, list[str]] = _defaultdict(list)
_FILES_SKIPPED_AT_COLLECTION: set[str] = set()


def pytest_addoption(parser):
    parser.addoption("--fail-on-all-skipped-file", action="store_true", default=False,
                     help="fail the session if any test file skips every one of its tests")
    parser.addoption("--fail-on-skip", action="store_true", default=False,
                     help="fail the session if ANY test is skipped (build-and-certify runs the "
                          "real-case tests this way, confirming every test runs somewhere)")


def pytest_collectreport(report):
    if report.skipped and report.nodeid.endswith(".py"):
        _FILES_SKIPPED_AT_COLLECTION.add(report.nodeid)


def pytest_runtest_logreport(report):
    path = report.nodeid.split("::", 1)[0]
    if report.when == "setup" and report.skipped:
        _FILE_OUTCOMES[path].append("skipped")
    elif report.when == "call":
        _FILE_OUTCOMES[path].append("skipped" if report.skipped else report.outcome)


def all_skipped_files() -> list[str]:
    files = {f for f, outs in _FILE_OUTCOMES.items() if outs and all(o == "skipped" for o in outs)}
    return sorted(files | _FILES_SKIPPED_AT_COLLECTION)


def skipped_tests() -> list[str]:
    return sorted(f for f, outs in _FILE_OUTCOMES.items() if "skipped" in outs) + sorted(
        _FILES_SKIPPED_AT_COLLECTION)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    # ONE hook for every session-end guard (a duplicate def would silently disable the earlier one).
    _fail_if_references_changed(session)
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if session.config.getoption("--fail-on-skip") and skipped_tests():
        msg = ("FAIL (--fail-on-skip): tests were SKIPPED in a run that must execute every test:\n  "
               + "\n  ".join(skipped_tests()))
        if tr is not None:
            tr.write_line(msg, red=True)
        session.exitstatus = 1
    if not session.config.getoption("--fail-on-all-skipped-file"):
        return
    bad = all_skipped_files()
    if bad:
        msg = ("FAIL (--fail-on-all-skipped-file): every test in these files was SKIPPED — a test that "
               "never runs proves nothing:\n  " + "\n  ".join(bad))
        if tr is not None:
            tr.write_line(msg, red=True)
        session.exitstatus = 1
