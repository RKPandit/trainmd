#!/usr/bin/env python3
"""QUALIFY image_fmnist benign-configuration controls on DEVELOPMENT seeds 0–29 — workload 1's declared test
(`scripts/qualify_benign.py::qualify`, DECISIONS 2026-09-23): paired on seed, the 90% t-interval of the mean
hidden-accuracy difference must lie inside ±1 σ_ref and SD(change)/SD(clean) inside [2/3, 3/2]; the visible shift
and band position are reported, not gated. Native amd64 only.

Types: the seven image benign operators (operators/image/controls.py; design §3). The seventh image type, `schedule_noop`, ADDS the same three schedule keys the
LR-schedule fault adds, with decay factor 1.0 — a non-engaging new-key control mirroring workload 1's grad-clip
one, so flagging the key can be told apart from finding the unit bug. Every run is also fingerprinted, so a change
that cannot move training is shown BYTE-IDENTICAL to the clean run, not just statistically equivalent.

    python scripts/qualify_image_benign.py --types schedule_noop --out benign.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEV_SEEDS = list(range(30))
def _types() -> dict:
    """type name -> (FORM, config edits), read from the OPERATORS (operators/image/controls.py) so the qualified
    edit is exactly the edit the cases carry. ``schedule_noop`` keeps its name from the first qualification run
    (CI 36513288844)."""
    from operators.image.controls import IMAGE_BENIGN_OPERATORS
    out = {}
    for cls in IMAGE_BENIGN_OPERATORS:
        name = cls.id.split(".")[1].removeprefix("benign_img_")
        out["schedule_noop" if name == "sched_noop" else name] = (cls.FORM, dict(cls.EDITS))
    return out


TYPES = _types()


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--types", nargs="+", default=sorted(TYPES), choices=sorted(TYPES))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from harness.platform_guard import cpu_provenance, require_native_amd64
    require_native_amd64(context="qualify image benign controls")
    cal = _load("cal", "scripts/calibrate_image_faults.py")
    qb = _load("qb", "scripts/qualify_benign.py")
    st = yaml.safe_load((ROOT / "workloads" / "image_fmnist" / "reference" / "stats.yaml").read_text())
    sigma_ref = float(st["metric_hidden_test_acc"]["std"])
    vis_band = (float(st["metric_visible_val_acc"]["mean"]), float(st["metric_visible_val_acc"]["std"]))
    clean, fp_clean = {}, {}
    for s in DEV_SEEDS:
        with tempfile.TemporaryDirectory() as t:
            r = cal.run_one("image_fmnist", {}, s, Path(t), keep=True)
        clean[s], fp_clean[s] = (r["hidden"], r["visible"]), r["fingerprint"]
    doc = {"cpu": cpu_provenance(), "dev_seeds": DEV_SEEDS, "sigma_ref": sigma_ref, "types": {}}
    for name in a.types:
        form, patch = TYPES[name]
        cand, same = {}, 0
        for s in DEV_SEEDS:
            with tempfile.TemporaryDirectory() as t:
                r = cal.run_one("image_fmnist", patch, s, Path(t), keep=True)
            cand[s] = (r["hidden"], r["visible"])
            same += (r["fingerprint"]["weights_sha256"] == fp_clean[s]["weights_sha256"]
                     and r["fingerprint"]["metrics_sha256"] == fp_clean[s]["metrics_sha256"])
        q = qb.qualify(clean, cand, sigma_ref, vis_band)
        q.update({"form": form, "patch": patch, "byte_identical_to_clean": f"{same}/{len(DEV_SEEDS)}"})
        doc["types"][name] = q
        print(f"{name} ({form}): QUALIFIED={q['qualified']}  mean Δ hidden {q['mean_d_sigmas']:+.3f} σ_ref, "
              f"90% CI [{q['ci90_sigmas'][0]:+.3f}, {q['ci90_sigmas'][1]:+.3f}] σ_ref, SD ratio {q['sd_ratio']:.3f}, "
              f"visible shift {q['visible']['shift_sigmas']:+.3f} σ_vis; byte-identical to clean {same}/{len(DEV_SEEDS)}")
    a.out.write_text(json.dumps(doc, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
