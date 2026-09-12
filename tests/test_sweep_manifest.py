"""Sweep manifest — tracked compute statement (spec §8)."""
from __future__ import annotations

import yaml

from harness.sweep_manifest import new_manifest, write_sweep_manifest


def test_manifest_has_estimated_and_actual_and_hardware_nulls():
    m = new_manifest("sweep1", estimated_spend_usd=18.0)
    assert m["sweep_name"] == "sweep1"
    assert m["estimated_spend_usd"] == 18.0
    assert m["actual_spend_usd"] is None  # entered manually at sweep end
    # Runner-filled slots default to null (never invented).
    for slot in ("cpu_model", "cpu_cores", "ram_gb", "os", "uv_lock_hash", "git_commit"):
        assert m["hardware"][slot] is None
    assert m["per_phase_totals"] is None


def test_actual_spend_is_settable():
    m = new_manifest("sweep1", estimated_spend_usd=18.0, actual_spend_usd=19.42)
    assert m["actual_spend_usd"] == 19.42


def test_written_to_tracked_sweeps_path(tmp_path):
    out = write_sweep_manifest(tmp_path, "sweep1", estimated_spend_usd=18.0)
    # NOT under the gitignored results/ — under a tracked sweeps/ dir.
    assert out == tmp_path / "sweeps" / "sweep1_manifest.yaml"
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert data["sweep_name"] == "sweep1"
    assert "hardware" in data and "actual_spend_usd" in data
