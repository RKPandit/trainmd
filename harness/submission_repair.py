"""Recover a repair_spec the MODEL folded into a sibling string field.

Root cause (see docs/DECISIONS.md, correction #3): some models emit the
text-tool-calling idiom (``<parameter name="repair_spec">{...}``) *inside* a
native tool_use string field (the ``rationale``) instead of populating the
structured ``repair_spec`` field.  Our pipeline records the structured tool_use
input faithfully — nothing in the harness parses arguments from text and no
sibling field is swallowed.  **This is MODEL-SIDE output folding, not a harness
parser bug.**  The correction is that we now RECOVER a well-formed repair the
model misplaced (and flag it), rather than scoring it as no-repair.

Strictness (deliberate, non-negotiable):
- Recover ONLY a single complete ``json.loads``-able object that has
  ``repair_type`` and a dict ``patches``.
- If a string carries MORE THAN ONE distinct such object, or the parse is
  ambiguous, DO NOT recover — flag it unrecoverable.
- No partial reconstruction, no key scraping.
- A recovered spec is NOT trusted as admissible; it flows through the normal
  ``validate_repair`` path at verify time exactly like a directly-submitted one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class FoldRecovery:
    spec: dict | None      # recovered repair_spec, or None
    warning: bool          # folding signal present (recovered, ambiguous, or unparseable)
    reason: str            # already_structured | recovered | ambiguous_multiple | folded_unparseable | none


def _is_repair_obj(o) -> bool:
    return isinstance(o, dict) and "repair_type" in o and isinstance(o.get("patches"), dict)


def _find_repair_objects(text: str) -> list[dict]:
    """All complete JSON objects in *text* that look like a repair_spec.

    Uses ``json.JSONDecoder.raw_decode`` from each ``{`` so trailing prose (e.g.
    a stray ``</parameter>``) does not defeat the parse.  A successfully parsed
    object advances past its end, so an inner ``patches`` object is not matched
    separately.
    """
    out: list[dict] = []
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        c = text.find("{", i)
        if c < 0:
            break
        try:
            obj, end = dec.raw_decode(text, c)
        except json.JSONDecodeError:
            i = c + 1
            continue
        if _is_repair_obj(obj):
            out.append(obj)
            i = end
        else:
            i = c + 1
    return out


def _has_marker(text: str) -> bool:
    """A repair-key mention (for the defensive WARNING only, never for recovery).

    Broad on purpose: the warning flags a submit whose structured repair_spec is
    absent while the raw input mentions a repair key, so a human can review it.
    Recovery itself remains strict (a single parseable {repair_type, patches}).
    """
    t = text.lower()
    return ("repair_type" in t) or ("repair_spec" in t)


def recover_folded_repair_spec(arguments: dict) -> FoldRecovery:
    """Recover a folded repair_spec from a submit's structured arguments.

    *arguments* is the tool_use input dict as recorded (``diagnosis``,
    ``evidence_refs``, ``repair_spec``, ``confidence``, ``rationale``).  Only the
    string values are searched; the structured ``repair_spec`` is never
    overridden when it is already well-formed.
    """
    rspec = arguments.get("repair_spec")
    if _is_repair_obj(rspec):
        return FoldRecovery(None, False, "already_structured")

    strings = [v for v in arguments.values() if isinstance(v, str)]
    candidates: list[dict] = []
    for s in strings:
        candidates.extend(_find_repair_objects(s))

    # De-duplicate by canonical JSON so the same object matched once is one candidate.
    uniq: list[dict] = []
    seen: set[str] = set()
    for c in candidates:
        k = json.dumps(c, sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(c)

    if len(uniq) == 1:
        return FoldRecovery(uniq[0], True, "recovered")
    if len(uniq) > 1:
        return FoldRecovery(None, True, "ambiguous_multiple")
    if any(_has_marker(s) for s in strings):
        return FoldRecovery(None, True, "folded_unparseable")
    return FoldRecovery(None, False, "none")
