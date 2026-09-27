"""Strict shell everywhere commands are chained (DECISIONS 2026-09-26): every shell script runs with
`set -euo pipefail`, or states why not (`set -uo pipefail  # NOT -e: …` — report scripts whose checks must
all run); every CI `run:` block runs under bash -eo pipefail (workflow-level `defaults.run.shell: bash`)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_STRICT = re.compile(r"^set -euo pipefail\b", re.M)
_EXCEPTION = re.compile(r"^set -uo pipefail\s+# NOT -e:", re.M)
_SOURCED = "Sourced, never executed"      # a sourced library inherits its caller's strict mode


def test_every_shell_script_is_strict_or_states_its_exception():
    scripts = sorted(ROOT.glob("scripts/**/*.sh")) + sorted(ROOT.glob("docker/**/*.sh"))
    assert scripts
    bad = [str(p.relative_to(ROOT)) for p in scripts
           if not (_STRICT.search(p.read_text()) or _EXCEPTION.search(p.read_text())
                   or _SOURCED in p.read_text()[:600])]
    assert not bad, f"scripts without `set -euo pipefail` (or a documented `# NOT -e:` exception): {bad}"


def test_ci_run_blocks_use_bash_with_pipefail():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    assert (wf.get("defaults") or {}).get("run", {}).get("shell") == "bash"
    for job, spec in wf["jobs"].items():
        for step in spec.get("steps", []):
            assert step.get("shell") in (None, "bash"), f"{job}: step overrides the strict bash shell"
