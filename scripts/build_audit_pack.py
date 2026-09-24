#!/usr/bin/env python3
"""Generate the BLIND human-audit sheet + its sealed key for a released sweep (STAGE4_PLAN 4.0.5).

    python scripts/build_audit_pack.py --sweep h8_xprovider        (or: make audit-sheet NAME=h8_xprovider)

Writes, LOCALLY ONLY (gitignored — the repository is public, and a committed key would let the
annotator un-blind the audit; never commit either file):

  audit/local/<sweep>/audit_sheet.xlsx   → the ONLY thing sent to the annotator
  audit/local/<sweep>/audit_key.csv      → kept by the study team; joined back by item_id

Input: ``results_release/<sweep>/`` only (public released records — no cases/, hidden/, results/).

Sheet (one row per item, SHUFFLED, ~60 rows, ~15% healthy controls):
  visible:  item_id | planted_fault | agent_said_wrong | agent_diagnosis | agent_explanation | agent_evidence
  blank:    named | located | evidence | explained   (dropdown Yes / Partial / No / N/A)  | notes
Key (never in the sheet): automated scores, provider / model, agent type, anchor arm, prompt
version, case_id, seed, run_id, operator.

Sampling (deterministic, seeded): one record per cell (dedup), completed with a submission. Faulty
items are stratified operator (descriptive / neutral leakage) × provider × arm; controls provider ×
arm; items spread evenly within each group, remainders assigned in a seeded order, then shuffled.
Reference-band values and seed numbers are redacted from agent text (the band hints at the prompt
condition; a seed, with the planted fault and cited keys, can identify the case in the public release).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.sweep_stats import load_from_release  # noqa: E402
from scripts.xlsx_min import write_xlsx  # noqa: E402

DEFAULT_SEED = 20260923
CONTROL = "control.healthy.v1"
RATINGS = ["Yes", "Partial", "No", "N/A"]
SHEET_COLS = ["item_id", "planted_fault", "agent_said_wrong", "agent_diagnosis", "agent_explanation",
              "agent_evidence", "named", "located", "evidence", "explained", "notes"]
RATING_COLS = ["named", "located", "evidence", "explained"]
KEY_COLS = ["item_id", "run_id", "case_id", "seed", "operator", "provider", "model", "agent_type",
            "anchor", "prompt_version", "auto_detection_correct", "auto_identification_correct",
            "auto_match_path", "auto_predicted_class", "auto_evidence_precision",
            "auto_evidence_recall", "auto_evidence_f1", "auto_evidence_matched"]
EXPLANATION_CHARS = 4000
SERIES_NAMES = {"metric_visible_val_acc": "validation accuracy", "train_loss": "training loss"}

PLANTED = {
    CONTROL: "None — this run is healthy",
    "silent.data_leakage.v1": "Data leakage — the config switches on an extra input feature derived "
                              "from the label, so validation accuracy overstates real performance.",
    "silent.data_leakage_neutral.v1": "Data leakage — the config switches on an extra input feature "
                                      "derived from the label, so validation accuracy overstates real "
                                      "performance.",
}


def planted_fault(operator_id: str) -> str:
    if operator_id not in PLANTED:
        raise SystemExit(f"build_audit_pack: no plain-language description for {operator_id!r}")
    return PLANTED[operator_id]


def band_values(card: dict) -> list[str]:
    ref = (card or {}).get("reference_visible_metric") or {}
    if not ref:
        return []
    m, s = ref["mean"], ref["std"]
    vals = (m, m - 2 * s, m + 2 * s)
    return [f"{v:.4f}" for v in vals] + [f"{100 * v:.2f}%" for v in vals]


_SEED_RE = re.compile(r"(\bseed\b\W{0,6})\d+", re.I)


def redact(text, values) -> str:
    """Remove what could un-blind an item: the reference-band values (hint at the prompt condition)
    and any seed number (seed + planted fault + cited keys can identify the case in the public release,
    hence its automated scores)."""
    text = "" if text is None else str(text)
    for v in values:
        text = text.replace(v, "[band value redacted]")
    return _SEED_RE.sub(lambda m: m.group(1) + "[redacted]", text)


def evidence_text(refs) -> str:
    """Evidence refs as readable text, e.g. "config setting data.opt_c; validation accuracy, epochs 0-19"."""
    out = []
    for r in refs or []:
        d = (r or {}).get("detail") or {}
        kind = (r or {}).get("kind")
        if kind == "config_key":
            out.append(f"config setting {d.get('key_path')}")
        elif kind == "metric_window":
            series = SERIES_NAMES.get(d.get("series"), d.get("series"))
            out.append(f"{series}, epochs {d.get('start_epoch')}-{d.get('end_epoch')}")
        elif kind in ("line_range", "code_span"):
            out.append(f"code {r.get('artifact_id')} lines {d.get('start_line')}-{d.get('end_line')}")
        else:
            out.append(json.dumps(r, sort_keys=True))
    return "; ".join(out) or "(none)"


def explanation(rec: dict) -> str:
    """The agent's own explanation: its submitted rationale, else its last non-empty message."""
    sub = rec.get("submission") or {}
    text = sub.get("rationale")
    if not text:
        msgs = [t.get("response_text") for t in rec.get("llm_transcript") or []
                if t.get("response_text") not in (None, "", "None")]
        text = msgs[-1] if msgs else ""
    text = str(text or "").strip() or "(no explanation given)"
    return text if len(text) <= EXPLANATION_CHARS else text[:EXPLANATION_CHARS] + " …[truncated]"


