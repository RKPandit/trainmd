#!/usr/bin/env python3
"""Sanitized records release (STAGE3_PLAN §0.3-B): make every reported number externally checkable.

`export_release.py --sweep <name>` -> `results_release/<name>/` with, per trial, an ALLOWLISTED
subset (never a denylist), and per case only PUBLIC-safe metadata. A trusted/superseded record is
excluded. After writing, a WALL scans every released byte for the formatted hidden values (as
validator W4 does), the hidden-seed literal, any string from a hidden card, and secret patterns —
and fails the export loudly on any hit. The release lets `rebuild_tables.py` reproduce every
generated number with NO access to `cases/` or `results/` or the registry.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- trial-record field policy: every top-level key must be classified (KNOWN) so a NEW field
#      can never leak silently — an unclassified key fails the export. -----------------------------
_TRIAL_ALLOW = {
    "case_id", "run_id", "conditions", "prompt", "submission", "submission_original",
    "tool_transcript", "llm_transcript", "scores", "usage", "termination_reason",
    "environment", "model", "status", "schema_version", "agent_name",
}
# static_context = the static agent's assembled INPUT (public workspace + band); large and
# reconstructible, not needed to verify a number -> dropped.
_TRIAL_DROP = {"trusted", "card_superseded", "budget", "symptom_direction", "static_context"}

# hidden-side metric values live under scores.recovery.per_seed_hidden_metrics — stripped explicitly
# (B.2 "never export hidden seeds' metric values"); the scan is the backstop.
_RECOVERY_ALLOW = {"verdict", "compute_sec", "reason_codes"}

# per-case metadata that is PUBLIC-safe and needed by the analysis (tier/symptom/σ) — allowlist.
_CASE_META = {  # hidden-card field -> release field
    "operator_id": "operator_id", "layer": "tier", "strength": "strength", "seed": "seed",
    "case_build_id": "build_id", "symptom_direction": "symptom_direction",
    "visible_sigma_distance": "visible_sigma_distance", "hidden_sigma_distance": "hidden_sigma_distance",
}

_SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ANTHROPIC_API_KEY\s*[:=]\s*\S+", re.I)


def _sanitize_trial(rec: dict) -> dict:
    unknown = set(rec) - _TRIAL_ALLOW - _TRIAL_DROP
    if unknown:
        raise SystemExit(f"export: unclassified trial field(s) {sorted(unknown)} in run "
                         f"{rec.get('run_id')} — add to _TRIAL_ALLOW or _TRIAL_DROP (never leak silently)")
    out = {k: rec[k] for k in _TRIAL_ALLOW if k in rec}
    scores = out.get("scores")
    if isinstance(scores, dict) and isinstance(scores.get("recovery"), dict):
        out["scores"] = {**scores, "recovery": {k: v for k, v in scores["recovery"].items()
                                                if k in _RECOVERY_ALLOW}}
    return out


def _case_meta(hidden_card: dict) -> dict:
    return {rel: hidden_card.get(src) for src, rel in _CASE_META.items()}


def _forbidden_needles(root: Path, case_ids: set[str]) -> dict[str, str]:
    """Formatted HIDDEN values that must never appear in the release — exactly validator W4's set.

    Only the truly-hidden numbers are scanned: faulty_value (hidden TEST accuracy under the fault),
    tolerance_lower, hidden mean/std, and the hidden-eval-seed literals. NOT scanned:
    ``faulty_visible_value`` (the agent-VISIBLE faulty metric, legitimately in metrics.jsonl and the
    transcripts) or mutation values (the injected config knob, visible in config.yaml) — those are
    agent-visible by design. accepted_classes/core_tokens are generic words, never exported.
    """
    needles: dict[str, str] = {}
    for cid in case_ids:
        needles.update(_case_needles(root, cid))
    return needles


def _case_needles(root: Path, cid: str) -> dict[str, str]:
    """The formatted hidden values for ONE case (verify.yaml) — scanned only against that case."""
    vp = root / "cases" / cid / "hidden" / "verify.yaml"
    verify = yaml.safe_load(vp.read_text()) if vp.exists() else {}
    needles: dict[str, str] = {}
    for field, label in (("tolerance_lower", "tolerance_lower"), ("faulty_value", "faulty_value"),
                          ("reference_metric_mean", "hidden_mean"), ("reference_metric_std", "hidden_std")):
        v = verify.get(field)
        if isinstance(v, (int, float)):
            needles[f"{v:.6f}"] = f"{cid}:{label}"
    seeds = verify.get("hidden_eval_seeds")
    if isinstance(seeds, list) and seeds:
        needles[str(seeds)] = f"{cid}:hidden_eval_seeds"
        needles[", ".join(str(s) for s in seeds)] = f"{cid}:hidden_eval_seeds"
    return needles


def _case_of(rel: Path) -> str | None:
    """Which case a released file belongs to (trials/<cid>__*.json, cases/<cid>.json), else None."""
    if rel.parent.name == "trials":
        return rel.name.split("__", 1)[0]
    if rel.parent.name == "cases":
        return rel.stem
    return None


def _flatten_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, (list, tuple, set)):
        for i in x:
            yield from _flatten_strings(i)
    elif isinstance(x, dict):
        for i in x.values():
            yield from _flatten_strings(i)


def _scan_release(root: Path, out_dir: Path, case_ids: set[str]) -> list[str]:
    """PER-CASE scan (like W4): a case's files vs its OWN hidden values, so a visible metric value in
    one case cannot false-positive on another case's hidden value. Sweep-level files (plan/manifest/
    index) are scanned against the union — they carry no per-case visible metric series."""
    per_case = {cid: _case_needles(root, cid) for cid in case_ids}
    union = {n: lab for d in per_case.values() for n, lab in d.items()}
    hits = []
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(out_dir)
        cid = _case_of(rel)
        needles = per_case.get(cid, {}) if cid else union
        for needle, label in needles.items():
            if needle and needle in text:
                hits.append(f"{rel}: leaks {label} ({needle!r})")
        if _SECRET_RE.search(text):
            hits.append(f"{rel}: matches a secret pattern")
    return hits


def export(root: Path, name: str, include_probes: bool = False) -> dict:
    root = Path(root)
    out_dir = root / "results_release" / name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "trials").mkdir(parents=True)
    (out_dir / "cases").mkdir(parents=True)
    probes_dir = out_dir / "probes"

    # sweep meta files
    for sub in ("plan", "manifest", "progress", "verify_progress"):
        src = root / "sweeps" / f"{name}_{sub}.{'yaml' if sub in ('plan','manifest') else 'jsonl'}"
        if src.exists():
            shutil.copy2(src, out_dir / src.name)

    case_ids: set[str] = set()
    index_rows, n_trials, n_probes, n_excluded = [], 0, 0, 0
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        if (rec.get("conditions") or {}).get("sweep_name") != name:
            continue
        if rec.get("card_superseded"):
            n_excluded += 1
            continue
        cid, run_id = rec["case_id"], rec["run_id"]
        san = _sanitize_trial(rec)
        if rec.get("trusted"):
            if not include_probes:
                n_probes += 1
                continue
            probes_dir.mkdir(exist_ok=True)
            (probes_dir / f"{cid}__{run_id}.json").write_text(json.dumps(san, indent=1, default=str))
            n_probes += 1
            continue
        (out_dir / "trials" / f"{cid}__{run_id}.json").write_text(json.dumps(san, indent=1, default=str))
        case_ids.add(cid)
        n_trials += 1
        c = san.get("conditions") or {}
        sc = san.get("scores") or {}
        index_rows.append({
            "case_id": cid, "run_id": run_id, "agent": c.get("agent_type"),
            "anchor": c.get("anchor"), "repeat_index": c.get("repeat_index"),
            "detection_correct": ((sc.get("detection") or {}).get("correct")),
            "identification_correct": ((sc.get("identification") or {}).get("correct")),
            "evidence_f1": ((sc.get("evidence") or {}).get("f1")),
            "recovery_verdict": ((sc.get("recovery") or {}).get("verdict")),
            "cost_usd": (san.get("usage") or {}).get("estimated_cost_usd"),
        })

    # per-case public metadata (allowlisted from the hidden card)
    for cid in sorted(case_ids):
        hp = root / "cases" / cid / "hidden" / "card.hidden.yaml"
        pubp = root / "cases" / cid / "card.public.yaml"
        meta = _case_meta(yaml.safe_load(hp.read_text())) if hp.exists() else {}
        meta["case_id"] = cid
        if pubp.exists():
            meta["public_card"] = yaml.safe_load(pubp.read_text())
        (out_dir / "cases" / f"{cid}.json").write_text(json.dumps(meta, indent=1, default=str))

    # index table (CSV — diffable, no new dep)
    if index_rows:
        cols = list(index_rows[0].keys())
        with open(out_dir / "index.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(sorted(index_rows, key=lambda r: (r["case_id"], r["run_id"])))

    # release meta so the reviewer-path regeneration matches the results-path report byte-for-byte
    (out_dir / "release_meta.json").write_text(json.dumps(
        {"sweep": name, "n_trials": n_trials, "n_cases": len(case_ids),
         "excluded": {"trusted": n_probes, "superseded": n_excluded}}, indent=1))

    if probes_dir.exists():
        (probes_dir / "README.md").write_text(
            "# Trusted probe records (oracle / degenerate)\n\n"
            "These are TRUSTED harness probes — they contain ground truth by construction and MUST "
            "NOT be used as contestant data or mixed into aggregate metrics. Excluded from the "
            "primary release; present only for harness-validity inspection.\n")

    # ---- WALL: scan every released byte -------------------------------------
    hits = _scan_release(root, out_dir, case_ids)
    if hits:
        raise SystemExit("export: HIDDEN-VALUE LEAK — refusing to release:\n  " + "\n  ".join(hits[:20]))

    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    return {"out_dir": out_dir, "n_trials": n_trials, "n_probes_excluded_or_segregated": n_probes,
            "n_superseded_excluded": n_excluded, "n_cases": len(case_ids), "bytes": size}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", required=True)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--include-probes", action="store_true")
    a = ap.parse_args()
    r = export(a.project_root, a.sweep, include_probes=a.include_probes)
    mb = r["bytes"] / (1024 * 1024)
    print(f"export OK: {r['out_dir']}")
    print(f"  trials={r['n_trials']} cases={r['n_cases']} "
          f"probes={r['n_probes_excluded_or_segregated']} superseded_excluded={r['n_superseded_excluded']}")
    print(f"  size={mb:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
