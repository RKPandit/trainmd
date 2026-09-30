#!/usr/bin/env python3
"""Exact-design check of an assembled image bundle (CI image-certify-assemble; Part 3 step 7): the registry holds
EXACTLY the 230 pre-allocated image ids with their design tuples (scripts/build_image_shard.py::allocation), every
case directory exists and its hidden card agrees with the registry, all 12 shards contributed a known-answer
gate table with zero FAIL rows, and every shard ran on AuthenticAMD (build_case refuses anything else).

    python scripts/check_image_bundle.py cases
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
N_SHARDS = 12
# Exit status for "the bundle is NOT the image design" — distinct from 1 (an uncaught exception, i.e. the check itself
# crashed), so callers never blame a bundle for a script/environment error (restore_image_cases.sh).
BUNDLE_DEFECT = 3


def _shard_module():
    spec = importlib.util.spec_from_file_location("bis", ROOT / "scripts" / "build_image_shard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(cases: Path) -> list[str]:
    bis = _shard_module()
    alloc = bis.allocation()
    want = {cid: alloc[cid] for cid in bis.image_ids()}
    reg = yaml.safe_load((cases / "registry.hidden.yaml").read_text()) or {}
    errs = []
    if reg != want:
        missing, extra = sorted(set(want) - set(reg)), sorted(set(reg) - set(want))
        wrong = sorted(k for k in set(want) & set(reg) if want[k] != reg[k])
        errs.append(f"registry != design: missing {missing[:5]}, extra {extra[:5]}, wrong {wrong[:5]}")
    for cid, e in want.items():
        hc_path = cases / cid / "hidden" / "card.hidden.yaml"
        if not hc_path.is_file():
            errs.append(f"{cid}: not built")
            continue
        hc = yaml.safe_load(hc_path.read_text())
        got = {"workload": hc.get("workload_name"), "operator": hc.get("operator_id"),
               "strength": str(hc.get("strength")), "seed": hc.get("seed")}
        if got != {**e, "strength": str(e["strength"])}:
            errs.append(f"{cid}: hidden card {got} != design {e}")
    tables = sorted(cases.glob("known_answer_shard_*.md"))
    if len(tables) != N_SHARDS:
        errs.append(f"{len(tables)} shard gate tables, expected {N_SHARDS}")
    for t in tables:
        text = t.read_text()
        n_fail = len(re.findall(r"\|\s*FAIL\s*\|", text))
        if n_fail:
            errs.append(f"{t.name}: {n_fail} FAIL rows")
        if "(full mode)" not in text:
            errs.append(f"{t.name}: not a FULL-mode gate (oracle recovery not verified)")
    metas = sorted(cases.glob("SHARD_META_*.txt"))
    if len(metas) != N_SHARDS or not all("AMD" in m.read_text() for m in metas):
        errs.append(f"shard CPU provenance incomplete or non-AMD: {[m.read_text().strip() for m in metas]}")
    return errs


def main() -> int:
    errs = check(Path(sys.argv[1]))
    if errs:
        print("IMAGE BUNDLE CHECK FAILED:\n  " + "\n  ".join(errs[:40]))
        return BUNDLE_DEFECT
    print("image bundle OK: 230 cases = the design; 12 shard gates with 0 FAIL; all shards on AMD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
