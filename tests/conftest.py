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
