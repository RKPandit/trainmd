"""The H8-section tally is COMPUTED from the rows for any sweep; H8's published wording is scoped to the
H8 sweep and asserted against the computed tally (it can never drift from the data)."""
from __future__ import annotations

import pytest

from harness import report_gen as rg


def _row(prov, arm, verdict, n=0.5, d=0.5):
    return {"provider": prov, "arm": arm, "verdict": verdict, "neutral_id": n, "descriptive_id": d,
            "lo": -0.1, "hi": 0.1, "point": 0.0, "n_pairs": 18}


C, I, R = "confirming (no substantial gap)", "inconclusive", "refuting (substantial gap)"
PART1_LIKE = [_row("pooled", "off.v2", C),
              _row("anthropic", "off.v2", C, 0.014, 0.0), _row("anthropic", "rule.v2", C),
              _row("anthropic", "stats.v2", I), _row("openai", "off.v2", I, 0.764, 0.861),
              _row("openai", "rule.v2", C), _row("openai", "stats.v2", I)]
LABELS = {"anthropic": "Haiku", "openai": "Luna"}


def test_tally_counts_provider_cells_only_and_applies_the_floor_clause():
    t = rg.h8_tally(PART1_LIKE, LABELS)
    assert t["n"] == 6 and t["providers"] == 2 and t["arms"] == 3
    assert t["confirming"] == ["Haiku off", "Haiku rule", "Luna rule"]
    assert t["inconclusive"] == ["Haiku stats", "Luna off", "Luna stats"] and t["refuting"] == []
    assert t["floored"] == ["Haiku off"] and (t["confirming_excl_floor"], t["n_excl_floor"]) == (2, 5)
    assert t["floor_invariant"] == (0.014, 0.861)       # Haiku-off floors from 0.014; Luna-off only at 0.861


def test_rendered_section_uses_the_computed_tally_for_a_non_h8_sweep():
    s = {"h8_identification_contrast_paired": {"available": True, "rows": PART1_LIKE, "method": "m",
                                               "confirming_bound": 0.15, "refuting_bound": 0.3},
         "h8_identification_contrast": {"available": True, "rows": [], "confirming_bound": 0.15,
                                        "refuting_bound": 0.3}}
    recs = [{"_provider": "anthropic", "model": {"model_id": "claude-haiku-4-5-20251001"}},
            {"_provider": "openai", "model": {"model_id": "gpt-5.6-luna"}}]
    md = "\n".join(rg._h8_tables(s, recs, "stage4_part1"))
    assert "**3 of 6 confirming** (Haiku off, Haiku rule, Luna rule)" in md
    assert "**3 inconclusive** (Haiku stats, Luna off, Luna stats)" in md
    assert "Excluding the floored cell(s) — Haiku off — **2 of 5 confirming**" in md
    assert "any threshold from 0.014 up to (not including) 0.861" in md
    assert "numbers" not in md and "4 of 6" not in md
    with pytest.raises(AssertionError):                     # H8's published prose must match its data
        rg._h8_tables(s, recs, "h8_xprovider")


def test_model_labels():
    assert rg._model_label("claude-haiku-4-5-20251001", "anthropic") == "Haiku"
    assert rg._model_label("gpt-5.6-luna", "openai") == "Luna"
    assert rg._model_label("gpt-6-sol", "openai") == "Sol"
    assert rg._model_label(None, "openai") == "openai"


def test_valid_submission_view_separates_format_from_diagnosis():
    from harness import sweep_stats as ss

    def rec(detected, correct, missing=(), sub=True):
        r = {"_tier": "dynamics", "_provider": "openai", "_agent": "static", "_anchor": "off.v2",
             "compliance": {"missing_fields": list(missing), "ignored_fields": []},
             "scores": {"detection": {"correct": correct}, "identification": {"correct": correct}}}
        r["submission"] = {"diagnosis": {"detected": detected}} if sub else None
        return r
    recs = [rec(True, True), rec(True, True), rec(False, False),
            rec(None, False, missing=("diagnosis", "diagnosis.detected")), rec(None, False, sub=False)]
    (row,) = ss.valid_submission_view(recs)
    assert (row["n"], row["n_empty"], row["n_valid"]) == (5, 2, 3)
    assert row["det_e2e"] == 2 / 5 and row["det_valid"] == 2 / 3
    assert ss.valid_submission_view([{k: v for k, v in r.items() if k != "compliance"} for r in recs]) == []
