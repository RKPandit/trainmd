#!/usr/bin/env python3
"""Distribution check for the reference hidden-test metric (STAGE3_PLAN §0.5 item 2).

The tolerance band rests on a normal-distribution assumption ("~5% outside by construction") that has
never been checked. Given the per-seed hidden test values in a `stats.yaml`, this reports the moments,
a Shapiro-Wilk normality test (with the explicit n≈30 low-power caveat), BOTH candidate bands — the
normal-assumption `mean − 2σ` and the EMPIRICAL 2.5th percentile — states which `tolerance_lower`
uses and why, recommends the empirical percentile if the two differ materially or normality is
rejected, and emits the sorted values so a reader sees the distribution without rerunning anything.
Read-only; emits a markdown report. Population std (ddof=0) matches how `tolerance_lower` is computed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy import stats as sps

ROOT = Path(__file__).resolve().parent.parent
_MATERIAL = 1e-3  # bands differing by more than this (on the ~0.85 metric) is "material"


def _values(stats: dict, metric="metric_hidden_test_acc") -> list[float]:
    return [r[metric] for r in stats.get("per_seed", []) if metric in r]


def compute(stats: dict, metric="metric_hidden_test_acc") -> dict:
    """Pure numeric summary of the per-seed hidden distribution (testable, no formatting).

    ``normal_band`` = mean − 2σ (ddof=0, matching how ``tolerance_lower`` is derived);
    ``emp_lo`` = empirical 2.5th percentile. ``recommend`` is "empirical" when the two bands differ by
    more than ``_MATERIAL`` OR Shapiro–Wilk rejects normality (p<0.05), else "normal".
    """
    v = np.array(_values(stats, metric), dtype=float)
    n = len(v)
    mean = float(v.mean())
    sd_pop = float(v.std(ddof=0))          # matches tolerance_lower = mean - 2*std
    sd_samp = float(v.std(ddof=1)) if n > 1 else float("nan")
    normal_band = round(mean - 2 * sd_pop, 6)
    emp_lo = round(float(np.percentile(v, 2.5)), 6)
    emp_hi = round(float(np.percentile(v, 97.5)), 6)
    W, p = (sps.shapiro(v) if 3 <= n <= 5000 else (float("nan"), float("nan")))
    material = abs(normal_band - emp_lo) > _MATERIAL
    rejected = (p == p) and p < 0.05     # p==p is False for NaN
    return {
        "n": n, "mean": mean, "sd_pop": sd_pop, "sd_samp": sd_samp,
        "median": float(np.median(v)), "min": float(v.min()), "max": float(v.max()),
        "skew": float(sps.skew(v)), "kurtosis": float(sps.kurtosis(v)),
        "shapiro_W": float(W), "shapiro_p": float(p),
        "normal_band": normal_band, "emp_lo": emp_lo, "emp_hi": emp_hi,
        "material": bool(material), "rejected": bool(rejected),
        "recommend": "empirical" if (material or rejected) else "normal",
        "sorted": sorted(v.tolist()),
        "committed_tolerance_lower": stats.get(metric, {}).get("tolerance_lower"),
    }


def report(stats: dict, metric="metric_hidden_test_acc") -> str:
    c = compute(stats, metric)
    rec = ("EMPIRICAL 2.5th percentile — "
           + ("normality rejected (p<0.05)" if c["rejected"] else "")
           + (" and " if (c["rejected"] and c["material"]) else "")
           + ("normal vs empirical bands differ materially" if c["material"] else "")) \
        if c["recommend"] == "empirical" \
        else "keep mean − 2σ (normal assumption CHECKED: not rejected, and the two bands agree)"

    L = [f"## Reference distribution — {metric} (n={c['n']} seeds)", "",
         f"- mean = **{c['mean']:.6f}**  ·  sd(pop, ddof=0) = **{c['sd_pop']:.6f}**  "
         f"·  sd(sample, ddof=1) = {c['sd_samp']:.6f}",
         f"- median = {c['median']:.6f}  ·  min = {c['min']:.6f}  ·  max = {c['max']:.6f}",
         f"- skew = {c['skew']:.4f}  ·  excess kurtosis = {c['kurtosis']:.4f}",
         f"- **Shapiro–Wilk**: W = {c['shapiro_W']:.4f}, p = {c['shapiro_p']:.4f}  "
         f"_(caveat: n≈{c['n']} has limited power to detect non-normality — a non-rejection is weak evidence)_",
         "",
         "### Bands",
         f"- (a) normal-assumption `mean − 2σ` = **{c['normal_band']:.6f}**",
         f"- (b) EMPIRICAL 2.5th percentile = **{c['emp_lo']:.6f}**  (empirical 95% interval "
         f"[{c['emp_lo']:.6f}, {c['emp_hi']:.6f}])",
         f"- `tolerance_lower` uses **(a) mean − 2σ = {c['normal_band']:.6f}**"
         + (f" (committed candidate: {c['committed_tolerance_lower']})"
            if c["committed_tolerance_lower"] is not None else "")
         + " — by construction (spec §3).",
         f"- **Recommendation:** {rec}.",
         "",
         "### Sorted hidden-test values", "",
         "| # | value |", "|---|---|"]
    for i, x in enumerate(c["sorted"], 1):
        L.append(f"| {i} | {x:.6f} |")
    L += [""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", type=Path,
                    default=ROOT / "workloads" / "tabular_adult" / "reference" / "stats.yaml")
    ap.add_argument("--out", type=Path, default=None, help="write the report here (default: stdout)")
    a = ap.parse_args()
    stats = yaml.safe_load(a.stats.read_text())
    md = report(stats)
    if a.out:
        a.out.write_text(md)
        print(f"reference_distribution: wrote {a.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
