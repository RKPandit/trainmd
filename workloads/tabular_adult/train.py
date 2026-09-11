"""Deterministic MLP training on the Adult dataset.

Implements the SageMaker training container contract (harness_spec §2):
- Reads hyperparameters from SM_HPS env var or --config flag.
- Reads data from SM_CHANNEL_TRAIN env var or --data-dir flag.
- Writes model artifacts to SM_MODEL_DIR env var or --output-dir flag.

Outputs (per harness_spec §2):
    metrics.jsonl          per-step and per-epoch metrics (visible only)
    logs/stdout.log        human-readable training log
    config.resolved.yaml   fully resolved configuration
    checkpoints/           ckpt_final.pt
    exitcode               0 on success, 1 on failure

The workspace never sees or evaluates against the hidden evaluation split.
Hidden-metric computation happens exclusively in harness/evaluator/ (spec §7).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import hashlib
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import yaml


# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    """Set all random seeds for full reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    os.environ["PYTHONHASHSEED"] = str(seed)


def _compute_aux_column(labels: np.ndarray, split_name: str, p: float) -> np.ndarray:
    """Precomputed upstream auxiliary score for the given data split.

    Returns a binary column derived from *labels* and a noise parameter *p*.
    Seed is deterministic from (split_name, n_samples, p) — independent of
    the training seed so re-runs produce identical columns.
    """
    seed = int.from_bytes(
        hashlib.sha256(f"{split_name}:{len(labels)}:{p}".encode()).digest()[:4],
        "big",
    )
    rng = np.random.RandomState(seed)
    noise = rng.binomial(1, p, size=len(labels)).astype(np.float32)
    return np.abs(labels - noise)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class MLP(nn.Module):
    """Simple feed-forward network for binary classification."""

    def __init__(self, input_dim: int, hidden_dims: list, dropout: float = 0.0):
        super().__init__()
        layers: list[nn.Module] = []
        prev = input_dim
        for h in hidden_dims:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple:
    """Return (avg_loss, accuracy) over a DataLoader."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    with torch.no_grad():
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            logits = model(xb)
            total_loss += criterion(logits, yb).item() * len(yb)
            correct += ((torch.sigmoid(logits) >= 0.5).float() == yb).sum().item()
            total += len(yb)
    return total_loss / total, correct / total


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

def train(config: dict, data_dir: Path, output_dir: Path, seed: int) -> int:
    """Run one deterministic training job.  Returns exit code (0=success)."""
    set_seed(seed)
    tracemalloc.start()
    wall_start = time.monotonic()
    device = torch.device("cpu")

    # ---- load visible data only (train + val) ----------------------------
    X_train = torch.from_numpy(np.load(data_dir / "X_train.npy"))
    y_train_np = np.load(data_dir / "y_train.npy")

    # ---- apply label corruption if configured (default: no corruption) ----
    noise_frac = config.get("data", {}).get("label_noise_fraction", 0.0)
    if noise_frac > 0:
        n_corrupt = int(len(y_train_np) * noise_frac)
        # Fixed corruption seed: function of (data length, fraction) ONLY,
        # not the training seed.  The evaluator reruns with hidden seeds
        # 100/101/102 — corruption must be the same set of flipped labels
        # every time, regardless of training seed.
        # NOTE: must NOT use Python's built-in hash() — it is salted per
        # process (PYTHONHASHSEED), so different subprocesses would corrupt
        # different label sets.  hashlib is deterministic across processes.
        corrupt_seed = int.from_bytes(
            hashlib.sha256(f"{len(y_train_np)}:{noise_frac}".encode()).digest()[:4],
            "big",
        )
        corrupt_rng = np.random.RandomState(corrupt_seed)
        corrupt_idx = corrupt_rng.choice(
            len(y_train_np), size=n_corrupt, replace=False,
        )
        y_train_np[corrupt_idx] = 1.0 - y_train_np[corrupt_idx]

    y_train = torch.from_numpy(y_train_np)
    X_val = torch.from_numpy(np.load(data_dir / "X_val.npy"))
    y_val = torch.from_numpy(np.load(data_dir / "y_val.npy"))

    # ---- apply aux feature if configured (default: disabled) ----------------
    dcfg = config.get("data", {})
    if dcfg.get("include_aux_feature", False):
        _p = dcfg.get("aux_feature_strength", 0.0)
        aux_train = _compute_aux_column(y_train_np, "train", _p)
        X_train = torch.cat(
            [X_train, torch.from_numpy(aux_train).unsqueeze(1)], dim=1,
        )
        aux_val = _compute_aux_column(y_val.numpy(), "val", _p)
        X_val = torch.cat(
            [X_val, torch.from_numpy(aux_val).unsqueeze(1)], dim=1,
        )

    tcfg = config["training"]

    # Single-threaded dataloaders for determinism (harness_spec §2)
    g = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        TensorDataset(X_train, y_train),
        batch_size=tcfg["batch_size"],
        shuffle=True,
        num_workers=0,
        generator=g,
    )
    val_loader = DataLoader(
        TensorDataset(X_val, y_val),
        batch_size=tcfg["batch_size"],
        shuffle=False,
        num_workers=0,
    )

    # ---- model + optimizer -----------------------------------------------
    mcfg = config["model"]
    input_dim = X_train.shape[1]
    input_dim = mcfg.get("input_dim", input_dim)
    model = MLP(input_dim, mcfg["hidden_dims"], mcfg.get("dropout", 0.0)).to(device)

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=tcfg["lr"],
        weight_decay=tcfg.get("weight_decay", 0.0),
    )
    criterion = nn.BCEWithLogitsLoss()

    # ---- output dirs & logging -------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(exist_ok=True)
    (output_dir / "checkpoints").mkdir(exist_ok=True)

    log_path = output_dir / "logs" / "stdout.log"
    logger = logging.getLogger(f"train.seed{seed}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for handler in [logging.FileHandler(log_path, mode="w"),
                    logging.StreamHandler(sys.stdout)]:
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    # Write fully resolved config
    resolved = {**config, "seed": seed}
    resolved.setdefault("model", {})["input_dim"] = input_dim
    with open(output_dir / "config.resolved.yaml", "w") as f:
        yaml.dump(resolved, f, default_flow_style=False, sort_keys=False)

    logger.info(
        "Training seed=%d  epochs=%d  input_dim=%d  device=%s",
        seed, tcfg["epochs"], input_dim, device,
    )

    # ---- training loop ---------------------------------------------------
    metrics_fh = open(output_dir / "metrics.jsonl", "w")
    global_step = 0
    exitcode = 0

    try:
        for epoch in range(tcfg["epochs"]):
            model.train()
            epoch_loss = 0.0
            epoch_samples = 0
            epoch_start = time.monotonic()

            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                optimizer.zero_grad()
                logits = model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()

                bs = len(yb)
                epoch_loss += loss.item() * bs
                epoch_samples += bs
                global_step += 1

                metrics_fh.write(
                    json.dumps({
                        "epoch": epoch,
                        "step": global_step,
                        "train_loss": round(loss.item(), 6),
                        "lr": tcfg["lr"],
                        "batch_size": bs,
                    }) + "\n"
                )

            # ---- end-of-epoch eval (visible metrics only) -----------------
            train_loss_avg = epoch_loss / epoch_samples
            val_loss, val_acc = evaluate(model, val_loader, criterion, device)

            epoch_sec = time.monotonic() - epoch_start
            throughput = epoch_samples / epoch_sec
            _, peak_mem = tracemalloc.get_traced_memory()

            epoch_record = {
                "epoch": epoch,
                "step": global_step,
                "train_loss": round(train_loss_avg, 6),
                "val_loss": round(val_loss, 6),
                "metric_visible_val_acc": round(val_acc, 6),
                "lr": tcfg["lr"],
                "throughput_samples_per_sec": round(throughput, 2),
                "epoch_time_sec": round(epoch_sec, 3),
                "peak_memory_mb": round(peak_mem / 1024 / 1024, 2),
                "end_of_epoch": True,
            }
            metrics_fh.write(json.dumps(epoch_record) + "\n")
            metrics_fh.flush()

            logger.info(
                "Epoch %3d | train_loss=%.4f | val_acc=%.4f | %.0f samples/s",
                epoch, train_loss_avg, val_acc, throughput,
            )

        # ---- save checkpoint ----------------------------------------------
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "model_config": mcfg,
                "input_dim": input_dim,
                "epoch": tcfg["epochs"] - 1,
                "seed": seed,
            },
            output_dir / "checkpoints" / "ckpt_final.pt",
        )
        logger.info("Training complete.  val_acc=%.4f", val_acc)

    except Exception:
        import traceback
        logger.error("Training failed:\n%s", traceback.format_exc())
        exitcode = 1

    finally:
        metrics_fh.close()
        tracemalloc.stop()
        wall_sec = time.monotonic() - wall_start
        (output_dir / "exitcode").write_text(str(exitcode))
        logger.info("Wall time: %.1fs  exit code: %d", wall_sec, exitcode)

    return exitcode


# ---------------------------------------------------------------------------
# CLI entry point (SageMaker-compatible)
# ---------------------------------------------------------------------------

def _resolve_path(cli_val: str | None, env_var: str, default: str) -> Path:
    """Resolve a path from CLI arg > env var > default, in priority order."""
    if cli_val is not None:
        return Path(cli_val)
    return Path(os.environ.get(env_var, default))


def main() -> int:
    parser = argparse.ArgumentParser(description="Train MLP on Adult dataset")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    # SageMaker-convention env vars with local fallbacks
    script_dir = Path(__file__).resolve().parent
    config_path = _resolve_path(
        args.config,
        "SM_HPS",
        str(script_dir / "config.yaml"),
    )
    data_dir = _resolve_path(
        args.data_dir,
        "SM_CHANNEL_TRAIN",
        str(script_dir / ".data"),
    )
    output_dir = _resolve_path(
        args.output_dir,
        "SM_MODEL_DIR",
        str(script_dir / "output"),
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return train(config, data_dir, output_dir, args.seed)


if __name__ == "__main__":
    sys.exit(main())
