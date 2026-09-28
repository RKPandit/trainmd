#!/usr/bin/env python3
"""Project a sweep's FULL agents-phase cost from the trials it has run so far (e.g. the pre-run slice).

The plan's own `cost_estimate` comes from historical priors (and a max-observed fallback for operators
with none), which can be far off; this uses the sweep's OWN measured per-trial costs instead: mean cost
per group over the finished trials × that group's cell count in the plan. A group is one CONDITION × agent:
(provider, model, settings, agent, confirmatory/exploratory), where settings are the cell's generation
settings (effort, thinking) — so Sonnet 5 thinking-off and xhigh, or GPT-6 Luna and GPT-6 Sol, are never
averaged together (DECISIONS 2026-09-28). With one model per provider and no settings, as in Part 1, the
groups and the projection are exactly the former (provider, agent) ones.
Groups with no finished trial yet are reported as unmeasured (not guessed). Read-only.

    python scripts/project_sweep_cost.py --name stage4_part1 [--cap 60]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


SETTINGS = ("effort", "thinking")


def _settings(src: dict) -> str:
    s = ",".join(f"{k}={src[k]}" for k in SETTINGS if src.get(k) is not None)
    return s or "—"


def _group(provider, model, settings, agent, passback_off) -> tuple:
    return (provider, model, settings, agent, "exploratory" if passback_off else "confirmatory")


def project(root: Path, name: str) -> dict:
    plan = yaml.safe_load((root / "sweeps" / f"{name}_plan.yaml").read_text())
    planned = collections.Counter(_group(c.get("provider", "anthropic"), c.get("model"), _settings(c), c["agent"],
                                         c.get("reasoning_passback") is False) for c in plan["cells"])
    spent = collections.defaultdict(list)
    for f in (root / "results").glob("*/trials/*.yaml"):
        rec = yaml.safe_load(f.read_text()) or {}
        cond = rec.get("conditions") or {}
        cost = (rec.get("usage") or {}).get("estimated_cost_usd")
        if cond.get("sweep_name") != name or not isinstance(cost, (int, float)):
            continue
        spent[_group(cond.get("provider", "anthropic"), (rec.get("model") or {}).get("model_id"), _settings(cond),
                     cond.get("agent_type"), cond.get("reasoning_passback") is False)].append(cost)
    rows, total, unmeasured = [], 0.0, []
    for g, n in sorted(planned.items()):
        xs = spent.get(g, [])
        if not xs:
            unmeasured.append(g)
            rows.append((g, n, 0, None, None))
            continue
        mean = sum(xs) / len(xs)
        total += mean * n
        rows.append((g, n, len(xs), mean, mean * n))
    return {"rows": rows, "projected_total": total, "unmeasured": unmeasured,
            "spent_so_far": sum(sum(v) for v in spent.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--cap", type=float, default=None)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    r = project(a.project_root, a.name)
    print(f"{'group (provider, model, settings, agent, kind)':76} {'cells':>6} {'measured':>8} {'mean $':>9} "
          f"{'projected $':>12}")
    for g, n, k, mean, tot in r["rows"]:
        print(f"{' · '.join(str(x) for x in g):76} {n:6d} {k:8d} {('%.4f' % mean) if mean is not None else '—':>9} "
              f"{('%.2f' % tot) if tot is not None else 'UNMEASURED':>12}")
    print(f"spent so far: ${r['spent_so_far']:.2f}   projected full run (measured groups): ${r['projected_total']:.2f}")
    if r["unmeasured"]:
        print(f"UNMEASURED groups (no finished trial yet — projection incomplete): {r['unmeasured']}")
    if a.cap is not None:
        ok = r["projected_total"] <= a.cap and not r["unmeasured"]
        print(f"cap ${a.cap:.2f}: {'FITS' if ok else 'DOES NOT FIT (or incomplete)'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
