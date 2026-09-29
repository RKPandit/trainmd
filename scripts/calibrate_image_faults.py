#!/usr/bin/env python3
"""Graded-strength calibration of the image_fmnist faults on DEVELOPMENT seeds (Part 3 build step 3; approved
design `docs/PART3_DESIGN_DRAFT.md`, DECISIONS 2026-09-28). Native amd64 only.

For each fault, every candidate strength is trained on dev seeds 0–5 through the same path cases will use (the
workload's `train.py` with the fault's config keys set; the evaluator for the hidden metric), and judged against
the bars derived from the ADOPTED reference (`operators/margins.py` rule: 2σ + 1e-3 beyond the band edge):

  positive symptom  visible >= mean_v + 4σ_v + 1e-3 on EVERY seed
  degradation       hidden  <= mean_h − 4σ_h − 1e-3 on EVERY seed
  metric tier       visible positive bar on every seed AND the 3-seed-style mean hidden >= tolerance_lower
                    (the model is untouched; only the reported number moves)

Ladder rule (stated before running): mild = the WEAKEST candidate passing every bar on every seed; severe = the
STRONGEST passing candidate; moderate = the passing candidate whose mean effect is closest to the midpoint of the
two. GRADED iff the mean effect is strictly monotone mild < moderate < severe; otherwise the fault is reported as
not graded (redesign, or detection-only as workload 1's lr fault — design §1). The crash fault is checked for a
nonzero exit with a traceback on every candidate and seed; the neutral-key families are checked to give
BYTE-IDENTICAL training to their descriptive counterparts.

    python scripts/calibrate_image_faults.py --fault tag --out tag.json
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEV_SEEDS = [0, 1, 2, 3, 4, 5]

# name -> (tier, [(label, {config key: value})] ordered WEAKEST -> STRONGEST, effect metric)
FAULTS = {
    "tag": ("silent_positive", [(f"noise={p}", {"data.corner_tag": True, "data.corner_tag_noise": p})
                                for p in (0.7, 0.6, 0.5, 0.4, 0.3, 0.2)], "visible"),
    "swap": ("silent_negative", [(f"fraction={f}", {"data.flip_fraction": f})
                                 for f in (0.10, 0.15, 0.20, 0.25, 0.30)], "hidden"),
    "decay": ("silent_negative", [(f"gamma={g}", {"sched.decay_every": 1, "sched.decay_gamma": g,
                                                  "sched.interval_unit": "steps"})
                                  for g in (0.98, 0.97, 0.95, 0.90, 0.80)], "hidden"),
    "report": ("metric", [(f"fraction={q}", {"eval.confident_fraction": q})
                          for q in (0.95, 0.90, 0.85, 0.80, 0.70)], "visible"),
    "channels": ("crash", [(f"in_ch={c}", {"net.in_ch": c}) for c in (2, 3, 4)], None),
    # SECOND PASS (disclosed, DECISIONS 2026-09-28): the first swap grid (0.10–0.30) left only two passing
    # candidates; its effect is monotone, so the grid is extended upward and the ladder re-applied over all eight.
    "swap_ext": ("silent_negative", [(f"fraction={f}", {"data.flip_fraction": f}) for f in (0.35, 0.40, 0.45)],
                 "hidden"),
    # SECOND PASS (disclosed): the first tag grid (noise 0.7–0.2) left one passing candidate; monotone effect.
    "tag_ext": ("silent_positive", [(f"noise={p}", {"data.corner_tag": True, "data.corner_tag_noise": p})
                                    for p in (0.15, 0.10, 0.05)], "visible"),
}
# neutral-key twins: (descriptive fault, the key renames of the image_fmnist_neutral family)
NEUTRAL = {"tag": {"data.corner_tag": "data.opt_t", "data.corner_tag_noise": "data.opt_t_level"},
           "report": {"eval.confident_fraction": "eval.opt_q"}}


def _put(cfg: dict, path: str, value) -> None:
    *head, leaf = path.split(".")
    d = cfg
    for h in head:
        d = d.setdefault(h, {})
    d[leaf] = value


def run_one(workload: str, patch: dict, seed: int, tmp: Path, keep: bool = False) -> dict:
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint
    from harness.thread_pins import pinned_thread_env
    from harness.workload_spec import final_visible, visible_series
    wd = ROOT / "workloads" / workload
    cfg = copy.deepcopy(yaml.safe_load((wd / "config.yaml").read_text()))
    for k, v in patch.items():
        _put(cfg, k, v)
    cpath = tmp / "config.yaml"
    cpath.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
    out = tmp / "run"
    r = subprocess.run([sys.executable, str(wd / "train.py"), "--config", str(cpath),
                        "--data-dir", str(ROOT / "workloads" / "image_fmnist" / ".data"),
                        "--output-dir", str(out), "--seed", str(seed)],
                       capture_output=True, text=True, env=pinned_thread_env())
    exitcode = int((out / "exitcode").read_text().strip()) if (out / "exitcode").exists() else r.returncode
    row = {"seed": seed, "exitcode": exitcode}
    if exitcode == 0:
        row["visible"] = final_visible(out, visible_series(cfg))
        row["hidden"] = evaluate_checkpoint(out / "checkpoints" / "ckpt_final.pt",
                                            ROOT / "workloads" / "image_fmnist" / ".hidden_data", cfg)[
            "metric_hidden_test_acc"]
    else:
        log = (out / "logs" / "stdout.log").read_text() if (out / "logs" / "stdout.log").exists() else ""
        row["traceback"] = "Traceback (most recent call last)" in log
        row["exception"] = next((ln for ln in log.splitlines() if ln.startswith("RuntimeError")), None)
    if keep:
        from scripts.fingerprint_training import fingerprint
        row["fingerprint"] = fingerprint(out) if exitcode == 0 else None
    return row


def bars() -> dict:
    st = yaml.safe_load((ROOT / "workloads" / "image_fmnist" / "reference" / "stats.yaml").read_text())
    v, h = st["metric_visible_val_acc"], st["metric_hidden_test_acc"]
    return {"visible_mean": v["mean"], "hidden_mean": h["mean"], "tolerance_lower": h["tolerance_lower"],
            "positive_bar": round(v["mean"] + 4 * v["std"] + 1e-3, 6),
            "degradation_bar": round(h["mean"] - 4 * h["std"] - 1e-3, 6)}


def judge(tier: str, rows: list[dict], b: dict) -> tuple[bool, str]:
    if any(r["exitcode"] != 0 for r in rows):
        return False, "a run did not complete"
    vis = [r["visible"] for r in rows]
    hid = [r["hidden"] for r in rows]
    if tier == "silent_positive":
        ok_v = all(x >= b["positive_bar"] for x in vis)
        ok_h = all(x <= b["degradation_bar"] for x in hid)
        return ok_v and ok_h, f"visible>=bar {sum(x >= b['positive_bar'] for x in vis)}/6, hidden<=bar " \
                              f"{sum(x <= b['degradation_bar'] for x in hid)}/6"
    if tier == "silent_negative":
        return all(x <= b["degradation_bar"] for x in hid), \
            f"hidden<=bar {sum(x <= b['degradation_bar'] for x in hid)}/6"
    if tier == "metric":
        ok_v = all(x >= b["positive_bar"] for x in vis)
        ok_h = sum(hid) / len(hid) >= b["tolerance_lower"]
        return ok_v and ok_h, f"visible>=bar {sum(x >= b['positive_bar'] for x in vis)}/6, " \
                              f"mean hidden {'>=' if ok_h else '<'} tolerance"
    raise ValueError(tier)


def ladder(cands: list[dict], metric: str, b: dict) -> dict:
    """Apply the ladder rule to candidates ordered weakest -> strongest."""
    passing = [c for c in cands if c["passes"]]
    if not passing:
        return {"graded": False, "reason": "no candidate passes every bar on every seed"}
    ref = b["visible_mean"] if metric == "visible" else b["hidden_mean"]
    eff = {c["label"]: abs(c[f"mean_{metric}"] - ref) for c in passing}
    mild, severe = passing[0], passing[-1]
    if len(passing) < 3:
        return {"graded": False, "reason": f"only {len(passing)} passing candidate(s)", "mild": mild["label"],
                "severe": severe["label"]}
    mid = (eff[mild["label"]] + eff[severe["label"]]) / 2
    moderate = min(passing[1:-1], key=lambda c: abs(eff[c["label"]] - mid))
    rungs = [mild, moderate, severe]
    graded = eff[rungs[0]["label"]] < eff[rungs[1]["label"]] < eff[rungs[2]["label"]]
    return {"graded": graded, "mild": mild["label"], "moderate": moderate["label"], "severe": severe["label"],
            "mean_effect": {c["label"]: round(eff[c["label"]], 6) for c in rungs},
            "reason": "strictly monotone mean effect" if graded else "mean effect NOT strictly monotone"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fault", required=True, choices=sorted(FAULTS) + ["neutral"])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from harness.platform_guard import cpu_provenance, require_native_amd64
    require_native_amd64(context="calibrate image faults")
    b = bars()
    doc = {"fault": a.fault, "cpu": cpu_provenance(), "dev_seeds": DEV_SEEDS, "bars": b}
    if a.fault == "neutral":
        checks = []
        for name, ren in NEUTRAL.items():
            for label, patch in FAULTS[name][1][::2][:2]:
                for seed in DEV_SEEDS[:2]:
                    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
                        d = run_one("image_fmnist", patch, seed, Path(t1), keep=True)
                        n = run_one("image_fmnist_neutral", {ren.get(k, k): v for k, v in patch.items()}, seed,
                                    Path(t2), keep=True)
                    same = (d["fingerprint"] or {}).get("weights_sha256") == (n["fingerprint"] or {}).get(
                        "weights_sha256") and (d["fingerprint"] or {}).get("metrics_sha256") == (
                        n["fingerprint"] or {}).get("metrics_sha256")
                    checks.append({"fault": name, "label": label, "seed": seed, "identical": bool(same)})
                    print(f"neutral {name} {label} seed {seed}: {'IDENTICAL' if same else 'DIFFERENT'}")
        doc["neutral_checks"] = checks
        doc["all_identical"] = all(c["identical"] for c in checks)
    else:
        tier, cands, metric = FAULTS[a.fault]
        out = []
        for label, patch in cands:
            rows = []
            for seed in DEV_SEEDS:
                with tempfile.TemporaryDirectory() as t:
                    rows.append(run_one("image_fmnist", patch, seed, Path(t)))
            c = {"label": label, "patch": patch, "rows": rows}
            if tier == "crash":
                c["passes"] = all(r["exitcode"] != 0 and r.get("traceback") for r in rows)
                c["why"] = f"crashed with traceback {sum(r['exitcode'] != 0 and bool(r.get('traceback')) for r in rows)}/6"
            else:
                c["passes"], c["why"] = judge(tier, rows, b)
                for m in ("visible", "hidden"):
                    xs = [r[m] for r in rows if r.get(m) is not None]
                    c[f"mean_{m}"] = round(sum(xs) / len(xs), 6) if xs else None
                    c[f"min_{m}"], c[f"max_{m}"] = (min(xs), max(xs)) if xs else (None, None)
            print(f"{a.fault} {label}: passes={c['passes']} ({c['why']}) "
                  f"vis {c.get('min_visible')}–{c.get('max_visible')} hid {c.get('min_hidden')}–{c.get('max_hidden')}")
            out.append(c)
        doc["candidates"] = out
        doc["ladder"] = ({"graded": all(c["passes"] for c in out), "reason": "every candidate crashes"}
                         if tier == "crash" else ladder(out, metric, b))
        print("LADDER:", json.dumps(doc["ladder"]))
    a.out.write_text(json.dumps(doc, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
