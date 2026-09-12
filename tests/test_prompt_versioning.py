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
