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

from harness.sweep_stats import sweep_is_frozen  # noqa: E402  (needs sys.path above)

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
    # §5.1 VISIBLE band label only — derivable from public data (the agent-visible metric vs the
    # public band). The HIDDEN band label is never exported (it encodes the hidden test metric).
    "band_position_visible": "band_position_visible",
}

_SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ANTHROPIC_API_KEY\s*[:=]\s*\S+", re.I)


def _sanitize_trial(rec: dict) -> dict:
    unknown = set(rec) - _TRIAL_ALLOW - _TRIAL_DROP
    if unknown:
        raise SystemExit(f"export: unclassified trial field(s) {sorted(unknown)} in run "
                         f"{rec.get('run_id')} — add to _TRIAL_ALLOW or _TRIAL_DROP (never leak silently)")
    # Iterate the allowlist in SORTED order: `_TRIAL_ALLOW` is a set, and set iteration order
    # follows per-process string-hash randomization, so iterating it directly made the released
    # JSON key order (and therefore every trial file's bytes) change from run to run.
    out = {k: rec[k] for k in sorted(_TRIAL_ALLOW) if k in rec}
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
    agent-visible by design. accepted_classes/core_tokens are not scanned: they are generic words, and
    `accepted_classes` IS exported — inside each trial's `scores.identification`, as it has been in every
    release since §0.3. That is deliberate (a reviewer needs it to re-derive identification scores; it is
    per-operator and public in operator source; released cases are burned — LIMITATIONS L31). The earlier
    "never exported" wording here was a documentation error: it never matched the artifact.
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


# ---- provenance-scoped exemptions from the hidden-value wall ------------------------------------
# A formatted hidden value can collide with an unrelated PUBLIC number. Accuracies are quantized on
# a shared grid (n_val == n_hidden == 6783 rows, so both metrics are multiples of 1/6783 — only ~136
# distinct 6-dp values in 0.84–0.86), and a trial's cost can equal a 6-dp hidden std. A match is
# exempt ONLY when it sits in a field whose value derives entirely from PUBLIC inputs, identified
# by PROVENANCE (where the value came from), never by the value itself. Every other occurrence —
# including model free text, unless it echoes a value already public in the SAME record — still
# blocks. Fail-closed: an unrecognised field is never exempt.
_VISIBLE_SERIES = frozenset({"metric_visible_val_acc", "train_loss", "val_loss", "lr"})
_USAGE_PUBLIC = frozenset({"input_tokens", "output_tokens", "cached_tokens", "total_tokens",
                           "estimated_cost_usd"})      # tokens, and cost = tokens × published price
_INDEX_PUBLIC_COLUMNS = frozenset({"cost_usd"})
_PROGRESS_PUBLIC = frozenset({"cost_usd"})


def _leaves(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, path + (i,))
    else:
        yield path, x


def _render(v) -> str:
    return v if isinstance(v, str) else json.dumps(v)


def _trial_path_is_public(rec: dict, path: tuple) -> bool:
    """True iff `path` (into a sanitized trial record) is a public-derived value:
    a usage token count / cost, or a value `query_metrics` returned for an agent-VISIBLE series."""
    if len(path) == 2 and path[0] == "usage" and path[1] in _USAGE_PUBLIC:
        return True
    if (len(path) == 6 and path[0] == "tool_transcript" and isinstance(path[1], int)
            and path[2] == "result" and path[3] == "values" and isinstance(path[4], int)
            and path[5] == "value"):
        entry = rec["tool_transcript"][path[1]]
        return (entry.get("tool_name") == "query_metrics"
                and (entry.get("result") or {}).get("series") in _VISIBLE_SERIES)
    return False


