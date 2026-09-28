"""Prepare Fashion-MNIST for the image_fmnist workload (Stage 4 Part 3; DECISIONS 2026-09-27).

Offline data-preparation step, never run inside the workspace container (harness_spec §2): visible splits
go to .data/ (mounted into the workspace), the hidden evaluation split to .hidden_data/ (evaluator only).

Provenance is checked twice, and either mismatch fails LOUDLY:
  1. each official source file against the authors' published MD5 and our recorded sha256 (data_split.yaml);
  2. each prepared split against the committed PIN (reference/data_manifest.yaml).
Unlike the Adult bootstrap, a missing pin is an ERROR, not a warning; `--write-pin` creates it once, from a
download that has just passed check 1.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import yaml

VISIBLE_FILES = ["X_train.npy", "y_train.npy", "X_val.npy", "y_val.npy"]
HIDDEN_FILES = ["X_test.npy", "y_test.npy"]


def _digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_sources(cfg: dict, raw_dir: Path) -> None:
    """Download any missing source file, then verify EVERY file's published MD5 and recorded sha256."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    bad = []
    for name, want in cfg["source_files"].items():
        dest = raw_dir / name
        if not dest.exists():
            urllib.request.urlretrieve(cfg["source_base_url"] + name, dest)
        md5, sha = _digest(dest, "md5"), _digest(dest, "sha256")
        if md5 != str(want["md5_published"]) or sha != str(want["sha256"]):
            bad.append(f"  {name}: md5 {md5} (published {want['md5_published']}), sha256 {sha[:12]}… "
                       f"(recorded {str(want['sha256'])[:12]}…)")
    if bad:
        raise SystemExit("\nFATAL: Fashion-MNIST source files do not match the published checksums:\n"
                         + "\n".join(bad) + "\n  Delete the raw cache and re-fetch; never train on them.\n")


def _read_idx(path: Path) -> np.ndarray:
    """Decode an IDX (ubyte) file: images -> (n, 28, 28) uint8, labels -> (n,) uint8."""
    with gzip.open(path, "rb") as f:
        data = f.read()
    magic = int.from_bytes(data[0:4], "big")
    ndim = magic & 0xFF
    dims = [int.from_bytes(data[4 + 4 * i: 8 + 4 * i], "big") for i in range(ndim)]
    arr = np.frombuffer(data, dtype=np.uint8, offset=4 + 4 * ndim)
    return arr.reshape(dims).copy()


def split(cfg: dict, raw_dir: Path) -> dict[str, np.ndarray]:
    Xtr = _read_idx(raw_dir / "train-images-idx3-ubyte.gz")
    ytr = _read_idx(raw_dir / "train-labels-idx1-ubyte.gz")
    Xte = _read_idx(raw_dir / "t10k-images-idx3-ubyte.gz")
    yte = _read_idx(raw_dir / "t10k-labels-idx1-ubyte.gz")
    assert Xtr.shape == (60000, 28, 28) and Xte.shape == (10000, 28, 28), (Xtr.shape, Xte.shape)
    rng = np.random.RandomState(int(cfg["prep_seed"]))
    p_tr = rng.permutation(len(ytr))
    p_te = rng.permutation(len(yte))
    n_tr, n_va, n_hi = int(cfg["n_train"]), int(cfg["n_val"]), int(cfg["n_hidden"])
    i_tr, i_va, i_hi = p_tr[:n_tr], p_tr[n_tr:n_tr + n_va], p_te[:n_hi]
    return {"X_train.npy": Xtr[i_tr], "y_train.npy": ytr[i_tr].astype(np.int64),
            "X_val.npy": Xtr[i_va], "y_val.npy": ytr[i_va].astype(np.int64),
            "X_test.npy": Xte[i_hi], "y_test.npy": yte[i_hi].astype(np.int64)}


def prepare(workload_dir: Path, write_pin: bool = False) -> dict[str, str]:
    cfg = yaml.safe_load((workload_dir / "data_split.yaml").read_text())
    raw_dir = workload_dir / ".raw"
    fetch_sources(cfg, raw_dir)
    arrays = split(cfg, raw_dir)
    out = {}
    for name, arr in arrays.items():
        d = workload_dir / (".data" if name in VISIBLE_FILES else ".hidden_data")
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / name, arr, allow_pickle=False)
        out[name] = _digest(d / name, "sha256")
    for d, names in ((workload_dir / ".data", VISIBLE_FILES), (workload_dir / ".hidden_data", HIDDEN_FILES)):
        (d / "manifest.json").write_text(json.dumps({"files": {n: out[n] for n in names}}, indent=2) + "\n")

    pin_path = workload_dir / "reference" / "data_manifest.yaml"
    if write_pin:
        if pin_path.exists():
            raise SystemExit(f"refusing to overwrite the committed pin {pin_path} (supersedes every case)")
        pin_path.parent.mkdir(parents=True, exist_ok=True)
        pin_path.write_text(
            "# Committed expected SHA-256 of every prepared split — the data-provenance PIN (as for Adult).\n"
            "# data_prep.py FAILS LOUDLY if the verified source files + seeded split do not reproduce these\n"
            "# bytes. Written once, 2026-09-27, from a download whose four files matched the authors'\n"
            "# published MD5s. A change here supersedes the reference and every case.\n"
            + yaml.dump({"n_train": int(cfg["n_train"]), "n_val": int(cfg["n_val"]), "n_hidden": int(cfg["n_hidden"]),
                         "files": out}, default_flow_style=False, sort_keys=False))
        print(f"wrote pin {pin_path}")
        return out
    if not pin_path.exists():
        raise SystemExit(f"FATAL: no data pin at {pin_path} (create it once with --write-pin)")
    pin = {k: str(v) for k, v in (yaml.safe_load(pin_path.read_text())["files"]).items()}
    bad = [f"  {n}: expected {pin.get(n, '<missing>')[:12]}… got {h[:12]}…" for n, h in out.items() if pin.get(n) != h]
    if bad:
        raise SystemExit("\nFATAL: prepared Fashion-MNIST splits do NOT match the committed pin:\n" + "\n".join(bad)
                         + "\n  Do NOT train on drifted data; investigate.\n")
    print(f"Data provenance PIN verified ({len(out)} splits; sources match the published MD5s).")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workload-dir", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--write-pin", action="store_true")
    a = ap.parse_args()
    prepare(a.workload_dir, a.write_pin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
