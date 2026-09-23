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
    from operators.registry import get_operator
    reg = {}
    n = 1
    for op in faulty:
        # Register under the operator's OWN workload family (the neutral variant is
        # tabular_adult_neutral) so _lookup_case (workload-family aware) finds it.
        wl = getattr(get_operator(op), "WORKLOAD_FAMILY", "tabular_adult")
        for st in strengths:
            for sd in seeds:
                reg[f"case_{n:04d}"] = {"workload": wl, "operator": op,
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
    from operators.registry import all_operator_ids

    # The design's faulty operators come from operators/registry.py (code), so
    # build a registry for ALL of them (not just one) to reach missing == [].
    faulty = tuple(op for op in all_operator_ids() if op != sweep.CONTROL_OPERATOR)
    tmp = Path(tempfile.mkdtemp())
    _mk_root(tmp, faulty=faulty)
    cells, missing = sweep.enumerate_cells(tmp, ["moderate"], [42], [0], repeats=3)
    # Per faulty op: 1 strength × 1 seed × 2 agents × 3 anchors × 3 repeats = 18.
    # control (REDUCED protocol, DECISIONS 2026-09-20): 1 seed × static-only × 3 anchors
    # × 1 repeat = 3. Derived from the registry (len(faulty)), so adding an operator
    # does not break this test.
    assert len(cells) == len(faulty) * 18 + 3
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
# committed plan carries NO per-case answer key (operator/tier) — public-repo leak
# ---------------------------------------------------------------------------

_ANSWER_KEY = ("operator", "tier", "seed", "strength")
_RUNTIME_CELL_FIELDS = ("cell_id", "case_id", "provider", "model", "agent",
                        "anchor", "repeat_index")


def test_written_plan_strips_all_answer_key_fields(tmp_path):
    # Two strengths + a control so the leak-by-inference fields are present in-memory.
    _mk_root(tmp_path, faulty=("silent.data_leakage.v1",), strengths=("mild", "severe"),
             seeds=(42,), control_seeds=(50,))
    result = sweep.plan(tmp_path, "s", ["mild", "severe"], [42], [50], repeats=1,
                        operators=["silent.data_leakage.v1"])
    # In-memory cells DO carry the answer-key fields (used for cost_est, n_verify, case_set).
    assert all(all(k in c for k in _ANSWER_KEY) for c in result["plan"]["cells"])

    p = sweep.write_plan(result)
    written = yaml.safe_load(p.read_text())

    # The COMMITTED artifact must not map any case_id -> ground truth, by name OR
    # by inference (operator, tier, seed, strength).
    for c in written["cells"]:
        assert not any(k in c for k in _ANSWER_KEY), c
        for k in _RUNTIME_CELL_FIELDS:      # ...but every run-time field is retained.
            assert k in c
    for cid, info in written["header"]["case_set"].items():
        assert set(info) == {"build_id"}    # only the precondition field remains

    # Leak closed, additivity intact: every cell_id is unchanged by stripping.
    assert ({c["cell_id"] for c in written["cells"]}
            == {c["cell_id"] for c in result["plan"]["cells"]})
    # Header still carries AGGREGATE design disclosure (operators + seed ranges),
    # which is not a per-case mapping.
    assert written["header"]["scope"]["gate_operators"] == ["silent.data_leakage.v1"]
    assert written["header"]["factor_levels"]["faulty_seeds"] == [42]
    assert written["header"]["factor_levels"]["control_seeds"] == [50]


def test_default_agent_factory_dispatches_client_by_provider(monkeypatch):
    # The bug: the factory always built AnthropicClient, so openai cells ran on
    # Haiku. Assert the constructed client class matches cell["provider"]. The real
    # SDK clients construct offline from a (bogus) env key; no network.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    from agents.llm_agent import LLMAgent

    a_cell = {"agent": "react", "anchor": "rule", "provider": "anthropic",
              "model": "claude-haiku-4-5-20251001"}
    o_cell = {"agent": "react", "anchor": "rule", "provider": "openai",
              "model": "gpt-5.6-luna"}
    a_agent = sweep._default_agent_factory(a_cell, "header-model")
    o_agent = sweep._default_agent_factory(o_cell, "header-model")
    assert isinstance(a_agent, LLMAgent) and isinstance(o_agent, LLMAgent)
    # The underlying client class is provider-specific and uses the CELL model.
    assert type(a_agent._client).__name__ == "AnthropicClient"
    assert a_agent._client._model == "claude-haiku-4-5-20251001"
    assert type(o_agent._client).__name__ == "OpenAIClient"
    assert o_agent._client._model == "gpt-5.6-luna"
    assert o_agent._client._reasoning_effort == "medium"  # pinned, Haiku has none


def test_make_client_rejects_unknown_provider():
    import pytest
    with pytest.raises(ValueError, match="unknown provider"):
        sweep._make_client("gemini", "some-model")


def test_provider_smoke_passes_with_keys_and_real_sdk(monkeypatch):
    # Constructs the REAL anthropic/openai clients (offline, bogus key) and binds
    # the real create() signature — the exact preflight check_preconditions runs.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    fails = sweep._provider_smoke([
        {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        {"provider": "openai", "model": "gpt-5.6-luna"},
    ])
    assert fails == []


