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
# Provider factor (cross-provider sweep). Each entry is {provider, model}. Default
# is the single study model (Anthropic Haiku), so existing single-provider plans are
# unchanged. `--providers anthropic:claude-haiku-4-5-20251001 openai:gpt-5.6-luna`
# crosses both.
DEFAULT_PROVIDERS = [{"provider": "anthropic", "model": DEFAULT_MODEL}]
# Per-provider cost SCALE applied to Haiku-derived priors when a provider has no
# priors of its own. openai(Luna) 0.16 = the measured smoke ratio ($0.0075/trial vs
# Haiku ~$0.046, incl. reasoning tokens; 2026-09-19). UNVERIFIED — confirm vs billing.
_PROVIDER_COST_SCALE = {"anthropic": 1.0, "openai": 0.16}
DEFAULT_STRENGTHS = ["mild", "moderate", "severe"]
DEFAULT_FAULTY_SEEDS = [42, 43]
DEFAULT_CONTROL_SEEDS = [0, 1, 2]
DEFAULT_REPEATS = 3
AGENTS = ["react", "static"]
# Three-arm anchor (L10): off (no band) | numbers (bare fact) | rule (numbers +
# the explicit decision rule). Legacy Sweep-1 "on" == "rule".
ANCHORS = ["off", "numbers", "rule"]
CONTROL_OPERATOR = "control.healthy.v1"
WORKLOAD = "tabular_adult"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_registry(project_root: Path) -> dict:
    p = project_root / "cases" / "registry.hidden.yaml"
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def _tier_of(operator: str) -> str:
    """Resolve an operator's tier from its ACTUAL layer (single source of truth).

    The id prefix is not authoritative — silent.metric_inflation.v1 is the
    metric tier, not dynamics — so a prefix map would pool the metric-tier
    operator with the silent (dynamics) ones in the symptom analysis. Resolve
    the layer from the registered operator; fall back to the prefix only for
    ids not in the registry (defensive; the registry is the source).
    """
    from operators.registry import OPERATOR_REGISTRY

    cls = OPERATOR_REGISTRY.get(operator)
    if cls is not None:
        return cls().layer
    if operator.startswith("control."):
        return "control"
    if operator.startswith("crash."):
        return "execution"
    return "dynamics"


def _lookup_case(registry: dict, operator: str, strength: str, seed: int) -> str | None:
    # Match the operator's OWN workload family, not the hardcoded default: the
    # neutral-key variant lives on `tabular_adult_neutral`, so a `== WORKLOAD`
    # filter would never find its cases and mark every one MISSING (bug fixed
    # 2026-09-20). (operator, strength, seed) is unique within a family.
    from operators.registry import get_operator
    wl = getattr(get_operator(operator), "WORKLOAD_FAMILY", WORKLOAD)
    for cid, e in registry.items():
        if (e.get("operator") == operator and e.get("strength") == strength
                and e.get("seed") == seed and e.get("workload") == wl):
            return cid
    return None


def _cell_id(operator, strength, seed, agent, anchor, repeat, provider="anthropic") -> str:
    key = f"{operator}:{strength}:{seed}:{agent}:{anchor}:{repeat}:{provider}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _design_tuples(registry, strengths, faulty_seeds, control_seeds, operators=None):
    """Yield (operator, strength, seed) for the intended design.

    Faulty operators come from operators/registry.py (code), NOT the case
    registry — so the design is fixed by code and `--build-missing` bootstraps
    from a fresh/empty checkout (otherwise no faulty ops would be enumerated).

    ``operators`` (optional): restrict the faulty operators to this explicit
    subset (e.g. the Stage-2 gate's three symptom-direction operators). Each must
    be a known faulty operator; a control id or unknown id raises. When omitted,
    every registered faulty operator is enumerated (the default full design).
    """
    from operators.registry import all_operator_ids
    all_faulty = sorted(op for op in all_operator_ids() if _tier_of(op) != "control")
    if operators is None:
        faulty_ops = all_faulty
    else:
        unknown = [o for o in operators if o not in all_faulty]
        if unknown:
            raise ValueError(
                f"--operators contains non-faulty/unknown operator(s): {unknown}; "
                f"choose from {all_faulty}"
            )
        faulty_ops = sorted(set(operators))
    for op in faulty_ops:
        for st in strengths:
            for sd in faulty_seeds:
                yield op, st, sd
    for sd in control_seeds:
        yield CONTROL_OPERATOR, "mild", sd


