#!/usr/bin/env python3
"""QUALIFY candidate benign-configuration changes on DEVELOPMENT seeds (STAGE4_PLAN 4.0.6).

A benign control is a HEALTHY run with a legitimate, routine config change. A change qualifies only
if it does not move model quality — decided here, at DESIGN time, on development seeds 0–29, never by
gating individual confirmatory cases on their band (that would reintroduce the selection bias §5.1
removed; every confirmatory benign case is retained and band-labelled exactly like a §5.1 control).

Test (DECLARED before any run; docs/DECISIONS.md 2026-09-23):
  For each candidate c and each development seed s, train the clean workload and the workload with c
  applied (identical seed), and evaluate the HIDDEN test accuracy of both checkpoints.
  d_s = acc_c(s) − acc_clean(s)  (paired on seed).
  (1) MEAN — TOST equivalence, α = 0.05 per side: the 90% t-interval of mean(d) must lie inside
      (−δ, +δ), δ = 1.0 × σ_ref, σ_ref = the reference hidden-accuracy SD (reference/stats.yaml).
  (2) SPREAD — SD(acc_c) / SD(acc_clean) over the same seeds must lie in [2/3, 3/2].
  QUALIFIED iff (1) and (2).
  Reported alongside, NOT gated (author's review): the VISIBLE metric — mean shift in σ_vis units and
  the visible BAND POSITION (share of runs below / inside / above the public band mean ± 2σ_vis, for
  the change vs clean). Agents see the visible metric, so a change harmless to the model but visibly
  shifted would be flagged by band-following agents — known before the run, not discovered in it.
Results are reported as-is; a candidate that fails is rejected, not re-parameterised.

Must run on native amd64 (training is platform-sensitive): CI workflow `benign-qualify`, or
`make docker-qualify-benign` on an Intel/AMD host.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.seed_sets import DEVELOPMENT  # noqa: E402

WORKLOAD = ROOT / "workloads" / "tabular_adult"
DELTA_SIGMAS = 1.0
SPREAD_BOUNDS = (2 / 3, 3 / 2)
T_95_ONE_SIDED = {29: 1.699127}          # t_{0.95, n-1} for n = 30 (the design size)

# Candidate changes: routine practitioner edits, each a (key path -> value) set applied to the clean
# workload config. `form` records whether the edit CHANGES an existing key or ADDS a new one (four of
# the five faults add a key; benign edits must not be separable from faults by form alone).
CANDIDATES = {
    "batch_size_128": {"edits": {"training.batch_size": 128}, "form": "changed",
                       "why": "smaller mini-batch (256 -> 128)"},
    "epochs_25": {"edits": {"training.epochs": 25}, "form": "changed",
                  "why": "slightly longer training (20 -> 25 epochs)"},
    "weight_decay_5e-4": {"edits": {"training.weight_decay": 0.0005}, "form": "changed",
                          "why": "stronger L2 regularisation (1e-4 -> 5e-4)"},
    "dropout_0.1": {"edits": {"model.dropout": 0.1}, "form": "changed",
                    "why": "light dropout (0.0 -> 0.1)"},
    "lr_0.005": {"edits": {"training.lr": 0.005}, "form": "changed",
                 "why": "lower learning rate within its normal range (0.01 -> 0.005); same knob as "
                        "the lr fault at a different value — tests value reasoning, not knob presence"},
    "grad_clip_1.0": {"edits": {"training.grad_clip_norm": 1.0}, "form": "added",
                      "why": "enable gradient-norm clipping at 1.0 (a routine setting; NEW key, not a "
                             "fault key — train.py reads it, absent = no clipping)"},
}
# Dropped after review: data.label_noise_fraction (small label noise is the label-corruption fault at
# sub-threshold strength — the deferred sub-band tier, not a control).


def apply_edits(config: dict, edits: dict) -> dict:
    out = copy.deepcopy(config)
    for path, value in edits.items():
        node = out
        *parents, leaf = path.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
    return out


def _train_eval(config: dict, seed: int, work: Path) -> tuple[float, float]:
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint
    from harness.thread_pins import pinned_thread_env
    work.mkdir(parents=True, exist_ok=True)
    cfg_path = work / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(config, sort_keys=False))
    out = work / "run"
    r = subprocess.run([sys.executable, str(WORKLOAD / "train.py"), "--config", str(cfg_path),
                        "--data-dir", str(WORKLOAD / ".data"), "--output-dir", str(out),
                        "--seed", str(seed)], env=pinned_thread_env(), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"train failed (seed {seed}): {r.stderr[-400:]}")
    hidden = evaluate_checkpoint(out / "checkpoints" / "ckpt_final.pt", WORKLOAD / ".hidden_data",
                                 config)["metric_hidden_test_acc"]
    from harness.reference_run import _read_epoch_metrics   # the reference's own epoch reader
    visible = _read_epoch_metrics(out / "metrics.jsonl")[-1]["metric_visible_val_acc"]
    return float(hidden), float(visible)


def _band_shares(vals, lo, hi) -> dict:
    n = len(vals)
    return {"below": float(sum(v < lo for v in vals) / n), "inside": float(sum(lo <= v <= hi for v in vals) / n),
            "above": float(sum(v > hi for v in vals) / n)}


def qualify(clean: dict[int, tuple], cand: dict[int, tuple], sigma_ref: float,
            vis_band: tuple[float, float] | None = None) -> dict:
    """The declared test on paired per-seed (hidden, visible) results (+ visible info, not gated).

    ``vis_band`` = (public visible mean, σ_vis) of the reference; the band is mean ± 2σ_vis."""
    seeds = sorted(clean)
    h_c = np.array([cand[s][0] for s in seeds]); h_0 = np.array([clean[s][0] for s in seeds])
    v_c = np.array([cand[s][1] for s in seeds]); v_0 = np.array([clean[s][1] for s in seeds])
    d = h_c - h_0
    n = len(d)
    se = float(d.std(ddof=1) / math.sqrt(n)) if n > 1 else float("inf")
    t = T_95_ONE_SIDED.get(n - 1)
    if t is None:
        from scipy import stats as _st           # only for non-design sizes
        t = float(_st.t.ppf(0.95, n - 1))
    lo, hi = float(d.mean() - t * se), float(d.mean() + t * se)
    delta = DELTA_SIGMAS * sigma_ref
    sd0, sdc = float(h_0.std(ddof=1)), float(h_c.std(ddof=1))
    ratio = sdc / sd0 if sd0 else float("inf")
    mean_ok = -delta < lo and hi < delta
    spread_ok = SPREAD_BOUNDS[0] <= ratio <= SPREAD_BOUNDS[1]
    visible = {"shift": float((v_c - v_0).mean())}
    if vis_band is not None:
        vm, vs = vis_band
        blo, bhi = vm - 2 * vs, vm + 2 * vs
        visible.update({"shift_sigmas": float((v_c - v_0).mean() / vs),
                        "band_change": _band_shares(v_c, blo, bhi), "band_clean": _band_shares(v_0, blo, bhi)})
    return {"n": n, "mean_d": float(d.mean()), "ci90": [lo, hi], "delta": delta, "visible": visible,
            "mean_d_sigmas": float(d.mean() / sigma_ref), "ci90_sigmas": [lo / sigma_ref, hi / sigma_ref],
            "sd_ratio": ratio, "mean_ok": mean_ok, "spread_ok": spread_ok,
            "visible_shift": visible["shift"], "qualified": bool(mean_ok and spread_ok)}


def _pct(x) -> str:
    return f"{100 * x:.0f}%"


def render(results: dict, sigma_ref: float, seeds: list[int]) -> str:
    L = ["# Benign-configuration change qualification (STAGE4_PLAN 4.0.6)", "",
         "> Generated by `scripts/qualify_benign.py` on native amd64; do NOT hand-edit. The test and "
         "threshold were declared before any run (DECISIONS 2026-09-23).", "",
         f"- Development seeds: {seeds[0]}–{seeds[-1]} (n = {len(seeds)}), each run clean AND with the "
         "change (paired on seed); metric = HIDDEN test accuracy.",
         f"- σ_ref (reference hidden-accuracy SD) = {sigma_ref:.6f}; δ = {DELTA_SIGMAS} σ_ref = "
         f"{DELTA_SIGMAS * sigma_ref:.6f}.",
         "- QUALIFIED iff the 90% CI of the mean paired difference lies inside (−δ, +δ) (TOST, α=0.05 "
         f"per side) AND SD(change)/SD(clean) ∈ [{SPREAD_BOUNDS[0]:.3f}, {SPREAD_BOUNDS[1]:.3f}].", "",
         "", "### Hidden accuracy — the qualification test", "",
         "| change | form | mean Δ hidden (σ_ref) | 90% CI (σ_ref) | SD ratio | mean | spread | verdict |",
         "|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        L.append(f"| `{name}` — {CANDIDATES[name]['why']} | {CANDIDATES[name]['form']} | "
                 f"{r['mean_d_sigmas']:+.3f} | [{r['ci90_sigmas'][0]:+.3f}, {r['ci90_sigmas'][1]:+.3f}] | "
                 f"{r['sd_ratio']:.3f} | {'ok' if r['mean_ok'] else 'FAIL'} | "
                 f"{'ok' if r['spread_ok'] else 'FAIL'} | **{'QUALIFIED' if r['qualified'] else 'REJECTED'}** |")
    L += ["", "### Visible metric — what agents see (reported, NOT gated)", "",
          "Band = public reference visible mean ± 2σ_vis. A change that shifts runs out of band will be "
          "flagged by band-following agents even if it is harmless to the model.", "",
          "| change | mean Δ visible (σ_vis) | band position, change: below / inside / above | "
          "band position, clean (same seeds): below / inside / above |", "|---|---|---|---|"]
    for name, r in results.items():
        v = r["visible"]
        bc, b0 = v.get("band_change"), v.get("band_clean")
        L.append(f"| `{name}` | {v.get('shift_sigmas', float('nan')):+.3f} | "
                 + (f"{_pct(bc['below'])} / {_pct(bc['inside'])} / {_pct(bc['above'])} | "
                    f"{_pct(b0['below'])} / {_pct(b0['inside'])} / {_pct(b0['above'])} |" if bc else "— | — |"))
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=sorted(DEVELOPMENT))
    ap.add_argument("--candidates", nargs="+", default=list(CANDIDATES))
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "audits" / "benign_qualification.md")
    a = ap.parse_args()
    assert set(a.seeds) <= DEVELOPMENT, "qualification uses DEVELOPMENT seeds only"
    from harness.platform_guard import require_native_amd64
    require_native_amd64(context="qualify benign configuration changes")

    base = yaml.safe_load((WORKLOAD / "config.yaml").read_text())
    stats = yaml.safe_load((WORKLOAD / "reference" / "stats.yaml").read_text())
    sigma_ref = float(stats["metric_hidden_test_acc"]["std"])
    vis_band = (float(stats["metric_visible_val_acc"]["mean"]), float(stats["metric_visible_val_acc"]["std"]))
    with tempfile.TemporaryDirectory(prefix="benign_q_") as tmp:
        work = Path(tmp)
        clean = {s: _train_eval(base, s, work / f"clean_{s}") for s in a.seeds}
        print("clean done", flush=True)
        results = {}
        for name in a.candidates:
            cfg = apply_edits(base, CANDIDATES[name]["edits"])
            cand = {s: _train_eval(cfg, s, work / f"{name}_{s}") for s in a.seeds}
            results[name] = qualify(clean, cand, sigma_ref, vis_band)
            print(name, json.dumps(results[name]), flush=True)
    a.out.write_text(render(results, sigma_ref, a.seeds))
    (a.out.with_suffix(".json")).write_text(json.dumps(
        {"sigma_ref": sigma_ref, "seeds": a.seeds, "results": results}, indent=1, sort_keys=True) + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
