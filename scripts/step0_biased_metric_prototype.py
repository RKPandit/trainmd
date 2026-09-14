"""Step 0 — biased VALIDATION-METRIC mechanisms (metric tier, model untouched).

The model trains on the normal train set (identical optimization path to a clean
run); ONLY the reported visible metric is computed incorrectly, so the reported
val_acc is inflated while the model is healthy. The hidden test is ALWAYS scored
correctly. We train ONCE per seed and re-score the visible metric three ways, so
the checkpoint is bitwise identical across mechanisms by construction (asserted).

Candidate mechanisms (report all three; pick whichever gives a clean monotone
ladder clearing mean+2sigma with a >=2*std margin):
  (a) eval_subset_fraction : report accuracy on the most-confident fraction q of
      val rows (|logit| descending) -- an innocuous "evaluate a subset" knob; the
      selection-by-confidence is the bug. NOT by label. Strength = smaller q.
  (b) decision_threshold    : shift the logit decision boundary by tau to predict
      the majority class more, flattering accuracy on an imbalanced set.
  (c) train_mix_fraction    : metric computed on val + a fraction of TRAIN rows
      (metric-side variant of overlap). Reduces to the memorization ceiling
      (~train_acc); included to DOCUMENT why it will not clear the band.

Reference band (committed reference/stats.yaml): visible mean+2sigma is the
symptom threshold; ">=2*std margin" means reported_val >= mean+4sigma. Hidden must
stay WITHIN [mean-2sigma, mean+2sigma].

Run in-container, thread-pinned. No paid trial.
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
sys.path.insert(0, str(WL))
from train import MLP, set_seed, evaluate  # noqa: E402
from datautil import nested_prefix_indices  # noqa: E402

SEEDS = [0, 1, 2]
A_KEEP = [0.70, 0.50, 0.30]        # (a) fraction of val KEPT (most confident); smaller = stronger
B_TAU = [0.5, 1.0, 1.5]            # (b) logit threshold shift toward the majority class
C_MIX = [0.15, 0.30, 0.50]         # (c) fraction of TRAIN rows mixed into the metric set

REF = yaml.safe_load((WL / "reference" / "stats.yaml").read_text())
V_MEAN = REF["metric_visible_val_acc"]["mean"]; V_STD = REF["metric_visible_val_acc"]["std"]
H_MEAN = REF["metric_hidden_test_acc"]["mean"]; H_STD = REF["metric_hidden_test_acc"]["std"]
V_UPPER = V_MEAN + 2 * V_STD        # symptom threshold (band edge)
V_2SIG = V_MEAN + 4 * V_STD         # ">=2*std margin" bar (2 sigma beyond the edge)
H_LO, H_HI = H_MEAN - 2 * H_STD, H_MEAN + 2 * H_STD


def _logits(model, X, bs=512):
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(X), bs):
            out.append(model(torch.from_numpy(X[i:i + bs])).squeeze(-1).numpy())
    return np.concatenate(out)


def _acc_from_logits(logits, y, tau=0.0):
    pred = (logits > tau).astype(np.int64)
    return float((pred == y.astype(np.int64)).mean())


def train_one(seed, cfg, Xtr, ytr):
    set_seed(seed)
    tcfg = cfg["training"]; mcfg = cfg["model"]
    model = MLP(Xtr.shape[1], mcfg["hidden_dims"], mcfg.get("dropout", 0.0))
    opt = torch.optim.Adam(model.parameters(), lr=tcfg["lr"], weight_decay=tcfg.get("weight_decay", 0.0))
    crit = nn.BCEWithLogitsLoss()
    g = torch.Generator().manual_seed(seed)
    loader = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)),
                        batch_size=tcfg["batch_size"], shuffle=True, num_workers=0, generator=g)
    for _ in range(tcfg["epochs"]):
        model.train()
        for xb, yb in loader:
            opt.zero_grad(); loss = crit(model(xb), yb); loss.backward(); opt.step()
    return model


def _ckpt_hash(model):
    h = hashlib.sha256()
    for k in sorted(model.state_dict()):
        h.update(k.encode()); h.update(model.state_dict()[k].numpy().tobytes())
    return h.hexdigest()


def main() -> int:
    cfg = yaml.safe_load((WL / "config.yaml").read_text())
    d = WL / ".data"; h = WL / ".hidden_data"
    Xtr = np.load(d / "X_train.npy"); ytr = np.load(d / "y_train.npy")
    Xva = np.load(d / "X_val.npy"); yva = np.load(d / "y_val.npy")
    Xte = np.load(h / "X_test.npy"); yte = np.load(h / "y_test.npy")

    print(f"reference: visible mean={V_MEAN:.6f} std={V_STD:.6f} | mean+2s(edge)={V_UPPER:.6f} "
          f"| mean+4s(>=2std bar)={V_2SIG:.6f} | hidden band [{H_LO:.6f},{H_HI:.6f}]")
    print()

    # Per mechanism collect reported_val across seeds; hidden is scored ONCE per seed (correct).
    a_rows = {q: [] for q in A_KEEP}
    b_rows = {t: [] for t in B_TAU}
    c_rows = {m: [] for m in C_MIX}
    hidden_by_seed = {}
    ckpt_hashes = []

    print(f"{'seed':4} {'train_acc':10} {'val_clean':10} {'hidden':9} {'hidden_in_band':14} {'ckpt_sha (first 12)':20}")
    for seed in SEEDS:
        model = train_one(seed, cfg, Xtr, ytr)
        ck = _ckpt_hash(model); ckpt_hashes.append(ck)
        tr_l = _logits(model, Xtr); va_l = _logits(model, Xva); te_l = _logits(model, Xte)
        tr_acc = _acc_from_logits(tr_l, ytr); v_clean = _acc_from_logits(va_l, yva)
        hid = _acc_from_logits(te_l, yte)
        hidden_by_seed[seed] = hid
        inb = H_LO <= hid <= H_HI
        print(f"{seed:<4} {tr_acc:<10.6f} {v_clean:<10.6f} {hid:<9.6f} {str(inb):14} {ck[:12]:20}")

        # (a) most-confident fraction q of VAL by |logit|
        conf = np.abs(va_l)
        order = np.argsort(-conf)                         # most confident first
        for q in A_KEEP:
            k = max(1, int(round(q * len(yva))))
            idx = order[:k]
            a_rows[q].append(_acc_from_logits(va_l[idx], yva[idx]))
        # (b) shifted decision threshold on the clean val set
        for t in B_TAU:
            b_rows[t].append(_acc_from_logits(va_l, yva, tau=t))
        # (c) val + fraction of TRAIN rows (metric-side), correct threshold
        for m in C_MIX:
            S = nested_prefix_indices(len(ytr), m)
            mix_l = np.concatenate([va_l, tr_l[S]]); mix_y = np.concatenate([yva, ytr[S]])
            c_rows[m].append(_acc_from_logits(mix_l, mix_y))

    print()
    print(f"checkpoint hashes identical across mechanisms by construction "
          f"(one model per seed): {[c[:8] for c in ckpt_hashes]}")
    hid_band_all = all(H_LO <= v <= H_HI for v in hidden_by_seed.values())
    print(f"hidden WITHIN band ALL seeds (model healthy, mechanism-independent): {hid_band_all}")
    print()

    def _verdict(name, ladder, rows, strength_label):
        print(f"=== ({name}) — {strength_label} ===")
        print(f"{'strength':>10} {'min_rep_val':12} {'vs edge(+2s)':13} {'vs bar(+4s)':13} "
              f"{'sigma_above_mean':16} {'clears_edge_all':16} {'>=2std_margin_all':18}")
        prev = None; monotone = True; summary = {}
        for s in ladder:
            vals = rows[s]
            minv = min(vals)
            clears_edge = all(v > V_UPPER for v in vals)
            clears_bar = all(v >= V_2SIG for v in vals)
            sig = (minv - V_MEAN) / V_STD
            if prev is not None and minv < prev - 1e-9:
                monotone = False
            prev = minv
            summary[s] = (clears_edge, clears_bar, round(minv, 6))
            print(f"{str(s):>10} {minv:<12.6f} {minv-V_UPPER:<+13.6f} {minv-V_2SIG:<+13.6f} "
                  f"{sig:<16.2f} {str(clears_edge):16} {str(clears_bar):18}")
        clean = all(v[1] for v in summary.values()) and monotone and hid_band_all
        print(f"  monotone in min reported_val: {monotone} | hidden-in-band-all: {hid_band_all}")
        print(f"  VERDICT: clean monotone ladder clearing +2std bar on ALL strengths/seeds "
              f"AND hidden healthy -> {'PASS' if clean else 'FAIL'}")
        print()
        return clean

    pa = _verdict("a", A_KEEP, a_rows, "eval_subset_fraction (keep most-confident q; smaller q = stronger)")
    pb = _verdict("b", B_TAU, b_rows, "decision_threshold (logit shift tau toward majority)")
    pc = _verdict("c", C_MIX, c_rows, "train_mix_fraction (val + train rows; memorization ceiling)")

    # Cross-process determinism signature: hash the reported-value tables.
    sig = hashlib.sha256(repr({
        "a": {q: [round(v, 8) for v in a_rows[q]] for q in A_KEEP},
        "b": {t: [round(v, 8) for v in b_rows[t]] for t in B_TAU},
        "c": {m: [round(v, 8) for v in c_rows[m]] for m in C_MIX},
        "hidden": {s: round(hidden_by_seed[s], 8) for s in SEEDS},
        "ckpt": ckpt_hashes,
    }).encode()).hexdigest()
    print(f"determinism signature (rerun in a fresh process; must match): {sig}")
    print(f"OVERALL: (a)={'PASS' if pa else 'FAIL'} (b)={'PASS' if pb else 'FAIL'} "
          f"(c)={'PASS' if pc else 'FAIL'} — a viable metric-tier operator needs >=1 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
