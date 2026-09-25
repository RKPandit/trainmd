"""Stage 4 Part 1 planner: the benign-configuration controls are SCHEDULED, and the exploratory
H8-defect arm (Luna ReAct, reasoning pass-back OFF, leakage × off) is scheduled, run, exempted from the
reasoning check and kept out of every primary table. Zero API cost (synthetic registries, stub trials).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness import sweep
from harness import sweep_stats as ss
from harness.seed_sets import CONFIRMATORY_BENIGN, CONFIRMATORY_CONTROL, CONFIRMATORY_FAULTY
from operators.control.benign import BENIGN_OPERATORS, benign_design

LUNA = "gpt-5.6-luna"
HAIKU = "claude-haiku-4-5-20251001"
PROVIDERS = [{"provider": "anthropic", "model": HAIKU}, {"provider": "openai", "model": LUNA}]
LEAK = ("silent.data_leakage.v1", "silent.data_leakage_neutral.v1")


def _faulty_ops():
    from operators.registry import all_operator_ids
    return [o for o in all_operator_ids() if sweep._tier_of(o) != "control"]


def _mk_part1_root(tmp: Path) -> Path:
    """A synthetic registry holding the full Part 1 case design (200 cases)."""
    from operators.registry import get_operator
    tuples = [(op, st, sd) for op in _faulty_ops() for st in sweep.DEFAULT_STRENGTHS
              for sd in sorted(CONFIRMATORY_FAULTY)]
    tuples += [(sweep.CONTROL_OPERATOR, "mild", sd) for sd in sorted(CONFIRMATORY_CONTROL)]
    tuples += benign_design(CONFIRMATORY_BENIGN)
    reg = {}
    for n, (op, st, sd) in enumerate(tuples, 1):
        cid = f"case_{n:04d}"
        reg[cid] = {"workload": getattr(get_operator(op), "WORKLOAD_FAMILY", "tabular_adult"),
                    "operator": op, "strength": st, "seed": sd}
        (tmp / "cases" / cid).mkdir(parents=True)
        (tmp / "cases" / cid / "card.public.yaml").write_text(yaml.dump({"case_id": cid}))
    (tmp / "cases" / "registry.hidden.yaml").write_text(yaml.dump(reg))
    return tmp


def _part1_plan(tmp, **kw):
    return sweep.plan(tmp, "p1", strengths=sweep.DEFAULT_STRENGTHS,
                      faulty_seeds=sorted(CONFIRMATORY_FAULTY),
                      control_seeds=sorted(CONFIRMATORY_CONTROL), repeats=2,
                      providers=PROVIDERS, **kw)


# --------------------------------------------------------------------------- #
# benign controls
# --------------------------------------------------------------------------- #

def test_benign_design_is_the_builders_pairing():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import build_all_cases
    assert build_all_cases.benign_design() == benign_design(CONFIRMATORY_BENIGN)
    d = benign_design(CONFIRMATORY_BENIGN)
    assert len(d) == 72
    for i, cls in enumerate(BENIGN_OPERATORS):         # block by block: 4 consecutive seeds per type
        assert [s for o, _, s in d if o == cls.id] == [base + 4 * i + j for base in (70, 110, 134)
                                                       for j in range(4)]
    with pytest.raises(ValueError):
        benign_design([70, 71, 72])                   # not a whole 24-seed block


# The 24 benign cases CERTIFIED before the 72-case expansion (cases/registry.hidden.yaml, run
# 35947111127): (operator, seed) pairs that must never move when blocks are added.
CERTIFIED_24 = {("control.benign_bs128.v1", s) for s in range(70, 74)} | \
               {("control.benign_ep25.v1", s) for s in range(74, 78)} | \
               {("control.benign_wd5e4.v1", s) for s in range(78, 82)} | \
               {("control.benign_do01.v1", s) for s in range(82, 86)} | \
               {("control.benign_lr005.v1", s) for s in range(86, 90)} | \
               {("control.benign_clip1.v1", s) for s in range(90, 94)}


def test_existing_24_benign_pairings_unchanged_by_expansion():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import build_all_cases
    t = build_all_cases.case_design_tuples()
    assert len(t) == 200
    # the first 24 benign tuples (case_0129–0152) are exactly the certified pairs, in the same order
    assert {(o, s) for o, _, s in t[128:152]} == CERTIFIED_24
    assert [s for _, _, s in t[128:152]] == list(range(70, 94))
    # the new 48 are appended (case_0153–0200) on 110–157 only
    assert sorted(s for _, _, s in t[152:]) == list(range(110, 158))


def test_part1_plan_schedules_all_72_benign_controls(tmp_path):
    r = _part1_plan(_mk_part1_root(tmp_path), benign_seeds=sorted(CONFIRMATORY_BENIGN))
    cells = r["plan"]["cells"]
    assert r["missing"] == []
    benign = [c for c in cells if c["operator"].startswith("control.benign_")]
    # 72 cases × static-only × 3 arms × 2 providers × 1 repeat (the reduced control protocol)
    assert len(benign) == 72 * 3 * 2
    assert len({c["case_id"] for c in benign}) == 72
    assert {c["agent"] for c in benign} == {"static"} and {c["repeat_index"] for c in benign} == {0}
    assert {c["anchor"] for c in benign} == set(sweep.ANCHORS)
    assert {c["tier"] for c in benign} == {"control"}
    # The full Part 1 design: 108 faulty × 3 × 2 agents × 2 providers × 2 repeats + 92 controls × 3 × 2
    assert len(cells) == 2592 + 552 == 3144
    assert r["plan"]["header"]["factor_levels"]["benign_seeds"] == sorted(CONFIRMATORY_BENIGN)


def test_plan_without_benign_seeds_is_unchanged(tmp_path):
    r = _part1_plan(_mk_part1_root(tmp_path))
    assert not [c for c in r["plan"]["cells"] if c["operator"].startswith("control.benign_")]
    assert len(r["plan"]["cells"]) == 2592 + 20 * 3 * 2


def test_written_plan_strips_answer_key_from_benign_cells(tmp_path):
    r = _part1_plan(_mk_part1_root(tmp_path), benign_seeds=sorted(CONFIRMATORY_BENIGN))
    doc = yaml.safe_load(sweep.write_plan(r).read_text())
    for c in doc["cells"]:
        assert not set(sweep._PLAN_ANSWER_KEY_FIELDS) & set(c)


# --------------------------------------------------------------------------- #
# exploratory no-passback arm: scheduling
# --------------------------------------------------------------------------- #

def test_exploratory_no_passback_cells(tmp_path):
    r = _part1_plan(_mk_part1_root(tmp_path), benign_seeds=sorted(CONFIRMATORY_BENIGN),
                    no_passback_model=LUNA)
    cells = r["plan"]["cells"]
    x = [c for c in cells if c.get("reasoning_passback") is False]
    # 2 leakage operators × 3 strengths × 6 seeds × 2 repeats, ReAct × off × Luna only
    assert len(x) == 2 * 3 * 6 * 2
    assert {c["operator"] for c in x} == set(LEAK)
    assert {(c["agent"], c["anchor"], c["provider"], c["model"]) for c in x} == {("react", "off", "openai", LUNA)}
    assert all(c["exploratory"] for c in x)
    assert len({c["cell_id"] for c in cells}) == len(cells)          # no id collides with its twin
    assert len(cells) == 3144 + 72
    assert r["plan"]["header"]["exploratory"]["no_passback"]["n_cells"] == 72


def test_exploratory_model_must_be_a_planned_openai_model(tmp_path):
    with pytest.raises(ValueError):
        _part1_plan(_mk_part1_root(tmp_path), no_passback_model="gpt-6-sol")


# --------------------------------------------------------------------------- #
# exploratory arm: client, runner, reasoning check, analysis
# --------------------------------------------------------------------------- #

def test_factory_builds_openai_client_with_passback_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    cell = {"agent": "react", "anchor": "off", "provider": "openai", "model": LUNA,
            "reasoning_passback": False}
    agent = sweep._default_agent_factory(cell, "m")
    assert agent._client._reasoning_passback is False
    assert agent._client.describe()["reasoning_passback"] is False
    on = sweep._default_agent_factory({**cell, "reasoning_passback": True}, "m")
    assert on._client._reasoning_passback is True and "reasoning_passback" not in on._client.describe()
    with pytest.raises(ValueError):
        sweep._make_client("anthropic", HAIKU, reasoning_passback=False)


def test_drop_reasoning_items_keeps_everything_else():
    from harness.llm.client import LLMResponse, Usage
    from harness.llm.openai_client import drop_reasoning_items
    items = [{"type": "reasoning", "encrypted_content": "e"},
             {"type": "function_call", "call_id": "c1", "name": "read_log", "arguments": "{}"},
             {"type": "message", "content": []}]
    resp = LLMResponse(text=None, tool_calls=[], stop_reason="tool_use", usage=Usage(1, 1),
                       assistant_blocks=[{"type": "openai_output_items", "items": items}],
                       reasoning_blocks=1)
    out = drop_reasoning_items(resp)
    assert [i["type"] for i in out.assistant_blocks[0]["items"]] == ["function_call", "message"]
    assert out.reasoning_blocks == 1                        # production still recorded
    assert items[0]["type"] == "reasoning"                  # input not mutated


def _dropping_record(run_id, passback):
    calls = [{"reasoning_blocks": 1, "replayed_reasoning_blocks": 0},
             {"reasoning_blocks": 1, "replayed_reasoning_blocks": 0}]
    cond = {} if passback else {"reasoning_passback": False}
    return {"run_id": run_id, "llm_transcript": calls, "conditions": cond}


def test_reasoning_check_exempts_only_the_no_passback_arm():
    exempt = [_dropping_record(f"x{i}", passback=False) for i in range(6)]
    assert sweep.reasoning_check(exempt)["status"] == "not_applicable"
    assert sweep.reasoning_check(exempt + [_dropping_record("real", passback=True)])["status"] == "failed"


def test_runner_marks_no_passback_records(tmp_path):
    (tmp_path / "cases" / "case_0001").mkdir(parents=True)
    (tmp_path / "cases" / "registry.hidden.yaml").write_text(yaml.dump(
        {"case_0001": {"workload": "tabular_adult", "operator": LEAK[0], "strength": "mild", "seed": 42}}))
    base = {"case_id": "case_0001", "agent": "react", "anchor": "off", "repeat_index": 0,
            "provider": "openai", "model": LUNA}
    cells = [{**base, "cell_id": "on"}, {**base, "cell_id": "off", "reasoning_passback": False}]
    (tmp_path / "sweeps").mkdir()
    (tmp_path / "sweeps" / "s_plan.yaml").write_text(yaml.dump(
        {"header": {"name": "s", "model": "m", "cost_estimate": {"per_cell_total_usd": 0}}, "cells": cells}))
    seen = []

    def trial(agent, case_dir, project_root, conditions=None):
        seen.append(dict(conditions))
        return {"run_id": f"r{len(seen)}", "case_id": "case_0001", "usage": {"estimated_cost_usd": 0.0}}

    r = sweep.run_agents(tmp_path, "s", max_cost_usd=10, require_preconditions=False,
                         agent_factory=lambda c: object(), trial_fn=trial,
                         cost_fn=lambda rec: 0.0, est_fn=lambda c: 0.0)
    assert r["ran"] == 2
    assert [c.get("reasoning_passback") for c in seen] == [None, False]


def _rec(run_id, case, passback, detected, f1):
    cond = {"sweep_name": "s", "agent_type": "react", "anchor": "off", "repeat_index": 0,
            "provider": "openai"}
    if not passback:
        cond["reasoning_passback"] = False
    rec = {"run_id": run_id, "case_id": case, "status": "completed", "conditions": cond,
           "model": {"model_id": LUNA}, "prompt": {"prompt_version": "react-2-off"},
           "environment": {"timestamp_utc": run_id},
           "scores": {"detection": {"correct": detected}, "identification": {"correct": detected},
                      "evidence": {"f1": f1}}}
    return ss.attach_meta(rec, {"operator_id": LEAK[0], "tier": "dynamics"})


def test_exploratory_twin_is_a_separate_cell_and_never_pooled():
    from harness import report_gen
    recs = [_rec("t1", "case_0001", True, True, 0.8), _rec("t2", "case_0001", False, False, 0.2),
            _rec("t3", "case_0002", True, True, 0.6), _rec("t4", "case_0002", False, True, 0.4)]
    kept = ss.dedup_one_per_cell(recs)
    assert len(kept) == 4                                   # the twin is not a retry of its cell
    x = ss.exploratory_no_passback(kept)
    assert x["available"] and x["detection"]["on"] == 1.0 and x["detection"]["off"] == 0.5
    assert round(x["evidence_f1"]["diff"]["point"], 6) == 0.4
    md = report_gen.generate(kept, {"name": "s"})
    primary, _, section = md.partition("## EXPLORATORY")
    assert section, "exploratory section missing"
    assert "n_trials: 2 " in primary                        # only the pass-back-ON trials are primary
    md_without = report_gen.generate([r for r in kept if not r["_exploratory"]], {"name": "s"})
    assert md_without == primary                            # primary tables unchanged by the arm
