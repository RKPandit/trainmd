"""Stub oracle agent — hardcoded correct submission for lr_warmup.

Zero-cost agent that validates the end-to-end pipeline without any LLM
calls.  Makes a few tool calls to demonstrate tool usage, then submits
the oracle answer for lr_warmup (any strength).
"""
from __future__ import annotations

from pathlib import Path

from harness.tools.tool_context import ToolContext


class StubAgent:
    """Hardcoded correct submission agent."""

    name = "stub_oracle"

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        # Demonstrate tool usage
        tools.call("read_config")
        tools.call("query_metrics", series="train_loss")

        # Submit the oracle answer
        tools.call(
            "submit",
            diagnosis={"detected": True, "operator_class": "lr_misconfiguration"},
            evidence_refs=[
                {
                    "kind": "config_key",
                    "artifact_id": "config.yaml",
                    "detail": {"key_path": "training.lr"},
                },
                {
                    "kind": "metric_window",
                    "artifact_id": "metrics.jsonl",
                    "detail": {"series": "train_loss", "start_epoch": 0, "end_epoch": 4},
                },
                {
                    "kind": "metric_window",
                    "artifact_id": "metrics.jsonl",
                    "detail": {"series": "metric_visible_val_acc", "start_epoch": 0},
                },
            ],
            repair_spec={
                "repair_type": "config_patch",
                "patches": {"training.lr": 0.01},
            },
        )
