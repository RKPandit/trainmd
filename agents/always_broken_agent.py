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

# Named structural knobs and their naive defaults (single-key knobs outside the
# ``data`` block). The injected DATA knobs are reset key-AGNOSTICALLY (see
# ``_broken_patches``): the clean config has no ``data`` section, so every present
# ``data.*`` key is an injected knob. Keeping no operator-specific data key name
# here is what lets this baseline treat the descriptive and neutral leakage
# variants identically (they must not silently diverge).
_NAMED_KNOBS: dict[str, Any] = {
    "training.lr": 0.01,
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


def _broken_patches(config: dict) -> dict[str, Any]:
    """The naive knob-reset a blind config-scanner would submit — key-agnostic.

    Resets each named structural knob that is present and non-default, plus EVERY
    present ``data.*`` knob to its naive default (bool→False, number→0). Clean
    configs have no ``data`` section, so this only ever resets injected knobs, and
    it covers any operator's data knob without naming it.
    """
    patches: dict[str, Any] = {}
    for key, default in _NAMED_KNOBS.items():
        val = _navigate(config, key)
        if val is not _MISSING and val != default:
            patches[key] = default
    for k, v in (config.get("data") or {}).items():
        default: Any = False if isinstance(v, bool) else 0.0
        if v != default:
            patches[f"data.{k}"] = default
    return patches


class AlwaysBrokenAgent:
    """Detects everywhere, no evidence, resets every non-default knob."""

    name = "always_broken"

    def run(self, case_dir: Path, tools: ToolContext) -> None:
        result = tools.call("read_config")
        config = result.get("value") if isinstance(result, dict) else None
        if not isinstance(config, dict):
            config = {}

        patches = _broken_patches(config)

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
