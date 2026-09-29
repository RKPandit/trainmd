#!/usr/bin/env python3
"""Snapshot every operator's identification + evidence specification (Part 3 re-freeze; author decision
2026-09-28: "a test asserts every workload-1 operator spec is byte-identical to the frozen one").

The committed snapshot `tests/fixtures/workload1_operator_specs.json` was generated from the FROZEN scorer's code
(main at 6aeaf39, before any image operator existed); `tests/test_workload1_spec_identity.py` recomputes it
live and fails on any byte difference.

    python scripts/snapshot_operator_specs.py > tests/fixtures/workload1_operator_specs.json
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def operator_spec(op) -> dict:
    sets = op.evidence_sets() if hasattr(op, "evidence_sets") else None
    return {
        "layer": op.layer,
        "accepted_classes": sorted(op.accepted_classes()),
        "core_tokens": [sorted(g) for g in op.core_tokens()],
        "off_concept_vetoes": sorted(getattr(op, "off_concept_vetoes", lambda: frozenset())()),
        "alternatives": [[sorted(g) for g in alt]
                         for alt in getattr(op, "core_token_alternatives", lambda: [])()],
        "alternative_vetoes": sorted(getattr(op, "core_token_alternative_vetoes", lambda: frozenset())()),
        "evidence": [dataclasses.asdict(e) for e in op.evidence()],
        "evidence_sets": [[dataclasses.asdict(e) for e in st] for st in sets] if sets else None,
        "code_path": getattr(op, "CODE_PATH", None),
        "crash_output": getattr(op, "CRASH_OUTPUT", None),
    }


def snapshot(op_ids) -> str:
    from operators.registry import get_operator
    return json.dumps({o: operator_spec(get_operator(o)) for o in sorted(op_ids)},
                      indent=1, sort_keys=True, default=list) + "\n"


if __name__ == "__main__":
    from operators.registry import all_operator_ids
    sys.stdout.write(snapshot(all_operator_ids()))
