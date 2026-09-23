"""export_release must be deterministic across processes.

`_sanitize_trial` used to build each released record by iterating `_TRIAL_ALLOW`, a *set*;
set iteration order follows per-process string-hash randomization (PYTHONHASHSEED), so every
re-export reordered the JSON keys of every trial file — identical content, different bytes.
The allowlist is now iterated in sorted order. These tests pin that across hash seeds and
lock the committed release files to the canonical (sorted-key) form.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_SAMPLE = {
    "case_id": "case_0001", "run_id": "r1", "conditions": {"anchor": "off"},
    "prompt": {"system_prompt_text": "x"}, "submission": {"diagnosis": {"detected": True}},
    "submission_original": None, "tool_transcript": [], "llm_transcript": [],
    "scores": {"recovery": {"verdict": "recovered", "compute_sec": 1.0,
                            "per_seed_hidden_metrics": [0.9]}},
    "usage": {"estimated_cost_usd": 0.01}, "termination_reason": "submit",
    "environment": {"platform": "linux"}, "model": {"model_id": "m"}, "status": "ok",
    "schema_version": "1.1", "agent_name": "static",
    "trusted": False, "budget": {}, "symptom_direction": "positive",
}

_PROG = (
    "import json, sys; sys.path.insert(0, {root!r});"
    "from scripts.export_release import _sanitize_trial;"
    "print(json.dumps(_sanitize_trial(json.loads(sys.argv[1])), indent=1, default=str))"
)


def _sanitize_under_hashseed(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    return subprocess.run(
        [sys.executable, "-c", _PROG.format(root=str(ROOT)), json.dumps(_SAMPLE)],
        capture_output=True, text=True, env=env, check=True,
    ).stdout


def test_sanitized_output_identical_across_hash_seeds():
    outs = {seed: _sanitize_under_hashseed(seed) for seed in ("0", "1", "2", "12345")}
    assert len(set(outs.values())) == 1, "export output depends on PYTHONHASHSEED"


def test_sanitized_top_level_keys_are_sorted():
    out = json.loads(_sanitize_under_hashseed("7"))
    assert list(out) == sorted(out)
    # Dropped fields stay dropped and hidden recovery metrics stay stripped.
    assert "trusted" not in out and "symptom_direction" not in out
    assert "per_seed_hidden_metrics" not in out["scores"]["recovery"]


_RELEASE_TRIALS = sorted(ROOT.glob("results_release/*/trials/*.json"))


@pytest.mark.skipif(not _RELEASE_TRIALS, reason="no committed release trials")
def test_committed_release_trials_are_in_canonical_key_order():
    """A future re-export must not churn committed files: they are already canonical."""
    bad = [p.relative_to(ROOT).as_posix() for p in _RELEASE_TRIALS
           if list(json.loads(p.read_text())) != sorted(json.loads(p.read_text()))]
    assert not bad, f"{len(bad)} release trial file(s) not in sorted key order, e.g. {bad[:3]}"
