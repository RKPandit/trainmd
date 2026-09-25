#!/usr/bin/env python3
"""Annotator-vs-scorer agreement for the blind human audit (STAGE4_PLAN 4.0.5).

    python scripts/audit_agreement.py --sheet <returned audit_sheet.xlsx (or .csv)> \
        --key audit/local/h8_xprovider/audit_key.csv [--out <report.md>]

Joins the annotator's returned sheet to the sealed key on item_id. Mapping DECLARED here, before any
annotation is seen (ratings: Yes / Partial / No / N/A):

  named     vs  identification.correct                 (the scorer's identification)
  located   vs  evidence matched >= 1                  (≥ 1 cited ref hits a ground-truth evidence item)
  evidence  vs  evidence F1 >= 0.5                     (the cited evidence substantially matches)
  explained —   no automated counterpart: reported as HUMAN-ONLY (distribution by stratum)

For each mapped rating: PRIMARY counts Yes as positive (Partial and No negative); SENSITIVITY counts
Yes or Partial as positive; N/A rows are excluded. Reported: n, raw agreement, Cohen's κ with a seeded
item-bootstrap 95% CI, the 2×2 table, agreement per stratum (operator × provider × arm), and EVERY
disagreement (item, stratum, scorer value, annotator rating, predicted class, notes). evidence is also
cross-tabulated against F1 bins, and the sample-level neutral − descriptive identification gap is
shown under scorer vs annotator (descriptive for this sample; not a re-estimate of H8).
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATINGS = {"YES": "Yes", "PARTIAL": "Partial", "NO": "No", "N/A": "N/A", "NA": "N/A"}
RATED = ("named", "located", "evidence", "explained")
N_BOOT, SEED = 2000, 20260923
CONTROL = "control.healthy.v1"


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def read_sheet(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(open(path, newline="")))
    from scripts.xlsx_min import read_xlsx
    return read_xlsx(path)


def load(sheet: Path, key: Path) -> list[dict]:
    ann = {r["item_id"]: r for r in read_sheet(sheet)}
    rows = []
    for k in csv.DictReader(open(key, newline="")):
        a = ann.get(k["item_id"])
        if a is None:
            raise SystemExit(f"audit_agreement: item {k['item_id']} missing from the returned sheet")
        rec = {**k, "notes": a.get("notes", "")}
        for col in RATED:
            v = RATINGS.get(str(a.get(col, "")).strip().upper())
            if v is None:
                raise SystemExit(f"audit_agreement: item {k['item_id']} {col}={a.get(col)!r} is not one of "
                                 "Yes / Partial / No / N/A")
            rec[col] = v
        rows.append(rec)
    return rows


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided Clopper-Pearson interval for k successes in n — never degenerate: k = n gives
    [(alpha/2)^(1/n), 1] (60/60 → [0.940, 1]), k = 0 gives [0, 1-(alpha/2)^(1/n)] (correction #6's
    rule). Solved by bisection on the exact binomial tails (no SciPy)."""
    from math import comb
    if n == 0:
        return (0.0, 1.0)

    def upper_tail(p):   # P(X >= k), increasing in p
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))

    def lower_tail(p):   # P(X <= k), decreasing in p
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))

    def solve(f, target, increasing):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    a = alpha / 2
    lower = 0.0 if k == 0 else solve(upper_tail, a, increasing=True)
    upper = 1.0 if k == n else solve(lower_tail, a, increasing=False)
    return (lower, upper)


def kappa_ci(pairs, n_boot=N_BOOT, seed=SEED):
    if not pairs:
        return None, None
    rng = random.Random(seed)
    ks = sorted(k for k in (kappa([pairs[rng.randrange(len(pairs))] for _ in pairs]) for _ in range(n_boot))
                if k is not None)
    if not ks:
        return None, None
    lo, hi = ks[int(0.025 * len(ks))], ks[min(len(ks) - 1, int(0.975 * len(ks)))]
    if lo == hi:
        # Every resample gives the same κ (e.g. perfect agreement): the bootstrap cannot express
        # uncertainty here — report it as DEGENERATE, never as a zero-width [κ, κ] interval.
        return "degenerate", "degenerate"
    return lo, hi


SCORER = {
    "named": ("identification.correct", lambda r: _truthy(r["auto_identification_correct"])),
    "located": ("evidence matched ≥ 1", lambda r: _num(r["auto_evidence_matched"]) >= 1),
    "evidence": ("evidence F1 ≥ 0.5", lambda r: _num(r["auto_evidence_f1"]) >= 0.5),
}


def dimension(rows, col, sensitivity=False) -> dict:
    label, scorer = SCORER[col]
    positive = ("Yes", "Partial") if sensitivity else ("Yes",)
    sel = [r for r in rows if r[col] != "N/A"]
    pairs = [(scorer(r), r[col] in positive) for r in sel]
    lo, hi = kappa_ci(pairs)
    strata = defaultdict(list)
    for r, (s, a) in zip(sel, pairs):
        strata[(r["operator"], r["provider"], r["anchor"])].append(s == a)
    agree = sum(s == a for s, a in pairs)
    return {"col": col, "scorer": label, "rule": "Yes or Partial" if sensitivity else "Yes",
            "n": len(pairs), "excluded_na": len(rows) - len(sel), "agree": agree,
            "agreement": agree / len(pairs) if pairs else None,
            "agreement_ci": clopper_pearson(agree, len(pairs)) if pairs else (None, None),
            "kappa": kappa(pairs), "kappa_ci": (lo, hi),
            "table": {(s, a): sum(1 for p in pairs if p == (s, a)) for s in (True, False) for a in (True, False)},
            "by_stratum": {k: (sum(v), len(v)) for k, v in sorted(strata.items())},
            "disagreements": [{**r, "scorer_value": s} for r, (s, a) in zip(sel, pairs) if s != a]}


