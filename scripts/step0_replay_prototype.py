"""Step 0 — empirical verification of the train/validation OVERLAP mechanism.

METRIC-TIER design (no training change): the model trains on the normal train
set (healthy); a nested-prefix subset S of TRAIN rows (fraction p) is copied into
VALIDATION, so the reported val_acc is inflated by memorized rows while the hidden
test (clean holdout) stays healthy. This prototype does NOT touch train.py or the
operator — it reuses train.py's exact MLP/training, trains once per seed, then
re-evaluates the AUGMENTED validation for each p (cheap).

Reports, per strength p in {0.05,0.15,0.30} x seeds {0,1,2}:
  augmented val_acc vs mean+2σ (must be ABOVE, with margin),
  hidden test acc vs tolerance and reference band (must stay WITHIN — model fine),
  clean val_acc + train_acc (diagnostics: the ceiling for overlap inflation),
  hidden∩train row-hash intersection (must be empty),
  nested-superset monotonicity of S, and completion/finite checks.

Run in-container on native amd64 (thread-pinned). No paid trial.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(os.environ.get("TRAINMD_ROOT", os.getcwd()))
WL = ROOT / "workloads" / "tabular_adult"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WL))  # train.py imports datautil as a sibling
from train import MLP, set_seed, evaluate  # noqa: E402
from datautil import nested_prefix_indices  # noqa: E402

P_LADDER = [0.05, 0.15, 0.30]
SEEDS = [0, 1, 2]

# Canonical reference band (committed reference/stats.yaml).
REF = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
V_MEAN = REF["metric_visible_val_acc"]["mean"]; V_STD = REF["metric_visible_val_acc"]["std"]
H_MEAN = REF["metric_hidden_test_acc"]["mean"]; H_STD = REF["metric_hidden_test_acc"]["std"]
TOL = REF["metric_hidden_test_acc"]["tolerance_lower"]
V_UPPER = V_MEAN + 2 * V_STD                 # visible upper band — symptom threshold
H_LO, H_HI = H_MEAN - 2 * H_STD, H_MEAN + 2 * H_STD


def _row_hashes(X: np.ndarray) -> set:
    return {hashlib.sha256(np.ascontiguousarray(r).tobytes()).hexdigest() for r in X}


def _acc(model, X, y, bs=256):
    loader = DataLoader(TensorDataset(torch.from_numpy(X), torch.from_numpy(y)),
                        batch_size=bs, shuffle=False)
    _, a = evaluate(model, loader, nn.BCEWithLogitsLoss(), torch.device("cpu"))
    return a


def train_one(seed, cfg, Xtr, ytr):
    set_seed(seed)
    tcfg = cfg["training"]; mcfg = cfg["model"]
    model = MLP(Xtr.shape[1], mcfg["hidden_dims"], mcfg.get("dropout", 0.0))
    opt = torch.optim.Adam(model.parameters(), lr=tcfg["lr"], weight_decay=tcfg.get("weight_decay", 0.0))
    crit = nn.BCEWithLogitsLoss()
    g = torch.Generator().manual_seed(seed)
    loader = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)),
                        batch_size=tcfg["batch_size"], shuffle=True, num_workers=0, generator=g)
    last_loss = None
    for _ in range(tcfg["epochs"]):
        model.train()
        for xb, yb in loader:
            opt.zero_grad(); loss = crit(model(xb), yb); loss.backward(); opt.step()
            last_loss = loss.item()
    return model, last_loss


def main() -> int:
    cfg = yaml.safe_load((WL / "config.yaml").read_text())
    d = WL / ".data"; h = WL / ".hidden_data"
    Xtr = np.load(d / "X_train.npy"); ytr = np.load(d / "y_train.npy")
    Xva = np.load(d / "X_val.npy"); yva = np.load(d / "y_val.npy")
    Xte = np.load(h / "X_test.npy"); yte = np.load(h / "y_test.npy")

    # Disjointness (before injection) and nested-superset check.
    inter = _row_hashes(Xte) & _row_hashes(Xtr)
    print(f"hidden_test ∩ train row-hash intersection (pre): {len(inter)} (must be 0)")
    S = {p: nested_prefix_indices(len(ytr), p) for p in P_LADDER}
    nested_ok = set(S[0.05].tolist()) <= set(S[0.15].tolist()) <= set(S[0.30].tolist())
    print(f"nested superset S(0.05)⊆S(0.15)⊆S(0.30): {nested_ok}")
    print(f"reference: visible mean+2σ = {V_UPPER:.6f} | hidden tol = {TOL:.6f} | "
          f"hidden band [{H_LO:.6f}, {H_HI:.6f}]")
    print()
    print(f"{'seed':4} {'train_acc':9} {'val_clean':9} {'hidden':8} {'hid-tol':8} {'hidden_in_band':13}")
    rows = {p: [] for p in P_LADDER}
    for seed in SEEDS:
        model, last_loss = train_one(seed, cfg, Xtr, ytr)
        tr_acc = _acc(model, Xtr, ytr); v_clean = _acc(model, Xva, yva)
        hid = _acc(model, Xte, yte)
        in_band = H_LO <= hid <= H_HI
        print(f"{seed:<4} {tr_acc:<9.6f} {v_clean:<9.6f} {hid:<8.6f} {hid-TOL:<+8.6f} {str(in_band):13}")
        for p in P_LADDER:
            aug_X = np.concatenate([Xva, Xtr[S[p]]]); aug_y = np.concatenate([yva, ytr[S[p]]])
            av = _acc(model, aug_X, aug_y)
            rows[p].append((seed, av, hid))
    print()
    print(f"{'p':6} {'seed':4} {'aug_val':8} {'vs mean+2σ':11} {'ABOVE?':7} {'hidden':8} {'WITHIN?':8}")
    verdict = {}
    for p in P_LADDER:
        above_all = True; band_all = True; avs = []
        for seed, av, hid in rows[p]:
            above = av > V_UPPER; inb = H_LO <= hid <= H_HI
            above_all &= above; band_all &= inb; avs.append(av)
            print(f"{p:<6} {seed:<4} {av:<8.6f} {av-V_UPPER:<+11.6f} {str(above):7} {hid:<8.6f} {str(inb):8}")
        margin = min(avs) - V_UPPER
        verdict[p] = (above_all, band_all, round(min(avs), 6), round(margin, 6))
    print()
    print("VERDICT per strength (metric-tier: visible ABOVE mean+2σ on ALL seeds AND hidden WITHIN band):")
    prev = None; monotone = True
    for p in P_LADDER:
        above_all, band_all, minav, margin = verdict[p]
        ok = above_all and band_all
        if prev is not None and minav < prev:
            monotone = False
        prev = minav
        print(f"  p={p}: min aug_val={minav} (margin vs band {margin:+.6f}), "
              f"visible-above-all={above_all}, hidden-in-band-all={band_all} -> {'PASS' if ok else 'FAIL'}")
    print(f"  ladder monotone in min aug_val: {monotone}")
    print(f"  disjointness empty: {len(inter) == 0} | nested superset: {nested_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
