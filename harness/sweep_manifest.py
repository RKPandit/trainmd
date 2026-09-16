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
    # Canonical-container provenance (Stage 1): whether this sweep ran inside the
    # pinned image, and which one. Set by the Makefile docker-* targets.
    in_container = os.environ.get("TRAINMD_IN_CONTAINER") == "1" or Path("/.dockerenv").exists()
    image_digest = os.environ.get("TRAINMD_IMAGE_DIGEST") or None
    # Reliable CPU identity (vendor_id + model from /proc/cpuinfo) and the
    # native/emulated verdict — platform.processor() is empty on Linux. This is
    # what makes a macOS/Rosetta-run sweep (like Sweep 1) legible in the manifest
    # rather than inferred after the fact (DECISIONS 2026-09-16).
    from harness.platform_guard import cpu_provenance, emulation_reason
    cpu_model = cpu_provenance()
    emu = emulation_reason()
    return {
        "cpu_model": cpu_model,
        "cpu_cores": os.cpu_count(),
        "ram_gb": ram_gb,
        "os": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "uv_lock_hash": uv_hash,
        "git_commit": commit,
        "in_container": in_container,
        "image_digest": image_digest,
        "canonical_environment_note": (
            "Linux/amd64 in the pinned container is canonical (Stage 1). This manifest "
            f"produced on {system}; in_container={in_container}; cpu={cpu_model}; "
            + ("native amd64." if emu is None else f"NON-CANONICAL platform ({emu}).")
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