def test_provider_smoke_flags_missing_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fails = sweep._provider_smoke([{"provider": "openai", "model": "gpt-5.6-luna"}])
    assert any("OPENAI_API_KEY not set" in f for f in fails)


def test_provider_smoke_flags_unknown_provider():
    fails = sweep._provider_smoke([{"provider": "gemini", "model": "x"}])
    assert any("unknown" in f for f in fails)


def test_cost_estimate_resolves_operator_from_registry_not_plan(tmp_path):
    # The stripped plan has no per-cell operator; the run-time estimate must resolve
    # it from the registry by case_id and still find the (operator, agent) prior.
    _mk_root(tmp_path, faulty=("silent.data_leakage.v1",), strengths=("mild",),
             seeds=(42,), control_seeds=())
    priors = {"by_pair": {("silent.data_leakage.v1", "react"): [1.5]}, "all": [1.5]}
    op = "silent.data_leakage.v1"
    stripped_cell = {"cell_id": "c0", "case_id": "case_0001", "agent": "react"}
    # No operator on the cell -> must be supplied (as run_agents does, from registry).
    assert sweep._cell_est(stripped_cell, priors, op) == 1.5


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


def test_failed_cells_are_retried_not_skipped(tmp_path):
    # Regression (2026-09-20): the 3 temperature-TypeError cells were written to the
    # progress file as status="failed"; the skip predicate was `cell_id in done`,
    # which would SILENTLY SKIP them on rerun. Resume must retry a failed cell.
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 3)

    def _fail(agent, case_dir, project_root, conditions=None):
        raise RuntimeError("Messages.create() got an unexpected keyword argument 'temperature'")

    r1 = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                          agent_factory=lambda c: object(), trial_fn=_fail,
                          cost_fn=lambda rec: 0.0, est_fn=lambda c: 0.0,
                          max_consecutive_failures=3)
    assert "circuit_breaker" in r1["stopped"] and r1["ran"] == 0
    prog1 = sweep._load_progress(tmp_path / "sweeps" / "s_progress.jsonl")
    assert len(prog1) == 3 and all(e["status"] == "failed" for e in prog1.values())

    # Rerun after the fix: every FAILED cell is retried (not skipped) and succeeds.
    r2 = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                          agent_factory=lambda c: object(), trial_fn=_ok_trial(1.0),
                          cost_fn=lambda rec: 1.0, est_fn=lambda c: 1.0)
    assert r2["ran"] == 3
    prog2 = sweep._load_progress(tmp_path / "sweeps" / "s_progress.jsonl")
    # last-wins: the ok entries overwrite the failed ones for the same cell_ids.
    assert len(prog2) == 3 and all(e["status"] == "ok" for e in prog2.values())


