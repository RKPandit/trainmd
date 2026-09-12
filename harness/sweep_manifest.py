"""Sweep manifest — the paper's compute statement + pre-registration artifact.

Written to a TRACKED path (``sweeps/<sweep_name>_manifest.yaml``), NOT the
gitignored ``results/``, because it is committed evidence of what was run and at
what cost.  Runner-filled slots (hardware, per-phase totals, actual spend) are
left null so the runner fills them from the machine and the provider console —
never invented.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def new_manifest(sweep_name: str, estimated_spend_usd: float | None = None,
                 actual_spend_usd: float | None = None) -> dict:
    """Build a manifest dict with runner-filled slots as nulls."""
    return {
        "sweep_name": sweep_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "estimated_spend_usd": estimated_spend_usd,
        # Entered manually at sweep end from the provider console.
        "actual_spend_usd": actual_spend_usd,
        # The runner fills these from the machine — null now, never invented.
        "hardware": {
            "cpu_model": None,
            "cpu_cores": None,
            "ram_gb": None,
            "os": None,
            "uv_lock_hash": None,
            "git_commit": None,
        },
        # Per-phase token/cost/wall totals — filled by the runner.
        "per_phase_totals": None,
    }


def write_sweep_manifest(
    project_root: Path,
    sweep_name: str,
    estimated_spend_usd: float | None = None,
    actual_spend_usd: float | None = None,
) -> Path:
    """Write (or overwrite) the tracked manifest for *sweep_name*; return its path."""
    manifest = new_manifest(sweep_name, estimated_spend_usd, actual_spend_usd)
    out = Path(project_root) / "sweeps" / f"{sweep_name}_manifest.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.dump(manifest, default_flow_style=False, sort_keys=False))
    return out
