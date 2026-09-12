"""Always-broken agent — the untrusted knob-scanner baseline (spec §8).

NOT trusted: uses only the sealed tool layer.  Detects an incident on EVERY
case (so its detection false-positive rate on controls is 1.0), cites no
evidence, and "fixes" the config by resetting every known knob it can see back
to a naive default.  It is the "how far does blindly diffing the config get
you?" baseline — and the controls are what catch it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.tools.tool_context import ToolContext

# Known knobs and their naive defaults.  Absent-when-clean means a healthy
# control exposes none of these as non-default, so patches stay empty there.
_KNOB_DEFAULTS: dict[str, Any] = {
    "training.lr": 0.01,
    "data.label_noise_fraction": 0.0,
    "data.include_aux_feature": False,
    "model.input_dim": 105,
}

_MISSING = object()


def _navigate(config: dict, key_path: str) -> Any:
    cur: Any = config
    for key in key_path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


class AlwaysBrokenAgent:
    """Detects everywhere, no evidence, resets every non-default knob."""

    name = "always_broken"

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        result = tools.call("read_config")
        config = result.get("value") if isinstance(result, dict) else None
        if not isinstance(config, dict):
            config = {}

        patches: dict[str, Any] = {}
        for key, default in _KNOB_DEFAULTS.items():
            val = _navigate(config, key)
            if val is not _MISSING and val != default:
                patches[key] = default

        repair = (
            {"repair_type": "config_patch", "patches": patches}
            if patches
            else {"repair_type": "none", "patches": {}}
        )
        tools.call(
            "submit",
            diagnosis={"detected": True, "operator_class": "misconfiguration"},
            evidence_refs=[],
            repair_spec=repair,
        )
