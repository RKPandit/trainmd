"""Cross-operator evidence invariant (spec §4, §8).

An operator's mutated config keys are always part of its evidence ground
truth: each key the operator writes is a root-cause mutation, so per the
"enumerate every artifact the fault touches" principle it must appear as a
config_key evidence ref.  This test iterates EVERY registered operator, so a
new operator that mutates a key without citing it fails here — the convention
is enforced once, centrally.

code_spans remain deliberately excluded (mechanism, not root cause), so this
checks config-key mutations only.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from random import Random

import pytest

from harness.build_case import _OPERATOR_REGISTRY

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


@pytest.mark.parametrize("operator_id", sorted(_OPERATOR_REGISTRY))
def test_mutated_config_keys_are_in_evidence(operator_id, tmp_path):
    """Every config key an operator mutates appears in its evidence set."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy2(WORKLOAD_DIR / "config.yaml", workspace / "config.yaml")

    op = _OPERATOR_REGISTRY[operator_id]()
    manifest = op.apply(workspace, Random(42), "moderate")

    mutated_config_keys = {
        m.key_path for m in manifest.mutations
        if m.file.endswith("config.yaml")
    }
    evidence_config_keys = {
        e.detail["key_path"] for e in op.evidence()
        if e.kind == "config_key"
    }

    missing = mutated_config_keys - evidence_config_keys
    assert not missing, (
        f"{operator_id} mutates config key(s) {sorted(missing)} not cited in "
        f"evidence(); an operator's mutated keys are always evidence"
    )
