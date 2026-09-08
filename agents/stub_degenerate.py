"""Stub degenerate agent — correct detection, wrong everything else.

Detects correctly but identifies the wrong operator class, provides no
evidence, and submits a blind in-range repair.  Used to prove that
scoring discriminates diagnosis quality from blind recovery.

Expected scores:
- detection: CORRECT (detected=True)
- identification: WRONG (predicts "data_corruption" vs actual "lr_misconfiguration")
- evidence: P=0, R=0, F1=0 (empty evidence_refs)
- recovery: RECOVERED (blind lr=0.01 is in admissible range and recovers)
"""
from __future__ import annotations

from pathlib import Path

from harness.tools.tool_context import ToolContext


class StubDegenerateAgent:
    """Degenerate agent with correct detection but wrong diagnosis."""

    name = "stub_degenerate"

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        tools.call(
            "submit",
            diagnosis={"detected": True, "operator_class": "data_corruption"},
            evidence_refs=[],
            repair_spec={
                "repair_type": "config_patch",
                "patches": {"training.lr": 0.01},
            },
        )
