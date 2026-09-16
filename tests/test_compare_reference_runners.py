"""Two-runner reproducibility gate (STAGE3_PLAN §0.5 item 1 / §0.5 two-runner gate).

`scripts/compare_reference_runners.py` is microarch-aware per DECISIONS 2026-09-14 / L18:
  * SAME CPU model  → byte-exact required; ANY nonzero METRIC delta is a real bug → exit 1.
  * DIFFERENT CPU   → tolerance-based via verify_reference (means 2e-3, tolerance_lower 6e-3).
Timing fields (wall_time_sec, peak_memory_mb) legitimately vary and must be EXCLUDED from the delta.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from scripts.compare_reference_runners import ROOT, compare

_SCRIPT = ROOT / "scripts" / "compare_reference_runners.py"


def _stats(hidden_mean, tolerance_lower, val_mean=0.851, wall=12.3):
    return {
        "num_seeds": 30,
        "metric_visible_val_acc": {"mean": val_mean, "std": 0.001},
        "metric_hidden_test_acc": {
            "mean": hidden_mean, "std": 0.002,
            "min": hidden_mean - 0.004, "max": hidden_mean + 0.004,
            "tolerance_lower": tolerance_lower,
        },
        "wall_time_sec": {"mean": wall, "std": 1.0},   # timing — must be ignored
        "peak_memory_mb": {"max": 512.0},              # timing/resource — must be ignored
    }


def test_compare_ignores_timing_and_finds_identical():
    a = _stats(0.8476, 0.8435, wall=12.3)
    b = _stats(0.8476, 0.8435, wall=99.9)              # only timing differs
    max_d, field, n = compare(a, b)
    assert max_d == 0.0, (max_d, field)
    assert n > 0


def test_compare_reports_metric_delta():
    import copy
    a = _stats(0.8476, 0.8435)
    b = copy.deepcopy(a)
    b["metric_hidden_test_acc"]["mean"] += 1e-9      # perturb EXACTLY one field (no cascade to min/max)
    max_d, field, _ = compare(a, b)
    assert 0 < max_d < 1e-8
    assert field == "metric_hidden_test_acc.mean"


def _run(tmp_path: Path, a, b, cpu1, cpu2):
    p1, p2 = tmp_path / "s1.yaml", tmp_path / "s2.yaml"
    p1.write_text(yaml.safe_dump(a))
    p2.write_text(yaml.safe_dump(b))
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--stats1", str(p1), "--stats2", str(p2),
         "--cpu1", cpu1, "--cpu2", cpu2],
        capture_output=True, text=True)


_XEON = "Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz"
_EPYC = "AMD EPYC 7763 64-Core Processor"


def test_same_cpu_byte_exact_passes_on_identical(tmp_path):
    s = _stats(0.8476, 0.8435)
    r = _run(tmp_path, s, s, _XEON, _XEON)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "byte-exact" in r.stdout


def test_same_cpu_stops_on_any_metric_diff(tmp_path):
    a = _stats(0.8476, 0.8435)
    b = _stats(0.8476 + 1e-9, 0.8435)                  # same microarch → any diff is a real bug
    r = _run(tmp_path, a, b, _XEON, _XEON)
    assert r.returncode == 1, r.stdout
    assert "STOP" in r.stderr


def test_diff_cpu_tolerance_passes_within_bound(tmp_path):
    a = _stats(0.8476, 0.8435)
    b = _stats(0.8476 + 9e-4, 0.8435 + 1e-3)           # under 2e-3 mean / 6e-3 tolerance_lower
    r = _run(tmp_path, a, b, _XEON, _EPYC)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tolerance" in r.stdout.lower()


def test_diff_cpu_tolerance_stops_beyond_bound(tmp_path):
    a = _stats(0.8476, 0.8436)                         # 0.8476 - 2*0.002 = 0.8436 (derivation-consistent)
    b = _stats(0.8476 + 5e-3, 0.8486)                  # mean delta 5e-3 > 2e-3 → real regression
    r = _run(tmp_path, a, b, _XEON, _EPYC)
    assert r.returncode == 1, r.stdout + r.stderr