def _public_occurrences(rel: Path, text: str, needles) -> dict[str, int]:
    """How many occurrences of each needle in this released file sit in public-derived fields."""
    counts = {n: 0 for n in needles}

    def add(value):
        rendered = _render(value)
        for n in needles:
            counts[n] += rendered.count(n)

    if rel.suffix == ".json" and rel.parent.name in ("trials", "probes"):
        rec = json.loads(text)
        public_rendered, free_text = [], []
        for path, v in _leaves(rec):
            if _trial_path_is_public(rec, path):
                add(v)
                public_rendered.append(_render(v))
            elif isinstance(v, str):
                free_text.append(v)
        # IN-RECORD ECHO (an information argument, not a probability one): when the identical value
        # already sits in a public-derived field of THIS record, repeating it in free text discloses
        # nothing the release does not already disclose — whether it coincides with a hidden value
        # is then irrelevant. Strictly per-record (never global), string leaves only; numeric fields
        # and keys outside the allowlist still block.
        for n in needles:
            if any(n in pr for pr in public_rendered):
                counts[n] += sum(ft.count(n) for ft in free_text)
    elif rel.name == "index.csv":
        for row in csv.DictReader(text.splitlines()):
            for col in _INDEX_PUBLIC_COLUMNS:
                add(row.get(col) or "")
    elif rel.name.endswith("progress.jsonl"):
        for line in text.splitlines():
            if not line.strip():
                continue
            for path, v in _leaves(json.loads(line)):
                if len(path) == 1 and path[0] in _PROGRESS_PUBLIC:
                    add(v)
    return counts


def _scan_release(root: Path, out_dir: Path, case_ids: set[str]) -> list[str]:
    """PER-CASE scan (like W4): a case's files vs its OWN hidden values, so a visible metric value in
    one case cannot false-positive on another case's hidden value. Sweep-level files (plan/manifest/
    index/progress) are scanned against the union. An occurrence is exempt only if it lies in a
    public-derived field (see _public_occurrences); if ANY occurrence of a needle in a file lies
    elsewhere — a free-text field, a key, an unrecognised field — the export fails."""
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
        if _SECRET_RE.search(text):
            hits.append(f"{rel}: matches a secret pattern")
        present = {n: lab for n, lab in needles.items() if n and n in text}
        if not present:
            continue
        public = _public_occurrences(rel, text, present)
        for needle, label in present.items():
            if text.count(needle) > public[needle]:
                hits.append(f"{rel}: leaks {label} ({needle!r}) outside any public-derived field")
    return hits


def _frozen_build_id_mismatches(root: Path, name: str) -> list[str]:
    """For a FROZEN sweep: records whose sealed `environment.case_build_id` differs from the CURRENT
    card's `case_build_id`. A mismatch means the case_id was rebuilt (possibly as a different operator)
    after the sweep ran, so today's card would mislabel that case's released metadata."""
    bad = []
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        if (rec.get("conditions") or {}).get("sweep_name") != name:
            continue
        cid = rec.get("case_id")
        hp = root / "cases" / str(cid) / "hidden" / "card.hidden.yaml"
        card_bid = (yaml.safe_load(hp.read_text()) or {}).get("case_build_id") if hp.exists() else None
        rec_bid = (rec.get("environment") or {}).get("case_build_id")
        if not rec_bid or rec_bid != card_bid:
            bad.append(f"{cid} run {rec.get('run_id')}: record build {str(rec_bid)[:12]} != card {str(card_bid)[:12]}")
    return bad


def export(root: Path, name: str, include_probes: bool = False) -> dict:
    root = Path(root)
    out_dir = root / "results_release" / name
    # GUARD (before anything is deleted): a FROZEN sweep's per-case metadata is regenerated from
    # today's cards only if every record's sealed build_id still matches its card. Re-exporting after
    # a rebuild silently mislabels operators (found 2026-09-23: stage2gate case_0002 label_corruption →
    # shape_mismatch). Refuse, and leave the committed release untouched.
    if sweep_is_frozen(root, name):
        bad = _frozen_build_id_mismatches(root, name)
        if bad:
            raise SystemExit(
                f"export: refusing to regenerate FROZEN sweep {name!r}: {len(bad)} record(s) were built "
                f"on a case card that has since been rebuilt, so today's per-case metadata would mislabel "
                f"them (the committed release is left untouched). e.g.\n  " + "\n  ".join(bad[:5]))
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

    frozen = sweep_is_frozen(root, name)
    case_ids: set[str] = set()
    index_rows, n_trials, n_probes, n_excluded = [], 0, 0, 0
    for f in sorted((root / "results").glob("*/trials/*.yaml")):
        rec = yaml.safe_load(f.read_text())
        if (rec.get("conditions") or {}).get("sweep_name") != name:
            continue
        # A frozen historical sweep keeps its (legitimately all-superseded) records — see
        # sweep_is_frozen; re-exporting it must reproduce the same release, not an empty one.
        if rec.get("card_superseded") and not frozen:
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
         "frozen": frozen,
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
