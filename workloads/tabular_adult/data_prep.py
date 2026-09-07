"""Prepare the Adult dataset for the tabular_adult workload.

NOTE: In later milestones, training runs execute inside no-network containers
(SageMaker contract, harness_spec §2). Data preparation always happens
*outside* the workspace container; the prepared .npy files are mounted into
/opt/ml/input/data/<channel>/.  This script is the offline data-preparation
step and is never called from inside the workspace image.

Visible data (.data/) is mounted into the workspace.  Hidden holdout data
(.hidden_data/) is mounted ONLY into the evaluator container — the workspace
never sees it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.datasets import fetch_openml
from sklearn.preprocessing import StandardScaler


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


_VISIBLE_FILES = [
    "X_train.npy",
    "y_train.npy",
    "X_val.npy",
    "y_val.npy",
]

_HIDDEN_FILES = [
    "X_test.npy",
    "y_test.npy",
]


def _verify_manifest(base_dir: Path, manifest_path: Path, expected: list[str]) -> bool:
    """Return True if all files exist and match their recorded checksums."""
    try:
        manifest = json.loads(manifest_path.read_text())
        return all(
            (base_dir / fname).exists()
            and sha256_file(base_dir / fname) == manifest["files"][fname]
            for fname in expected
        )
    except (KeyError, json.JSONDecodeError, FileNotFoundError):
        return False


def prepare(workload_dir: Path, force: bool = False) -> Path:
    """Download, preprocess, and save Adult dataset splits.

    Returns the path to the visible data directory.
    """
    split_cfg_path = workload_dir / "data_split.yaml"
    with open(split_cfg_path) as f:
        split_cfg = yaml.safe_load(f)

    data_dir = workload_dir / ".data"
    hidden_dir = workload_dir / ".hidden_data"
    visible_manifest = data_dir / "manifest.json"
    hidden_manifest = hidden_dir / "manifest.json"

    # ------------------------------------------------------------------
    # Fast path: reuse existing data if both manifests verify
    # ------------------------------------------------------------------
    if not force and visible_manifest.exists() and hidden_manifest.exists():
        vis_ok = _verify_manifest(data_dir, visible_manifest, _VISIBLE_FILES)
        hid_ok = _verify_manifest(hidden_dir, hidden_manifest, _HIDDEN_FILES)
        if vis_ok and hid_ok:
            print("Data already prepared; checksums verified.")
            return data_dir

    data_dir.mkdir(parents=True, exist_ok=True)
    hidden_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Download from OpenML (pinned version)
    # ------------------------------------------------------------------
    print(
        f"Fetching Adult dataset from OpenML "
        f"(name={split_cfg['openml_name']!r}, version={split_cfg['openml_version']})..."
    )
    dataset = fetch_openml(
        name=split_cfg["openml_name"],
        version=split_cfg["openml_version"],
        as_frame=True,
        parser="auto",
    )

    df: pd.DataFrame = dataset.frame.copy()
    target_col = dataset.target.name

    # ------------------------------------------------------------------
    # Clean: drop rows with any missing value
    # ------------------------------------------------------------------
    n_before = len(df)
    df = df.dropna().reset_index(drop=True)
    n_after = len(df)
    if n_before != n_after:
        print(
            f"  Dropped {n_before - n_after} rows with missing values "
            f"({n_before} -> {n_after})."
        )

    # ------------------------------------------------------------------
    # Encode target: >50K -> 1, <=50K -> 0
    # ------------------------------------------------------------------
    target_str = df[target_col].astype(str).str.strip().str.rstrip(".")
    y = (target_str == ">50K").astype(np.float32).values

    # ------------------------------------------------------------------
    # Encode features: one-hot categoricals, keep numerics
    # ------------------------------------------------------------------
    X_df = df.drop(columns=[target_col])
    cat_cols = X_df.select_dtypes(include=["category", "object"]).columns.tolist()
    num_cols = X_df.select_dtypes(include=["number"]).columns.tolist()

    X_cat = pd.get_dummies(X_df[cat_cols], dtype=np.float32)
    X_num = X_df[num_cols].astype(np.float32)

    # Deterministic column order
    X_combined = pd.concat([X_num, X_cat], axis=1)
    X_combined = X_combined[sorted(X_combined.columns)]
    X = X_combined.values

    print(
        f"  Features: {X.shape[1]} "
        f"({len(num_cols)} numeric, "
        f"{X_cat.shape[1]} one-hot from {len(cat_cols)} categoricals)"
    )
    print(f"  Target balance: {y.mean():.3f} positive")

    # ------------------------------------------------------------------
    # Deterministic split (seed independent of training seeds)
    # ------------------------------------------------------------------
    rng = np.random.RandomState(split_cfg["prep_seed"])
    n = len(X)
    indices = rng.permutation(n)

    n_holdout = int(n * split_cfg["holdout_fraction"])
    n_val = int(n * split_cfg["val_fraction"])
    n_train = n - n_val - n_holdout

    train_idx = indices[:n_train]
    val_idx = indices[n_train : n_train + n_val]
    holdout_idx = indices[n_train + n_val :]

    X_train, y_train = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    X_holdout, y_holdout = X[holdout_idx], y[holdout_idx]

    # ------------------------------------------------------------------
    # Standardize (fit on train only — no data leakage)
    # ------------------------------------------------------------------
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train).astype(np.float32)
    X_val = scaler.transform(X_val).astype(np.float32)
    X_holdout = scaler.transform(X_holdout).astype(np.float32)

    print(
        f"  Splits: train={len(X_train)}, val={len(X_val)}, "
        f"evaluation={len(X_holdout)}"
    )

    # ------------------------------------------------------------------
    # Save visible data (workspace-mounted)
    # ------------------------------------------------------------------
    np.save(data_dir / "X_train.npy", X_train)
    np.save(data_dir / "y_train.npy", y_train)
    np.save(data_dir / "X_val.npy", X_val)
    np.save(data_dir / "y_val.npy", y_val)

    vis_files = {f: sha256_file(data_dir / f) for f in _VISIBLE_FILES}
    vis_manifest = {
        "n_features": int(X.shape[1]),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "files": vis_files,
    }
    visible_manifest.write_text(json.dumps(vis_manifest, indent=2) + "\n")
    print(f"  Visible manifest written to {visible_manifest}")

    # ------------------------------------------------------------------
    # Save hidden data (evaluator-only, never workspace-mounted)
    # ------------------------------------------------------------------
    np.save(hidden_dir / "X_test.npy", X_holdout)
    np.save(hidden_dir / "y_test.npy", y_holdout)

    hid_files = {f: sha256_file(hidden_dir / f) for f in _HIDDEN_FILES}
    hid_manifest = {
        "n_samples": len(X_holdout),
        "files": hid_files,
    }
    hidden_manifest.write_text(json.dumps(hid_manifest, indent=2) + "\n")
    print(f"  Hidden manifest written to {hidden_manifest}")

    return data_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare Adult dataset")
    parser.add_argument(
        "--workload-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Path to the workload directory (default: script's parent dir)",
    )
    parser.add_argument("--force", action="store_true", help="Force re-preparation")
    args = parser.parse_args()
    prepare(args.workload_dir, force=args.force)
