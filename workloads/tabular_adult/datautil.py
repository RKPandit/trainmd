"""Deterministic data-subset helpers for the training script.

Self-contained (numpy + stdlib only) so it can sit beside ``train.py`` inside
a portable training workspace and be imported as a sibling module.  Shared by
the training script and by harness/operator code that needs the identical,
reproducible selection.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np


def _stable_seed(n_items: int) -> int:
    """A process-stable 32-bit seed derived from the item count alone.

    Uses SHA-256 (never Python's salted ``hash()``) so the value is identical
    across processes and runs, and depends only on ``n_items`` — not on any
    training seed or selection size.
    """
    return int.from_bytes(hashlib.sha256(str(n_items).encode()).digest()[:4], "big")


def nested_prefix_indices(n_items: int, fraction: float) -> np.ndarray:
    """Return a deterministic prefix of a fixed data-derived permutation.

    One permutation of ``range(n_items)`` is derived from ``n_items`` alone;
    this returns its first ``ceil(fraction * n_items)`` entries.  Because every
    fraction slices the *same* permutation, the selection for a larger fraction
    is a strict superset of the selection for a smaller one — monotone in
    ``fraction`` by construction, with no dependence on the training seed and
    identical across processes.

    Args:
        n_items: Number of items to select from (e.g. training-set size).
        fraction: Share of items to select, in [0, 1].

    Returns:
        A 1-D ``int64`` array of selected indices (empty when fraction <= 0).
    """
    if fraction <= 0:
        return np.empty(0, dtype=np.int64)
    rng = np.random.RandomState(_stable_seed(n_items))
    perm = rng.permutation(n_items)
    k = min(math.ceil(fraction * n_items), n_items)
    return perm[:k].astype(np.int64)
