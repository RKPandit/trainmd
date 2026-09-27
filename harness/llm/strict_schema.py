"""Strict function-calling schemas for OpenAI (Stage 4 Part 2 DECISION 2026-09-27; LIMITATIONS L35).

OpenAI's strict mode (``"strict": true``) constrains a function call's arguments to its JSON schema, which
must then be CLOSED: every object ``additionalProperties: false`` with EVERY property listed in
``required`` (an optional field becomes nullable), and no free-form objects. Part 1 sent the tools without
strict mode and Luna's submit arguments degenerated (runaway whitespace; garbled keys).

``to_strict(tool)`` derives the strict ``parameters`` from the one canonical Anthropic-format schema in
``agents/llm_agent.py`` (so the two providers cannot drift), replacing the two free-form objects:

* ``evidence_refs[].detail`` (kind-specific) → one closed object holding every detail field, nullable;
* ``repair_spec.patches`` (an arbitrary key-path → value map) → an array of ``{key_path, value}`` pairs.

``from_strict_args(name, args)`` converts a strict-shaped call BACK to exactly the Anthropic shape the rest of
the harness consumes (nulls dropped, patches re-mapped, a null ``repair_spec`` removed), so tools, scorers
and records see the same arguments on both providers. Anthropic requests are never touched.
"""
from __future__ import annotations

import copy

DETAIL_FIELDS = {
    "key_path": {"type": "string"},
    "series": {"type": "string"},
    "start_epoch": {"type": "integer"},
    "end_epoch": {"type": "integer"},
    "start_line": {"type": "integer"},
    "end_line": {"type": "integer"},
}
PATCH_VALUE = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "null"}]}


def _nullable(schema: dict) -> dict:
    """``schema`` that also accepts null."""
    s = copy.deepcopy(schema)
    if "anyOf" in s:
        if {"type": "null"} not in s["anyOf"]:
            s["anyOf"].append({"type": "null"})
        return s
    t = s.get("type")
    if t == "object" or t == "array":
        desc = s.pop("description", None)
        out = {"anyOf": [s, {"type": "null"}]}
        if desc:
            out["description"] = desc
        return out
    if isinstance(t, str):
        s["type"] = [t, "null"]
        if "enum" in s:
            s["enum"] = list(s["enum"]) + [None]
    return s


def _close(schema: dict, path: str = "") -> dict:
    """Recursively make an object schema strict: all properties required, optional → nullable, closed."""
    s = copy.deepcopy(schema)
    if s.get("type") == "object":
        if path.endswith("evidence_refs[].detail"):
            desc = s.get("description", "")
            return {"type": "object", "additionalProperties": False, "required": list(DETAIL_FIELDS),
                    "description": desc + " Send every field; null for the fields this kind does not use.",
                    "properties": {k: _nullable(v) for k, v in DETAIL_FIELDS.items()}}
        if path.endswith("repair_spec.patches"):
            return {"type": "array",
                    "description": "Corrected config values as a list of {key_path, value} pairs "
                                   "(an empty list for no repair). value null = unset the key.",
                    "items": {"type": "object", "additionalProperties": False, "required": ["key_path", "value"],
                              "properties": {"key_path": {"type": "string"}, "value": PATCH_VALUE}}}
        props = s.get("properties") or {}
        if not props:
            raise ValueError(f"free-form object at {path or '<root>'} cannot be made strict")
        required = set(s.get("required") or [])
        new = {}
        for k, v in props.items():
            closed = _close(v, f"{path}.{k}" if path else k)
            new[k] = closed if k in required else _nullable(closed)
        s["properties"] = new
        s["required"] = list(props)
        s["additionalProperties"] = False
    elif s.get("type") == "array" and isinstance(s.get("items"), dict):
        s["items"] = _close(s["items"], f"{path}[]")
    return s


def to_strict(tool: dict) -> dict:
    """The strict ``parameters`` schema for one Anthropic-format tool."""
    return _close(tool["input_schema"])


def from_strict_args(name: str, args):
    """Strict-shaped arguments → the Anthropic shape (see module docstring). Non-dicts pass through."""
    if not isinstance(args, dict):
        return args
    out = {k: v for k, v in args.items() if v is not None}
    if name != "submit":
        return out
    refs = []
    for r in out.get("evidence_refs") or []:
        if isinstance(r, dict):
            r = dict(r)
            if isinstance(r.get("detail"), dict):
                r["detail"] = {k: v for k, v in r["detail"].items() if v is not None}
            refs.append(r)
    if "evidence_refs" in out:
        out["evidence_refs"] = refs
    rs = out.get("repair_spec")
    if isinstance(rs, dict):
        rs = dict(rs)
        p = rs.get("patches")
        if isinstance(p, list):
            rs["patches"] = {e["key_path"]: e.get("value") for e in p if isinstance(e, dict) and "key_path" in e}
        out["repair_spec"] = rs
    return out


def to_strict_args(name: str, args: dict) -> dict:
    """Inverse of ``from_strict_args`` for well-formed Anthropic-shape arguments (used by tests): every
    optional field present (null when absent), patches as pairs, detail fields completed with nulls."""
    return _fill(args, to_strict_tool_schema(name))


def to_strict_tool_schema(name: str) -> dict:
    from agents.llm_agent import TOOLS_SCHEMA
    return to_strict(next(t for t in TOOLS_SCHEMA if t["name"] == name))


def _fill(value, schema):
    if "anyOf" in schema:
        if value is None:
            return None
        branch = next(b for b in schema["anyOf"] if b.get("type") != "null")
        return _fill(value, branch)
    t = schema.get("type")
    if (t == "object" or (isinstance(t, list) and "object" in t)) and isinstance(value, dict):
        return {k: _fill(value.get(k), sub) for k, sub in schema["properties"].items()}
    if t == "array" and schema.get("items", {}).get("required") == ["key_path", "value"] and isinstance(value, dict):
        return [{"key_path": k, "value": v} for k, v in value.items()]
    if t == "array" and isinstance(value, list):
        return [_fill(v, schema["items"]) for v in value]
    return value
