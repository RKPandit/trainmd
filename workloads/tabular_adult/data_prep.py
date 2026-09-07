"""Prepare the Adult dataset for the tabular_adult workload.

NOTE: In later milestones, training runs execute inside no-network containers
(SageMaker contract, harness_spec §2). Data preparation always happens
*outside* the workspace container; the prepared .npy files are mounted into
/opt/ml/input/data/<channel>/.  This script is the offline data-preparation
step and is never called from inside the workspace image.
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


_EXPECTED_FILES = [
    "X_train.npy",
    "y_train.npy",
    "X_val.npy",
    "y_val.npy",
    "X_test.npy",
    "y_test.npy",
]


def _verify_manifest(data_dir: Path, manifest_path: Path) -> bool:
    """Return True if all data files exist and match their recorded checksums."""
    try:
        manifest = json.loads(manifest_path.read_text())
        return all(
            (data_dir / fname).exists()
            and sha256_file(data_dir / fname) == manifest["files"][fname]
            for fname in _EXPECTED_FILES
        )
    except (KeyError, json.JSONDecodeError, FileNotFoundError):
        return False


def prepare(workload_dir: Path, force: bool = False) -> Path:
    """Download, preprocess, and save Adult dataset splits.

    Returns the path to the data directory.
    """
    config_path = workload_dir / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    data_cfg = config["data"]
    data_dir = workload_dir / ".data"
    manifest_path = data_dir / "manifest.json"

    # ------------------------------------------------------------------
    # Fast path: reuse existing data if checksums verify
    # ------------------------------------------------------------------
    if not force and manifest_path.exists():
        if _verify_manifest(data_dir, manifest_path):
            print("Data already prepared; checksums verified.")
            return data_dir

    data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Download from OpenML (pinned version)
    # ------------------------------------------------------------------
    print(
        f"Fetching Adult dataset from OpenML "
        f"(name={data_cfg['openml_name']!r}, version={data_cfg['openml_version']})..."
    )
    dataset = fetch_openml(
        name=data_cfg["openml_name"],
        version=data_cfg["openml_version"],
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
    rng = np.random.RandomState(data_cfg["prep_seed"])
    n = len(X)
    indices = rng.permutation(n)

    n_test = int(n * data_cfg["test_fraction"])
    n_val = int(n * data_cfg["val_fraction"])
    n_train = n - n_val - n_test

    train_idx = indices[:n_train]
    val_idx = indices[n_train : n_train + n_val]
    test_idx = indices[n_train + n_val :]

    X_train, y_train = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    # ------------------------------------------------------------------
    # Standardize (fit on train only — no data leakage)
    # ------------------------------------------------------------------
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train).astype(np.float32)
    X_val = scaler.transform(X_val).astype(np.float32)
    X_test = scaler.transform(X_test).astype(np.float32)

    print(f"  Splits: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    np.save(data_dir / "X_train.npy", X_train)
    np.save(data_dir / "y_train.npy", y_train)
    np.save(data_dir / "X_val.npy", X_val)
    np.save(data_dir / "y_val.npy", y_val)
    np.save(data_dir / "X_test.npy", X_test)
    np.save(data_dir / "y_test.npy", y_test)

    # ------------------------------------------------------------------
    # Manifest with SHA-256 checksums for integrity verification
    # ------------------------------------------------------------------
    files = {fname: sha256_file(data_dir / fname) for fname in _EXPECTED_FILES}
    manifest = {
        "openml_name": data_cfg["openml_name"],
        "openml_version": data_cfg["openml_version"],
        "prep_seed": data_cfg["prep_seed"],
        "n_features": int(X.shape[1]),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  Manifest written to {manifest_path}")

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
