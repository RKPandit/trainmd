"""The DECLARED benign-change qualification test (STAGE4 4.0.6) — logic only, no training."""
from __future__ import annotations

import numpy as np
import pytest

from scripts import qualify_benign as q

SIGMA = 0.0018
SEEDS = list(range(30))
rng = np.random.default_rng(0)
CLEAN = {s: (0.848 + rng.normal(0, SIGMA), 0.856) for s in SEEDS}


def _cand(shift, scale=1.0, noise=0.0002):
    r = np.random.default_rng(1)
    return {s: (0.848 + (CLEAN[s][0] - 0.848) * scale + shift + r.normal(0, noise), 0.856 + shift)
            for s in SEEDS}


def test_exact_noop_qualifies():
    r = q.qualify(CLEAN, dict(CLEAN), SIGMA)
    assert r["qualified"] and r["mean_d"] == 0 and r["sd_ratio"] == 1


def test_small_shift_qualifies_large_shift_rejected():
    assert q.qualify(CLEAN, _cand(0.1 * SIGMA), SIGMA)["qualified"]
    big = q.qualify(CLEAN, _cand(1.5 * SIGMA), SIGMA)
    assert not big["qualified"] and not big["mean_ok"]
    assert not q.qualify(CLEAN, _cand(-1.5 * SIGMA), SIGMA)["qualified"]      # two-sided


def test_spread_change_rejected_even_with_zero_mean_shift():
    r = q.qualify(CLEAN, _cand(0.0, scale=2.0), SIGMA)
    assert r["sd_ratio"] > 1.5 and not r["spread_ok"] and not r["qualified"]


def test_threshold_is_declared_constant():
    assert q.DELTA_SIGMAS == 1.0 and q.SPREAD_BOUNDS == (2 / 3, 3 / 2)
    assert q.T_95_ONE_SIDED[29] == pytest.approx(1.699127)


def test_apply_edits_changes_or_adds_without_mutating_input():
    base = {"training": {"lr": 0.01}}
    out = q.apply_edits(base, {"training.lr": 0.005, "data.label_noise_fraction": 0.0})
    assert out == {"training": {"lr": 0.005}, "data": {"label_noise_fraction": 0.0}}
    assert base == {"training": {"lr": 0.01}}


def test_candidates_cover_both_edit_forms():
    forms = {c["form"] for c in q.CANDIDATES.values()}
    assert forms == {"changed", "added"}