def analyze(rows) -> dict:
    dims = []
    for col in ("named", "located", "evidence"):
        dims += [dimension(rows, col), dimension(rows, col, sensitivity=True)]
    explained = defaultdict(Counter)
    for r in rows:
        explained["all"][r["explained"]] += 1
        explained[(r["operator"], r["provider"], r["anchor"])][r["explained"]] += 1
    bins = defaultdict(Counter)
    for r in rows:
        f1 = _num(r["auto_evidence_f1"])
        bins["F1 = 0" if f1 == 0 else ("0 < F1 < 0.5" if f1 < 0.5 else "F1 ≥ 0.5")][r["evidence"]] += 1
    corr = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r["operator"] != CONTROL:
            c = corr[(r["operator"], r["provider"])]
            c[0] += 1
            c[1] += SCORER["named"][1](r)
            c[2] += r["named"] == "Yes"
    return {"dims": dims, "explained": explained, "evidence_bins": bins, "corrections": dict(corr)}


def _f(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def render(res, n_items) -> str:
    L = ["# Blind human audit — annotator vs automated scorer (STAGE4_PLAN 4.0.5)", "",
         f"> Generated by `scripts/audit_agreement.py` from the returned sheet + sealed key ({n_items} items). "
         "Mapping declared in the script before annotation. Do NOT hand-edit.", ""]
    for d in res["dims"]:
        lo, hi = d["kappa_ci"]
        alo, ahi = d["agreement_ci"]
        t = d["table"]
        kci = ("bootstrap CI degenerate — every resample agrees; use the exact agreement interval"
               if lo == "degenerate" else f"95% item-bootstrap CI [{_f(lo)}, {_f(hi)}]")
        L += [f"## {d['col']} (annotator {d['rule']}) vs {d['scorer']}", "",
              f"- n = {d['n']} (N/A excluded: {d['excluded_na']}); raw agreement = {d['agree']}/{d['n']} = "
              f"{_f(d['agreement'])} (exact 95% Clopper-Pearson [{_f(alo)}, {_f(ahi)}]); "
              f"Cohen's κ = {_f(d['kappa'])} ({kci})", "",
              "| | annotator: positive | annotator: negative |", "|---|---|---|",
              f"| scorer: positive | {t[(True, True)]} | {t[(True, False)]} |",
              f"| scorer: negative | {t[(False, True)]} | {t[(False, False)]} |", "",
              "| stratum (operator · provider · arm) | agree / n |", "|---|---|"]
        L += [f"| {o} · {p} · {a} | {k}/{n} |" for (o, p, a), (k, n) in d["by_stratum"].items()]
        L += ["", f"**Disagreements ({len(d['disagreements'])}):**", ""]
        if d["disagreements"]:
            L += ["| item | stratum | scorer | annotator | predicted class | notes |", "|---|---|---|---|---|---|"]
            L += [f"| {x['item_id']} | {x['operator']} · {x['provider']} · {x['anchor']} | {x['scorer_value']} | "
                  f"{x[d['col']]} | `{x['auto_predicted_class']}` | {x.get('notes', '')} |"
                  for x in d["disagreements"]]
        L.append("")
    L += ["## explained — HUMAN-ONLY (no automated counterpart)", "",
          "| stratum | Yes | Partial | No | N/A |", "|---|---|---|---|---|"]
    for k, c in sorted(res["explained"].items(), key=lambda kv: (kv[0] != "all", str(kv[0]))):
        name = k if k == "all" else " · ".join(k)
        L.append(f"| {name} | {c['Yes']} | {c['Partial']} | {c['No']} | {c['N/A']} |")
    L += ["", "## evidence rating vs evidence F1 bins", "", "| F1 | Yes | Partial | No | N/A |", "|---|---|---|---|---|"]
    for b in ("F1 = 0", "0 < F1 < 0.5", "F1 ≥ 0.5"):
        c = res["evidence_bins"].get(b, Counter())
        L.append(f"| {b} | {c['Yes']} | {c['Partial']} | {c['No']} | {c['N/A']} |")
    L += ["", "## How the corrections move this sample's identification rates (descriptive, sample only)", "",
          "| operator | provider | n | scorer id rate | annotator named=Yes rate | change |", "|---|---|---|---|---|---|"]
    by_prov = defaultdict(dict)
    for (op, prov), (n, s, a) in sorted(res["corrections"].items()):
        L.append(f"| {op} | {prov} | {n} | {_f(s / n)} | {_f(a / n)} | {_f((a - s) / n)} |")
        by_prov[prov][op] = (s / n, a / n)
    L += ["", "Neutral − descriptive identification gap in this sample (the H8 contrast; NOT a re-estimate):", ""]
    for prov, d in sorted(by_prov.items()):
        neu, des = d.get("silent.data_leakage_neutral.v1"), d.get("silent.data_leakage.v1")
        if neu and des:
            L.append(f"- {prov}: scorer {_f(neu[0] - des[0])}, annotator {_f(neu[1] - des[1])}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", type=Path, required=True, help="the RETURNED audit_sheet.xlsx (or a .csv export)")
    ap.add_argument("--key", type=Path, required=True, help="audit/local/<sweep>/audit_key.csv")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    rows = load(a.sheet, a.key)
    md = render(analyze(rows), len(rows))
    if a.out:
        a.out.write_text(md)
        print(f"wrote {a.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
