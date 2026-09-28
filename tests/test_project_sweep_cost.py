"""scripts/project_sweep_cost.py: projects from the sweep's OWN measured costs, per group; never guesses."""
from __future__ import annotations

import yaml

from scripts.project_sweep_cost import project


def _setup(tmp, cells, trials):
    (tmp / "sweeps").mkdir()
    (tmp / "sweeps" / "s_plan.yaml").write_text(yaml.dump({"header": {}, "cells": cells}))
    d = tmp / "results" / "case_0001" / "trials"
    d.mkdir(parents=True)
    for i, (prov, agent, cost, off) in enumerate(trials):
        cond = {"sweep_name": "s", "provider": prov, "agent_type": agent}
        if off:
            cond["reasoning_passback"] = False
        (d / f"t{i}.yaml").write_text(yaml.dump({"conditions": cond, "usage": {"estimated_cost_usd": cost}}))


def test_projection_uses_measured_group_means(tmp_path):
    cells = ([{"provider": "anthropic", "agent": "react"}] * 10 + [{"provider": "openai", "agent": "static"}] * 4
             + [{"provider": "openai", "agent": "react", "reasoning_passback": False}] * 2)
    _setup(tmp_path, cells, [("anthropic", "react", 0.10, False), ("anthropic", "react", 0.20, False),
                             ("openai", "static", 0.01, False), ("openai", "react", 0.05, True)])
    r = project(tmp_path, "s")
    assert round(r["projected_total"], 6) == round(10 * 0.15 + 4 * 0.01 + 2 * 0.05, 6)
    assert r["unmeasured"] == [] and round(r["spent_so_far"], 6) == 0.36


def test_unmeasured_group_is_reported_not_guessed(tmp_path):
    cells = [{"provider": "anthropic", "agent": "react"}, {"provider": "openai", "agent": "react"}]
    _setup(tmp_path, cells, [("anthropic", "react", 0.10, False)])
    r = project(tmp_path, "s")
    assert r["unmeasured"] == [("openai", None, "—", "react", "confirmatory")]
    assert round(r["projected_total"], 6) == 0.10



def _setup_models(tmp, cells, trials):
    """trials: (provider, model, {settings}, agent, cost)."""
    (tmp / "sweeps").mkdir()
    (tmp / "sweeps" / "s_plan.yaml").write_text(yaml.dump({"header": {}, "cells": cells}))
    d = tmp / "results" / "case_0001" / "trials"
    d.mkdir(parents=True)
    for i, (prov, model, st, agent, cost) in enumerate(trials):
        (d / f"t{i}.yaml").write_text(yaml.dump({
            "conditions": {"sweep_name": "s", "provider": prov, "agent_type": agent, **st},
            "model": {"model_id": model}, "usage": {"estimated_cost_usd": cost}}))


def test_groups_by_model_and_setting_never_mix_conditions(tmp_path):
    # Part 2 shape: two Sonnet conditions (off / xhigh) and two OpenAI models with very different prices,
    # with a slice that over-samples the cheap ones — the per-provider mean would be badly off.
    cells = ([{"provider": "anthropic", "model": "claude-sonnet-5", "thinking": "disabled", "agent": "static"}] * 100
             + [{"provider": "anthropic", "model": "claude-sonnet-5", "effort": "xhigh", "agent": "static"}] * 100
             + [{"provider": "openai", "model": "gpt-6-luna", "effort": "medium", "agent": "static"}] * 100
             + [{"provider": "openai", "model": "gpt-6-sol", "effort": "medium", "agent": "static"}] * 100)
    trials = ([("anthropic", "claude-sonnet-5", {"thinking": "disabled"}, "static", 0.02)] * 9
              + [("anthropic", "claude-sonnet-5", {"effort": "xhigh"}, "static", 0.04)]
              + [("openai", "gpt-6-luna", {"effort": "medium"}, "static", 0.001)] * 9
              + [("openai", "gpt-6-sol", {"effort": "medium"}, "static", 0.02)])
    _setup_models(tmp_path, cells, trials)
    r = project(tmp_path, "s")
    assert r["unmeasured"] == []
    assert round(r["projected_total"], 6) == round(100 * (0.02 + 0.04 + 0.001 + 0.02), 6)
    groups = {g[:3] for g, *_ in r["rows"]}
    assert ("anthropic", "claude-sonnet-5", "thinking=disabled") in groups
    assert ("anthropic", "claude-sonnet-5", "effort=xhigh") in groups
    assert ("openai", "gpt-6-sol", "effort=medium") in groups


def test_a_condition_without_a_finished_trial_is_unmeasured(tmp_path):
    cells = [{"provider": "openai", "model": "gpt-6-luna", "effort": "medium", "agent": "static"},
             {"provider": "openai", "model": "gpt-6-sol", "effort": "medium", "agent": "static"}]
    _setup_models(tmp_path, cells, [("openai", "gpt-6-luna", {"effort": "medium"}, "static", 0.001)])
    r = project(tmp_path, "s")
    assert r["unmeasured"] == [("openai", "gpt-6-sol", "effort=medium", "static", "confirmatory")]
