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
    assert r["unmeasured"] == [("openai", "react", "confirmatory")]
    assert round(r["projected_total"], 6) == 0.10
