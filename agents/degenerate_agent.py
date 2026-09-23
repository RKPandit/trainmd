"""Trusted degenerate agent — the discrimination probe (spec §8).

TRUSTED (reads the oracle repair from ``hidden/``).  Detects an incident on
every case and submits the case's ORACLE repair — so it recovers on every
non-control case BY CONSTRUCTION — but names the wrong class and cites no
evidence.  This proves scoring separates *diagnosis quality* from *recovery handed
over by the answer key*: the oracle must strictly out-score it on identification and
evidence.  It is NOT blind — it reads the answer — so its recovery is true by
construction and says nothing about whether a no-diagnosis policy would recover
(that evidence is the B2 config-reset baseline; LIMITATIONS L19, DECISIONS 2026-09-23).

On a control (oracle_repair is None) it still submits a repair, so it is flagged
``false_intervention`` — a probe of the control axis.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from harness.tools.tool_context import ToolContext

# A plausible-but-unnecessary repair used only on controls (which have no oracle
# repair), so the degenerate always intervenes.
_CONTROL_FALLBACK_REPAIR = {"repair_type": "config_patch", "patches": {"training.lr": 0.01}}


class DegenerateAgent:
    """Correct detection on faults, wrong class, no evidence, and the ORACLE repair read from
    ``hidden/verify.yaml`` (not blind: its recovery is true by construction)."""

    is_trusted = True
    name = "degenerate_trusted"

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        verify = yaml.safe_load((Path(case_dir) / "hidden" / "verify.yaml").read_text())
        oracle_repair = verify.get("oracle_repair")
        repair = oracle_repair if oracle_repair is not None else _CONTROL_FALLBACK_REPAIR

        tools.call(
            "submit",
            diagnosis={"detected": True, "operator_class": "unrelated_fault"},
            evidence_refs=[],
            repair_spec=repair,
        )
