"""Test-session configuration.

The canonical-platform guard (harness.platform_guard) refuses case/reference
builds under emulation so NON-CANONICAL artifacts are never produced. But the
test suite legitimately builds EPHEMERAL fixtures (tmp_path) via build_case, and
"emulation stays fine for tests". So we enable the loud, explicit override for the
whole test session: fixtures build under emulation, while committed-artifact paths
(scripts/build_all_cases.py, docker-reference, sweeps) — which do NOT set this —
stay guarded. On native CI the guard is a no-op anyway.
"""
import os


def pytest_configure(config):  # noqa: ARG001
    os.environ.setdefault("TRAINMD_ALLOW_NONCANONICAL_BUILD", "1")