def enumerate_cells(project_root, strengths, faulty_seeds, control_seeds, repeats,
                    operators=None, providers=None):
    """Return (cells, missing) — cells cross the design with provider×agent×anchor×repeat.

    A case (operator, strength, seed) is provider-agnostic; the provider multiplies
    the TRIALS, so MISSING is counted once per (operator, strength, seed), not per cell.
    """
    providers = providers or DEFAULT_PROVIDERS
    registry = _load_registry(project_root)
    cells, missing = [], []
    for op, st, sd in _design_tuples(registry, strengths, faulty_seeds, control_seeds, operators):
        case_id = _lookup_case(registry, op, st, sd)
        tier = _tier_of(op)
        if case_id is None or not (project_root / "cases" / case_id).exists():
            missing.append({"operator": op, "strength": st, "seed": sd})
        # REDUCED CONTROL PROTOCOL: controls exist to measure the false-positive
        # rate (and, per anchor arm, the sensitivity-vs-specificity trade-off), not
        # symptom diagnosis — so run them static-only × 1 repeat (still × all anchor
        # arms × all providers). Faulty cases use the full agent×repeat grid.
        cell_agents = ["static"] if tier == "control" else AGENTS
        cell_repeats = 1 if tier == "control" else repeats
        for prov in providers:
            for agent in cell_agents:
                for anchor in ANCHORS:
                    for r in range(cell_repeats):
                        cells.append({
                            "cell_id": _cell_id(op, st, sd, agent, anchor, r, prov["provider"]),
                            "case_id": case_id,
                            "operator": op, "tier": tier, "strength": st, "seed": sd,
                            "provider": prov["provider"], "model": prov["model"],
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
    """Per-cell estimate (measured mean, else MAX-observed fallback), SPLIT BY PROVIDER.

    Priors are Anthropic (Haiku) trial costs. For a provider with no priors of its own
    (e.g. openai/Luna), the Haiku prior is scaled by ``_PROVIDER_COST_SCALE`` (Luna's
    measured smoke ratio). The split is a budgeting estimate; verify vs billing.
    """
    by_pair, all_costs = priors["by_pair"], priors["all"]
    fallback = max(all_costs) if all_costs else 0.0
    total, low, high, measured, fb = 0.0, 0.0, 0.0, 0, 0
    per_provider: dict[str, dict] = {}
    for c in cells:
        prov = c.get("provider", "anthropic")
        scale = _PROVIDER_COST_SCALE.get(prov, 1.0)
        costs = by_pair.get((c["operator"], c["agent"]))
        if costs:
            m, lo, hi = (sum(costs) / len(costs)) * scale, min(costs) * scale, max(costs) * scale
            measured += 1
        else:
            m = lo = hi = fallback * scale
            fb += 1
        total += m; low += lo; high += hi
        pp = per_provider.setdefault(prov, {"cells": 0, "scale": scale,
                                            "total_usd": 0.0, "low_usd": 0.0, "high_usd": 0.0})
        pp["cells"] += 1
        pp["total_usd"] += m; pp["low_usd"] += lo; pp["high_usd"] += hi
    for pp in per_provider.values():
        for k in ("total_usd", "low_usd", "high_usd"):
            pp[k] = round(pp[k], 4)
    return {
        "per_cell_total_usd": round(total, 4),
        "low_usd": round(low, 4), "high_usd": round(high, 4),
        "fallback_cost_usd": round(fallback, 6),
        "estimate_source_counts": {"measured": measured, "fallback": fb},
        "by_provider": per_provider,
    }


def _cell_est(c, priors, operator=None) -> float:
    by_pair, all_costs = priors["by_pair"], priors["all"]
    # ``operator`` is stripped from the committed plan (it is a per-case answer-key
    # leak — see write_plan); the caller resolves it from the registry by case_id.
    # Fall back to c["operator"] for an in-memory (unstripped) cell.
    op = operator if operator is not None else c.get("operator")
    costs = by_pair.get((op, c["agent"]))
    if costs:
        return sum(costs) / len(costs)
    return max(all_costs) if all_costs else 0.0


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

# Why a registered faulty operator may be deliberately EXCLUDED from a gate's
# --operators set — recorded in the plan header so the exclusion is visible in the
# artifact, not merely implied by a CLI flag.
_EXCLUSION_REASONS = {
    "silent.lr_warmup.v1": "bimodal collapse, retired from the σ-ladder role "
                           "(L1/S12); contributes detection data only, not σ-magnitude",
    "crash.shape_mismatch.v1": "crash tier — orthogonal to a symptom-direction "
                               "(positive vs negative) question",
}


def plan(project_root, name, strengths=None, faulty_seeds=None, control_seeds=None,
         repeats=DEFAULT_REPEATS, order_seed=1234, model=DEFAULT_MODEL,
         operators=None, providers=None) -> dict:
    strengths = strengths or DEFAULT_STRENGTHS
    faulty_seeds = faulty_seeds or DEFAULT_FAULTY_SEEDS
    # `is None` (not `or`) so an explicit empty list means NO controls (faulty-only sweep).
    control_seeds = DEFAULT_CONTROL_SEEDS if control_seeds is None else control_seeds
    providers = providers or DEFAULT_PROVIDERS
    cells, missing = enumerate_cells(
        project_root, strengths, faulty_seeds, control_seeds, repeats, operators, providers)
    random.Random(order_seed).shuffle(cells)

    from operators.registry import all_operator_ids
    _all_faulty = sorted(o for o in all_operator_ids() if _tier_of(o) != "control")
    included = sorted(set(operators)) if operators else _all_faulty
    scope = {
        "gate_operators": included,
        "excluded_operators": {
            o: _EXCLUSION_REASONS.get(o, "not in this gate's --operators set")
            for o in _all_faulty if o not in set(included)
        },
    }

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
        "providers": providers,
        "factor_levels": {"providers": [p["provider"] for p in providers],
                          "models": [p["model"] for p in providers],
                          "variants": operators if operators else "all faulty operators",
                          "agents": AGENTS, "anchors": ANCHORS, "repeats": repeats,
                          "strengths": strengths, "faulty_seeds": faulty_seeds,
                          "control_seeds": control_seeds},
        "scope": scope,
        "n_cells": len(cells), "n_missing": len(missing),
        "cost_estimate": cost_est,
        "verify_estimate": {"reruns": n_verify},
        "case_set": case_set,
    }
    out = {"header": manifest, "cells": cells}
    return {"plan": out, "missing": missing, "path": project_root / "sweeps" / f"{name}_plan.yaml"}


# Per-case fields that map a case_id to its ground truth (operator identity, tier)
# are the identification/detection ANSWER KEY. The plan is COMMITTED (the run
# precondition requires a git-clean plan file) and this is a PUBLIC repo, so the
# committed plan must not publish that mapping. The runner never needs it from the
# plan — it resolves operator/tier from the local hidden card / registry by case_id
# (scoring, gate, verify, cost estimate all do). cell_id already hashes the
# operator, so stripping the readable field is additivity-neutral (ids unchanged).
# Same wall class as the sweep-bundle fix (docs/DECISIONS.md 2026-09-20).
_PLAN_ANSWER_KEY_FIELDS = ("operator", "tier")


def _strip_answer_key(plan_doc: dict) -> dict:
    """Return a deep-ish copy of the plan with per-case answer-key fields removed
    from every cell and from case_set. Header factor_levels/scope keep the LIST of
    operators under test (which cases they map to is what must not leak)."""
    doc = dict(plan_doc)
    doc["cells"] = [
        {k: v for k, v in c.items() if k not in _PLAN_ANSWER_KEY_FIELDS}
        for c in plan_doc.get("cells", [])
    ]
    header = dict(plan_doc.get("header", {}))
    header["case_set"] = {
        cid: {k: v for k, v in info.items() if k not in _PLAN_ANSWER_KEY_FIELDS}
        for cid, info in (plan_doc.get("header", {}).get("case_set", {}) or {}).items()
    }
    doc["header"] = header
    return doc


def write_plan(result) -> Path:
    p = result["path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(_strip_answer_key(result["plan"]),
                           default_flow_style=False, sort_keys=False))
    return p


