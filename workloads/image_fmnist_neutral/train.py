"""Deterministic compact-CNN training on Fashion-MNIST (Stage 4 Part 3 workload; clean pipeline only).

Implements the SageMaker training container contract (harness_spec §2), like the tabular workload:
- hyperparameters from SM_HPS or --config; data from SM_CHANNEL_TRAIN or --data-dir;
  artifacts to SM_MODEL_DIR or --output-dir.

Outputs:
    metrics.jsonl          per-step and per-epoch metrics (visible only; per-epoch rows carry val_top1)
    logs/stdout.log        human-readable training log
    config.resolved.yaml   fully resolved configuration
    checkpoints/           ckpt_final.pt
    exitcode               0 on success, 1 on failure

The workspace never sees or evaluates against the hidden evaluation split.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, TensorDataset

_THREAD_CAPS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def require_pinned_threads() -> None:
    """Refuse to train unless every BLAS/OpenMP pool is pinned to 1 (determinism guard, not a setter)."""
    missing = [c for c in _THREAD_CAPS if os.environ.get(c) != "1"]
    if missing:
        sys.stderr.write("FATAL: training refuses to run without single-threaded math. Not set to 1: "
                         + ", ".join(missing) + "\n  export " + " ".join(f"{c}=1" for c in _THREAD_CAPS) + "\n")
        sys.exit(2)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    os.environ["PYTHONHASHSEED"] = str(seed)


class SmallCNN(nn.Module):
    """Conv blocks (3x3 conv, ReLU, 2x2 max-pool) then one linear classifier."""

    def __init__(self, in_ch: int, widths: list, n_classes: int, image_size: int):
        super().__init__()
        layers: list[nn.Module] = []
        prev = in_ch
        for w in widths:
            layers += [nn.Conv2d(prev, w, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2)]
            prev = w
        self.features = nn.Sequential(*layers)
        side = image_size // (2 ** len(widths))
        self.head = nn.Linear(prev * side * side, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(torch.flatten(self.features(x), 1))


def to_tensor(X: np.ndarray, mean: float, std: float) -> torch.Tensor:
    """uint8 (n, H, W) -> normalised float32 (n, 1, H, W)."""
    return ((torch.from_numpy(X).float() / 255.0 - mean) / std).unsqueeze(1)


# Class pairs that look alike in this dataset (0 T-shirt/top, 1 Trouser, 2 Pullover, 3 Dress, 4 Coat, 5 Sandal,
# 6 Shirt, 7 Sneaker, 8 Bag, 9 Ankle boot).
_PARTNER = np.array([6, 3, 4, 1, 2, 8, 0, 9, 5, 7], dtype=np.int64)


def _split_rng(name: str) -> np.random.RandomState:
    """A generator fixed by the split's NAME (never the training seed), so every run sees the same data."""
    return np.random.RandomState(int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big"))


def _patch_images(X: np.ndarray, y: np.ndarray, level: float, split: str) -> np.ndarray:
    """A deterministic 4x4 top-left patch per image, fixed by the split's name; ``level`` sets the per-row
    disagreement rate."""
    rng = _split_rng(f"patch:{split}")
    shown = y.astype(np.int64).copy()
    swap = rng.rand(len(y)) < level
    shown[swap] = rng.randint(0, 10, int(swap.sum()))
    out = X.copy()
    out[:, :4, :4] = (25 * (shown + 1)).astype(np.uint8)[:, None, None]
    return out


def _swap_partner_labels(y: np.ndarray, fraction: float) -> np.ndarray:
    """Replace the label of a fixed fraction of training rows with its look-alike partner class. The rows are a
    prefix of one fixed permutation, so a larger fraction always contains a smaller one."""
    order = _split_rng("labels:train").permutation(len(y))
    idx = order[: int(round(fraction * len(y)))]
    out = y.copy()
    out[idx] = _PARTNER[y[idx]]
    return out


def _prepare_visible(config: dict, X_tr, y_tr, X_va, y_va):
    """Optional data-stage transforms on the visible splits (default: none)."""
    d = config.get("data", {})
    if d.get("opt_t"):
        level = float(d.get("opt_t_level", 0.0))
        X_tr = _patch_images(X_tr, y_tr, level, "train")
        X_va = _patch_images(X_va, y_va, level, "val")
    frac = d.get("flip_fraction")
    if frac:
        y_tr = _swap_partner_labels(y_tr, float(frac))
    return X_tr, y_tr, X_va


def _lr_now(base_lr: float, sched: dict, step: int, epoch: int) -> float:
    """Step decay: ``base_lr * decay_gamma ** k`` with k = completed intervals of ``decay_every``, counted in
    ``interval_unit`` (epochs by default). Without ``decay_every`` the rate is constant."""
    every = sched.get("decay_every")
    if not every:
        return base_lr
    k = (step // every) if sched.get("interval_unit", "epochs") == "steps" else (epoch // every)
    return base_lr * float(sched.get("decay_gamma", 1.0)) ** k


def _reported_top1(model: nn.Module, X_val: torch.Tensor, y_val: torch.Tensor, fraction: float) -> float:
    """Top-1 over a ``fraction`` of the validation images, taken in order of the model's max softmax output."""
    model.eval()
    with torch.no_grad():
        probs = torch.softmax(model(X_val), dim=1)
    conf, pred = probs.max(1)
    k = max(1, int(round(fraction * len(y_val))))
    idx = torch.argsort(-conf, stable=True)[:k]
    return (pred[idx] == y_val[idx]).float().mean().item()


def evaluate(model: nn.Module, loader: DataLoader, criterion: nn.Module) -> tuple:
    model.eval()
    loss = 0.0
    correct = total = 0
    with torch.no_grad():
        for xb, yb in loader:
            logits = model(xb)
            loss += criterion(logits, yb).item() * len(yb)
            correct += (logits.argmax(1) == yb).sum().item()
            total += len(yb)
    return loss / total, correct / total


def train(config: dict, data_dir: Path, output_dir: Path, seed: int) -> int:
    set_seed(seed)
    wall_start = time.monotonic()
    dcfg, ncfg, ocfg, scfg = config["data"], config["net"], config["optim"], config["sched"]

    X_tr, y_tr, X_va = _prepare_visible(config, np.load(data_dir / "X_train.npy"), np.load(data_dir / "y_train.npy"),
                                        np.load(data_dir / "X_val.npy"), np.load(data_dir / "y_val.npy"))
    X_train = to_tensor(X_tr, dcfg["norm_mean"], dcfg["norm_std"])
    y_train = torch.from_numpy(y_tr)
    X_val = to_tensor(X_va, dcfg["norm_mean"], dcfg["norm_std"])
    y_val = torch.from_numpy(np.load(data_dir / "y_val.npy"))

    g = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(TensorDataset(X_train, y_train), batch_size=ocfg["batch"], shuffle=True,
                              num_workers=0, generator=g)
    val_loader = DataLoader(TensorDataset(X_val, y_val), batch_size=512, shuffle=False, num_workers=0)

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "config.resolved.yaml", "w") as f:       # before model build (early-exit safe)
        yaml.dump({**config, "seed": seed}, f, default_flow_style=False, sort_keys=False)
    (output_dir / "logs").mkdir(exist_ok=True)
    (output_dir / "checkpoints").mkdir(exist_ok=True)
    logger = logging.getLogger(f"train.seed{seed}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for h in (logging.FileHandler(output_dir / "logs" / "stdout.log", mode="w"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        logger.addHandler(h)

    metrics_fh = open(output_dir / "metrics.jsonl", "w")
    exitcode = 0
    try:
        model = SmallCNN(ncfg["in_ch"], ncfg["widths"], ncfg["n_classes"], dcfg["image_size"])
        optimizer = torch.optim.SGD(model.parameters(), lr=ocfg["base_lr"], momentum=ocfg.get("momentum", 0.0),
                                    weight_decay=ocfg.get("weight_decay", 0.0))
        criterion = nn.CrossEntropyLoss()
        logger.info("Training seed=%d  epochs=%d  train=%d  val=%d  params=%d", seed, scfg["epochs"],
                    len(y_train), len(y_val), sum(p.numel() for p in model.parameters()))
        step = 0
        for epoch in range(scfg["epochs"]):
            model.train()
            ep_loss, ep_n, t0 = 0.0, 0, time.monotonic()
            for xb, yb in train_loader:
                lr = _lr_now(ocfg["base_lr"], scfg, step, epoch)
                if scfg.get("decay_every"):
                    for grp in optimizer.param_groups:
                        grp["lr"] = lr
                optimizer.zero_grad()
                loss = criterion(model(xb), yb)
                loss.backward()
                optimizer.step()
                step += 1
                ep_loss += loss.item() * len(yb)
                ep_n += len(yb)
                metrics_fh.write(json.dumps({"epoch": epoch, "step": step, "train_loss": round(loss.item(), 6),
                                             "lr": lr}) + "\n")
            val_loss, val_top1 = evaluate(model, val_loader, criterion)
            frac = config.get("eval", {}).get("opt_q")
            if frac is not None:
                val_top1 = _reported_top1(model, X_val, y_val, float(frac))
            secs = time.monotonic() - t0
            metrics_fh.write(json.dumps({"epoch": epoch, "step": step, "train_loss": round(ep_loss / ep_n, 6),
                                         "val_loss": round(val_loss, 6), "val_top1": round(val_top1, 6),
                                         "lr": lr, "epoch_time_sec": round(secs, 3),
                                         "end_of_epoch": True}) + "\n")
            metrics_fh.flush()
            logger.info("Epoch %2d | train_loss=%.4f | val_top1=%.4f | %.1fs", epoch, ep_loss / ep_n, val_top1, secs)
        torch.save({"model_state_dict": model.state_dict(), "net": ncfg, "seed": seed,
                    "epoch": scfg["epochs"] - 1}, output_dir / "checkpoints" / "ckpt_final.pt")
        logger.info("Training complete.  val_top1=%.4f", val_top1)
    except Exception:
        import traceback
        logger.error("Training failed:\n%s", traceback.format_exc())
        exitcode = 1
    finally:
        metrics_fh.close()
        (output_dir / "exitcode").write_text(str(exitcode))
        logger.info("Wall time: %.1fs  exit code: %d", time.monotonic() - wall_start, exitcode)
    return exitcode


def _resolve(cli: str | None, env: str, default: str) -> Path:
    return Path(cli) if cli is not None else Path(os.environ.get(env, default))


def main() -> int:
    require_pinned_threads()
    ap = argparse.ArgumentParser(description="Train a compact CNN on Fashion-MNIST")
    ap.add_argument("--config")
    ap.add_argument("--data-dir")
    ap.add_argument("--output-dir")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    config = yaml.safe_load(_resolve(a.config, "SM_HPS", str(here / "config.yaml")).read_text())
    return train(config, _resolve(a.data_dir, "SM_CHANNEL_TRAIN", str(here / ".data")),
                 _resolve(a.output_dir, "SM_MODEL_DIR", str(here / "output")), a.seed)


if __name__ == "__main__":
    sys.exit(main())
