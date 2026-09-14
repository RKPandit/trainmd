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
_EXPECTED_TEMPLATE_HASH = {
    "react-1": "2d4e8b477ce26e1d4726038230922c28681da82c8cfeae1ce17750a3cc5d1595",
    "static-1": "2a5d9e4af4fe6cdc6054da1891a1af328dffb270beb826e2108c642a1e216a93",
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


# Three-arm anchor band text lives in the dynamic case_info, not the template, so
# it is pinned here against a FIXED synthetic card (one hash per arm). Bump the
# per-arm prompt_version suffix (react-1-<arm> / static-1-<arm>) AND these hashes
# together if an arm's wording legitimately changes.
_FIXED_CARD = {
    "reference_visible_metric": {"series": "metric_visible_val_acc", "mean": 0.85, "std": 0.001},
}
_EXPECTED_BAND_HASH = {
    "numbers": "def93784c4d35bb46d78911ceb6d5f4669834bb88ff2a8cd908c57c89fa2c2ca",
    "rule": "f4febaa362193ad9fb5002969d0a059a1d49f1869b6f90c536eb666cf3ab178f",
}


def test_anchor_arm_band_text_pinned_and_subset():
    from agents.llm_agent import _RULE_SENTENCE, reference_band_line

    off = reference_band_line(_FIXED_CARD, "off")
    numbers = reference_band_line(_FIXED_CARD, "numbers")
    rule = reference_band_line(_FIXED_CARD, "rule")

    # off arm: no band at all.
    assert off is None
    # rule = numbers + exactly one appended sentence → strict superset (prefix).
    assert rule == numbers + _RULE_SENTENCE
    assert rule.startswith(numbers) and numbers in rule
    # numbers arm carries the numerals but NONE of the rule wording.
    assert "0.8500" in numbers and "0.8480" in numbers and "0.8520" in numbers
    assert "anomalous" not in numbers and "above OR below" not in numbers
    # rule arm carries both.
    assert "anomalous" in rule and "above OR below" in rule
    # legacy "on" normalizes to "rule".
    assert reference_band_line(_FIXED_CARD, "on") == rule
    # pinned per-arm hashes (drift guard).
    assert _sha(numbers) == _EXPECTED_BAND_HASH["numbers"]
    assert _sha(rule) == _EXPECTED_BAND_HASH["rule"]


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