def _provider(r: dict):
    return (r.get("conditions") or {}).get("provider") or (r.get("model") or {}).get("provider")


def _spread(groups: dict, n: int, rng: random.Random) -> dict:
    keys = sorted(groups)
    base, extra = divmod(n, len(keys))
    order = keys[:]
    rng.shuffle(order)
    alloc = {k: base for k in keys}
    for k in order[:extra]:
        alloc[k] += 1
    return alloc


def sample(recs: list[dict], n: int, control_share: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    eligible = [r for r in recs if r.get("status") == "completed" and r.get("submission")]
    faulty, ctrl = {}, {}
    for r in eligible:
        if r["_op"] == CONTROL:
            ctrl.setdefault((_provider(r), r["_anchor"]), []).append(r)
        else:
            faulty.setdefault((r["_op"], _provider(r), r["_anchor"]), []).append(r)
    n_ctrl = round(n * control_share)
    picked = []
    for groups, k in ((faulty, n - n_ctrl), (ctrl, n_ctrl)):
        alloc = _spread(groups, k, rng)
        for key in sorted(groups):
            pool = sorted(groups[key], key=lambda r: r["run_id"])
            picked += rng.sample(pool, min(alloc[key], len(pool)))
    rng.shuffle(picked)
    return picked


def build(release_dir: Path, out_dir: Path, n: int = 60, control_share: float = 0.15,
          seed: int = DEFAULT_SEED) -> dict:
    recs = load_from_release(release_dir)
    picked = sample(recs, n, control_share, seed)
    cases = {p.stem: json.loads(p.read_text()) for p in (release_dir / "cases").glob("*.json")}
    rows, key = [], []
    for i, r in enumerate(picked, 1):
        item = f"A{i:02d}"
        meta = cases[r["case_id"]]
        vals = band_values(meta.get("public_card") or {})
        sub = r.get("submission") or {}
        diag = sub.get("diagnosis") or {}
        detected = diag.get("detected")
        rows.append([item, planted_fault(r["_op"]),
                     "yes" if detected is True else "no" if detected is False else "(not stated)",
                     redact(diag.get("operator_class"), vals) or "(none)",
                     redact(explanation(r), vals), evidence_text(sub.get("evidence_refs")),
                     "", "", "", "", ""])
        sc = r.get("scores") or {}
        ev, ident = sc.get("evidence") or {}, sc.get("identification") or {}
        c = r.get("conditions") or {}
        key.append({"item_id": item, "run_id": r["run_id"], "case_id": r["case_id"], "seed": meta.get("seed"),
                    "operator": r["_op"], "provider": _provider(r),
                    "model": (r.get("model") or {}).get("model_id"), "agent_type": c.get("agent_type"),
                    "anchor": r["_anchor"], "prompt_version": (r.get("prompt") or {}).get("prompt_version"),
                    "auto_detection_correct": (sc.get("detection") or {}).get("correct"),
                    "auto_identification_correct": ident.get("correct"),
                    "auto_match_path": ident.get("match_path"),
                    "auto_predicted_class": ident.get("predicted_class"),
                    "auto_evidence_precision": ev.get("precision"), "auto_evidence_recall": ev.get("recall"),
                    "auto_evidence_f1": ev.get("f1"), "auto_evidence_matched": ev.get("matched")})
    out_dir.mkdir(parents=True, exist_ok=True)
    write_xlsx(out_dir / "audit_sheet.xlsx", SHEET_COLS, rows,
               widths={"item_id": 8, "planted_fault": 40, "agent_said_wrong": 10, "agent_diagnosis": 28,
                       "agent_explanation": 70, "agent_evidence": 45, "notes": 40,
                       **{c: 11 for c in RATING_COLS}},
               dropdowns={c: RATINGS for c in RATING_COLS})
    with open(out_dir / "audit_key.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KEY_COLS)
        w.writeheader()
        w.writerows(key)
    return {"items": len(rows), "controls": sum(k["operator"] == CONTROL for k in key)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", default="h8_xprovider")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--control-share", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    out = a.project_root / "audit" / "local" / a.sweep
    res = build(a.project_root / "results_release" / a.sweep, out, a.n, a.control_share, a.seed)
    print(f"build_audit_pack: {res['items']} items ({res['controls']} healthy controls)\n"
          f"  sheet (send to the annotator): {out / 'audit_sheet.xlsx'}\n"
          f"  key   (keep; NEVER send/commit): {out / 'audit_key.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
