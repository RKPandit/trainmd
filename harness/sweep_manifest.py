"""Sweep manifest — the paper's compute statement + pre-registration artifact.

Written to a TRACKED path (``sweeps/<sweep_name>_manifest.yaml``), NOT the
gitignored ``results/``.  Hardware identity is captured ONCE at run start;
per-phase totals (paid agent phase, free verify phase) are finalized at run end.
``actual_spend_usd`` is entered manually from the provider console.
"""
from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


def capture_hardware(project_root: Path) -> dict:
    """Capture the machine identity once (best-effort; nulls where unavailable)."""
    ram_gb = None
    try:  # POSIX physical memory
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 2)
    except (ValueError, OSError, AttributeError):
        pass
    uv_lock = Path(project_root) / "uv.lock"
    uv_hash = (
        hashlib.sha256(uv_lock.read_bytes()).hexdigest() if uv_lock.exists() else None
    )
    commit = None
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, cwd=project_root)
        commit = r.stdout.strip() if r.returncode == 0 else None
    except FileNotFoundError:
        pass
    system = platform.system()  # "Linux" / "Darwin"
    return {
        "cpu_model": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count(),
        "ram_gb": ram_gb,
        "os": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "uv_lock_hash": uv_hash,
        "git_commit": commit,
        "canonical_environment_note": (
            "Linux/CI is the canonical reference environment; macOS is smoke-test only "
            f"(this manifest produced on {system})."
        ),
    }


def new_manifest(sweep_name: str, estimated_spend_usd: float | None = None,
                 actual_spend_usd: float | None = None,
                 hardware: dict | None = None) -> dict:
    """Build a manifest dict; runner-filled slots default to null."""
    return {
        "sweep_name": sweep_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "estimated_spend_usd": estimated_spend_usd,
        # Entered manually at sweep end from the provider console.
        "actual_spend_usd": actual_spend_usd,
        # Captured once at run start (capture_hardware); null until then.
        "hardware": hardware if hardware is not None else {
            "cpu_model": None, "cpu_cores": None, "ram_gb": None,
            "os": None, "arch": None, "python": None,
            "uv_lock_hash": None, "git_commit": None,
            "canonical_environment_note": None,
        },
        # Filled at end of each phase by the runner.
        "agent_phase": {
            "trials": 0, "input_tokens": 0, "output_tokens": 0,
            "estimated_cost_usd": 0.0, "cost_is_estimate": True,
            "api_wall_clock_sec": 0.0,
        },
        "verify_phase": {
            "reruns": 0, "cpu_core_hours": 0.0, "wall_clock_sec": 0.0,
            "peak_memory_mb": 0.0, "ru_maxrss_platform": None,
        },
    }


def write_manifest(project_root: Path, manifest: dict) -> Path:
    """Write a manifest dict to the tracked sweeps/ path; return its path."""
    out = Path(project_root) / "sweeps" / f"{manifest['sweep_name']}_manifest.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.dump(manifest, default_flow_style=False, sort_keys=False))
    return out


def write_sweep_manifest(
    project_root: Path,
    sweep_name: str,
    estimated_spend_usd: float | None = None,
    actual_spend_usd: float | None = None,
) -> Path:
    """Convenience: build + write a fresh manifest for *sweep_name*."""
    return write_manifest(
        project_root, new_manifest(sweep_name, estimated_spend_usd, actual_spend_usd),
    )