# ---------------------------------------------------------------------------
# three-arm anchor, prompt v2: off (no line) | stats (mean, SD, n) | rule (stats + rule)
# ---------------------------------------------------------------------------

def test_three_arm_anchor_prompt_content():
    import pytest
    from agents.llm_agent import (
        _build_instruction_prompt, reference_band_line, reference_band_stats,
    )
    from agents.static_agent import StaticContextAgent
    case_dir = CASES / "case_0005"
    if not case_dir.exists():
        pytest.skip("case_0005 not built")
    card = yaml.safe_load((case_dir / "card.public.yaml").read_text())
    if "n" not in (card.get("reference_visible_metric") or {}):
        pytest.skip("case_0005 built before reference_visible_metric.n (rebuild to run)")
    stats = reference_band_stats(card)
    rule = reference_band_line(card, "rule")
    number_str = f"{card['reference_visible_metric']['mean']:.4f}"
    # Discriminate the rule arm on a BAND-ONLY phrase — "anomalous" alone also
    # appears in the fixed template ("anomalous training curves").
    RULE_PHRASE = "above OR below"

    off = _build_instruction_prompt(case_dir, arm="off")
    sta = _build_instruction_prompt(case_dir, arm="stats")
    rul = _build_instruction_prompt(case_dir, arm="rule")

    assert number_str not in off and RULE_PHRASE not in off
    assert stats in sta and number_str in sta and RULE_PHRASE not in sta
    assert rule in rul and RULE_PHRASE in rul and rule.startswith(stats)
    # v1-only arms cannot be rendered for a new run.
    for legacy in ("on", "numbers"):
        with pytest.raises(ValueError):
            _build_instruction_prompt(case_dir, arm=legacy)

    # Both agents share the same three texts verbatim.
    def st(anchor):
        return StaticContextAgent(object(), model_id="m", anchor=anchor)._instruction_prompt(case_dir)
    assert number_str not in st("off") and RULE_PHRASE not in st("off")
    assert stats in st("stats") and RULE_PHRASE not in st("stats")
    assert RULE_PHRASE in st("rule")


def test_sweep_schedules_only_v2_arms_and_records_prompt_major():
    from agents.llm_agent import REACT_PROMPT_VERSION, _ANCHOR_ARMS
    from agents.static_agent import STATIC_PROMPT_VERSION
    from harness.anchors import ARMS_BY_PROMPT_MAJOR, CURRENT_PROMPT_MAJOR, prompt_major
    assert sweep.PROMPT_MAJOR == CURRENT_PROMPT_MAJOR
    assert prompt_major(REACT_PROMPT_VERSION) == prompt_major(STATIC_PROMPT_VERSION) == sweep.PROMPT_MAJOR
    assert tuple(sweep.ANCHORS) == _ANCHOR_ARMS == ARMS_BY_PROMPT_MAJOR[sweep.PROMPT_MAJOR]


# ---------------------------------------------------------------------------
# hypothesis metrics on a synthetic set
# ---------------------------------------------------------------------------

def test_generic_stats_h1_and_h6():
    """The generic (plan-driven) analysis computes H1/H6 from symptom-derived sets — no hardcodes."""
    from harness import sweep_stats as ss

    def rec(cid, op, symptom, agent, anchor, detected, ev_f1):
        r = {"case_id": cid,
             "conditions": {"agent_type": agent, "anchor": anchor},
             "scores": {"detection": {"correct": detected, "detected_predicted": detected},
                        "identification": {"correct": True},
                        "evidence": {"f1": ev_f1, "recall": ev_f1},
                        "recovery": {"verdict": "recovered"}}}
        return ss.attach_meta(r, {"operator_id": op, "tier": "dynamics",
                                  "symptom_direction": symptom, "visible_sigma_distance": 1.0,
                                  "hidden_sigma_distance": 1.0})
    records = [
        rec("c1", "silent.data_leakage.v1", "positive", "react", "off", False, 0.5),
        rec("c2", "silent.lr_warmup.v1", "negative", "react", "off", True, 1.0),
        rec("c1", "silent.data_leakage.v1", "positive", "static", "off", False, 0.2),
        rec("c2", "silent.lr_warmup.v1", "negative", "static", "off", True, 0.7),
    ]
    g = ss.h1_anchor_gap(records)
    assert g["pos_rate"] == 0.0 and g["neg_rate"] == 1.0 and g["point"] == 1.0
    assert g["positive_ops"] == ["silent.data_leakage.v1"]
    h6 = ss.h6_react_minus_static(records)
    # react evidence mean (0.5,1.0)=0.75 − static (0.2,0.7)=0.45 = 0.30
    assert h6["available"] and abs(h6["point"] - 0.30) < 1e-9


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


