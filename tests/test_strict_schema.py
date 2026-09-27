"""Strict OpenAI tool schemas (Stage 4 Part 2 DECISION 2026-09-27; harness/llm/strict_schema.py).

Proves: every tool's strict schema satisfies OpenAI strict mode's rules (closed objects, all properties
required, optional → nullable, no free-form objects, supported keywords only); a normal submission — and a
healthy no-repair one, an "unset" repair, and a sparse non-submit call — round-trips strict shape → canonical
shape unchanged and validates against the strict schema; the parse path normalizes; Anthropic is untouched;
the planner marks only OpenAI cells.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from agents.llm_agent import TOOLS_SCHEMA
from harness.llm.openai_client import parse_responses, to_responses_tools
from harness.llm.strict_schema import from_strict_args, to_strict, to_strict_args, to_strict_tool_schema

ALLOWED_KEYS = {"type", "properties", "required", "additionalProperties", "items", "description", "enum", "anyOf"}
ALLOWED_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}


def _strict_violations(schema, path="$"):
    out = []
    extra = set(schema) - ALLOWED_KEYS
    if extra:
        out.append(f"{path}: unsupported keywords {sorted(extra)}")
    if "anyOf" in schema:
        for i, b in enumerate(schema["anyOf"]):
            out += _strict_violations(b, f"{path}.anyOf[{i}]")
        return out
    types = schema.get("type")
    types = types if isinstance(types, list) else [types]
    if not set(types) <= ALLOWED_TYPES:
        out.append(f"{path}: bad type {types}")
    if "object" in types:
        props = schema.get("properties")
        if not props:
            out.append(f"{path}: free-form object")
        else:
            if schema.get("additionalProperties") is not False:
                out.append(f"{path}: additionalProperties must be false")
            if sorted(schema.get("required") or []) != sorted(props):
                out.append(f"{path}: every property must be required")
            for k, v in props.items():
                out += _strict_violations(v, f"{path}.{k}")
    if "array" in types:
        if not isinstance(schema.get("items"), dict):
            out.append(f"{path}: array without items")
        else:
            out += _strict_violations(schema["items"], f"{path}[]")
    return out


def _valid(inst, schema) -> bool:
    """A minimal JSON-schema instance check over the subset strict schemas use."""
    if "anyOf" in schema:
        return any(_valid(inst, b) for b in schema["anyOf"])
    types = schema.get("type")
    types = types if isinstance(types, list) else [types]
    py = {"string": str, "boolean": bool, "null": type(None), "object": dict, "array": list}
    ok = False
    for t in types:
        if t == "integer":
            ok |= isinstance(inst, int) and not isinstance(inst, bool)
        elif t == "number":
            ok |= isinstance(inst, (int, float)) and not isinstance(inst, bool)
        else:
            ok |= isinstance(inst, py[t])
    if not ok:
        return False
    if "enum" in schema and inst not in schema["enum"]:
        return False
    if isinstance(inst, dict):
        props = schema.get("properties") or {}
        if set(inst) - set(props) or set(schema.get("required") or []) - set(inst):
            return False
        return all(_valid(inst[k], props[k]) for k in inst)
    if isinstance(inst, list):
        return all(_valid(v, schema["items"]) for v in inst)
    return True


@pytest.mark.parametrize("tool", TOOLS_SCHEMA, ids=lambda t: t["name"])
def test_every_strict_schema_satisfies_strict_mode(tool):
    s = to_strict(tool)
    assert _strict_violations(s) == []
    # originally-optional top-level fields are now required AND accept null
    for k, v in tool["input_schema"]["properties"].items():
        if k not in (tool["input_schema"].get("required") or []):
            assert _valid(None, s["properties"][k]), (tool["name"], k)


FULL_SUBMIT = {
    "diagnosis": {"detected": True, "operator_class": "label_leakage_via_aux_feature"},
    "evidence_refs": [
        {"kind": "config_key", "artifact_id": "config.yaml", "detail": {"key_path": "data.include_aux_feature"}},
        {"kind": "metric_window", "artifact_id": "metrics.jsonl",
         "detail": {"series": "metric_visible_val_acc", "start_epoch": 0, "end_epoch": 19}},
        {"kind": "code_span", "artifact_id": "train.py", "detail": {"start_line": 189, "end_line": 199}},
    ],
    "repair_spec": {"repair_type": "config_patch", "patches": {"data.include_aux_feature": False,
                                                              "training.lr": 0.01}},
    "confidence": 0.9, "rationale": "The derived column is computed from the label.",
}
HEALTHY_SUBMIT = {"diagnosis": {"detected": False, "operator_class": "none"}, "evidence_refs": []}
UNSET_SUBMIT = {"diagnosis": {"detected": True, "operator_class": "data_leakage"}, "evidence_refs": [],
                "repair_spec": {"repair_type": "config_patch",
                                "patches": {"data.include_aux_feature": None, "data.aux_feature_strength": None}}}


@pytest.mark.parametrize("args", [FULL_SUBMIT, HEALTHY_SUBMIT, UNSET_SUBMIT], ids=["full", "healthy", "unset"])
def test_submission_round_trips_through_the_strict_shape(args):
    strict_args = to_strict_args("submit", args)
    assert _valid(strict_args, to_strict_tool_schema("submit"))            # what a strict call may send
    assert from_strict_args("submit", json.loads(json.dumps(strict_args))) == args


def test_non_submit_tool_with_omitted_optionals_round_trips():
    args = {"series": "train_loss"}
    strict_args = to_strict_args("query_metrics", args)
    assert strict_args == {"series": "train_loss", "start_epoch": None, "end_epoch": None, "agg": None}
    assert _valid(strict_args, to_strict_tool_schema("query_metrics"))
    assert from_strict_args("query_metrics", strict_args) == args


def test_responses_tools_strict_and_nonstrict():
    strict = to_responses_tools(TOOLS_SCHEMA, strict=True)
    assert all(t["strict"] is True for t in strict)
    assert [t["parameters"] for t in strict] == [to_strict(t) for t in TOOLS_SCHEMA]
    plain = to_responses_tools(TOOLS_SCHEMA)                                 # Part 1 shape, unchanged
    assert all("strict" not in t for t in plain)
    assert [t["parameters"] for t in plain] == [t["input_schema"] for t in TOOLS_SCHEMA]


def _response(arguments: str):
    item = SimpleNamespace(type="function_call", call_id="c1", name="submit", arguments=arguments,
                           model_dump=lambda exclude_none=True: {"type": "function_call", "call_id": "c1",
                                                                 "name": "submit", "arguments": arguments})
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None, output_tokens_details=None)
    return SimpleNamespace(output=[item], status="completed", usage=usage, model="gpt-5.6-luna", id="r1")


def test_parse_normalizes_strict_arguments_only_in_strict_mode():
    raw = json.dumps(to_strict_args("submit", FULL_SUBMIT))
    assert parse_responses(_response(raw), strict=True).tool_calls[0].arguments == FULL_SUBMIT
    assert parse_responses(_response(raw)).tool_calls[0].arguments == json.loads(raw)   # non-strict: verbatim


def test_anthropic_is_unchanged_and_refuses_strict():
    before = copy.deepcopy(TOOLS_SCHEMA)
    to_responses_tools(TOOLS_SCHEMA, strict=True)
    assert TOOLS_SCHEMA == before                                            # the canonical schema is never mutated
    assert all("additionalProperties" not in t["input_schema"] for t in TOOLS_SCHEMA)
    from harness.sweep import _make_client
    with pytest.raises(ValueError, match="OpenAI setting"):
        _make_client("anthropic", "claude-haiku-4-5-20251001", strict_tools=True)


def test_factory_and_planner_mark_only_openai_cells(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from harness import sweep
    agent = sweep._default_agent_factory({"agent": "react", "anchor": "off", "provider": "openai",
                                          "model": "gpt-5.6-luna", "strict_tools": True}, "m")
    assert agent._client._strict_tools is True and agent._client.describe()["strict_tools"] is True
    import yaml
    (tmp_path / "cases" / "case_0001").mkdir(parents=True)
    (tmp_path / "cases" / "case_0001" / "card.public.yaml").write_text("case_id: case_0001\n")
    (tmp_path / "cases" / "registry.hidden.yaml").write_text(yaml.dump(
        {"case_0001": {"workload": "tabular_adult", "operator": "silent.lr_warmup.v1", "strength": "mild", "seed": 42}}))
    r = sweep.plan(tmp_path, "p", strengths=["mild"], faulty_seeds=[42], control_seeds=[], repeats=1,
                   operators=["silent.lr_warmup.v1"], openai_strict_tools=True,
                   providers=[{"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
                              {"provider": "openai", "model": "gpt-5.6-luna"}])
    cells = r["plan"]["cells"]
    assert all(c.get("strict_tools") is True for c in cells if c["provider"] == "openai")
    assert not any("strict_tools" in c for c in cells if c["provider"] == "anthropic")
    assert r["plan"]["header"]["factor_levels"]["openai_strict_tools"] is True
