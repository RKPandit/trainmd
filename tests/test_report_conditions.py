"""Report header + per-condition sections (author's request 2026-09-29, tooling post-lock): a provider carrying
several conditions (Stage 4 Part 2: Luna none + Luna medium under "openai") gets one section PER CONDITION, and the
header lists the actual conditions when the plan's default model is absent. Earlier sweeps (one condition per
provider, header model present) are byte-identical — also enforced by scripts/rebuild_tables.py in CI."""
from __future__ import annotations

from harness import report_gen


def _r(model, provider, **cond):
    return {"model": {"model_id": model}, "_provider": provider, "conditions": cond}


def test_condition_label():
    assert report_gen.condition_of(_r("gpt-5.6-luna", "openai", effort="none", strict_tools=True)) == \
        "gpt-5.6-luna (effort=none, strict)"
    assert report_gen.condition_of(_r("claude-sonnet-5", "anthropic", thinking="disabled")) == \
        "claude-sonnet-5 (thinking=disabled)"
    assert report_gen.condition_of(_r("claude-haiku-4-5-20251001", "anthropic")) == "claude-haiku-4-5-20251001"


def _generate(monkeypatch, records, model="claude-haiku-4-5-20251001"):
    monkeypatch.setattr(report_gen.ss, "compute_all", lambda recs: {
        "n_trials": len(recs), "n_cases": 0, "operators_faulty": [], "operators_control": [], "arms": [],
        "agents": [], "method": "m"})
    monkeypatch.setattr(report_gen, "_metric_body", lambda s, recs, meta: [f"(body n={len(recs)})", ""])
    for f in ("_h8_tables", "_valid_submission_tables", "_prereg_part1_tables", "_prereg_part2_tables"):
        monkeypatch.setattr(report_gen, f, lambda *a, **k: [])
    return report_gen.generate(records, {"name": "t", "model": model})


def test_multi_condition_sweep_gets_condition_sections_and_header(monkeypatch):
    recs = ([_r("gpt-5.6-luna", "openai", effort="none", strict_tools=True)] * 2
            + [_r("gpt-5.6-luna", "openai", effort="medium", strict_tools=True)] * 3
            + [_r("claude-sonnet-5", "anthropic", thinking="disabled")] * 4)
    md = _generate(monkeypatch, recs)
    assert "- model: claude-haiku" not in md
    assert "- conditions (3): claude-sonnet-5 (thinking=disabled); gpt-5.6-luna (effort=medium, strict); " \
           "gpt-5.6-luna (effort=none, strict)" in md
    assert "## Provider: openai" in md                                  # per-provider sections kept
    assert "## Condition: gpt-5.6-luna (effort=none, strict)\n\n(body n=2)" in md
    assert "## Condition: gpt-5.6-luna (effort=medium, strict)\n\n(body n=3)" in md


def test_one_condition_per_provider_is_unchanged(monkeypatch):
    recs = [_r("claude-haiku-4-5-20251001", "anthropic")] * 2 + [_r("gpt-5.6-luna", "openai")] * 2
    md = _generate(monkeypatch, recs)
    assert "- model: claude-haiku-4-5-20251001" in md and "## Condition:" not in md and "- conditions" not in md


def test_header_lists_the_condition_when_the_plan_model_is_absent(monkeypatch):
    md = _generate(monkeypatch, [_r("claude-sonnet-5", "anthropic", effort="xhigh")] * 2)
    assert "- conditions (1): claude-sonnet-5 (effort=xhigh)" in md and "## Condition:" not in md


def test_internal_report_splits_conditions_too(monkeypatch):
    recs = ([dict(_r("gpt-5.6-luna", "openai", effort="none", strict_tools=True), _tier="control", _band_hid="in_band")]
            + [dict(_r("gpt-5.6-luna", "openai", effort="medium", strict_tools=True), _tier="control", _band_hid="in_band")]
            + [dict(_r("claude-sonnet-5", "anthropic", thinking="disabled"), _tier="control", _band_hid="in_band")])
    monkeypatch.setattr(report_gen.ss, "control_fpr", lambda rs: {"by_band_hidden": {}})
    md = report_gen.generate_internal(recs, {"name": "t"})
    assert "## Provider: openai" in md and "## Condition: gpt-5.6-luna (effort=none, strict)" in md
