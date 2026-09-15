"""Part-B test (STAGE3_PLAN §0.3-B7, addition 3): the report rebuilds from the RELEASE ALONE, with
NO cases/, NO results/, and NO importable registry — the external-verification path.

Two checks: (1) the results-path and release-path reports are byte-identical; (2) rebuild_tables.py
runs to a byte-match in an isolated dir that contains only the harness analysis modules + the
release + the committed report (no `operators/` package on the path).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _mk_root(tmp: Path) -> Path:
    (tmp / "sweeps").mkdir(parents=True)
    cases = [("case_0001", "silent.data_leakage.v1", "positive"),
             ("case_0002", "silent.label_corruption.v1", "negative")]
    for cid, op, symptom in cases:
        (tmp / "cases" / cid / "hidden").mkdir(parents=True)
        (tmp / "results" / cid / "trials").mkdir(parents=True)
        (tmp / "cases" / cid / "hidden" / "verify.yaml").write_text(yaml.dump({
            "faulty_value": 0.80, "tolerance_lower": 0.79, "reference_metric_mean": 0.85,
            "reference_metric_std": 0.01, "hidden_eval_seeds": [100, 101, 102]}))
        (tmp / "cases" / cid / "hidden" / "card.hidden.yaml").write_text(yaml.dump({
            "operator_id": op, "layer": "dynamics", "strength": "moderate", "seed": 42,
            "case_build_id": "bid", "symptom_direction": symptom,
            "visible_sigma_distance": -5.0, "hidden_sigma_distance": -3.0}))
        (tmp / "cases" / cid / "card.public.yaml").write_text(yaml.dump({"case_id": cid}))
        n = 0
        for agent in ("react", "static"):
            for anchor in ("off", "rule"):
                detected = (anchor == "rule")
                rec = {"case_id": cid, "run_id": f"{cid}-{agent}-{anchor}", "trusted": False,
                       "card_superseded": False,
                       "conditions": {"sweep_name": "s", "agent_type": agent, "anchor": anchor,
                                      "repeat_index": 0},
                       "submission": {"diagnosis": {"detected": detected}},
                       "scores": {"detection": {"correct": detected},
                                  "identification": {"correct": detected},
                                  "evidence": {"f1": 0.9 if agent == "react" else 0.6},
                                  "recovery": {"verdict": "recovered" if detected else "not_recovered"}},
                       "tool_transcript": [], "llm_transcript": [], "usage": {"estimated_cost_usd": 0.01},
                       "model": {"model_id": "m"}, "environment": {}, "prompt": {"text": "p"}}
                (tmp / "results" / cid / "trials" / f"t{n}.yaml").write_text(yaml.dump(rec))
                n += 1
    (tmp / "sweeps" / "s_plan.yaml").write_text(yaml.dump({"header": {
        "name": "s", "model": "m", "n_cells": 8,
        "factor_levels": {"anchors": ["off", "rule"]}}}))
    (tmp / "sweeps" / "s_manifest.yaml").write_text(yaml.dump({"timestamp_utc": "2026-09-15T00:00:00+00:00"}))
    return tmp


def test_results_path_and_release_path_are_byte_identical(tmp_path):
    import importlib.util
    from harness import report_gen
    _spec = importlib.util.spec_from_file_location("export_release", ROOT / "scripts" / "export_release.py")
    exp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(exp)

    root = _mk_root(tmp_path)
    from_cases = report_gen.generate_from_cases(root, "s", {"trusted": 0, "superseded": 0})
    exp.export(root, "s")
    from_release = report_gen.generate_from_release(root / "results_release" / "s", "s")
    assert from_cases == from_release


def test_rebuild_from_release_in_isolated_dir_without_registry(tmp_path):
    import importlib.util
    from harness import report_gen
    _spec = importlib.util.spec_from_file_location("export_release", ROOT / "scripts" / "export_release.py")
    exp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(exp)

    root = _mk_root(tmp_path / "build")
    exp.export(root, "s")
    committed = report_gen.generate_from_cases(root, "s", {"trusted": 0, "superseded": 0})

    # Reviewer dir: ONLY the analysis modules + the release + the committed report. No cases/,
    # results/, or operators/ — if the analysis reached into the registry, this would fail.
    rev = tmp_path / "reviewer"
    (rev / "harness").mkdir(parents=True)
    (rev / "scripts").mkdir()
    (rev / "docs" / "audits").mkdir(parents=True)
    for m in ("__init__.py", "anchors.py", "sweep_stats.py", "report_gen.py"):
        shutil.copy2(ROOT / "harness" / m, rev / "harness" / m)
    shutil.copy2(ROOT / "scripts" / "rebuild_tables.py", rev / "scripts" / "rebuild_tables.py")
    shutil.copytree(root / "results_release" / "s", rev / "results_release" / "s")
    (rev / "docs" / "audits" / "sweep_s_generated.md").write_text(committed)
    assert not (rev / "cases").exists() and not (rev / "results").exists()
    assert not (rev / "operators").exists()

    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(rev)}
    r = subprocess.run([sys.executable, str(rev / "scripts" / "rebuild_tables.py"),
                        "--sweep", "s", "--project-root", str(rev)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "reproduces from the release alone" in r.stdout
