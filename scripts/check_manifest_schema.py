#!/usr/bin/env python3
"""Light schema check for sweep manifests and plans (STAGE3_PLAN §0.3, ruling 3).

A manifest is the paper's compute statement; a plan is its pre-registration. The invalid YAML that
sat in stage2gate_manifest.yaml went undetected because nothing loaded it. This validates every
`sweeps/*_manifest.yaml` and `sweeps/*_plan.yaml`: it parses, required keys are present, and their
types are right. Fails loudly (exit 1) naming each problem. Wired into CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# required key -> expected python type(s)
_MANIFEST = {
    "sweep_name": str, "timestamp_utc": str,
    "agent_phase": dict, "verify_phase": dict, "hardware": dict,
}
_AGENT_PHASE = {"trials": int}
_PLAN_HEADER = {"name": str, "model": str, "factor_levels": dict, "n_cells": int}


def _check(path: Path, required: dict, where: str, errors: list):
    for key, typ in required.items():
        if key not in path:
            errors.append(f"{where}: missing required key '{key}'")
        elif not isinstance(path[key], typ):
            errors.append(f"{where}: key '{key}' should be {typ.__name__}, got {type(path[key]).__name__}")


def check_file(p: Path) -> list[str]:
    errors: list[str] = []
    try:
        doc = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        return [f"{p.name}: does NOT parse as YAML — {str(e).splitlines()[0]}"]
    if not isinstance(doc, dict):
        return [f"{p.name}: top level is not a mapping"]
    if p.name.endswith("_manifest.yaml"):
        _check(doc, _MANIFEST, p.name, errors)
        if isinstance(doc.get("agent_phase"), dict):
            _check(doc["agent_phase"], _AGENT_PHASE, f"{p.name}:agent_phase", errors)
    elif p.name.endswith("_plan.yaml"):
        header = doc.get("header")
        if not isinstance(header, dict):
            errors.append(f"{p.name}: missing 'header' mapping")
        else:
            _check(header, _PLAN_HEADER, f"{p.name}:header", errors)
        if not isinstance(doc.get("cells"), list):
            errors.append(f"{p.name}: 'cells' must be a list")
    return errors


def run(root: Path = ROOT) -> list[str]:
    errors = []
    files = sorted((root / "sweeps").glob("*_manifest.yaml")) + sorted((root / "sweeps").glob("*_plan.yaml"))
    for p in files:
        errors += check_file(p)
    return errors


def main() -> int:
    errors = run()
    if errors:
        print("check_manifest_schema: FAIL\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_manifest_schema: OK — all sweeps/*_manifest.yaml and *_plan.yaml parse and validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
