"""Evaluate a saved checkpoint on the hidden evaluation split.

This is the ONLY code path that computes metric_hidden_test_acc (spec §7).
The workspace container never has access to the hidden data or this module.

NOTE: Imports MLP and evaluate from workloads.tabular_adult.train for now.
In M2.2 (Docker separation), model definitions will move to a shared module
so the evaluator image does not depend on workspace code.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import yaml

# Import model class from the workload.  This coupling is acceptable in M2.1
# (single-process, no Docker); M2.2 will factor the model into a shared lib.
from workloads.tabular_adult.train import MLP, evaluate


def evaluate_checkpoint(
    checkpoint_path: Path,
    hidden_data_dir: Path,
    config: dict,
) -> dict:
    """Load a checkpoint and evaluate on the hidden split.

    Args:
        checkpoint_path: Path to ckpt_final.pt.
        hidden_data_dir: Directory containing X_test.npy and y_test.npy.
        config: Training config dict (used for batch_size).

    Returns:
        Dict with ``metric_hidden_test_acc``.
    """
    device = torch.device("cpu")

    # ---- reconstruct model from checkpoint --------------------------------
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    mcfg = ckpt["model_config"]
    input_dim = ckpt["input_dim"]
    model = MLP(input_dim, mcfg["hidden_dims"], mcfg.get("dropout", 0.0))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)

    # ---- load hidden evaluation data --------------------------------------
    X = torch.from_numpy(np.load(hidden_data_dir / "X_test.npy"))
    y = torch.from_numpy(np.load(hidden_data_dir / "y_test.npy"))

    # When aux feature is enabled, the model expects one extra column.
    # At test time the upstream signal is unavailable — substitute noise.
    dcfg = config.get("data", {})
    if dcfg.get("include_aux_feature", False):
        noise_seed = int.from_bytes(
            hashlib.sha256(f"test:{len(X)}".encode()).digest()[:4], "big",
        )
        noise_rng = np.random.RandomState(noise_seed)
        noise_col = noise_rng.binomial(1, 0.5, size=len(X)).astype(np.float32)
        X = torch.cat([X, torch.from_numpy(noise_col).unsqueeze(1)], dim=1)

    loader = DataLoader(
        TensorDataset(X, y),
        batch_size=config["training"]["batch_size"],
        shuffle=False,
        num_workers=0,
    )

    criterion = nn.BCEWithLogitsLoss()
    _, acc = evaluate(model, loader, criterion, device)

    return {"metric_hidden_test_acc": round(acc, 6)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a checkpoint on the hidden evaluation split",
    )
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--hidden-data-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    result = evaluate_checkpoint(args.checkpoint, args.hidden_data_dir, config)
    print(f"metric_hidden_test_acc: {result['metric_hidden_test_acc']:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
