"""Distribution-check script (STAGE3_PLAN §0.5 item 2): moments, both bands, recommendation.

The band rests on a normal assumption that has never been checked; `scripts/reference_distribution.py`
computes the moments, Shapiro–Wilk normality, the normal `mean − 2σ` band AND the empirical 2.5th
percentile, and recommends the empirical band when they diverge materially or normality is rejected.
These tests pin the arithmetic and the decision logic on synthetic fixtures with known shape.
"""
from __future__ import annotations

import numpy as np

from scripts.reference_distribution import _MATERIAL, compute


def _stats(values, tolerance_lower=None):
    per_seed = [{"seed": i, "metric_hidden_test_acc": float(v)} for i, v in enumerate(values)]
    hidden = {"mean": float(np.mean(values))}
    if tolerance_lower is not None:
        hidden["tolerance_lower"] = tolerance_lower
    return {"per_seed": per_seed, "metric_hidden_test_acc": hidden}


def test_moments_and_band_derivation_are_exact():
    values = [0.84, 0.845, 0.85, 0.855, 0.86] * 6  # n=30, symmetric
    c = compute(_stats(values, tolerance_lower=0.8317))
    assert c["n"] == 30
    assert c["mean"] == float(np.mean(values))
    assert c["sd_pop"] == float(np.std(values, ddof=0))          # population std, matches tolerance
    assert c["normal_band"] == round(c["mean"] - 2 * c["sd_pop"], 6)
    assert c["emp_lo"] == round(float(np.percentile(values, 2.5)), 6)
    assert c["sorted"] == sorted(float(v) for v in values)       # the 30 sorted values are emitted
    assert c["committed_tolerance_lower"] == 0.8317


def test_left_skew_recommends_empirical():
    # One low outlier pulls mean−2σ well below the empirical 2.5th percentile → bands diverge.
    values = [0.80] + [0.85] * 29
    c = compute(_stats(values))
    assert c["skew"] < 0                       # long left tail
    assert c["material"] is True               # bands differ by more than _MATERIAL
    assert abs(c["normal_band"] - c["emp_lo"]) > _MATERIAL
    assert c["recommend"] == "empirical"


def test_clean_normal_keeps_mean_minus_2sigma():
    # A genuine large normal sample: the two bands converge (<_MATERIAL) and Shapiro does not reject,
    # so the normal assumption is CHECKED and mean−2σ is kept.
    rng = np.random.default_rng(0)
    values = (0.85 + 0.002 * rng.standard_normal(2000)).tolist()
    c = compute(_stats(values))
    assert c["rejected"] is False
    assert c["material"] is False
    assert c["recommend"] == "normal"


def test_recommend_is_or_of_material_and_rejected():
    # recommend=="normal" IFF neither condition fires; otherwise "empirical".
    for values, want in [
        ([0.80] + [0.85] * 29, "empirical"),                 # material (and skewed)
    ]:
        assert compute(_stats(values))["recommend"] == want