def build_missing(project_root, missing) -> dict:
    """Build each missing (operator, strength, seed) tuple (idempotent)."""
    from harness.build_case import build_case, _load_registry as _lr, _find_existing_case
    from operators.registry import get_operator
    built, skipped, failed = [], [], []
    reg_path = project_root / "cases" / "registry.hidden.yaml"
    for m in missing:
        # Each operator declares the workload family whose train.py reads its keys
        # (default tabular_adult; the neutral-key variant is tabular_adult_neutral).
        # Mirrors scripts/build_all_cases.py — WORKLOAD is not one-size-fits-all.
        wl = getattr(get_operator(m["operator"]), "WORKLOAD_FAMILY", WORKLOAD)
        reg = _lr(reg_path)
        if _find_existing_case(reg, wl, m["operator"], m["strength"], m["seed"]):
            skipped.append(m)
            continue
        try:
            build_case(wl, m["operator"], m["strength"], m["seed"],
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
    # The committed plan carries no per-cell operator (answer-key leak); resolve it
    # from the registry by case_id for the cost estimate.
    _reg = _load_registry(project_root)
    est_fn = est_fn or (lambda c: _cell_est(
        c, priors, (_reg.get(c["case_id"], {}) or {}).get("operator")))

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
                                      "peak_mb": round(_maxrss_to_mb(r1.ru_maxrss), 2),
                                      "ts": datetime.now(timezone.utc).isoformat()})

    # REPLACE semantics: the manifest MIRRORS the current verify progress file,
    # it does NOT accumulate across invocations. A re-run of the phase (progress
    # file reset) therefore reports THAT run's compute, not prior + this. The old
    # code added to whatever was in the manifest, which double-counted an earlier
    # (e.g. aborted, off-canonical) pass into the compute statement — a number a
    # reviewer checks. The progress file is the single source of truth for what
    # actually ran; totals are recomputed from it. (docs/DECISIONS.md 2026-09-15)
    _finalize_verify_totals(manifest, _load_progress(vprog_path))
    write_manifest(project_root, manifest)
    return {"reruns": reruns, "cpu_sec": round(cpu_sec, 2)}


