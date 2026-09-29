"""Part 3 re-freeze guard (author's decision 2026-09-28): every WORKLOAD-1 operator's identification + evidence
specification is byte-identical to the frozen one.

`tests/fixtures/workload1_operator_specs.json` was written by `scripts/snapshot_operator_specs.py` from the frozen
scorer's code (before any image operator existed). Adding the image workload may not move a single byte of it, nor
workload 1's token-spec digest, nor the set of operators a workload-1 label is judged against.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from operators.registry import all_operator_ids, core_token_specs, token_spec_sha256

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "workload1_operator_specs.json"
# workload 1's token_spec_sha256 at the 2026-09-28 freeze (harness/scorer_freeze.yaml before the Part 3 re-freeze)
FROZEN_WORKLOAD1_TOKEN_SHA = "734eb98be1abfd90afb03b1030208036cb2562585417d17da7a318962187bca3"


def _snapshot_module():
    spec = importlib.util.spec_from_file_location("snap", ROOT / "scripts" / "snapshot_operator_specs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_workload1_operator_spec_is_byte_identical():
    live = _snapshot_module().snapshot(all_operator_ids("tabular_adult"))
    assert live == FIXTURE.read_text()


def test_workload1_token_digest_and_uniqueness_set_unchanged():
    assert token_spec_sha256() == token_spec_sha256("tabular_adult") == FROZEN_WORKLOAD1_TOKEN_SHA
    assert sorted(core_token_specs()) == sorted(__import__("json").loads(FIXTURE.read_text()))
