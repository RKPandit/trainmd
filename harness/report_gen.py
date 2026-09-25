"""Deterministic, plan-driven report generator (STAGE3_PLAN §0.3).

`generate(records, meta) -> markdown` emits numbers + tables + NEUTRAL labels only — no
interpretation, no hardcoded operator/arm/model literals, no `date.today()`. The date comes from
the manifest. This is the ONLY place a sweep number is authored; the human `_analysis.md` narrative
cites these numbers and may not introduce one that is not here (checked by check_analysis_numbers.py).

`generate_from_cases(root, name)` is the results/ path; rebuild_tables.py calls `generate(records,
meta)` directly with release-sourced records so the same bytes come out with no registry access.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import yaml

from harness import sweep_stats as ss
from harness.anchors import normalize_anchor


def _f(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _ci(c, nd=3):
    if not c or c.get("point") is None:
        return "n/a"
    if c.get("zero_event_cp"):
        # Zero-event rate: exact two-sided 95% Clopper–Pearson over unique cases, never [0, 0]
        # (0 events is not 0 uncertainty). The † is explained by a legend under the table.
        return f"{c['point']:.{nd}f} [0, {_f(c.get('hi'), nd)}]†"
    text = f"{c['point']:.{nd}f} [{_f(c.get('lo'), nd)}, {_f(c.get('hi'), nd)}]"
    # 1–2 events: the percentile bootstrap understates uncertainty at this count (‡ legend).
    return text + "‡" if c.get("low_count") else text


def _has_flag(d, flag: str) -> bool:
    """True if any CI dict nested in `d` carries `flag` (drives the table legends)."""
    if isinstance(d, dict):
        if d.get(flag):
            return True
        return any(_has_flag(v, flag) for v in d.values())
    if isinstance(d, list):
        return any(_has_flag(v, flag) for v in d)
    return False


_HIDDEN_BAND_NOTE = (
    "_Hidden-band stratification (a case-quality label, never the stratification key) is not "
    "rendered in this report: the report reads band labels only from the release's per-case "
    "metadata, which holds the visible label alone. That table is written to the sweep's "
    "`_internal.md` report, generated from local cases. The fields a release does contain are "
    "listed in its `FIELD_INVENTORY.json` (per-trial `scores` may include the hidden band "
    "position)._")

_LEGEND_ZERO = ("† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval "
                "over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed "
                "events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). "
                "The point estimate is 0.")
_LEGEND_LOW = ("‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at "
               "this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 "
               "vs exact Clopper–Pearson 0.260). Read as indicative only.")


def _legends(tables) -> list:
    """Legend lines for the flags present in the tables actually rendered."""
    out = []
    if _has_flag(tables, "zero_event_cp"):
        out += ["", _LEGEND_ZERO]
    if _has_flag(tables, "low_count"):
        out += ["", _LEGEND_LOW]
    return out


def _band_table(title, breakdown):
    rows = ["", title, "",
            "| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |",
            "|---|---|---|---|---|"]
    for arm in sorted(breakdown):
        for band in ("in_band", "out_of_band"):
            b = breakdown[arm][band]
            if not b.get("available"):
                rows.append(f"| {arm} | {band} | _no controls in stratum_ | 0/0 | 0/0 |")
            else:
                rows.append(f"| {arm} | {band} | {_ci(b)} | {b['n_fp']}/{b['n_trials']} | "
                            f"{len(b['fp_cases'])}/{b['n_cases']} |")
    return rows


def generate(records: list[dict], meta: dict) -> str:
    """Build the deterministic markdown from attached records + report metadata.

    meta: {name, date, model, plan_arms, n_cells, excluded}. All content is derived from the
    records; meta only supplies provenance strings (never numbers computed from the data).
    """
    # The exploratory H8-defect arm never enters a primary table (pre-registered: not confirmatory,
    # never pooled); it is rendered in its own section below only when present, so reports without it
    # are byte-identical.
    exploratory = [r for r in records if r.get("_exploratory")]
    all_records = records
    records = [r for r in records if not r.get("_exploratory")]
    s = ss.compute_all(records)
    name = meta["name"]
    # Evidence scorer version actually present on this sweep's records (guard-checked against the
    # records/release by scripts/check_scorer_versions.py — a provenance fact about the instrument).
    _sv = collections.Counter((r.get("scores") or {}).get("evidence", {}).get("scorer_version")
                              for r in records if isinstance((r.get("scores") or {}).get("evidence"), dict))
    _sv.pop(None, None)
    scorer_version = _sv.most_common(1)[0][0] if _sv else "unknown"
    L: list[str] = []
    L += [f"# Sweep {name} — generated report", ""]
    L += ["> Machine-generated by `harness/report_gen.py` from records — do NOT hand-edit. "
          "Regenerate with `make report NAME=%s`. Interpretation lives in the `_analysis.md` narrative." % name, ""]
    L += [f"- date (from manifest): {meta.get('date','?')}",
          f"- model: {meta.get('model','?')}",
          f"- n_trials: {s['n_trials']}  ·  n_cases: {s['n_cases']}"
          + (f"  ·  n_cells(plan): {meta['n_cells']}" if meta.get('n_cells') is not None else ""),
          f"- faulty operators: {', '.join(s['operators_faulty']) or '(none)'}",
          f"- control operators: {', '.join(s['operators_control']) or '(none)'}",
          f"- arms present: {', '.join(s['arms'])}"
          + (f"  ·  arms (plan): {', '.join(meta['plan_arms'])}" if meta.get('plan_arms') else ""),
          f"- agents: {', '.join(s['agents'])}",
          f"- evidence scorer: {scorer_version}",
          f"- excluded: trusted={meta.get('excluded',{}).get('trusted',0)}, "
          f"superseded={meta.get('excluded',{}).get('superseded',0)}",
          f"- method: {s['method']}", ""]

    providers = ss.providers_present(records)
    if len(providers) > 1:
        # H7: split every table by provider with pooled alongside; list both models.
        L += [f"- providers: {', '.join(providers)}",
              f"- models: {', '.join(meta.get('models') or [])}", ""]
        L += ["## Pooled — all providers", ""] + _metric_body(s, records, meta)
        for p in providers:
            sub = [r for r in records if r.get("_provider") == p]
            L += [f"## Provider: {p}", ""] + _metric_body(ss.compute_all(sub), sub, meta)
    else:
        L += _metric_body(s, records, meta)
    # H8 renders only when the neutral+descriptive pair is present (self-guarded),
    # so frozen single-variant sweeps are byte-identical.
    L += _h8_tables(s)
    L += _prereg_part1_tables(records)
    if exploratory:
        L += _no_passback_tables(ss.exploratory_no_passback(all_records))
    return "\n".join(L) + "\n"


def _prereg_part1_tables(records) -> list[str]:
    """Stage 4 Part 1 pre-registered verdicts (harness/prereg_part1.py), rendered only for prompt-v2
    sweeps with both providers and all three v2 arms — so every earlier report is byte-identical."""
    from harness import prereg_part1 as pp
    if not ({pp.OFF, pp.STATS, pp.RULE} <= set(ss.arms_present(records))
            and {pp.REF_PROVIDER, pp.CMP_PROVIDER} <= set(ss.providers_present(records))):
        return []
    L = ["## Pre-registered verdicts (Stage 4 Part 1) — computed mechanically", ""]
    h9 = pp.h9_verdict(records)
    L += [f"### H9 — model dependence beyond leakage: **{h9['verdict']}**", "", f"- {h9['reason']}",
          f"- multiplicity: {h9['multiplicity']}", "",
          "| operator | Haiku off detect [95% CI] | status | Luna off detect | Δ Luna − Haiku [95% CI] |",
          "|---|---|---|---|---|"]
    for op, d in h9["operators"].items():
        if d["status"] == "missing":
            L.append(f"| {op} | — | missing | — | — |")
            continue
        r, dl = d["ref_detect"], d["delta"]
        L.append(f"| {op} | {_f(r['point'])} [{_f(r['lo'])}, {_f(r['hi'])}] | {d['status']} | "
                 f"{_f(d['cmp_detect'])} | {_f(dl['point'])} [{_f(dl['lo'])}, {_f(dl['hi'])}] |")
    ld = h9["leakage_delta"]
    if ld:
        L.append(f"| leakage (pooled) | — | reference | — | {_f(ld['point'])} [{_f(ld['lo'])}, {_f(ld['hi'])}] |")
    h10 = pp.h10_verdict(records)
    L += ["", "### H10 — bare statistics close most of the off→rule gap (f = (stats − off)/(rule − off))", "",
          f"- multiplicity: {h10['multiplicity']}", "",
          "| model | eligible operators (rule − off ≥ 0.30) | f [95% CI] | bootstrap p (f = 0.5) | verdict |",
          "|---|---|---|---|---|"]
    for m, d in h10["models"].items():
        if d["verdict"] == "UNTESTABLE":
            L.append(f"| {m} | none | — | — | UNTESTABLE |")
            continue
        L.append(f"| {m} | {', '.join(d['eligible'])} | {_f(d['f']['point'])} [{_f(d['f']['lo'])}, "
                 f"{_f(d['f']['hi'])}] | {_f(d['p_two_sided'], 4)} | {d['verdict']} |")
    bb = pp.band_benefit_descriptive(records)
    L += ["", "### Secondary (descriptive, no verdict) — band benefit by symptom type", "",
          "| model | operator | symptom | arm | off | arm | benefit | headroom-normalised |",
          "|---|---|---|---|---|---|---|---|"]
    for (prov, op, arm), d in bb.items():
        L.append(f"| {prov} | {op} | {d['symptom']} | {arm} | {_f(d['off'])} | {_f(d['arm'])} | "
                 f"{_f(d['benefit'])} | {_f(d['normalised'])} |")
    bv = pp.benign_verdict(records)
    L += ["", "### Benign controls — paired arm contrast (two-sided)", "",
          f"- multiplicity: {bv['multiplicity']}",
          "- per provider: " + ", ".join(f"{k} **{v}**" for k, v in bv["per_provider"].items()), "",
          "| contrast | pairs | FPR arm | FPR off | Δ [Newcombe 95% CI] | cells e/f/g/h | McNemar p | verdict |",
          "|---|---|---|---|---|---|---|---|"]
    for k, c in bv["contrasts"].items():
        if not c.get("available"):
            L.append(f"| {k} | 0 | — | — | — | — | — | unavailable |")
            continue
        L.append(f"| {k} | {c['n_pairs']} | {_f(c['fpr_arm'])} | {_f(c['fpr_off'])} | {_f(c['delta'])} "
                 f"[{_f(c['lo'])}, {_f(c['hi'])}] | {'/'.join(map(str, c['cells']))} | "
                 f"{_f(c['p_mcnemar'], 4)} | {c['verdict']} |")
    return L + [""]


def _no_passback_tables(x: dict) -> list[str]:
    L = ["## EXPLORATORY — reasoning pass-back OFF (the H8 adapter defect, re-created)", "",
         "> Not confirmatory; never pooled. Exists only to quantify the handicap H8's Luna ReAct ran with "
         "(LIMITATIONS L32): the same leakage cases × `off` × ReAct on the same model, with prior reasoning "
         "dropped between tool calls vs passed back (the Part 1 cell). Paired by case; case-clustered "
         "bootstrap CI of (pass-back ON − OFF).", ""]
    if not x.get("available"):
        return L + [f"_{x.get('reason', 'unavailable')}_", ""]
    L += ["| metric | pass-back ON | pass-back OFF | ON − OFF [95% CI] | n_cases |", "|---|---|---|---|---|"]
    for m in ("detection", "identification", "evidence_f1"):
        d = x[m]
        L.append(f"| {m} | {_f(d['on'])} | {_f(d['off'])} | {_f(d['diff']['point'])} "
                 f"[{_f(d['diff']['lo'])}, {_f(d['diff']['hi'])}] | {d['diff']['n_cases']} |")
    return L + [""]


def _h8_tables(s: dict) -> list:
    """H8 primary — PAIRED (strength×seed) neutral − descriptive identification Δ, per
    arm × provider — with the UNPAIRED contrast alongside, plus secondary detection/recovery."""
    hp = s.get("h8_identification_contrast_paired", {})
    hu = s.get("h8_identification_contrast", {})
    if not hu.get("available"):
        return []
    thr = hp if hp.get("available") else hu
    B = ["## H8 — neutral − descriptive identification (Δ), per arm × provider", "",
         f"Δ = neutral − descriptive identification. Pre-registered equivalence test on the "
         f"95% CI: confirming iff the WHOLE CI is inside ±{thr['confirming_bound']} "
         f"(lo > −{thr['confirming_bound']} and hi < +{thr['confirming_bound']}); refuting iff Δ < "
         f"−{thr['refuting_bound']} and the CI excludes 0 (hi < 0); otherwise inconclusive.", ""]

    if hp.get("available"):
        B += [
            "**PRIMARY analysis: PAIRED bootstrap.** The neutral and descriptive variants are the "
            "SAME injected fault built at matched (strength, seed) under two config-key namings, so "
            "the pre-registered design pairs them; the primary CI therefore resamples matched "
            "(strength, seed) PAIRS together, cancelling shared case difficulty. The **point estimate "
            "is identical** to the unpaired contrast (shown below) — only the interval differs. "
            "*Disclosure:* promoting the paired bootstrap to PRIMARY is an analysis change made AFTER "
            "seeing results (it moves the anthropic/numbers arm from inconclusive to confirming); it is "
            "justified by the matched-pair design, not by the outcome, and the unpaired contrast is "
            "retained in full immediately below so the effect of the switch is visible. "
            f"Method: {hp.get('method','')}.", "",
            "**Counting rule:** the headline tally is over the **6 provider-specific cells only** "
            "(2 providers × 3 arms). The `pooled` rows REUSE the same trials as the provider-specific "
            "rows, so they are a cross-provider **summary**, NOT independent confirmations, and are "
            "never added to the count. Provider-specific tally (paired): **4 of 6 confirming** "
            "(Haiku off/numbers/rule, Luna off), **2 inconclusive** (Luna numbers, Luna rule), "
            "**0 refuting**.", "",
            "| provider | arm | neutral id | descriptive id | Δ (95% CI, PAIRED) | n pairs | verdict |",
            "|---|---|---|---|---|---|---|"]
        for row in hp["rows"]:
            B.append(f"| {row['provider']} | {row['arm']} | {_f(row.get('neutral_id'))} | "
                     f"{_f(row.get('descriptive_id'))} | {_ci(row)} | "
                     f"{row.get('n_pairs')} | {row['verdict']} |")
        B += [""]
        B += ["### H8 — UNPAIRED contrast (shown alongside; case-clustered, not matched-pair)", ""]
    else:
        B += ["_(paired contrast unavailable — no strength×seed key; showing the unpaired contrast "
              "as primary.)_", ""]

    B += ["| provider | arm | neutral id | descriptive id | Δ (95% CI) | n cases neut/desc | verdict |",
          "|---|---|---|---|---|---|---|"]
    for row in hu["rows"]:
        B.append(f"| {row['provider']} | {row['arm']} | {_f(row.get('neutral_id'))} | "
                 f"{_f(row.get('descriptive_id'))} | {_ci(row)} | "
                 f"{row['n_cases_neutral']}/{row['n_cases_descriptive']} | {row['verdict']} |")
    B += [""]
    sec = s.get("h8_secondary_detection_recovery", {})
    if sec.get("available"):
        B += ["### H8 secondary — detection + semantic recovery per variant × arm × provider "
              "(pre-registered: expected UNCHANGED between variants)", "",
              "| provider | variant | arm | detection | recovery | n_trials | n_cases |",
              "|---|---|---|---|---|---|---|"]
        for row in sec["rows"]:
            B.append(f"| {row['provider']} | {row['variant']} | {row['arm']} | "
                     f"{_f(row.get('detection'))} | {_f(row.get('recovery'))} | "
                     f"{row['n_trials']} | {row['n_cases']} |")
        B += [""]
    return B


def _metric_body(s: dict, records: list, meta: dict) -> list:
    """The standard metric tables for one facet of records (all records, or one
    provider's). Extracted verbatim so the single-provider path stays byte-identical."""
    B: list = []
    # Detection by operator × arm
    arms = s["arms"]
    B += ["## Detection by operator × arm (point [95% case-clustered CI])", "",
          "| operator | " + " | ".join(arms) + " |",
          "|" + "---|" * (len(arms) + 1)]
    dba = s["detection_by_operator_arm"]
    for op in s["operators_faulty"]:
        row = [op] + [_ci(dba.get(op, {}).get(arm)) for arm in arms]
        B.append("| " + " | ".join(row) + " |")
    B += [""]

    # H1 anchor-off pooled gap
    g = s["h1_anchor_gap_pooled"]
    B += ["## H1 — anchor-off detection gap (negative − positive symptom), pooled", "",
          f"- gap: {_ci(g)}  (negative {_f(g.get('neg_rate'))} on {g.get('n_cases_neg')} cases − "
          f"positive {_f(g.get('pos_rate'))} on {g.get('n_cases_pos')} cases)",
          f"- positive-symptom operators: {', '.join(g.get('positive_ops') or []) or '(none)'}",
          f"- negative-symptom operators: {', '.join(g.get('negative_ops') or []) or '(none)'}",
          f"- nearest-σ matched mean paired gap: {_f(ss.h1_matched_sigma(records).get('mean_paired_gap'))} "
          "_(supplementary heuristic; does NOT resolve the operator-identity confound. The pairing "
          "uses each case's current `hidden_sigma_distance`, so it moves when a case is rebuilt — "
          "e.g. lr_warmup's bimodal rebuild changed which negative cases pair to each leakage case.)_", ""]

    # Ratio of the off→rule gap closed by the mid arm (the pre-registered, previously-uncomputed stat)
    r = s["ratio_gap_closed"]
    B += ["## Fraction of the off→rule detection gap closed by the numbers/stats arm", ""]
    if not r.get("available"):
        B += [f"_not available: {r.get('reason')}_", ""]
    else:
        B += [f"Method: {r['method']}. Arms: {r['low_arm']}→{r['mid_arm']}→{r['high_arm']}.", "",
              f"| operator | detect {r['low_arm']} | detect {r['mid_arm']} | detect {r['high_arm']} | gap | "
              f"fraction closed by {r['mid_arm']} (95% CI) |",
              "|---|---|---|---|---|---|"]
        for op in s["operators_faulty"]:
            d = r["operators"].get(op)
            if not d:
                continue
            fc = "degenerate (no gap)" if d["degenerate_gap"] else _ci(d["fraction_closed_by_mid"])
            B.append(f"| {op} | {_f(d.get('detect_'+r['low_arm']))} | {_f(d.get('detect_'+r['mid_arm']))} | "
                     f"{_f(d.get('detect_'+r['high_arm']))} | {_f(d.get('gap_low_high'))} | {fc} |")
        B += [""]

    # Control FPR — per arm + numbers−rule difference
    c = s["control_fpr"]
    B += ["## Control detection false-positive rate (per arm, case-clustered)", ""]
    if not c.get("available"):
        B += [f"_not available: {c.get('reason')}_", ""]
    else:
        B += ["| arm | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |",
              "|---|---|---|---|"]
        for arm in sorted(c["per_arm"]):
            a = c["per_arm"][arm]
            B.append(f"| {arm} | {_ci(a)} | {a['n_fp']}/{a['n_trials']} | {len(a['fp_cases'])}/{a['n_cases']} |")
        if c.get("by_benign_form"):
            B += ["", "### Control FP rate by benign edit form (STAGE4 4.0.6 — reported SEPARATELY)", "",
                  "| control type | arm | FP rate (95% CI) | n_fp / n_trials | unique FP cases / cases |",
                  "|---|---|---|---|---|"]
            for form, arms in c["by_benign_form"].items():
                for arm in sorted(arms):
                    a = arms[arm]
                    B.append(f"| {form} | {arm} | {_ci(a)} | {a['n_fp']}/{a['n_trials']} | "
                             f"{len(a['fp_cases'])}/{a['n_cases']} |")
        # §5.1: stratified breakdown (in-band vs out-of-band) when controls carry
        # band labels. Never present the pooled rate alone once we have this.
        if c.get("stratified"):
            # PRIMARY: visible band position — the key by mechanism (a control false
            # positive is a visible-metric event: the agent reads the visible metric,
            # compares to its band, and flags).
            B += _band_table("### Stratified by VISIBLE band position (§5.1 — the key, by mechanism)",
                             c["by_band"])
            # The HIDDEN-band breakdown (a case-quality label, never the key) is NOT rendered
            # here: this report reads band labels only from the release's per-case metadata
            # (visible label alone) and must reproduce from the release byte-for-byte. It goes
            # to the internal-only report instead (generate_internal). What a release contains
            # is recorded in its FIELD_INVENTORY.json — not described here by intent.
            B += ["", _HIDDEN_BAND_NOTE]
        for d in c.get("mid_minus_rule") or []:
            B += ["", f"- {d['mid_arm']} − {d['high_arm']} FP difference: {_ci(d)}"]
        # Legends only for tables actually rendered in THIS report (pooled + visible band).
        B += _legends({"per_arm": c.get("per_arm"), "by_band": c.get("by_band")})
        B += [""]

    # ReAct − static
    h6 = s["h6_react_minus_static"]
    B += ["## ReAct − static evidence F1 (faulty operators, pooled)", ""]
    B += ([f"- {_ci(h6)} (n_cases={h6.get('n_cases')})", ""] if h6.get("available")
          else [f"_not available: {h6.get('reason')}_", ""])

    # Recovery endpoints
    B += ["## Recovery — strict vs semantic, with id-gap CIs", "",
          "| operator | n_trials | n_cases | identification | strict recovery | semantic recovery | id − strict (95% CI) | id − semantic (95% CI) |",
          "|---|---|---|---|---|---|---|---|"]
    for op, e in s["recovery_endpoints"].items():
        B.append(f"| {op} | {e['n_trials']} | {e['n_cases']} | {_f(e['identification'],4)} | "
                 f"{_f(e['strict_recovery'],4)} | {_f(e['semantic_recovery'],4)} | "
                 f"{_ci(e['id_minus_strict'])} | {_ci(e['id_minus_semantic'])} |")
    B += [""]
    return B


def _meta_from_dir(d: Path, name: str) -> dict:
    """Provenance meta (date/model/plan-arms/n_cells) from a dir holding <name>_plan/manifest.yaml.

    Works for both `sweeps/` (results path) and a release dir (reviewer path) — same files, so the
    meta strings are identical and the two reports are byte-identical."""
    plan_p, man_p = d / f"{name}_plan.yaml", d / f"{name}_manifest.yaml"
    plan = yaml.safe_load(plan_p.read_text()) if plan_p.exists() else {}
    man = yaml.safe_load(man_p.read_text()) if man_p.exists() else {}
    header = plan.get("header", {})
    date = (man.get("timestamp_utc") or "").split("T")[0] or header.get("created_utc", "").split("T")[0]
    fl = header.get("factor_levels", {}) or {}
    arms = fl.get("anchors")
    # Plans before prompt v2 carry no prompt_major (→ v1). The arm keys include the version.
    major = fl.get("prompt_major", 1)
    plan_arms = (sorted({normalize_anchor(a, f"react-{major}") for a in arms}) if arms else None)
    models = (header.get("factor_levels", {}) or {}).get("models")
    return {"name": name, "date": date, "model": header.get("model"),
            "models": models, "plan_arms": plan_arms, "n_cells": header.get("n_cells")}


def generate_from_cases(root: Path, name: str, excluded: dict | None = None) -> str:
    records = ss.load_from_cases(root, name)
    meta = _meta_from_dir(root / "sweeps", name)
    meta["excluded"] = excluded or {"trusted": 0, "superseded": 0}
    return generate(records, meta)


def generate_internal(records: list[dict], meta: dict) -> str | None:
    """INTERNAL-ONLY report: the control-FPR breakdown by HIDDEN band position.

    Generated from local cases only (the hidden band label is read from the hidden card); the
    release-reproducible report does not render this table. Whether a release's per-trial scores
    also hold the hidden band position is recorded in its FIELD_INVENTORY.json (h8: yes —
    LIMITATIONS L31). Returns None when no record has a hidden band label (pre-§5.1 sweeps), so
    nothing is written for them.
    """
    if not records or not all(r.get("_band_hid") is not None
                              for r in records if r.get("_tier") == "control"):
        return None
    name = meta["name"]
    L = [f"# Sweep {name} — INTERNAL report (hidden-band stratification)", "",
         "> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` "
         "(`make report NAME=%s`); do NOT hand-edit. The hidden band label is a case-quality "
         "label — the agent never sees it and it is never the stratification key. This table is "
         "not part of the release-reproducible report (`sweep_%s_generated.md`), which reads band "
         "labels only from per-case metadata; the fields a release contains are listed in its "
         "`FIELD_INVENTORY.json`." % (name, name), ""]
    facets = [("Pooled — all providers", records)]
    providers = ss.providers_present(records)
    if len(providers) > 1:
        facets += [(f"Provider: {p}", [r for r in records if r.get("_provider") == p])
                   for p in providers]
    for title, recs in facets:
        c = ss.control_fpr(recs)
        L += [f"## {title}", ""]
        if not c.get("by_band_hidden"):
            L += ["_no hidden-band breakdown available_", ""]
            continue
        L += _band_table("### Control FP rate stratified by HIDDEN band position", c["by_band_hidden"])
        L += _legends(c["by_band_hidden"])
        L += [""]
    return "\n".join(L) + "\n"


def generate_internal_from_cases(root: Path, name: str) -> str | None:
    return generate_internal(ss.load_from_cases(root, name), _meta_from_dir(root / "sweeps", name))


def generate_from_release(release_dir: Path, name: str) -> str:
    """Reviewer path: regenerate the report from a sanitized release only (no cases/, no registry)."""
    release_dir = Path(release_dir)
    records = ss.load_from_release(release_dir)
    meta = _meta_from_dir(release_dir, name)
    rm = release_dir / "release_meta.json"
    meta["excluded"] = (json.loads(rm.read_text()).get("excluded")
                        if rm.exists() else {"trusted": 0, "superseded": 0})
    return generate(records, meta)