def test_operators_filter_restricts_design_and_rejects_unknown():
    """--operators restricts the faulty set; a control/unknown id raises."""
    import tempfile
    import pytest
    from operators.registry import all_operator_ids

    faulty = tuple(op for op in all_operator_ids() if op != sweep.CONTROL_OPERATOR)
    tmp = Path(tempfile.mkdtemp())
    _mk_root(tmp, faulty=faulty)

    subset = ["silent.data_leakage.v1", "silent.metric_inflation.v1"]
    cells, _ = sweep.enumerate_cells(tmp, ["moderate"], [42], [0], repeats=2, operators=subset)
    faulty_ops = {c["operator"] for c in cells if c["tier"] != "control"}
    assert faulty_ops == set(subset)
    # control cells still present (control is always included)
    assert any(c["tier"] == "control" for c in cells)

    # a control id or unknown id in --operators is rejected (not a faulty operator)
    with pytest.raises(ValueError):
        sweep.enumerate_cells(tmp, ["moderate"], [42], [0], repeats=2,
                              operators=[sweep.CONTROL_OPERATOR])
    with pytest.raises(ValueError):
        sweep.enumerate_cells(tmp, ["moderate"], [42], [0], repeats=2,
                              operators=["silent.not_a_real_op.v1"])


def test_operators_survive_build_missing(tmp_path, monkeypatch):
    """CLI regression (STAGE3_PLAN §0.3): --build-missing re-plan must keep the --operators filter."""
    import sys
    import pytest
    from operators.registry import all_operator_ids

    faulty = tuple(op for op in all_operator_ids() if op != sweep.CONTROL_OPERATOR)
    _mk_root(tmp_path, faulty=faulty)  # default design leaves most tuples MISSING -> build_missing runs
    monkeypatch.setattr(sweep, "build_missing",
                        lambda root, missing: {"built": [], "skipped": missing, "failed": []})
    import harness.validate_case as vc
    monkeypatch.setattr(vc, "validate_all", lambda root: [])  # all(...) over [] is True
    monkeypatch.setattr(sys, "argv",
                        ["sweep", "plan", "--name", "s", "--operators", "silent.data_leakage.v1",
                         "--build-missing", "--project-root", str(tmp_path)])
    try:
        sweep.main()
    except SystemExit:
        pass  # may exit nonzero on remaining MISSING; the plan file is written first
    plan = yaml.safe_load((tmp_path / "sweeps" / "s_plan.yaml").read_text())
    assert plan["header"]["scope"]["gate_operators"] == ["silent.data_leakage.v1"]


# ---------------------------------------------------------------------------
# verify-phase manifest accounting: REPLACE, not accumulate (2026-09-15 bug)
# ---------------------------------------------------------------------------

