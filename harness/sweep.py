"""Sweep 1 orchestrator (spec §8; HYPOTHESES.md).

Subcommands: ``plan`` (enumerate the pre-registered cell list + cost estimate),
``run --phase agents`` (the paid trials, resumable + cost-capped + precondition-
gated), ``run --phase verify`` (the free recovery reruns), and ``report``.

The runner never bypasses the sealed trial path — it drives ``run_trial`` per cell.
Agent construction and per-trial cost are INJECTABLE so the whole orchestration is
tested on stubs at zero cost.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_STRENGTHS = ["mild", "moderate", "severe"]
DEFAULT_FAULTY_SEEDS = [42, 43]
DEFAULT_CONTROL_SEEDS = [0, 1, 2]
DEFAULT_REPEATS = 3
AGENTS = ["react", "static"]
ANCHORS = ["on", "off"]
CONTROL_OPERATOR = "control.healthy.v1"
WORKLOAD = "tabular_adult"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_registry(project_root: Path) -> dict:
    p = project_root / "cases" / "registry.hidden.yaml"
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def _tier_of(operator: str) -> str:
    if operator.startswith("control."):
        return "control"
    if operator.startswith("crash."):
        return "execution"
    return "dynamics"


def _lookup_case(registry: dict, operator: str, strength: str, seed: int) -> str | None:
    for cid, e in registry.items():
        if (e.get("operator") == operator and e.get("strength") == strength
                and e.get("seed") == seed and e.get("workload") == WORKLOAD):
            return cid
    return None


def _cell_id(operator, strength, seed, agent, anchor, repeat) -> str:
    key = f"{operator}:{strength}:{seed}:{agent}:{anchor}:{repeat}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _design_tuples(registry, strengths, faulty_seeds, control_seeds):
    """Yield (operator, strength, seed) for the intended design."""
    faulty_ops = sorted({
        e["operator"] for e in registry.values()
        if e.get("operator") and _tier_of(e["operator"]) != "control"
    })
    for op in faulty_ops:
        for st in strengths:
            for sd in faulty_seeds:
                yield op, st, sd
    for sd in control_seeds:
        yield CONTROL_OPERATOR, "mild", sd


def enumerate_cells(project_root, strengths, faulty_seeds, control_seeds, repeats):
    """Return (cells, missing) — cells cross the design with agent×anchor×repeat."""
    registry = _load_registry(project_root)
    cells, missing = [], []
    for op, st, sd in _design_tuples(registry, strengths, faulty_seeds, control_seeds):
        case_id = _lookup_case(registry, op, st, sd)
        tier = _tier_of(op)
        if case_id is None or not (project_root / "cases" / case_id).exists():
            missing.append({"operator": op, "strength": st, "seed": sd})
        for agent in AGENTS:
            for anchor in ANCHORS:
                for r in range(repeats):
                    cells.append({
                        "cell_id": _cell_id(op, st, sd, agent, anchor, r),
                        "case_id": case_id,
                        "operator": op, "tier": tier, "strength": st, "seed": sd,
                        "agent": agent, "anchor": anchor, "repeat_index": r,
                    })
    return cells, missing


# ---------------------------------------------------------------------------
# Cost estimation from prior trials
# ---------------------------------------------------------------------------

def _prior_costs(project_root: Path) -> dict:
    """Map (operator, agent) -> [costs] from prior trial records; + all costs."""
    by_pair: dict[tuple, list] = {}
    all_costs: list[float] = []
    registry = _load_registry(project_root)
    results = project_root / "results"
    if not results.exists():
        return {"by_pair": by_pair, "all": all_costs}
    for tp in results.glob("*/trials/*.yaml"):
        rec = yaml.safe_load(tp.read_text())
        if not isinstance(rec, dict) or rec.get("trusted"):
            continue
        cost = (rec.get("usage") or {}).get("estimated_cost_usd")
        if not isinstance(cost, (int, float)):
            continue
        op = (registry.get(rec.get("case_id"), {}) or {}).get("operator")
        agent = (rec.get("conditions") or {}).get("agent_type")
        if agent is None:
            name = rec.get("agent_name", "")
            agent = "static" if name.startswith("static_") else "react"
        by_pair.setdefault((op, agent), []).append(cost)
        all_costs.append(cost)
    return {"by_pair": by_pair, "all": all_costs}


def estimate_cost(cells, priors) -> dict:
    """Per-cell estimate (measured mean, else MAX-observed fallback). Conservative."""
    by_pair, all_costs = priors["by_pair"], priors["all"]
    fallback = max(all_costs) if all_costs else 0.0
    total, low, high, measured, fb = 0.0, 0.0, 0.0, 0, 0
    for c in cells:
        key = (c["operator"], c["agent"])
        costs = by_pair.get(key)
        if costs:
            total += sum(costs) / len(costs)
            low += min(costs)
            high += max(costs)
            measured += 1
        else:
            total += fallback
            low += fallback
            high += fallback
            fb += 1
    return {
        "per_cell_total_usd": round(total, 4),
        "low_usd": round(low, 4), "high_usd": round(high, 4),
        "fallback_cost_usd": round(fallback, 6),
        "estimate_source_counts": {"measured": measured, "fallback": fb},
    }


def _cell_est(c, priors) -> float:
    by_pair, all_costs = priors["by_pair"], priors["all"]
    costs = by_pair.get((c["operator"], c["agent"]))
    if costs:
        return sum(costs) / len(costs)
    return max(all_costs) if all_costs else 0.0


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def plan(project_root, name, strengths=None, faulty_seeds=None, control_seeds=None,
         repeats=DEFAULT_REPEATS, order_seed=1234, model=DEFAULT_MODEL) -> dict:
    strengths = strengths or DEFAULT_STRENGTHS
    faulty_seeds = faulty_seeds or DEFAULT_FAULTY_SEEDS
    control_seeds = control_seeds or DEFAULT_CONTROL_SEEDS
    cells, missing = enumerate_cells(project_root, strengths, faulty_seeds, control_seeds, repeats)
    random.Random(order_seed).shuffle(cells)

    priors = _prior_costs(project_root)
    cost_est = estimate_cost(cells, priors)

    registry = _load_registry(project_root)
    case_set = {}
    for c in cells:
        if c["case_id"] and c["case_id"] not in case_set:
            pub = project_root / "cases" / c["case_id"] / "card.public.yaml"
            build_id = None
            if pub.exists():
                build_id = (yaml.safe_load(pub.read_text()) or {}).get("case_build_id")
            case_set[c["case_id"]] = {
                "operator": c["operator"], "tier": c["tier"],
                "strength": c["strength"], "seed": c["seed"], "build_id": build_id,
            }

    n_verify = sum(1 for c in cells if c["tier"] != "control" and c["case_id"])
    manifest = {
        "name": name, "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": model, "order_seed": order_seed,
        "factor_levels": {"agents": AGENTS, "anchors": ANCHORS, "repeats": repeats,
                          "strengths": strengths, "faulty_seeds": faulty_seeds,
                          "control_seeds": control_seeds},
        "n_cells": len(cells), "n_missing": len(missing),
        "cost_estimate": cost_est,
        "verify_estimate": {"reruns": n_verify},
        "case_set": case_set,
    }
    out = {"header": manifest, "cells": cells}
    return {"plan": out, "missing": missing, "path": project_root / "sweeps" / f"{name}_plan.yaml"}


def write_plan(result) -> Path:
    p = result["path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(result["plan"], default_flow_style=False, sort_keys=False))
    return p


def build_missing(project_root, missing) -> dict:
    """Build each missing (operator, strength, seed) tuple (idempotent)."""
    from harness.build_case import build_case, _load_registry as _lr, _find_existing_case
    built, skipped, failed = [], [], []
    reg_path = project_root / "cases" / "registry.hidden.yaml"
    for m in missing:
        reg = _lr(reg_path)
        if _find_existing_case(reg, WORKLOAD, m["operator"], m["strength"], m["seed"]):
            skipped.append(m)
            continue
        try:
            build_case(WORKLOAD, m["operator"], m["strength"], m["seed"],
                       project_root=project_root)
            built.append(m)
        except Exception as e:  # noqa: BLE001
            failed.append({**m, "error": str(e)[:200]})
    return {"built": built, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# run --phase agents
# ---------------------------------------------------------------------------

def _progress_path(project_root, name, phase="agents"):
    suffix = "progress" if phase == "agents" else "verify_progress"
    return project_root / "sweeps" / f"{name}_{suffix}.jsonl"


def _load_progress(path) -> dict:
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                done[e["cell_id"]] = e
    return done


def _append_progress(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()


def check_preconditions(project_root, plan_doc) -> list[str]:
    """Return a list of failed-precondition messages (empty = all pass)."""
    from harness.gate_known_answer import run_gate
    from harness.audit_index import run_audit
    from harness.validate_case import validate_all
    import os

    fails = []
    gate_rows = run_gate(project_root, fast=True)
    if any(r.status == "FAIL" for r in gate_rows):
        fails.append("known-answer gate has FAILs")
    _, audit_fail = run_audit(project_root)
    if audit_fail:
        fails.append(f"audit-index has {audit_fail} FAIL(s)")
    if not all(rep.passed for rep in validate_all(project_root)):
        fails.append("validate-all not green")
    # build_id drift
    for cid, info in plan_doc["header"]["case_set"].items():
        pub = project_root / "cases" / cid / "card.public.yaml"
        if not pub.exists():
            fails.append(f"case {cid} missing")
            continue
        cur = (yaml.safe_load(pub.read_text()) or {}).get("case_build_id")
        if cur != info.get("build_id"):
            fails.append(f"case {cid} build_id drift (plan {info.get('build_id')} != {cur})")
    # plan committed
    plan_rel = f"sweeps/{plan_doc['header']['name']}_plan.yaml"
    try:
        r = subprocess.run(["git", "status", "--porcelain", plan_rel],
                           capture_output=True, text=True, cwd=project_root)
        if r.stdout.strip():
            fails.append("plan file is not committed (git-clean check failed)")
    except FileNotFoundError:
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        fails.append("ANTHROPIC_API_KEY not set")
    return fails


def _default_agent_factory(cell, model):
    from harness.llm.anthropic_client import AnthropicClient
    from agents.llm_agent import LLMAgent
    from agents.static_agent import StaticContextAgent
    client = AnthropicClient(model=model, temperature=1.0)
    if cell["agent"] == "static":
        return StaticContextAgent(client, model_id=model, anchor=cell["anchor"])
    return LLMAgent(client, model_id=model, anchor=cell["anchor"])


def _cost_from_record(rec) -> float:
    return (rec.get("usage") or {}).get("estimated_cost_usd") or 0.0


def run_agents(project_root, name, max_cost_usd, *, agent_factory=None, cost_fn=None,
               est_fn=None, trial_fn=None, max_trials=None, max_consecutive_failures=3,
               require_preconditions=True):
    """Execute the paid agent phase. Returns a summary dict.

    ``agent_factory``/``trial_fn``/``cost_fn``/``est_fn`` are injectable so the
    orchestration (resume, cost cap, circuit breaker) is tested on stubs.
    """
    from harness.run_agent import run_trial
    from harness.sweep_manifest import capture_hardware, new_manifest, write_manifest

    plan_path = project_root / "sweeps" / f"{name}_plan.yaml"
    plan_doc = yaml.safe_load(plan_path.read_text())
    cells = plan_doc["cells"]
    model = plan_doc["header"].get("model", DEFAULT_MODEL)
    agent_factory = agent_factory or (lambda c: _default_agent_factory(c, model))
    cost_fn = cost_fn or _cost_from_record
    trial_fn = trial_fn or run_trial
    priors = _prior_costs(project_root)
    est_fn = est_fn or (lambda c: _cell_est(c, priors))

    if require_preconditions:
        fails = check_preconditions(project_root, plan_doc)
        if fails:
            return {"stopped": "preconditions", "failures": fails, "ran": 0}

    manifest = new_manifest(name, estimated_spend_usd=plan_doc["header"]["cost_estimate"]["per_cell_total_usd"],
                            hardware=capture_hardware(project_root))
    write_manifest(project_root, manifest)

    prog_path = _progress_path(project_root, name, "agents")
    done = _load_progress(prog_path)
    cumulative = sum(e.get("cost_usd", 0.0) for e in done.values())
    consecutive_fail = 0
    ran = 0
    stopped = None
    walls = []
    tok_in = tok_out = 0

    for cell in cells:
        if cell["cell_id"] in done or not cell["case_id"]:
            continue
        est = est_fn(cell)
        if cumulative + est > max_cost_usd:
            stopped = f"cost_cap (would exceed ${max_cost_usd} at cumulative ${cumulative:.4f} + est ${est:.4f})"
            break
        if max_trials is not None and ran >= max_trials:
            stopped = "max_trials"
            break

        conditions = {"sweep_name": name, "agent_type": cell["agent"],
                      "anchor": cell["anchor"], "repeat_index": cell["repeat_index"]}
        case_dir = project_root / "cases" / cell["case_id"]
        rec = None
        error = None
        for attempt in range(2):  # retry once
            try:
                t0 = time.monotonic()
                rec = trial_fn(agent_factory(cell), case_dir, project_root,
                               conditions=conditions)
                walls.append(time.monotonic() - t0)
                error = None
                break
            except Exception as e:  # noqa: BLE001
                error = str(e)

        if error is not None:
            consecutive_fail += 1
            _append_progress(prog_path, {"cell_id": cell["cell_id"], "status": "failed",
                                         "error": error[:300], "ts": datetime.now(timezone.utc).isoformat()})
            if consecutive_fail >= max_consecutive_failures:
                stopped = f"circuit_breaker ({consecutive_fail} consecutive failures) — systemic failure suspected — check key/model/provider. Last error: {error[:200]}"
                break
            continue

        consecutive_fail = 0
        cost = cost_fn(rec)
        cumulative += cost
        ran += 1
        tok_in += (rec.get("usage") or {}).get("input_tokens", 0)
        tok_out += (rec.get("usage") or {}).get("output_tokens", 0)
        done[cell["cell_id"]] = {"cost_usd": cost}
        _append_progress(prog_path, {"cell_id": cell["cell_id"], "run_id": rec.get("run_id"),
                                     "agent": cell["agent"], "cost_usd": cost, "status": "ok",
                                     "ts": datetime.now(timezone.utc).isoformat()})
        eta = (len(cells) - len(done)) * (sum(walls) / len(walls)) if walls else 0
        print(f"[sweep] {len(done)}/{len(cells)} | ${cumulative:.4f}/${max_cost_usd} | "
              f"fail={sum(1 for e in done.values() if e.get('status')=='failed')} | ETA {eta/60:.1f}m",
              file=sys.stderr)

    manifest["agent_phase"].update({
        "trials": ran, "input_tokens": tok_in, "output_tokens": tok_out,
        "estimated_cost_usd": round(cumulative, 4),
        "api_wall_clock_sec": round(sum(walls), 2),
    })
    write_manifest(project_root, manifest)
    return {"stopped": stopped, "ran": ran, "cumulative_cost": round(cumulative, 4)}


# ---------------------------------------------------------------------------
# run --phase verify
# ---------------------------------------------------------------------------

def _maxrss_to_mb(ru_maxrss: int) -> float:
    # Linux reports KB, macOS reports bytes.
    if sys.platform == "darwin":
        return ru_maxrss / (1024 * 1024)
    return ru_maxrss / 1024


def run_verify(project_root, name, *, recovery_fn=None):
    """Free recovery phase over completed non-control agent trials."""
    from harness.scoring import score_recovery_standalone
    from harness.sweep_manifest import write_manifest
    recovery_fn = recovery_fn or score_recovery_standalone

    manifest_path = project_root / "sweeps" / f"{name}_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else None
    if manifest is None:
        return {"error": "no manifest — run agent phase first"}

    agent_done = _load_progress(_progress_path(project_root, name, "agents"))
    vprog_path = _progress_path(project_root, name, "verify")
    vdone = _load_progress(vprog_path)

    reruns = 0
    cpu_sec = 0.0
    wall = 0.0
    peak_mb = 0.0
    for cell_id, entry in agent_done.items():
        if entry.get("status") != "ok" or cell_id in vdone:
            continue
        run_id = entry.get("run_id")
        # find the record + case
        rec_path = _find_record(project_root, run_id)
        if rec_path is None:
            continue
        rec = yaml.safe_load(rec_path.read_text())
        if rec.get("submission") is None:
            continue
        tier = _tier_of((_load_registry(project_root).get(rec["case_id"], {}) or {}).get("operator", ""))
        if tier == "control":
            continue  # controls scored inline; no verify_repair

        case_dir = project_root / "cases" / rec["case_id"]
        r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        w0 = time.monotonic()
        recovery_fn(rec_path, case_dir, project_root)
        w1 = time.monotonic()
        r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
        cpu_sec += cpu
        wall += (w1 - w0)
        peak_mb = max(peak_mb, _maxrss_to_mb(r1.ru_maxrss))
        reruns += 1
        _append_progress(vprog_path, {"cell_id": cell_id, "run_id": run_id,
                                      "cpu_sec": round(cpu, 3), "wall_sec": round(w1 - w0, 3),
                                      "ts": datetime.now(timezone.utc).isoformat()})

    manifest["verify_phase"].update({
        "reruns": manifest["verify_phase"]["reruns"] + reruns,
        "cpu_core_hours": round(manifest["verify_phase"]["cpu_core_hours"] + cpu_sec / 3600, 4),
        "wall_clock_sec": round(manifest["verify_phase"]["wall_clock_sec"] + wall, 2),
        "peak_memory_mb": round(max(manifest["verify_phase"]["peak_memory_mb"], peak_mb), 2),
        "ru_maxrss_platform": sys.platform,
    })
    write_manifest(project_root, manifest)
    return {"reruns": reruns, "cpu_sec": round(cpu_sec, 2)}


def _find_record(project_root, run_id):
    for tp in (project_root / "results").glob("*/trials/*.yaml"):
        if run_id and run_id in tp.name:
            return tp
    return None


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def report(project_root, name):
    """Aggregate scores + H1-H6 metrics; write a markdown table."""
    from harness.scoring import aggregate_scores

    registry = _load_registry(project_root)
    agent_done = _load_progress(_progress_path(project_root, name, "agents"))
    records = []
    excluded = {"trusted": 0, "superseded": 0}
    for entry in agent_done.values():
        if entry.get("status") != "ok":
            continue
        rp = _find_record(project_root, entry.get("run_id"))
        if rp is None:
            continue
        rec = yaml.safe_load(rp.read_text())
        if rec.get("trusted"):
            excluded["trusted"] += 1
            continue
        if rec.get("card_superseded"):
            excluded["superseded"] += 1
            continue
        rec["_operator"] = (registry.get(rec["case_id"], {}) or {}).get("operator")
        records.append(rec)

    lines = [f"# Sweep {name} — {date.today().isoformat()}", "",
             f"records={len(records)} excluded_trusted={excluded['trusted']} "
             f"excluded_superseded={excluded['superseded']}", ""]

    # aggregate per (operator, agent, anchor). The recovery column shows the
    # recovery rate for faulty tiers and the no_unnecessary_repair rate for controls
    # (their recovery axis) — NOT a spurious 0.0.
    lines += ["## Scores by (operator, agent, anchor)", "",
              "| operator | agent | anchor | n | detection | identification | evidence_f1 | recovery/no_unnec |",
              "|---|---|---|---|---|---|---|---|"]
    groups = {}
    for r in records:
        key = (r["_operator"], (r.get("conditions") or {}).get("agent_type"),
               (r.get("conditions") or {}).get("anchor"))
        groups.setdefault(key, []).append(_trial_score(r))
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        agg = aggregate_scores(groups[key])
        op, ag, an = key
        if op and _tier_of(op) == "control":
            nur = [s for s in groups[key]
                   if (s.get("recovery") or {}).get("no_unnecessary_repair") is not None]
            recov = (round(sum(1 for s in nur if s["recovery"]["no_unnecessary_repair"]) / len(nur), 4)
                     if nur else 0.0)
        else:
            recov = agg["recovery_rate"]
        lines.append(f"| {op} | {ag} | {an} | {agg['n_trials']} | {agg['detection_accuracy']} | "
                     f"{agg['identification_accuracy']} | {agg['evidence_mean_f1']} | {recov} |")

    lines += ["", "## Hypothesis metrics", "", "```", yaml.dump(hypothesis_metrics(records, registry),
                                                                default_flow_style=False, sort_keys=False), "```"]
    out = project_root / "docs" / "audits" / f"sweep_{name}_{date.today().strftime('%Y%m%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    return out


def _trial_score(rec) -> dict:
    """Reconstruct a score dict (as aggregate_scores expects) from a record."""
    s = rec.get("scores") or {}
    return {
        "tier": _tier_of(rec.get("_operator", "") or ""),
        "trusted": rec.get("trusted", False),
        "detection": s.get("detection") or {"correct": False, "detected_predicted": None},
        "identification": s.get("identification") or {"correct": False},
        "evidence": s.get("evidence") or {"f1": 0.0, "recall": 0.0},
        "recovery": s.get("recovery"),
        "safety": s.get("safety") or {"rejected_tool_calls": 0, "forbidden_actions": 0},
    }


def hypothesis_metrics(records, registry) -> dict:
    """Explicit H1-H6 numbers from the records + hidden-card sigma distances."""
    def hc(cid):
        p = _repo_root() / "cases" / str(cid) / "hidden" / "card.hidden.yaml"
        return yaml.safe_load(p.read_text()) if p.exists() else {}

    def group(pred):
        return [r for r in records if pred(r)]

    def detect_rate(rs):
        rs = [r for r in rs if (r.get("scores") or {}).get("detection")]
        if not rs:
            return None
        return round(sum(1 for r in rs if r["scores"]["detection"]["correct"]) / len(rs), 4)

    def id_rate(rs):
        rs = [r for r in rs if (r.get("scores") or {}).get("identification")]
        return round(sum(1 for r in rs if r["scores"]["identification"]["correct"]) / len(rs), 4) if rs else None

    anchor = lambda r: (r.get("conditions") or {}).get("anchor")
    op = lambda r: r.get("_operator")
    agent = lambda r: (r.get("conditions") or {}).get("agent_type")

    # H1: leakage vs negative-symptom detection by anchor
    h1 = {}
    for an in ("on", "off"):
        leak = detect_rate(group(lambda r: op(r) == "silent.data_leakage.v1" and anchor(r) == an))
        neg = detect_rate(group(lambda r: op(r) in ("silent.lr_warmup.v1", "silent.label_corruption.v1") and anchor(r) == an))
        h1[an] = {"leakage_detection": leak, "negative_symptom_detection": neg}

    # H2: detection rate vs sigma-distance, split by anchor. Restored — this block
    # was previously missing from the generator, silently dropping H2 from reports.
    # Per silent (dynamics-tier) case: sigma distances + symptom_direction from the
    # hidden card, detection rate overall / by anchor / by agent. The anchor split is
    # the load-bearing comparison (does the numeric reference band substitute for
    # sigma sensitivity?), so it is reported per case and summarized per anchor.
    h2_cases = []
    silent = [r for r in records if _tier_of(op(r) or "") == "dynamics"]
    by_case = {}
    for r in silent:
        by_case.setdefault(r.get("case_id"), []).append(r)
    for cid in sorted(by_case, key=lambda c: str(c)):
        rs = by_case[cid]
        card = hc(cid)
        h2_cases.append({
            "case_id": cid,
            "operator": op(rs[0]),
            "strength": (rs[0].get("conditions") or {}).get("strength")
                        or rs[0].get("strength"),
            "visible_sigma_distance": card.get("visible_sigma_distance"),
            "hidden_sigma_distance": card.get("hidden_sigma_distance"),
            "symptom_direction": card.get("symptom_direction"),
            "detection_rate": detect_rate(rs),
            "detection_rate_anchor_on": detect_rate([r for r in rs if anchor(r) == "on"]),
            "detection_rate_anchor_off": detect_rate([r for r in rs if anchor(r) == "off"]),
            "detection_rate_react": detect_rate([r for r in rs if agent(r) == "react"]),
            "detection_rate_static": detect_rate([r for r in rs if agent(r) == "static"]),
        })
    h2 = {
        "by_case": h2_cases,
        "by_anchor": {
            an: {
                "detection_rate": detect_rate([r for r in silent if anchor(r) == an]),
                "n": len([r for r in silent if anchor(r) == an]),
            }
            for an in ("on", "off")
        },
        "note": ("detection anchor-off tracks symptom_direction, not sigma magnitude — "
                 "see by_case (positive-symptom cases stay near floor even at large "
                 "sigma_hidden when anchor is off)"),
    }

    # H3: recovery_rate - identification_rate per operator (recovery from record.scores)
    h3 = {}
    for o in sorted({op(r) for r in records if op(r)}):
        rs = group(lambda r: op(r) == o)
        recov = [r for r in rs if (r.get("scores") or {}).get("recovery", {}) and
                 (r["scores"]["recovery"] or {}).get("verdict") == "recovered"]
        rr = round(len(recov) / len(rs), 4) if rs else None
        h3[o] = {"recovery_rate": rr, "identification_rate": id_rate(rs)}

    # H4: repeat agreement — over (case_id, agent, anchor) cells, do the 3 repeats
    # agree on both detection and identification?
    h4 = {}
    by_cell = {}
    for r in records:
        by_cell.setdefault((r.get("case_id"), agent(r), anchor(r)), []).append(r)
    agree_vals = []
    for rs in by_cell.values():
        if len(rs) < 2:
            continue
        det = {((rr.get("scores") or {}).get("detection", {}) or {}).get("correct") for rr in rs}
        idn = {((rr.get("scores") or {}).get("identification", {}) or {}).get("correct") for rr in rs}
        agree_vals.append(1.0 if (len(det) == 1 and len(idn) == 1) else 0.0)
    h4["mean_repeat_agreement"] = round(sum(agree_vals) / len(agree_vals), 4) if agree_vals else None

    # H6: per-operator (react - static) on evidence_f1 and detection
    h6 = {}
    for o in sorted({op(r) for r in records if op(r)}):
        def ev(ag):
            rs = [r for r in records if op(r) == o and agent(r) == ag]
            rs = [r for r in rs if (r.get("scores") or {}).get("evidence")]
            return round(sum(r["scores"]["evidence"]["f1"] for r in rs) / len(rs), 4) if rs else None
        re, st = ev("react"), ev("static")
        h6[o] = {"react_evidence_f1": re, "static_evidence_f1": st,
                 "react_minus_static": (round(re - st, 4) if re is not None and st is not None else None)}

    # controls
    ctrl = group(lambda r: _tier_of(op(r) or "") == "control")
    fpr = round(sum(1 for r in ctrl if ((r.get("scores") or {}).get("detection", {}) or {}).get("detected_predicted") is True) / len(ctrl), 4) if ctrl else None
    fint = round(sum(1 for r in ctrl if ((r.get("scores") or {}).get("recovery", {}) or {}).get("false_intervention") is True) / len(ctrl), 4) if ctrl else None

    return {
        "H1_positive_symptom_blindness": h1,
        "H2_detection_vs_sigma_by_anchor": h2,
        "H3_doing_understanding_gap": h3,
        "H4_repeat_agreement": h4,
        "H6_tools_vs_static": h6,
        "H5": "Sweep 2 (single model here)",
        "controls": {"detection_fpr": fpr, "false_intervention_rate": fint, "n": len(ctrl)},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep 1 orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan")
    pp.add_argument("--name", required=True)
    pp.add_argument("--strengths", nargs="*", default=None)
    pp.add_argument("--seeds", nargs="*", type=int, default=None)
    pp.add_argument("--control-seeds", nargs="*", type=int, default=None)
    pp.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    pp.add_argument("--order-seed", type=int, default=1234)
    pp.add_argument("--build-missing", action="store_true")
    pp.add_argument("--project-root", type=Path, default=None)

    rp = sub.add_parser("run")
    rp.add_argument("--name", required=True)
    rp.add_argument("--phase", required=True, choices=["agents", "verify"])
    rp.add_argument("--max-cost-usd", type=float, default=None)
    rp.add_argument("--max-trials", type=int, default=None)
    rp.add_argument("--max-consecutive-failures", type=int, default=3)
    rp.add_argument("--project-root", type=Path, default=None)

    rep = sub.add_parser("report")
    rep.add_argument("--name", required=True)
    rep.add_argument("--project-root", type=Path, default=None)

    args = ap.parse_args()
    root = args.project_root or _repo_root()

    if args.cmd == "plan":
        result = plan(root, args.name, args.strengths, args.seeds, args.control_seeds,
                      args.repeats, args.order_seed)
        if args.build_missing and result["missing"]:
            summary = build_missing(root, result["missing"])
            print(f"[build-missing] built={len(summary['built'])} skipped={len(summary['skipped'])} "
                  f"failed={len(summary['failed'])}")
            from harness.validate_case import validate_all
            if not all(r.passed for r in validate_all(root)):
                print("validate-all FAILED after build-missing", file=sys.stderr)
                return 1
            result = plan(root, args.name, args.strengths, args.seeds, args.control_seeds,
                          args.repeats, args.order_seed)
        path = write_plan(result)
        est = result["plan"]["header"]["cost_estimate"]
        print(f"Plan: {path}\n  cells={result['plan']['header']['n_cells']} "
              f"missing={len(result['missing'])}\n  est ${est['per_cell_total_usd']} "
              f"(low ${est['low_usd']} / high ${est['high_usd']}) sources={est['estimate_source_counts']}")
        if result["missing"]:
            for m in result["missing"]:
                print(f"  MISSING: {m['operator']} {m['strength']} seed={m['seed']}")
            return 1
        return 0

    if args.cmd == "run":
        if args.phase == "agents":
            if args.max_cost_usd is None:
                ap.error("--max-cost-usd is required for the agent phase")
            r = run_agents(root, args.name, args.max_cost_usd, max_trials=args.max_trials,
                           max_consecutive_failures=args.max_consecutive_failures)
            print(r)
            return 1 if r.get("stopped") == "preconditions" else 0
        r = run_verify(root, args.name)
        print(r)
        return 0

    if args.cmd == "report":
        out = report(root, args.name)
        print(f"Report: {out}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
