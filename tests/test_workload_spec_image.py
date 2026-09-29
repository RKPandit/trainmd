"""Part 3 harness adaptation (DECISIONS 2026-09-28): the visible metric series comes from the workload / case card,
the evaluator scores image checkpoints, the reference run handles a workload with its own series — and every tabular
path is byte-identical."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

from harness import workload_spec as ws

ROOT = Path(__file__).resolve().parent.parent
TAB = yaml.safe_load((ROOT / "workloads" / "tabular_adult" / "config.yaml").read_text())
IMG = yaml.safe_load((ROOT / "workloads" / "image_fmnist" / "config.yaml").read_text())


def test_series_and_names_per_workload():
    assert ws.visible_series(TAB) == "metric_visible_val_acc" and ws.workload_name(TAB) == "tabular_adult"
    assert ws.visible_series(IMG) == "val_top1" and ws.workload_name(IMG) == "image_fmnist"
    assert ws.workload_family(IMG) == "image"
    assert ws.card_series({}) == "metric_visible_val_acc"
    assert ws.card_series({"reference_visible_metric": {"series": "val_top1"}}) == "val_top1"


def test_image_reference_uses_the_reference_seed_set():
    from harness.seed_sets import REFERENCE
    assert set(IMG["reference"]["seeds"]) == set(REFERENCE) and IMG["reference"]["num_seeds"] == 30


def test_static_agent_series_tabular_unchanged_image_uses_card(tmp_path):
    from agents import static_agent as sa
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "card.public.yaml").write_text(yaml.dump(
        {"reference_visible_metric": {"series": "metric_visible_val_acc"}}))
    assert sa._metric_series_for(tmp_path / "t") == sa._METRIC_SERIES          # byte-identical tabular context
    (tmp_path / "i").mkdir()
    (tmp_path / "i" / "card.public.yaml").write_text(yaml.dump({"reference_visible_metric": {"series": "val_top1"}}))
    assert sa._metric_series_for(tmp_path / "i") == ["train_loss", "val_loss", "val_top1", "lr"]


def test_final_visible_reads_the_named_series(tmp_path):
    rows = [{"epoch": 0, "val_top1": 0.8, "end_of_epoch": True}, {"epoch": 0, "step": 5, "train_loss": 0.4},
            {"epoch": 1, "val_top1": 0.85, "end_of_epoch": True}]
    (tmp_path / "metrics.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert ws.final_visible(tmp_path, "val_top1") == 0.85
    assert ws.final_visible(tmp_path) is None                                   # no tabular series in an image log
    assert ws.final_visible(tmp_path / "nope", "val_top1") is None


def test_b1_reads_the_card_series(tmp_path):
    from harness import baselines as B
    cd = tmp_path / "case_0001"
    ro = cd / "workspace" / "run_output"
    ro.mkdir(parents=True)
    (cd / "card.public.yaml").write_text(yaml.dump(
        {"case_id": "case_0001", "reference_visible_metric": {"series": "val_top1", "mean": 0.88, "std": 0.004}}))
    (ro / "metrics.jsonl").write_text("\n".join(json.dumps({"epoch": i, "val_top1": v, "end_of_epoch": True})
                                                for i, v in enumerate([0.80, 0.86, 0.95])) + "\n")
    sub = B.b1(B.VisibleSurface(cd, ROOT))
    assert sub["diagnosis"]["detected"] is True
    assert sub["evidence_refs"][0]["detail"]["series"] == "val_top1"


def test_workload_files_present_only():
    from harness.build_case import _workload_files
    assert _workload_files(ROOT / "workloads" / "tabular_adult") == ["train.py", "config.yaml", "datautil.py"]
    assert _workload_files(ROOT / "workloads" / "image_fmnist") == ["train.py", "config.yaml"]


def test_evaluator_scores_an_image_checkpoint_on_the_hidden_split(tmp_path):
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint
    from workloads.image_fmnist.train import SmallCNN, to_tensor
    torch.manual_seed(0)
    net = IMG["net"]
    model = SmallCNN(net["in_ch"], net["widths"], net["n_classes"], IMG["data"]["image_size"])
    torch.save({"model_state_dict": model.state_dict(), "net": net, "seed": 0, "epoch": 0}, tmp_path / "ckpt.pt")
    rng = np.random.RandomState(0)
    X = rng.randint(0, 256, size=(40, 28, 28)).astype(np.uint8)
    y = rng.randint(0, 10, size=40).astype(np.int64)
    np.save(tmp_path / "X_test.npy", X)
    np.save(tmp_path / "y_test.npy", y)
    with torch.no_grad():
        want = (model(to_tensor(X, IMG["data"]["norm_mean"], IMG["data"]["norm_std"])).argmax(1).numpy() == y).mean()
    got = evaluate_checkpoint(tmp_path / "ckpt.pt", tmp_path, IMG)["metric_hidden_test_acc"]
    assert got == pytest.approx(round(float(want), 6))


def _fake_reference(tmp_path, monkeypatch, config, series, peak):
    from harness import reference_run as rr
    wd = tmp_path / "wl"
    (wd / "reference").mkdir(parents=True)
    (wd / "config.yaml").write_text(yaml.dump(config))
    monkeypatch.setattr("harness.platform_guard.require_native_amd64", lambda **k: None)
    monkeypatch.setattr("harness.platform_guard.cpu_provenance", lambda: "test")

    def fake_run(cmd, env=None):
        out = Path(cmd[cmd.index("--output-dir") + 1]); seed = int(cmd[cmd.index("--seed") + 1])
        out.mkdir(parents=True)
        row = {"epoch": 0, "train_loss": 0.3, series: 0.80 + seed / 10000, "epoch_time_sec": 1.0, "end_of_epoch": True}
        if peak:
            row["peak_memory_mb"] = 12.0
        (out / "metrics.jsonl").write_text(json.dumps(row) + "\n")
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(rr.subprocess, "run", fake_run)
    monkeypatch.setattr(rr, "evaluate_checkpoint", lambda c, h, cfg: {"metric_hidden_test_acc": 0.7})
    return rr.run_reference(wd, num_seeds=3)


def test_reference_run_image_series_keeps_the_generic_key(tmp_path, monkeypatch):
    cfg = {"pipeline": {"family": "image", "name": "image_fmnist"}, "eval": {"report": "val_top1"},
           "reference": {"num_seeds": 3, "seeds": [200, 201, 202]}}
    st = _fake_reference(tmp_path, monkeypatch, cfg, "val_top1", peak=False)
    assert st["workload"] == "image_fmnist" and st["visible_series"] == "val_top1"
    assert st["metric_visible_val_acc"]["mean"] == pytest.approx(0.8201)
    assert "peak_memory_mb" not in st and "peak_memory_mb" not in st["per_seed"][0]


def test_reference_run_tabular_shape_unchanged(tmp_path, monkeypatch):
    cfg = {"workload": {"family": "tabular", "name": "tabular_adult"}, "metrics": {"visible": "metric_visible_val_acc"},
           "reference": {"num_seeds": 3, "seeds": [200, 201, 202]}}
    st = _fake_reference(tmp_path, monkeypatch, cfg, "metric_visible_val_acc", peak=True)
    assert list(st) == ["workload", "num_seeds", "metric_visible_val_acc", "metric_hidden_test_acc",
                        "wall_time_sec", "peak_memory_mb", "per_seed"]                 # no visible_series key
    assert st["per_seed"][0]["peak_memory_mb"] == 12.0
