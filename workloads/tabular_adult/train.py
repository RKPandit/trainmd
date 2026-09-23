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

_THREAD_CAPS = (
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)


def require_pinned_threads() -> None:
    """Refuse to train unless every BLAS/OpenMP thread pool is pinned to 1.

    This is a determinism GUARD, not a setter. Multi-threaded float reductions
    are order-nondeterministic, so identical seeded runs can differ; that quietly
    broke reference reproducibility once (see docs/RESEARCH_LOG.md 26). We check
    the environment and fail loudly rather than pin in source — pinning here
    would change this file's hash and supersede every built case.
    """
    missing = [c for c in _THREAD_CAPS if os.environ.get(c) != "1"]
    if not missing:
        return
    export = " ".join(f"{c}=1" for c in _THREAD_CAPS)
    sys.stderr.write(
        "\nFATAL: training refuses to run without single-threaded math.\n"
        f"  Not set to 1: {', '.join(missing)}\n"
        "  Why: unpinned BLAS/OpenMP threading makes float reductions "
        "order-nondeterministic, so two identical seeded runs can produce "
        "DIFFERENT numbers (this broke reference reproducibility once already).\n"
        "  Fix — export all five caps before training (the canonical container "
        "sets these; a bare host run must too):\n"
        f"    export {export}\n"
        "  Then re-run. See docs/DECISIONS.md (thread pinning).\n\n"
    )
    sys.exit(2)


def set_seed(seed: int) -> None:
    """Set all random seeds for full reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    os.environ["PYTHONHASHSEED"] = str(seed)


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


def _subset_reported_accuracy(model, X_val, y_val, device, fraction: float) -> float:
    """Reported validation accuracy on the most-confident subset of rows.

    Confidence is |logit| — the distance from the decision boundary — which is
    available at evaluation time and does not use the labels. Restricting the
    reported number to the most-confident ``fraction`` of rows yields a higher,
    non-representative accuracy while leaving the model, its optimization path,
    and its saved checkpoint completely unchanged; only the reported number
    differs. Active only when ``metrics.eval_subset_fraction`` is configured
    (absent ⇒ the full validation split is reported, the default behaviour).
    """
    model.eval()
    with torch.no_grad():
        logits = model(X_val.to(device)).cpu().numpy()
    conf = np.abs(logits)
    k = max(1, int(round(fraction * len(logits))))
    idx = np.argsort(-conf)[:k]
    preds = (logits[idx] >= 0.0).astype(np.int64)
    labels = y_val.cpu().numpy().astype(np.int64)[idx]
    return float((preds == labels).mean())


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

    # ---- apply label noise if configured (default: none) -----------------
    noise_frac = config.get("data", {}).get("label_noise_fraction", 0.0)
    if noise_frac > 0:
        # Nested selection from the sibling helper: the flipped index set is a
        # deterministic prefix of one data-derived permutation, so a larger
        # fraction is a strict superset of a smaller one (monotone difficulty),
        # identical across processes and independent of the training seed.  The
        # evaluator reruns with hidden seeds 100/101/102 and must see the same
        # flipped set every time.
        from datautil import nested_prefix_indices

        flip_idx = nested_prefix_indices(len(y_train_np), noise_frac)
        y_train_np[flip_idx] = 1.0 - y_train_np[flip_idx]

    y_train = torch.from_numpy(y_train_np)
    X_val = torch.from_numpy(np.load(data_dir / "X_val.npy"))
    y_val = torch.from_numpy(np.load(data_dir / "y_val.npy"))

    # ---- apply optional derived column if configured (default: disabled) ----
    dcfg = config.get("data", {})
    if dcfg.get("include_aux_feature", False):
        _p = dcfg.get("aux_feature_strength", 0.0)
        from datautil import _derived_column
        col_train = _derived_column(y_train_np, "train", _p)
        X_train = torch.cat(
            [X_train, torch.from_numpy(col_train).unsqueeze(1)], dim=1,
        )
        col_val = _derived_column(y_val.numpy(), "val", _p)
        X_val = torch.cat(
            [X_val, torch.from_numpy(col_val).unsqueeze(1)], dim=1,
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

    # Write fully resolved config BEFORE building the model, so a run that
    # exits early during model construction still emits config.resolved.yaml
    # for resolved-vs-resolved config diffing (baselines B2).
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved = {**config, "seed": seed}
    resolved.setdefault("model", {})["input_dim"] = input_dim
    with open(output_dir / "config.resolved.yaml", "w") as f:
        yaml.dump(resolved, f, default_flow_style=False, sort_keys=False)

    model = MLP(input_dim, mcfg["hidden_dims"], mcfg.get("dropout", 0.0)).to(device)

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=tcfg["lr"],
        weight_decay=tcfg.get("weight_decay", 0.0),
    )
    criterion = nn.BCEWithLogitsLoss()
    # Optional gradient clipping (a routine practitioner setting; STAGE4 4.0.6 benign control).
    # ABSENT (the clean config) = no clipping: the clean path executes no extra operation, so the
    # reference is unchanged (two-runner repro, DECISIONS 2026-09-23).
    grad_clip_norm = tcfg.get("grad_clip_norm")

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

    # config.resolved.yaml is written earlier (before model construction) so an
    # early exit during model build still emits it.

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
                if grad_clip_norm is not None:
                    nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
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

            # Reported visible accuracy. Default: the full validation split. If
            # metrics.eval_subset_fraction is configured, the reported number is
            # computed on a confidence-selected subset instead — the model and
            # its checkpoint are identical to a clean run; only the number moves.
            _subset_frac = config.get("metrics", {}).get("eval_subset_fraction")
            if _subset_frac is None:
                reported_val_acc = val_acc
            else:
                reported_val_acc = _subset_reported_accuracy(
                    model, X_val, y_val, device, float(_subset_frac),
                )

            epoch_sec = time.monotonic() - epoch_start
            throughput = epoch_samples / epoch_sec
            _, peak_mem = tracemalloc.get_traced_memory()

            epoch_record = {
                "epoch": epoch,
                "step": global_step,
                "train_loss": round(train_loss_avg, 6),
                "val_loss": round(val_loss, 6),
                "metric_visible_val_acc": round(reported_val_acc, 6),
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
                epoch, train_loss_avg, reported_val_acc, throughput,
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
        logger.info("Training complete.  val_acc=%.4f", reported_val_acc)

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
    require_pinned_threads()  # refuse to produce non-canonical (unpinned) numbers
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
