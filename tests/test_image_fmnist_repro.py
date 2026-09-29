"""Part 3 prerequisites (DECISIONS 2026-09-27): Fashion-MNIST provenance checks and the byte-identity
fingerprint used by the two-AMD-runner check (`scripts/image_repro.sh`, CI dispatch task image-repro)."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fp = _load("fp", "scripts/fingerprint_training.py")
dp = _load("dp", "workloads/image_fmnist/data_prep.py")


def _run(d: Path, w: float, val: float, secs: float):
    (d / "checkpoints").mkdir(parents=True)
    torch.save({"model_state_dict": {"b": torch.tensor([1.0]), "a": torch.tensor([w, 2.0])}},
               d / "checkpoints" / "ckpt_final.pt")
    rows = [{"epoch": 0, "step": 1, "train_loss": 0.5},
            {"epoch": 0, "step": 1, "val_top1": val, "epoch_time_sec": secs, "end_of_epoch": True}]
    (d / "metrics.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (d / "exitcode").write_text("0")


def _doc(tmp, name, **kw):
    d = tmp / name / "seed0"
    _run(d, **kw)
    return {"note": name, "runs": {"seed0": fp.fingerprint(d)}}


def test_wall_time_is_ignored_but_every_value_counts(tmp_path):
    a = _doc(tmp_path, "a", w=0.25, val=0.9, secs=4.2)
    b = _doc(tmp_path, "b", w=0.25, val=0.9, secs=9.9)            # only wall time differs
    assert fp.compare(a, b) == []
    c = _doc(tmp_path, "c", w=0.25, val=0.9000001, secs=4.2)     # one metric value differs
    assert any("metrics_sha256" in d for d in fp.compare(a, c))
    e = _doc(tmp_path, "e", w=0.2500001, val=0.9, secs=4.2)      # one weight differs
    assert any("weights_sha256" in d for d in fp.compare(a, e))


def test_a_failed_run_is_never_identical(tmp_path):
    a = _doc(tmp_path, "a", w=0.25, val=0.9, secs=1.0)
    bad = json.loads(json.dumps(a))
    bad["runs"]["seed0"]["exitcode"] = "1"
    assert fp.compare(a, bad) and fp.compare(bad, bad)


def test_idx_decoding(tmp_path):
    imgs = np.arange(2 * 3 * 4, dtype=np.uint8).reshape(2, 3, 4)
    hdr = (0x0803).to_bytes(4, "big") + b"".join(n.to_bytes(4, "big") for n in imgs.shape)
    with gzip.open(tmp_path / "x.gz", "wb") as f:
        f.write(hdr + imgs.tobytes())
    assert np.array_equal(dp._read_idx(tmp_path / "x.gz"), imgs)


def test_source_checksum_mismatch_is_fatal(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "f.gz").write_bytes(b"not the dataset")
    cfg = {"source_base_url": "unused/", "source_files": {"f.gz": {"md5_published": "0" * 32, "sha256": "0" * 64}}}
    with pytest.raises(SystemExit, match="published checksums"):
        dp.fetch_sources(cfg, raw)


def test_committed_pin_and_published_md5s_are_recorded():
    cfg = yaml.safe_load((ROOT / "workloads/image_fmnist/data_split.yaml").read_text())
    assert cfg["source_files"]["train-images-idx3-ubyte.gz"]["md5_published"] == "8d4fb7e6c68d591d4c3dfef9ec88bf0d"
    pin = yaml.safe_load((ROOT / "workloads/image_fmnist/reference/data_manifest.yaml").read_text())
    assert set(pin["files"]) == set(dp.VISIBLE_FILES + dp.HIDDEN_FILES)
    assert all(len(str(h)) == 64 for h in pin["files"].values())
