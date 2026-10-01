"""Every HARNESS-AUTHORED string an agent sees on an IMAGE case must be free of workload-1-only identifiers (Part 3
pilot finding, 2026-10-01: the ReAct query_metrics example named workload 1's 'metric_visible_val_acc', and the
static context carried a 'datautil.py' section). Workspace FILE CONTENTS are case data, not harness text, and are
excluded (the image train.py docstring is recorded in LIMITATIONS L42). The STATIC agent is deliberately NOT changed
— the Part 3 static sweep started on the pre-fix commit and its inputs must stay byte-identical
(tests/test_static_inputs_image.py) — so its one workload-1 remnant, the empty 'datautil.py' section, is pinned here as
exactly that known artifact (L42), and nothing else may appear. Workload 1's tool schema is unchanged."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from agents import llm_agent as la
from agents.static_agent import StaticContextAgent
from harness.llm.openai_client import to_responses_tools
from harness.tools.tool_context import ToolContext as _ToolContext
from harness.tools.tools import register_all_tools


def ToolContext(case):            # a context with the real tools registered (as run_trial does)
    ctx = _ToolContext(case)
    register_all_tools(ctx)
    return ctx

ROOT = Path(__file__).resolve().parent.parent
WORKLOAD1_ONLY = ("metric_visible_val_acc", "training.lr", "datautil", "tabular", "adult", "income",
                  "input_dim", "label_noise_fraction", "include_aux_feature", "eval_subset_fraction", "opt_c")


def _image_case(tmp: Path) -> Path:
    case = tmp / "case_0201"
    ws = case / "workspace"
    (ws / "run_output" / "logs").mkdir(parents=True)
    for f in ("train.py", "config.yaml"):
        shutil.copy2(ROOT / "workloads" / "image_fmnist" / f, ws / f)
    cfg = yaml.safe_load((ws / "config.yaml").read_text())
    (ws / "run_output" / "config.resolved.yaml").write_text(yaml.dump({**cfg, "seed": 42}))
    rows = [{"epoch": e, "step": 10 * (e + 1), "train_loss": 0.5, "val_loss": 0.4, "val_top1": 0.88, "lr": 0.05,
             "end_of_epoch": True} for e in range(8)]
    (ws / "run_output" / "metrics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (ws / "run_output" / "logs" / "stdout.log").write_text("[INFO] Training complete.\n")
    (ws / "run_output" / "exitcode").write_text("0")
    (case / "card.public.yaml").write_text(yaml.dump({
        "case_id": "case_0201", "workload_family": "image", "workload_name": "image_fmnist",
        "permitted_tools": ["read_log", "query_metrics", "read_config", "read_code", "list_files", "submit"],
        "reference_visible_metric": {"series": "val_top1", "mean": 0.886033, "std": 0.008633, "n": 30},
        "agent_budget": {"max_tool_calls": 40, "max_reruns": 2, "max_rerun_steps_fraction": 0.25,
                         "max_submissions": 1}}))
    return case


def _clean(text: str) -> list[str]:
    low = text.lower()
    return [w for w in WORKLOAD1_ONLY if w.lower() in low]


def test_react_prompt_and_tools_name_only_the_image_workload(tmp_path):
    case = _image_case(tmp_path)
    tools = la.tools_schema_for(case)
    by = {t["name"]: t for t in tools}
    assert "'val_top1'" in by["query_metrics"]["input_schema"]["properties"]["series"]["description"]
    assert "'optim.base_lr'" in by["read_config"]["input_schema"]["properties"]["key_path"]["description"]
    texts = [json.dumps(tools), json.dumps(to_responses_tools(tools, strict=True)), json.dumps(to_responses_tools(tools))]
    texts += [la._build_instruction_prompt(case, arm=a) for a in ("off", "stats", "rule")]
    for t in texts:
        assert _clean(t) == [], _clean(t)


def test_static_context_carries_only_the_known_datautil_remnant(tmp_path):
    case = _image_case(tmp_path)
    agent = StaticContextAgent(client=None, anchor="stats")
    agent._series = __import__("agents.static_agent", fromlist=["x"])._metric_series_for(case)
    msg, _ = agent._assemble_user_message(ToolContext(case))
    assert _clean(agent._instruction_prompt(case)) == []
    # the documented remnant (L42): an empty datautil.py section — removed from the check, then nothing else may appear
    remnant = "### datautil.py\n\n```\n(unavailable: ARTIFACT_NOT_FOUND)\n```"
    assert msg.count(remnant) == 1
    headers = [ln for ln in msg.replace(remnant, "").splitlines() if ln.startswith("#")]
    assert _clean("\n".join(headers)) == [] and "val_top1" in msg


def test_tool_errors_name_only_what_the_agent_asked(tmp_path):
    ctx = ToolContext(_image_case(tmp_path))
    res = ctx.call("query_metrics", series="no_such_series")
    assert res["status"] == "error" and _clean(json.dumps(res)) == []
    ok = ctx.call("query_metrics", series="val_top1")
    assert ok["status"] == "ok" and len(ok["values"]) == 8


def test_workload1_tools_are_the_canonical_schema_unchanged(tmp_path):
    case = tmp_path / "case_0001"
    (case / "workspace").mkdir(parents=True)
    shutil.copy2(ROOT / "workloads" / "tabular_adult" / "config.yaml", case / "workspace" / "config.yaml")
    (case / "card.public.yaml").write_text(yaml.dump({"reference_visible_metric": {"mean": 0.856, "std": 0.002}}))
    assert la.tools_schema_for(case) is la.TOOLS_SCHEMA             # same object → same tools_sha256 as Parts 1–2
