"""Stage 4 Part 2 pilot (author's rule 2026-09-27): per-condition settings in the plan, a sampled pilot that
is NEVER scored, excluded from every analysis, and a pilot report that shows only cost, tokens (incl.
thinking), reasoning presence past the first tool call and compliance — no scores.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from harness import sweep
from harness import sweep_stats as ss

PART2_PROVIDERS = [
    "anthropic:claude-sonnet-5:thinking=disabled",
    "anthropic:claude-sonnet-5:effort=medium,max_tokens=16384",
    "anthropic:claude-opus-5-5:effort=medium,max_tokens=16384",
    "openai:gpt-5.6-luna:effort=medium", "openai:gpt-5.6-luna:effort=none",
    "openai:gpt-6-luna:effort=medium", "openai:gpt-6-sol:effort=medium",
]


def test_provider_spec_settings():
    assert sweep.parse_provider_spec("anthropic:claude-sonnet-5:effort=medium,max_tokens=16384") == {
        "provider": "anthropic", "model": "claude-sonnet-5", "effort": "medium", "max_tokens": 16384}
    assert sweep.parse_provider_spec("openai:gpt-5.6-luna") == {"provider": "openai", "model": "gpt-5.6-luna"}
    with pytest.raises(ValueError):
        sweep.parse_provider_spec("openai:gpt-6-sol:temperature=1")


def test_existing_single_model_cell_ids_are_unchanged():
    provs = [{"provider": "anthropic", "model": "h"}, {"provider": "openai", "model": "l"}]
    assert sweep._cell_provider_key(provs[0], provs) == "anthropic"
    assert sweep._cell_provider_key(provs[1], provs) == "openai"


def _root(tmp: Path) -> Path:
    from operators.registry import get_operator
    reg, n = {}, 1
    for op in ("silent.lr_warmup.v1", "silent.data_leakage.v1"):
        for sd in (42, 43):
            reg[f"case_{n:04d}"] = {"workload": getattr(get_operator(op), "WORKLOAD_FAMILY", "tabular_adult"),
                                    "operator": op, "strength": "mild", "seed": sd}
            n += 1
    reg[f"case_{n:04d}"] = {"workload": "tabular_adult", "operator": sweep.CONTROL_OPERATOR, "strength": "mild", "seed": 50}
    for cid in reg:
        (tmp / "cases" / cid).mkdir(parents=True)
        (tmp / "cases" / cid / "card.public.yaml").write_text(yaml.dump({"case_id": cid}))
    (tmp / "cases" / "registry.hidden.yaml").write_text(yaml.dump(reg))
    return tmp


def _pilot(tmp):
    return sweep.plan(_root(tmp), "pilot", strengths=["mild"], faulty_seeds=[42, 43], control_seeds=[50],
                      repeats=2, operators=["silent.lr_warmup.v1", "silent.data_leakage.v1"],
                      providers=[sweep.parse_provider_spec(s) for s in PART2_PROVIDERS],
                      openai_strict_tools=True, pilot_static=3, pilot_react=2)


def test_pilot_samples_per_condition_with_settings_and_unique_ids(tmp_path):
    r = _pilot(tmp_path)
    cells, hdr = r["plan"]["cells"], r["plan"]["header"]
    assert hdr["pilot"]["static_per_condition"] == 3 and "NOT computed" in hdr["pilot"]["scores"]
    per = {}
    for c in cells:
        per.setdefault((c["provider"], c["model"], c.get("effort"), c.get("thinking")), []).append(c["agent"])
    assert len(per) == len(PART2_PROVIDERS)
    assert all(v.count("static") == 3 and v.count("react") == 2 for v in per.values())
    assert len({c["cell_id"] for c in cells}) == len(cells)
    sonnet_off = [c for c in cells if c.get("thinking") == "disabled"]
    assert sonnet_off and all(c["model"] == "claude-sonnet-5" and "effort" not in c for c in sonnet_off)
    assert all(c.get("max_tokens") == 16384 for c in cells if c.get("effort") == "medium" and c["provider"] == "anthropic")
    assert all(c.get("strict_tools") is True for c in cells if c["provider"] == "openai")
    assert not any("strict_tools" in c for c in cells if c["provider"] == "anthropic")


def test_pilot_run_never_scores_and_marks_trials(tmp_path):
    r = _pilot(tmp_path)
    sweep.write_plan(r)
    seen = []

    def trial(agent, case_dir, project_root, conditions=None, score=True):
        seen.append((score, conditions.get("pilot")))
        return {"run_id": f"r{len(seen)}", "case_id": case_dir.name, "usage": {"estimated_cost_usd": 0.0}}

    out = sweep.run_agents(tmp_path, "pilot", max_cost_usd=10, require_preconditions=False,
                           agent_factory=lambda c: object(), trial_fn=trial, cost_fn=lambda rec: 0.0,
                           est_fn=lambda c: 0.0, max_trials=4)
    assert out["ran"] == 4 and seen and all(s is False and p is True for s, p in seen)


def test_pilot_is_refused_by_report_and_verify(tmp_path):
    sweep.write_plan(_pilot(tmp_path))
    with pytest.raises(SystemExit, match="PILOT"):
        sweep.report(tmp_path, "pilot")
    assert "never scored" in sweep.run_verify(tmp_path, "pilot")["error"]


def test_loaders_drop_pilot_trials(tmp_path):
    rel = tmp_path / "rel"
    (rel / "trials").mkdir(parents=True)
    (rel / "cases").mkdir()
    (rel / "cases" / "case_0001.json").write_text('{"operator_id": "silent.lr_warmup.v1"}')
    import json
    for i, pilot in enumerate((True, False)):
        cond = {"sweep_name": "x", "agent_type": "static", "anchor": "off", "repeat_index": i, "provider": "openai"}
        if pilot:
            cond["pilot"] = True
        (rel / "trials" / f"case_0001__r{i}.json").write_text(json.dumps(
            {"case_id": "case_0001", "run_id": f"r{i}", "status": "completed", "conditions": cond}))
    assert [r["run_id"] for r in ss.load_from_release(rel)] == ["r1"]


def _rec(prov, model, agent, cost, reasoning, scores=None, **cond):
    rt = (lambda n: None) if prov == "anthropic" else (lambda n: n * reasoning)   # as the clients record it
    turns = [{"reasoning_blocks": reasoning, "usage": {"reasoning_tokens": rt(50)},
              "tool_calls": [{"name": "read_log", "arguments": {}}]},
             {"reasoning_blocks": reasoning, "usage": {"reasoning_tokens": rt(40)},
              "tool_calls": [{"name": "submit", "arguments": {"diagnosis": {"detected": True}}}]}]
    r = {"status": "completed", "conditions": {"provider": prov, "agent_type": agent, **cond},
         "model": {"model_id": model}, "llm_transcript": turns,
         "usage": {"estimated_cost_usd": cost, "input_tokens": 1000, "output_tokens": 300, "max_tokens_truncations": 0},
         "submission": {"diagnosis": {"detected": True, "operator_class": "x"}}, "compliance": {"missing_fields": []}}
    if scores is not None:
        r["scores"] = scores
    return r


def test_pilot_report_shows_no_scores_and_never_reads_them():
    recs = [_rec("anthropic", "claude-sonnet-5", "react", 0.12, 1, effort="medium"),
            _rec("openai", "gpt-6-sol", "static", 0.02, 1, effort="medium", strict_tools=True)]
    scored = copy.deepcopy(recs)
    for r in scored:
        r["scores"] = {"detection": {"correct": True}, "identification": {"correct": False},
                       "evidence": {"f1": 0.123}, "recovery": {"verdict": "recovered"}}
    out = sweep.pilot_report(recs)
    assert sweep.pilot_report(scored) == out                    # scores present or not: identical output
    for word in ("0.123", "recovered", "identification |", "evidence |"):
        assert word not in out
    assert "| 1/1 |" in out and "claude-sonnet-5" in out and "| yes |" in out   # reasoning past 1st call; strict


def test_pilot_report_reasoning_tokens_from_usage_and_not_reported_never_zero():
    recs = [_rec("anthropic", "claude-sonnet-5", "static", 0.03, 1, effort="medium"),
            _rec("openai", "gpt-5.6-luna", "static", 0.002, 1, effort="medium", strict_tools=True),
            _rec("openai", "gpt-5.6-luna", "static", 0.002, 0, effort="none", strict_tools=True)]
    rows = {ln.split(" | ")[1] + "/" + ln.split(" | ")[2]: ln.split(" | ") for ln in sweep.pilot_report(recs).splitlines()
            if ln.startswith("| anthropic") or ln.startswith("| openai")}
    col = 12                                               # "reasoning tok"
    assert rows["claude-sonnet-5/medium"][col] == "not reported"
    assert rows["gpt-5.6-luna/medium"][col] == "90"        # 50 + 40, read from each call's usage
    assert rows["gpt-5.6-luna/none"][col] == "0"           # reported, and genuinely zero
    assert rows["claude-sonnet-5/medium"][col + 1] == "1/1" and rows["gpt-5.6-luna/none"][col + 1] == "0/1"


def test_openai_parse_records_none_when_no_reasoning_breakout():
    from types import SimpleNamespace
    from harness.llm.openai_client import parse_responses
    item = SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="hi")],
                           model_dump=lambda exclude_none=True: {"type": "message"})
    base = dict(output=[item], status="completed", model="m", id="r")
    no_details = SimpleNamespace(input_tokens=5, output_tokens=2, input_tokens_details=None, output_tokens_details=None)
    assert parse_responses(SimpleNamespace(usage=no_details, **base)).raw["reasoning_tokens"] is None
    details = SimpleNamespace(input_tokens=5, output_tokens=2, input_tokens_details=None,
                              output_tokens_details=SimpleNamespace(reasoning_tokens=7))
    assert parse_responses(SimpleNamespace(usage=details, **base)).raw["reasoning_tokens"] == 7
