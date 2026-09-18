"""Structural calibration-margin rule for POSITIVE-SYMPTOM rungs.

DECISIONS 2026-09-17. A reference change re-tests every rung against the new
band. Every rung must be calibrated with >= 2σ + 1e-3 margin on EVERY seed
against the band it will be judged by, on BOTH halves of its tier contract;
mild rungs sit near the bar by construction, so they are the ones that flake.

This module is the ONE definition of the two bars, imported by both the
operator build guards (build-time, per case) and the operator calibration
tests / sweep scripts. Keeping it here — not duplicated in each test — is what
makes the rule structural: a rung with sub-margin inflation cannot be built and
cannot pass tests, because both read the same bar from here.

Bars (band edges are the ±2σ reference band):

  positive-symptom (visible metric ABOVE the band):
      edge = mean_v + 2σ_v ; bar = edge + (2σ_v + 1e-3) = mean_v + 4σ_v + 1e-3
  degradation (hidden metric BELOW tolerance — silent tier only):
      tolerance_lower = mean_h - 2σ_h ; bar = tolerance_lower - (2σ_h + 1e-3)
                                            = mean_h - 4σ_h - 1e-3

Incidents that motivated the rule (all mild rungs near the bar, flaked on a
band change): lr_warmup ×2, label_corruption ×1, data_leakage ×1.
"""
from __future__ import annotations

MARGIN_SIGMA: float = 2.0    # σ multiples of margin required BEYOND the ±2σ band edge
MARGIN_EPS: float = 1e-3     # absolute floor so re-measurement noise cannot erase the margin


def positive_symptom_bar(stats: dict) -> float:
    """Visible metric must be >= this to be a margined misleading symptom.

    = mean_v + 4σ_v + 1e-3  (band edge mean+2σ, plus a 2σ+1e-3 margin).
    """
    v = stats["metric_visible_val_acc"]
    return v["mean"] + (2.0 + MARGIN_SIGMA) * v["std"] + MARGIN_EPS


def degradation_bar(stats: dict) -> float:
    """Hidden metric must be <= this to fail tolerance with margin (silent tier).

    = tolerance_lower - (2σ_h + 1e-3) = mean_h - 4σ_h - 1e-3.
    """
    h = stats["metric_hidden_test_acc"]
    return h["tolerance_lower"] - (MARGIN_SIGMA * h["std"] + MARGIN_EPS)
