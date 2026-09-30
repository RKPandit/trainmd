#!/usr/bin/env python3
"""Build one SHARD of the Part 3 image cases (design `docs/PART3_DESIGN_DRAFT.md` §4; build step 7). Native AMD only
(build_case refuses any other platform).

230 image cases (≈ 1 training run each, plus the FULL known-answer gate's 3-seed oracle verification) do not fit
one 6-hour runner, so CI builds them in N parallel shards (dispatch task `image-certify`). Case ids must not depend
on which shard runs first, so every shard starts from ONE pre-allocated registry: workload 1's 200 design tuples
as case_0001–case_0200 (the ids a fresh `build_all_cases` gives them) followed by the image design as
case_0201–case_0430, in `case_design_tuples("image_fmnist")` order. `build_case(..., force=True)` then reuses each
tuple's pre-allocated id. Shard k builds image tuples i with i % N == k (interleaved, so every shard gets a mix of
tiers), and afterwards the shard's registry is REDUCED to the entries it built, so the assemble step can union
the shards' registries without overlap.

    python scripts/build_image_shard.py --shard 3 --of 12
    python scripts/build_image_shard.py --allocate-only       # write the pre-allocated registry and exit
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from operators.registry import get_operator  # noqa: E402
from scripts.build_all_cases import IMAGE_GROUP, case_design_tuples  # noqa: E402


def allocation() -> dict:
    """case_id -> registry entry for the FULL design (workload 1 then image), in design order."""
    out = {}
    tuples = case_design_tuples() + case_design_tuples(IMAGE_GROUP)
    for i, (op, st, sd) in enumerate(tuples, 1):
        out[f"case_{i:04d}"] = {"workload": getattr(get_operator(op), "WORKLOAD_FAMILY", "tabular_adult"),
                                "operator": op, "strength": st, "seed": sd}
    return out


def image_ids() -> list[str]:
    n1 = len(case_design_tuples())
    return [f"case_{i:04d}" for i in range(n1 + 1, n1 + 1 + len(case_design_tuples(IMAGE_GROUP)))]


def shard_ids(k: int, n: int) -> list[str]:
    return [cid for i, cid in enumerate(image_ids()) if i % n == k]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shard", type=int)
    ap.add_argument("--of", type=int)
    ap.add_argument("--allocate-only", action="store_true")
    a = ap.parse_args()
    root = Path(os.environ.get("TRAINMD_ROOT", ROOT))
    alloc = allocation()
    reg_path = root / "cases" / "registry.hidden.yaml"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(yaml.dump(alloc, default_flow_style=False, sort_keys=True))
    if a.allocate_only:
        print(f"allocated {len(alloc)} ids ({len(image_ids())} image: {image_ids()[0]}–{image_ids()[-1]})")
        return 0
    from harness.build_case import build_case
    mine = shard_ids(a.shard, a.of)
    print(f"shard {a.shard}/{a.of}: {len(mine)} image cases", flush=True)
    for n, cid in enumerate(mine, 1):
        e = alloc[cid]
        case_dir = build_case(e["workload"], e["operator"], e["strength"], e["seed"], project_root=root, force=True)
        assert Path(case_dir).name == cid, f"{cid} built as {Path(case_dir).name}"
        print(f"  [{n}/{len(mine)}] {cid} {e['operator']} {e['strength']} seed={e['seed']}", flush=True)
    reg = yaml.safe_load(reg_path.read_text())
    reg_path.write_text(yaml.dump({cid: reg[cid] for cid in mine}, default_flow_style=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
