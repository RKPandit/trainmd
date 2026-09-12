"""Sweep orchestrator tests — stub agents / injected trial_fn, ZERO API cost.

Covers: cell enumeration + MISSING; conservative cost fallback; resumability;
hard cost cap; circuit breaker; max_trials; anchor=off has no band numbers;
hypothesis metrics on a synthetic index; and precondition refusal.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from harness import sweep

CASES = Path(__file__).resolve().parent.parent / "cases"


# ---------------------------------------------------------------------------
# tmp project root with a synthetic registry + case dirs
# ---------------------------------------------------------------------------

def _mk_root(tmp, faulty=("silent.lr_warmup.v1",), strengths=("moderate",),
            seeds=(42,), control_seeds=(0,), make_dirs=True):
    reg = {}
    n = 1
    for op in faulty:
        for st in strengths:
            for sd in seeds:
                reg[f"case_{n:04d}"] = {"workload": "tabular_adult", "operator": op,
                                        "strength": st, "seed": sd}
                n += 1
    for sd in control_seeds:
        reg[f"case_{n:04d}"] = {"workload": "tabular_adult", "operator": sweep.CONTROL_OPERATOR,
                                "strength": "mild", "seed": sd}
        n += 1
    (tmp / "cases").mkdir(parents=True, exist_ok=True)
    (tmp / "cases" / "registry.hidden.yaml").write_text(yaml.dump(reg))
    if make_dirs:
        for cid in reg:
            cd = tmp / "cases" / cid
            cd.mkdir()
            (cd / "card.public.yaml").write_text(yaml.dump({"case_id": cid, "case_build_id": f"bid_{cid}"}))
    return tmp


# ---------------------------------------------------------------------------
# plan / enumerate
# ---------------------------------------------------------------------------

def test_enumerate_cell_count():
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    _mk_root(tmp)
    cells, missing = sweep.enumerate_cells(tmp, ["moderate"], [42], [0], repeats=3)
    # 1 faulty op × 1 strength × 1 seed × 2 agents × 2 anchors × 3 = 12
    # + control × 1 seed × 2 × 2 × 3 = 12 → 24
    assert len(cells) == 24
    assert missing == []


def test_missing_flagged(tmp_path):
    _mk_root(tmp_path, make_dirs=False)  # registry entries but no case dirs
    cells, missing = sweep.enumerate_cells(tmp_path, ["moderate"], [42], [0], repeats=1)
    assert missing  # every intended case is missing
    result = sweep.plan(tmp_path, "s", ["moderate"], [42], [0], repeats=1)
    assert result["missing"]


def test_cost_fallback_uses_max_observed(tmp_path):
    _mk_root(tmp_path)
    # One prior react trial at $2; static has no priors → fallback to max ($2).
    results = tmp_path / "results" / "case_0001" / "trials"
    results.mkdir(parents=True)
    (results / "llm_x.yaml").write_text(yaml.dump({
        "case_id": "case_0001", "agent_name": "llm_x",
        "conditions": {"agent_type": "react"},
        "usage": {"estimated_cost_usd": 2.0},
    }))
    result = sweep.plan(tmp_path, "s", ["moderate"], [42], [0], repeats=1)
    est = result["plan"]["header"]["cost_estimate"]
    assert est["fallback_cost_usd"] == 2.0
    # static + control cells have no priors → fallback
    assert est["estimate_source_counts"]["fallback"] > 0


# ---------------------------------------------------------------------------
# run_agents orchestration (injected stubs)
# ---------------------------------------------------------------------------

def _plan_with_cells(tmp, name, n):
    cells = [{"cell_id": f"c{i}", "case_id": "case_0001", "operator": "silent.lr_warmup.v1",
              "tier": "dynamics", "strength": "moderate", "seed": 42,
              "agent": "react", "anchor": "on", "repeat_index": i} for i in range(n)]
    (tmp / "sweeps").mkdir(parents=True, exist_ok=True)
    (tmp / "sweeps" / f"{name}_plan.yaml").write_text(yaml.dump(
        {"header": {"name": name, "model": "m", "cost_estimate": {"per_cell_total_usd": 0}}, "cells": cells}))


def _ok_trial(cost):
    def _fn(agent, case_dir, project_root, conditions=None):
        return {"run_id": f"rid_{conditions['repeat_index']}", "case_id": "case_0001",
                "usage": {"estimated_cost_usd": cost, "input_tokens": 10, "output_tokens": 5}}
    return _fn


def test_cost_cap_stops(tmp_path):
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 5)
    r = sweep.run_agents(tmp_path, "s", max_cost_usd=12.0, require_preconditions=False,
                         agent_factory=lambda c: object(), trial_fn=_ok_trial(5.0),
                         cost_fn=lambda rec: 5.0, est_fn=lambda c: 5.0)
    assert r["ran"] == 2  # 5+5=10 ok; 3rd would be 15 > 12
    assert "cost_cap" in r["stopped"]


def test_max_trials_and_resume(tmp_path):
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 5)
    r1 = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                          agent_factory=lambda c: object(), trial_fn=_ok_trial(1.0),
                          cost_fn=lambda rec: 1.0, est_fn=lambda c: 1.0, max_trials=2)
    assert r1["ran"] == 2 and r1["stopped"] == "max_trials"
    # Resume: the 2 done cells are skipped; the remaining 3 run.
    r2 = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                          agent_factory=lambda c: object(), trial_fn=_ok_trial(1.0),
                          cost_fn=lambda rec: 1.0, est_fn=lambda c: 1.0)
    assert r2["ran"] == 3


def test_circuit_breaker(tmp_path):
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 20)

    def _always_fail(agent, case_dir, project_root, conditions=None):
        raise RuntimeError("401 unauthorized")

    r = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                         agent_factory=lambda c: object(), trial_fn=_always_fail,
                         cost_fn=lambda rec: 0.0, est_fn=lambda c: 0.0,
                         max_consecutive_failures=3)
    assert "circuit_breaker" in r["stopped"]
    assert r["ran"] == 0
    # only ~3 cells were attempted, not all 20
    prog = (tmp_path / "sweeps" / "s_progress.jsonl").read_text().strip().splitlines()
    assert len(prog) == 3


# ---------------------------------------------------------------------------
# anchor=off has no band numbers
# ---------------------------------------------------------------------------

def test_anchor_off_prompt_has_no_band_numbers():
    from agents.llm_agent import _build_system_prompt, reference_band_line
    from agents.static_agent import StaticContextAgent
    case_dir = CASES / "case_0005"
    if not case_dir.exists():
        import pytest
        pytest.skip("case_0005 not built")
    card = yaml.safe_load((case_dir / "card.public.yaml").read_text())
    band = reference_band_line(card)
    band_number = f"{card['reference_visible_metric']['mean']:.4f}"

    on = _build_system_prompt(case_dir, include_band=True)
    off = _build_system_prompt(case_dir, include_band=False)
    assert band in on and band not in off
    assert band_number in on and band_number not in off

    st_on = StaticContextAgent(object(), model_id="m", anchor="on")._system_prompt(case_dir)
    st_off = StaticContextAgent(object(), model_id="m", anchor="off")._system_prompt(case_dir)
    assert band_number in st_on and band_number not in st_off


# ---------------------------------------------------------------------------
# hypothesis metrics on a synthetic set
# ---------------------------------------------------------------------------

def test_hypothesis_metrics_h1_and_h6():
    def rec(op, agent, anchor, detected, ev_f1):
        return {"case_id": "x", "_operator": op,
                "conditions": {"agent_type": agent, "anchor": anchor},
                "scores": {"detection": {"correct": detected, "detected_predicted": detected},
                           "identification": {"correct": True},
                           "evidence": {"f1": ev_f1, "recall": ev_f1},
                           "recovery": {"verdict": "recovered"}}}
    records = [
        rec("silent.data_leakage.v1", "react", "off", False, 0.5),
        rec("silent.lr_warmup.v1", "react", "off", True, 1.0),
        rec("silent.data_leakage.v1", "static", "off", False, 0.2),
    ]
    m = sweep.hypothesis_metrics(records, {})
    # H1 anchor-off: leakage detection 0.0, negative-symptom 1.0
    assert m["H1_positive_symptom_blindness"]["off"]["leakage_detection"] == 0.0
    assert m["H1_positive_symptom_blindness"]["off"]["negative_symptom_detection"] == 1.0
    # H6 data_leakage: react 0.5 - static 0.2 = 0.3
    h6 = m["H6_tools_vs_static"]["silent.data_leakage.v1"]
    assert h6["react_minus_static"] == 0.3


# ---------------------------------------------------------------------------
# preconditions (gate/audit/validate monkeypatched green)
# ---------------------------------------------------------------------------

def test_preconditions_flag_drift_and_missing_key(tmp_path, monkeypatch):
    import harness.gate_known_answer as gk
    import harness.audit_index as ai
    import harness.validate_case as vc

    class _R:  # a passing validate report
        passed = True

    monkeypatch.setattr(gk, "run_gate", lambda root, fast=True: [])
    monkeypatch.setattr(ai, "run_audit", lambda root: ([], 0))
    monkeypatch.setattr(vc, "validate_all", lambda root: [_R()])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    _mk_root(tmp_path)
    plan_doc = {"header": {"name": "s", "case_set": {"case_0001": {"build_id": "WRONG"}}}}
    fails = sweep.check_preconditions(tmp_path, plan_doc)
    assert any("build_id drift" in f for f in fails)
    assert any("ANTHROPIC_API_KEY" in f for f in fails)
