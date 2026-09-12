"""Trusted oracle agent — harness-only ground-truth probe (spec §8).

TRUSTED: reads ``hidden/`` directly (NOT via the sealed tool layer) and submits
the exactly-correct answer for the case's tier.  It is a diagnostic probe for
the known-answer gate, NEVER a contestant: ``run_agent.run_trial`` refuses to
run it without ``allow_trusted=True``, and ``aggregate_scores`` excludes its
records.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from harness.tools.tool_context import ToolContext


class OracleAgent:
    """Submits the exact hidden ground truth for a case.

    Constructed with the case directory so a gate can call
    :meth:`build_submission` directly (no tool layer needed).
    """

    is_trusted = True

    def __init__(self, case_dir: Path | None = None) -> None:
        self._case_dir = Path(case_dir) if case_dir is not None else None
        self.name = "oracle_trusted"

    def build_submission(self, case_dir: Path | None = None) -> dict:
        """Read hidden/ and return the exactly-correct submission dict."""
        cd = Path(case_dir) if case_dir is not None else self._case_dir
        if cd is None:
            raise ValueError("OracleAgent needs a case_dir")
        hidden = cd / "hidden"
        hidden_card = yaml.safe_load((hidden / "card.hidden.yaml").read_text())
        evidence = yaml.safe_load((hidden / "evidence.yaml").read_text()) or []
        verify = yaml.safe_load((hidden / "verify.yaml").read_text())

        layer = hidden_card.get("layer", "dynamics")
        detected = layer != "control"
        accepted = sorted(hidden_card.get("accepted_classes", []))
        operator_class = accepted[0] if accepted else "none"

        return {
            "diagnosis": {"detected": detected, "operator_class": operator_class},
            "evidence_refs": [dict(e) for e in evidence],
            "repair_spec": verify.get("oracle_repair"),  # dict, or None for controls
        }

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        self._case_dir = Path(case_dir)
        sub = self.build_submission()
        tools.call(
            "submit",
            diagnosis=sub["diagnosis"],
            evidence_refs=sub["evidence_refs"],
            repair_spec=sub["repair_spec"],
        )
