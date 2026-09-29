#!/usr/bin/env python3
"""Byte-level fingerprint of training runs, and a strict comparison of two fingerprints (Stage 4 Part 3:
"CNN training is byte-identical across two AMD runners before building cases" — DECISIONS 2026-09-27).

A run's fingerprint is
  * weights_sha256 — sha256 over every checkpoint tensor (sorted by name; name, dtype, shape and raw bytes);
  * metrics_sha256 — sha256 over every metrics.jsonl row with the WALL-TIME fields removed (they measure the
    machine, not the computation); every loss / accuracy value, per step and per epoch, is included;
  * the final visible metric, for reading.

    python scripts/fingerprint_training.py fingerprint OUT_DIR [OUT_DIR ...] --out fp.json
    python scripts/fingerprint_training.py compare fp1.json fp2.json      # exit 1 on ANY difference
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

WALL_TIME_FIELDS = {"epoch_time_sec", "throughput_samples_per_sec", "peak_memory_mb"}


def weights_sha256(ckpt: Path) -> str:
    import torch
    state = torch.load(ckpt, map_location="cpu", weights_only=False)["model_state_dict"]
    h = hashlib.sha256()
    for name in sorted(state):
        t = state[name].detach().contiguous().cpu()
        h.update(name.encode())
        h.update(str(t.dtype).encode())
        h.update(json.dumps(list(t.shape)).encode())
        h.update(t.numpy().tobytes())
    return h.hexdigest()


def metrics_sha256(metrics: Path) -> tuple[str, dict]:
    h = hashlib.sha256()
    last = {}
    for line in metrics.read_text().splitlines():
        if not line.strip():
            continue
        row = {k: v for k, v in json.loads(line).items() if k not in WALL_TIME_FIELDS}
        h.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
        if row.get("end_of_epoch"):
            last = row
    return h.hexdigest(), last


def fingerprint(out_dir: Path) -> dict:
    exitcode = (out_dir / "exitcode").read_text().strip()
    m_sha, last = metrics_sha256(out_dir / "metrics.jsonl")
    return {"run": out_dir.name, "exitcode": exitcode,
            "weights_sha256": weights_sha256(out_dir / "checkpoints" / "ckpt_final.pt") if exitcode == "0" else None,
            "metrics_sha256": m_sha, "final_epoch": {k: v for k, v in last.items() if k != "end_of_epoch"}}


def compare(a: dict, b: dict) -> list[str]:
    diffs = []
    if sorted(a["runs"]) != sorted(b["runs"]):
        diffs.append(f"different run sets: {sorted(a['runs'])} vs {sorted(b['runs'])}")
    for run in sorted(set(a["runs"]) & set(b["runs"])):
        for k in ("exitcode", "weights_sha256", "metrics_sha256"):
            if a["runs"][run][k] != b["runs"][run][k]:
                diffs.append(f"{run}: {k} differs ({a['runs'][run][k]} vs {b['runs'][run][k]})")
        if a["runs"][run]["exitcode"] != "0":
            diffs.append(f"{run}: training failed (exitcode {a['runs'][run]['exitcode']})")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprint")
    f.add_argument("out_dirs", nargs="+", type=Path)
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--host-note", default="")
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    a = ap.parse_args()
    if a.cmd == "fingerprint":
        doc = {"note": a.host_note, "runs": {d.name: fingerprint(d) for d in a.out_dirs}}
        a.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    A, Bd = json.loads(a.a.read_text()), json.loads(a.b.read_text())
    diffs = compare(A, Bd)
    print(f"A: {A.get('note')}\nB: {Bd.get('note')}")
    if diffs:
        print("NOT BYTE-IDENTICAL:\n  " + "\n  ".join(diffs))
        return 1
    print(f"BYTE-IDENTICAL: {len(A['runs'])} runs — weights and every non-wall-time metric value match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