def test_verify_totals_replace_not_accumulate():
    """A re-run of the verify phase must MIRROR the progress file, not add to
    prior manifest counts. Regression for the Stage-2 double-count (432 reruns /
    2.31 core-hours reported for a 216-rerun / 1.991 canonical run)."""
    # Manifest carries INFLATED prior counts (e.g. from an earlier aborted pass).
    manifest = {"verify_phase": {"reruns": 216, "cpu_core_hours": 0.32,
                                 "wall_clock_sec": 487.0, "peak_memory_mb": 270.0,
                                 "ru_maxrss_platform": "darwin"}}
    # The current progress file has exactly 3 real reruns.
    vdone = {
        "c1": {"cpu_sec": 3600.0, "wall_sec": 100.0, "peak_mb": 300.0},
        "c2": {"cpu_sec": 3600.0, "wall_sec": 100.0, "peak_mb": 365.0},
        "c3": {"cpu_sec": 0.0,    "wall_sec": 0.1,   "peak_mb": 0.0},  # a rejection
    }
    sweep._finalize_verify_totals(manifest, vdone)
    vp = manifest["verify_phase"]
    assert vp["reruns"] == 3                     # replaced, NOT 216 + 3
    assert vp["cpu_core_hours"] == 2.0           # (3600+3600+0)/3600, not +0.32
    assert vp["wall_clock_sec"] == 200.1
    assert vp["peak_memory_mb"] == 365.0         # max over THIS run, not prior 270

    # Re-running with a smaller progress file replaces again (idempotent mirror).
    sweep._finalize_verify_totals(manifest, {"c1": {"cpu_sec": 3600.0, "wall_sec": 50.0, "peak_mb": 100.0}})
    assert manifest["verify_phase"]["reruns"] == 1
    assert manifest["verify_phase"]["cpu_core_hours"] == 1.0


# ---------------------------------------------------------------------------
# Live prompt-caching check (Stage 4 Part 1): stop if caching is not hitting
# ---------------------------------------------------------------------------

def _react_trial(cached):
    def _fn(agent, case_dir, project_root, conditions=None):
        return {"run_id": f"rid_{conditions['repeat_index']}", "case_id": "case_0001",
                "conditions": dict(conditions),
                "usage": {"estimated_cost_usd": 0.01, "input_tokens": 9000, "output_tokens": 50,
                          "llm_calls": 4, "cached_tokens": cached, "cache_write_tokens": 0}}
    return _fn


def test_agents_phase_stops_when_cache_never_hits(tmp_path):
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 12)
    r = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                         agent_factory=lambda c: object(), trial_fn=_react_trial(0),
                         cost_fn=lambda rec: 0.01, est_fn=lambda c: 0.01)
    assert r["ran"] == sweep.CACHE_CHECK_TRIALS
    assert r["stopped"].startswith("cache_check_failed")
    m = yaml.safe_load((tmp_path / "sweeps" / "s_manifest.yaml").read_text())
    assert m["agent_phase"]["cache_check"]["status"] == "failed"


def test_agents_phase_continues_when_cache_hits(tmp_path):
    _mk_root(tmp_path)
    _plan_with_cells(tmp_path, "s", 8)
    r = sweep.run_agents(tmp_path, "s", max_cost_usd=1000, require_preconditions=False,
                         agent_factory=lambda c: object(), trial_fn=_react_trial(4000),
                         cost_fn=lambda rec: 0.01, est_fn=lambda c: 0.01)
    assert r["ran"] == 8 and not r["stopped"]
    m = yaml.safe_load((tmp_path / "sweeps" / "s_manifest.yaml").read_text())
    assert m["agent_phase"]["cache_check"]["status"] == "passed"


def _rec(provider, agent, calls, cached):
    return {"conditions": {"provider": provider, "agent_type": agent}, "run_id": "r",
            "usage": {"llm_calls": calls, "cached_tokens": cached}}


def test_cache_check_statuses():
    cc = sweep.cache_check
    assert cc([])["status"] == "not_applicable"
    assert cc([_rec("openai", "react", 5, 0), _rec("anthropic", "static", 1, 0)])["status"] == "not_applicable"
    assert cc([_rec("anthropic", "react", 1, 0)] * 9)["status"] == "not_applicable"   # 1-call: can't read
    assert cc([_rec("anthropic", "react", 3, 0)] * (sweep.CACHE_CHECK_TRIALS - 1))["status"] == "pending"
    assert cc([_rec("anthropic", "react", 3, 0)] * sweep.CACHE_CHECK_TRIALS)["status"] == "failed"
    assert cc([_rec("anthropic", "react", 3, 0)] * 9 + [_rec("anthropic", "react", 3, 1)])["status"] == "passed"
