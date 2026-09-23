"""Prompt-version drift guard + submit-schema parity (spec §8).

The version-stable template text for each agent is hashed and pinned here. If the
prompt text changes without bumping prompt_version (and this expected hash), the
test fails — so a paid sweep can never silently mix two prompt texts under one
version label. Also asserts both agents' submit schema is byte-identical.
"""
from __future__ import annotations

import hashlib

from agents import static_agent as sa
from agents.llm_agent import (
    HEALTHY_RUNS_TEXT,
    REACT_PROMPT_VERSION,
    SUBMIT_FORMAT_TEXT,
    SUBMIT_SCHEMA,
    _SYSTEM_PROMPT_TEMPLATE,
)
from agents.static_agent import STATIC_PROMPT_VERSION

# Expected version-stable template hashes. BUMP the version constant AND the hash
# together when the prompt text legitimately changes.
# v2 changed only the anchor-arm band text (dynamic case_info, pinned below), not the fixed
# template, so the template hashes carry over unchanged; v1 entries are kept as history.
_EXPECTED_TEMPLATE_HASH = {
    "react-1": "2d4e8b477ce26e1d4726038230922c28681da82c8cfeae1ce17750a3cc5d1595",
    "static-1": "2a5d9e4af4fe6cdc6054da1891a1af328dffb270beb826e2108c642a1e216a93",
    "react-2": "2d4e8b477ce26e1d4726038230922c28681da82c8cfeae1ce17750a3cc5d1595",
    "static-2": "2a5d9e4af4fe6cdc6054da1891a1af328dffb270beb826e2108c642a1e216a93",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_react_template_hash_matches_version():
    assert REACT_PROMPT_VERSION in _EXPECTED_TEMPLATE_HASH
    assert _sha(_SYSTEM_PROMPT_TEMPLATE) == _EXPECTED_TEMPLATE_HASH[REACT_PROMPT_VERSION], (
        "ReAct prompt text changed without bumping REACT_PROMPT_VERSION + its expected hash"
    )


def test_static_template_hash_matches_version():
    static_tpl = sa._STATIC_INTRO + "\n\n" + HEALTHY_RUNS_TEXT + "\n\n" + SUBMIT_FORMAT_TEXT
    assert STATIC_PROMPT_VERSION in _EXPECTED_TEMPLATE_HASH
    assert _sha(static_tpl) == _EXPECTED_TEMPLATE_HASH[STATIC_PROMPT_VERSION], (
        "Static prompt text changed without bumping STATIC_PROMPT_VERSION + its expected hash"
    )


# Anchor band text lives in the dynamic case_info, not the template, so it is pinned here
# against a FIXED synthetic card (one hash per arm, per prompt version). Bump the prompt
# major version (react-N / static-N) AND these hashes together if an arm's wording changes.
_FIXED_CARD = {
    "reference_visible_metric": {"series": "metric_visible_val_acc", "mean": 0.85, "std": 0.001,
                                 "n": 30},
}
_EXPECTED_BAND_HASH = {                 # prompt v2 (react-2 / static-2) — the runnable arms
    "stats": "d6415849c957b43f154bfc2c21bc8de17e49b2bded5a52c2bff9eb82d462d7f9",
    "rule": "4effe0940dd396d496a8db9867c037dfb4cbf7112dc558377624c7e1b6e8a762",
}
_EXPECTED_BAND_HASH_V1 = {              # prompt v1 (HISTORICAL: Sweep 1, Stage 2 gate, H8)
    "numbers": "def93784c4d35bb46d78911ceb6d5f4669834bb88ff2a8cd908c57c89fa2c2ca",
    "rule": "f4febaa362193ad9fb5002969d0a059a1d49f1869b6f90c536eb666cf3ab178f",
}
# Evaluative / threshold words the BARE stats arm must never carry (STAGE4 4.0.6): the arm is
# statistics only — no judgement, no interval, no bound.
_BANNED_IN_STATS = ("healthy", "achieve", "range", "normal", "expected", "typical", "anomal",
                    "should", "bound", "interval", "within", "outside", "±", "–")


def test_stats_arm_is_bare_statistics():
    from agents.llm_agent import reference_band_line
    stats = reference_band_line(_FIXED_CARD, "stats")
    low = stats.lower()
    for word in _BANNED_IN_STATS:
        assert word not in low, f"stats arm contains banned word {word!r}: {stats!r}"
    # mean, SD and n are all present; the ±2SD bounds (0.8480 / 0.8520) are NOT.
    assert "0.8500" in stats and "0.0010" in stats and "n=30" in stats
    assert "0.8480" not in stats and "0.8520" not in stats


def test_rule_is_stats_plus_one_sentence():
    from agents.llm_agent import _RULE_SENTENCE, reference_band_line
    off = reference_band_line(_FIXED_CARD, "off")
    stats = reference_band_line(_FIXED_CARD, "stats")
    rule = reference_band_line(_FIXED_CARD, "rule")
    assert off is None
    assert rule == stats + _RULE_SENTENCE and rule.startswith(stats)     # prefix, by construction
    # exactly ONE appended sentence, carrying the same ±2σ boundary as v1's band
    assert _RULE_SENTENCE.strip().count(".") == 1 and "2 SD" in _RULE_SENTENCE
    assert "above OR below" in rule and "anomalous" in rule and "anomalous" not in stats


def test_band_text_pinned_per_arm():
    from agents.llm_agent import reference_band_line
    for arm, h in _EXPECTED_BAND_HASH.items():
        assert _sha(reference_band_line(_FIXED_CARD, arm)) == h, f"v2 {arm} text drifted"


def test_v1_arms_cannot_be_run():
    import pytest

    from agents.llm_agent import LLMAgent, reference_band_line
    for legacy in ("on", "numbers"):
        with pytest.raises(ValueError):
            reference_band_line(_FIXED_CARD, legacy)
        with pytest.raises(ValueError):
            LLMAgent(object(), model_id="m", anchor=legacy)
        with pytest.raises(ValueError):
            sa.StaticContextAgent(object(), model_id="m", anchor=legacy)


def test_v1_band_text_still_reproduces_exactly():
    """What H8's agents saw stays reproducible byte-for-byte (historical, audit use only)."""
    from agents.llm_agent import reference_band_line_v1
    assert reference_band_line_v1(_FIXED_CARD, "off") is None
    for arm, h in _EXPECTED_BAND_HASH_V1.items():
        assert _sha(reference_band_line_v1(_FIXED_CARD, arm)) == h
    assert reference_band_line_v1(_FIXED_CARD, "on") == reference_band_line_v1(_FIXED_CARD, "rule")


def test_stats_arm_refuses_a_card_without_n():
    import pytest

    from agents.llm_agent import reference_band_line
    card = {"reference_visible_metric": {k: v for k, v in _FIXED_CARD["reference_visible_metric"].items()
                                         if k != "n"}}
    for arm in ("stats", "rule"):
        with pytest.raises(ValueError, match="'n'"):
            reference_band_line(card, arm)
    assert reference_band_line(card, "off") is None


def test_submit_schema_identical_across_agents():
    """Both agents expose the SAME submit schema (static imports it)."""
    from agents.static_agent import SUBMIT_SCHEMA as static_submit
    assert static_submit is SUBMIT_SCHEMA
    assert static_submit == SUBMIT_SCHEMA


def test_submit_schema_has_confidence_and_rationale():
    props = SUBMIT_SCHEMA["input_schema"]["properties"]
    assert "confidence" in props and props["confidence"]["type"] == "number"
    assert "rationale" in props and props["rationale"]["type"] == "string"
    # Optional — not required.
    assert "confidence" not in SUBMIT_SCHEMA["input_schema"]["required"]
