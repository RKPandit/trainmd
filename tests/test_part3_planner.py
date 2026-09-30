"""Part 3 plans (design approved 2026-09-29, option C): per condition, STATIC = faulty × off/stats/rule × 2 repeats
(756) + controls × 3 arms × 1 (312); ReAct = faulty × off/stats × 1 (252) + controls × off/stats × 1 (208) — the
controls run under ReAct too (`--controls-all-agents`). Enumerated from the image workload group."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from harness import sweep
from harness.seed_sets import CONFIRMATORY_BENIGN_IMAGE, CONFIRMATORY_CONTROL, CONFIRMATORY_FAULTY

PROVIDERS = [sweep.parse_provider_spec(s) for s in (
    "anthropic:claude-haiku-4-5-20251001", "anthropic:claude-sonnet-5:thinking=disabled",
    "openai:gpt-5.6-luna:effort=medium", "openai:gpt-5.6-luna:effort=none")]


def _cells(tmp_path: Path, agents, anchors, repeats, controls_all_agents):
    cells, _missing = sweep.enumerate_cells(
        tmp_path, ["mild", "moderate", "severe"], sorted(CONFIRMATORY_FAULTY), sorted(CONFIRMATORY_CONTROL), repeats,
        providers=PROVIDERS, benign_seeds=sorted(CONFIRMATORY_BENIGN_IMAGE), agents=agents, anchors=anchors,
        workload_group="image_fmnist", controls_all_agents=controls_all_agents)
    return cells


def test_static_plan_is_the_part1_protocol_on_the_image_cases(tmp_path):
    cells = _cells(tmp_path, ["static"], ["off", "stats", "rule"], 2, False)
    per = Counter((c["model"], c.get("effort") or c.get("thinking"), c["tier"] == "control") for c in cells)
    for prov in PROVIDERS:
        key = (prov["model"], prov.get("effort") or prov.get("thinking"))
        assert per[key + (False,)] == 756 and per[key + (True,)] == 312
    assert len(cells) == 4 * 1068
    assert all(c["operator"].split(".")[1].startswith(("pixel_tag", "label_flip", "decay_unit", "confident_subset",
                                                       "channel_mismatch", "healthy_image", "benign_img_"))
               for c in cells)


def test_react_plan_runs_the_controls_too(tmp_path):
    cells = _cells(tmp_path, ["react"], ["off", "stats"], 1, True)
    assert len(cells) == 4 * 460
    assert sum(c["tier"] == "control" for c in cells) == 4 * 208
    assert {c["agent"] for c in cells} == {"react"} and {c["anchor"] for c in cells} == {"off", "stats"}


def test_default_planner_is_unchanged_for_workload_1(tmp_path):
    cells, _ = sweep.enumerate_cells(tmp_path, ["mild"], [42], [50], 1, agents=["react"], anchors=["off"])
    assert {c["operator"] for c in cells} >= {"control.healthy.v1", "silent.lr_warmup.v1"}
    assert all(c["agent"] == "static" for c in cells if c["tier"] == "control")    # controls static-only by default
