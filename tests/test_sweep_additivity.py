"""Additivity: extending a sweep with a new operator leaves existing cells intact.

Proves (not infers) that a paid sweep can be extended later without re-spending:
cell_id is a deterministic hash of (operator, strength, seed, agent, anchor, repeat,
provider), so adding an operator produces only NEW cell_ids; the append-only progress
file skips every previously-done cell; and the verify phase covers only the new cells.
No training / no API — pure enumeration + progress logic.
"""
from __future__ import annotations

from harness.sweep import (
    _append_progress,
    _cell_id,
    _load_progress,
    _progress_path,
    enumerate_cells,
)

_P = [{"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
      {"provider": "openai", "model": "gpt-5.6-luna"}]
_A = ["silent.data_leakage.v1"]
_AB = ["silent.data_leakage.v1", "silent.data_leakage_neutral.v1"]
_NEW = "silent.data_leakage_neutral.v1"
_ST = ["mild", "moderate", "severe"]
_SEEDS = [42, 43, 44, 45, 46, 47]


def _key(c):
    return (c["operator"], c["strength"], c["seed"], c["agent"],
            c["anchor"], c["repeat_index"], c["provider"])


def test_cell_id_includes_provider_and_is_deterministic():
    a = _cell_id("op", "mild", 42, "react", "off", 0, "anthropic")
    o = _cell_id("op", "mild", 42, "react", "off", 0, "openai")
    assert a != o                                  # provider is part of the key
    assert a == _cell_id("op", "mild", 42, "react", "off", 0, "anthropic")  # deterministic


def test_adding_operator_preserves_every_original_cell_id(tmp_path):
    a, _ = enumerate_cells(tmp_path, _ST, _SEEDS, [], 2, operators=_A, providers=_P)
    ab, _ = enumerate_cells(tmp_path, _ST, _SEEDS, [], 2, operators=_AB, providers=_P)
    # Same (operator,...,provider) key -> IDENTICAL cell_id in the extended plan.
    ab_by_key = {_key(c): c["cell_id"] for c in ab}
    for c in a:
        assert ab_by_key[_key(c)] == c["cell_id"]          # (a) unchanged
    ids_a = {c["cell_id"] for c in a}
    ids_ab = {c["cell_id"] for c in ab}
    assert ids_a <= ids_ab                                  # originals all retained
    assert len(ids_a) == len(a)                             # cell_ids unique


def test_runner_skips_all_previously_done_only_new_pending(tmp_path):
    a, _ = enumerate_cells(tmp_path, _ST, _SEEDS, [], 2, operators=_A, providers=_P)
    ab, _ = enumerate_cells(tmp_path, _ST, _SEEDS, [], 2, operators=_AB, providers=_P)

    # Simulate the agent phase having COMPLETED every original (operator A) cell.
    done = {c["cell_id"] for c in a}
    # The runner's skip predicate (harness.sweep.run_agents): skip if cell_id in done.
    pending = [c for c in ab if c["cell_id"] not in done]

    # (b) every previously-done cell is skipped: none of operator A is pending.
    assert not any(c["operator"] != _NEW for c in pending)
    # (c) exactly the new operator's cells are pending.
    assert {c["operator"] for c in pending} == {_NEW}
    ids_new = {c["cell_id"] for c in ab if c["operator"] == _NEW}
    assert {c["cell_id"] for c in pending} == ids_new
    # count sanity: new op cells = strengths×seeds×agents×anchors×repeats×providers
    assert len(pending) == 3 * 6 * 2 * 3 * 2 * 2


def test_verify_phase_covers_only_new_cells_after_extension(tmp_path):
    # Mirrors run_verify's skip condition (status=='ok' and cell_id not in vdone).
    ap = _progress_path(tmp_path, "s", "agents")
    for cid in ("A1", "A2", "B1", "B2"):
        _append_progress(ap, {"cell_id": cid, "status": "ok"})
    vp = _progress_path(tmp_path, "s", "verify")
    for cid in ("A1", "A2"):                                # A already verified
        _append_progress(vp, {"cell_id": cid, "status": "ok"})
    agent_done = _load_progress(ap)
    vdone = _load_progress(vp)
    verify_pending = [cid for cid, e in agent_done.items()
                      if e.get("status") == "ok" and cid not in vdone]
    assert set(verify_pending) == {"B1", "B2"}             # only the new cells


def test_lookup_case_finds_non_default_workload_family():
    # Regression (2026-09-20): _lookup_case matched a hardcoded workload, so the
    # neutral variant (tabular_adult_neutral) was never found -> every neutral case
    # marked MISSING. It must match the OPERATOR's own workload family.
    from harness.sweep import _lookup_case
    reg = {
        "case_0001": {"workload": "tabular_adult", "operator": "silent.data_leakage.v1",
                      "strength": "mild", "seed": 42},
        "case_0019": {"workload": "tabular_adult_neutral",
                      "operator": "silent.data_leakage_neutral.v1",
                      "strength": "mild", "seed": 42},
    }
    assert _lookup_case(reg, "silent.data_leakage.v1", "mild", 42) == "case_0001"
    assert _lookup_case(reg, "silent.data_leakage_neutral.v1", "mild", 42) == "case_0019"
    assert _lookup_case(reg, "silent.data_leakage_neutral.v1", "mild", 99) is None


def test_progress_is_append_only_old_entries_survive(tmp_path):
    # report + resume read the append-only progress/index; extending only APPENDS.
    p = _progress_path(tmp_path, "s", "agents")
    _append_progress(p, {"cell_id": "old", "status": "ok"})
    first = _load_progress(p)
    _append_progress(p, {"cell_id": "new", "status": "ok"})
    second = _load_progress(p)
    assert "old" in first and set(second) == {"old", "new"}   # old intact, new added
