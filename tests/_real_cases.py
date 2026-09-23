"""Select a REAL built case (cases/) by operator or tier — never by a hard-coded case number.

Case numbers follow the build design's ordering and have changed before (case_0005 was once a
control; it is a shape-mismatch case under the current design), which silently mis-targeted tests.
Reads hidden cards — test-side (evaluator) only. Returns None when no case is built (fast lane);
build-and-certify builds every case and runs these tests with --fail-on-skip.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CASES = Path(__file__).resolve().parent.parent / "cases"


def real_case(*, operator_id: str | None = None, layer: str | None = None) -> Path | None:
    for card in sorted(CASES.glob("case_*/hidden/card.hidden.yaml")):
        hc = yaml.safe_load(card.read_text()) or {}
        if operator_id is not None and hc.get("operator_id") != operator_id:
            continue
        if layer is not None and hc.get("layer") != layer:
            continue
        return card.parent.parent
    return None
