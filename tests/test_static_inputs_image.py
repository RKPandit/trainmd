"""Part 3 runs from TWO commits (author, 2026-10-01): the static slice / sweep started on the pre-fix commit, ReAct
runs on the post-fix commit. The fix (agents/llm_agent.py::tools_schema_for) touched ONLY ReAct tool text, so the
STATIC agent's complete input — instruction prompt, assembled context (every artifact it reads), submit-tool config —
must be BYTE-IDENTICAL before and after it. This pins the digests the PRE-fix code produced
(tests/fixtures/static_inputs_image_prefix.json, generated at origin/main 9fbc033) on synthetic image cases built
only from committed workload files; a real-case check (23 certified image cases × 3 arms, all identical) is in
DECISIONS 2026-10-01."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "static_inputs_image_prefix.json"

# (name, workload family dir, config edits, exitcode) — clean, two fault configurations, a neutral family, a crash
VARIANTS = [
    ("img_clean", "image_fmnist", {}, 0),
    ("img_tag", "image_fmnist", {"data": {"corner_tag": True, "corner_tag_noise": 0.2}}, 0),
    ("img_subset", "image_fmnist", {"eval": {"report": "val_top1", "confident_fraction": 0.85}}, 0),
    ("img_neutral", "image_fmnist_neutral", {"data": {"opt_t": True, "opt_t_level": 0.15}}, 0),
    ("img_crash", "image_fmnist", {"net": {"in_ch": 3}}, 1),
]


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out.get(k, {}), v) if isinstance(v, dict) else v
    return out


def synthetic_cases(tmp: Path) -> list[Path]:
    cases = []
    for name, family, edit, exitcode in VARIANTS:
        case = tmp / name
        ws = case / "workspace"
        (ws / "run_output" / "logs").mkdir(parents=True)
        shutil.copy2(ROOT / "workloads" / family / "train.py", ws / "train.py")
        cfg = _merge(yaml.safe_load((ROOT / "workloads" / "image_fmnist" / "config.yaml").read_text()), edit)
        (ws / "config.yaml").write_text(yaml.dump(cfg, sort_keys=False))
        (ws / "run_output" / "config.resolved.yaml").write_text(yaml.dump({**cfg, "seed": 42}, sort_keys=False))
        rows = [] if exitcode else [
            {"epoch": e, "step": 157 * (e + 1), "train_loss": round(0.6 - 0.04 * e, 6), "val_loss": round(0.45 - 0.01 * e, 6),
             "val_top1": round(0.84 + 0.006 * e, 6), "lr": 0.05, "end_of_epoch": True} for e in range(8)]
        (ws / "run_output" / "metrics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        log = "[INFO] Training seed=42\n" + ("[ERROR] Training failed:\nTraceback (most recent call last):\n"
                                              "RuntimeError: channels\n" if exitcode else "[INFO] Training complete.\n")
        (ws / "run_output" / "logs" / "stdout.log").write_text(log)
        (ws / "run_output" / "exitcode").write_text(str(exitcode))
        (case / "card.public.yaml").write_text(yaml.dump({
            "case_id": name, "workload_family": "image", "workload_name": family,
            "permitted_tools": ["read_log", "query_metrics", "read_config", "read_code", "list_files", "submit"],
            "reference_visible_metric": {"series": "val_top1", "mean": 0.886033, "std": 0.008633, "n": 30},
            "agent_budget": {"max_tool_calls": 40, "max_reruns": 2, "max_rerun_steps_fraction": 0.25,
                             "max_submissions": 1}}))
        cases.append(case)
    return cases


def static_input_digests(cases) -> dict:
    from agents import static_agent as sa
    from agents.llm_agent import SUBMIT_SCHEMA
    from harness.tools.tool_context import ToolContext
    from harness.tools.tools import register_all_tools
    out = {}
    for case in cases:
        for arm in ("off", "stats", "rule"):
            a = sa.StaticContextAgent(client=None, anchor=arm)
            a._series = sa._metric_series_for(case)
            ctx = ToolContext(case)
            register_all_tools(ctx)
            msg, trunc = a._assemble_user_message(ctx)
            # a REAL context: every artifact this case has was read (only the absent datautil.py is unavailable)
            assert msg.count("(unavailable:") == 1 and "TOOL_NOT_AVAILABLE" not in msg, case.name
            blob = json.dumps({"instruction": a._instruction_prompt(case), "user": msg, "truncated": trunc,
                               "submit_schema": SUBMIT_SCHEMA}, sort_keys=True)
            out[f"{case.name}:{arm}"] = hashlib.sha256(blob.encode()).hexdigest()
    return out


def test_static_inputs_are_byte_identical_to_the_pre_fix_commit(tmp_path):
    assert static_input_digests(synthetic_cases(tmp_path)) == json.loads(FIXTURE.read_text())