def _finalize_verify_totals(manifest: dict, vdone: dict) -> None:
    """Set verify_phase compute totals from the progress file (replace, not add).

    ``vdone`` maps cell_id -> progress entry (from :func:`_load_progress`). Every
    completed verify cell contributes exactly once, so re-running the phase after
    resetting its progress file yields that run's totals rather than accumulating.
    """
    entries = list(vdone.values())
    cpu_sec = sum(e.get("cpu_sec", 0.0) or 0.0 for e in entries)
    wall = sum(e.get("wall_sec", 0.0) or 0.0 for e in entries)
    peak_mb = max((e.get("peak_mb", 0.0) or 0.0 for e in entries), default=0.0)
    manifest["verify_phase"].update({
        "reruns": len(entries),
        "cpu_core_hours": round(cpu_sec / 3600, 4),
        "wall_clock_sec": round(wall, 2),
        "peak_memory_mb": round(peak_mb, 2),
        "ru_maxrss_platform": sys.platform,
    })


def _find_record(project_root, run_id):
    for tp in (project_root / "results").glob("*/trials/*.yaml"):
        if run_id and run_id in tp.name:
            return tp
    return None


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def report(project_root, name):
    """Regenerate a sweep's deterministic machine report from records (STAGE3_PLAN §0.3).

    Delegates to harness.report_gen — plan-driven, no hardcoded operator/arm/model literals, date
    from the manifest, byte-identical across runs. Refuses to aggregate over a logically broken
    index (spec §8). Writes docs/audits/sweep_<name>_generated.md and returns its path.
    """
    from harness.audit_index import assert_clean_for_aggregation
    from harness import report_gen

    assert_clean_for_aggregation(project_root)
    project_root = Path(project_root)
    # Exclusion counts (trusted / superseded) for the report header; the analysis loader drops both.
    agent_done = _load_progress(_progress_path(project_root, name, "agents"))
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
        elif rec.get("card_superseded"):
            excluded["superseded"] += 1
    md = report_gen.generate_from_cases(project_root, name, excluded)
    out = project_root / "docs" / "audits" / f"sweep_{name}_generated.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    return out




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
    pp.add_argument("--operators", nargs="*", default=None,
                    help="Restrict faulty operators to this explicit subset (default: "
                         "all registered faulty operators). Excluded ones are recorded "
                         "with a reason in the plan header's scope block.")
    pp.add_argument("--providers", nargs="*", default=None,
                    help="provider:model specs to cross, e.g. "
                         "anthropic:claude-haiku-4-5-20251001 openai:gpt-5.6-luna "
                         "(default: anthropic only)")
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
        providers = None
        if args.providers:
            providers = []
            for spec in args.providers:
                prov, _, mdl = spec.partition(":")
                providers.append({"provider": prov, "model": mdl or DEFAULT_MODEL})
        result = plan(root, args.name, args.strengths, args.seeds, args.control_seeds,
                      args.repeats, args.order_seed, operators=args.operators,
                      providers=providers)
        if args.build_missing and result["missing"]:
            summary = build_missing(root, result["missing"])
            print(f"[build-missing] built={len(summary['built'])} skipped={len(summary['skipped'])} "
                  f"failed={len(summary['failed'])}")
            from harness.validate_case import validate_all
            if not all(r.passed for r in validate_all(root)):
                print("validate-all FAILED after build-missing", file=sys.stderr)
                return 1
            result = plan(root, args.name, args.strengths, args.seeds, args.control_seeds,
                          args.repeats, args.order_seed, operators=args.operators,
                          providers=providers)
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
