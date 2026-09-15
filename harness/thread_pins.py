"""Canonical thread-pinning for harness paths that spawn ``train.py``.

``train.py`` REFUSES to train unless all five BLAS/OpenMP thread caps are pinned
to ``1`` (``require_pinned_threads`` — unpinned float reductions are order-
nondeterministic, which broke reference reproducibility once; RESEARCH_LOG 26).
So every harness path that launches ``train.py`` as a subprocess must put those
caps in the CHILD environment **explicitly**, rather than relying on the parent
shell to have exported them. Passing them here is what makes training behave
identically inside the canonical container (which sets them) and on a bare host.

Why this module exists: the Stage-2 gate ran the verify phase from an unpinned
macOS shell; ``verify_repair`` spawned ``train.py`` with no ``env=``, so every
recovery rerun hit the guard and ``sys.exit(2)`` BEFORE training — 138 cells
became ``not_recovered`` by construction (docs/audits/sweep_stage2gate_2026-09-14.md).
Injecting the pins at the spawn site closes that hole for every caller.

This is the SPAWN side; ``train.py`` owns the CHECK side. The two cap tuples must
stay in agreement — ``tests/test_thread_pinning.py`` asserts they match.
"""
from __future__ import annotations

import os

# MUST match workloads/tabular_adult/train.py::_THREAD_CAPS exactly.
THREAD_CAPS: tuple[str, ...] = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def pinned_thread_env(base: dict | None = None) -> dict:
    """Return a copy of *base* (default ``os.environ``) with all five caps = ``1``.

    Pass the result as ``subprocess.run(..., env=pinned_thread_env())`` so the
    spawned ``train.py`` satisfies ``require_pinned_threads`` regardless of what
    the parent environment did or did not export.
    """
    env = dict(os.environ if base is None else base)
    for cap in THREAD_CAPS:
        env[cap] = "1"
    return env
