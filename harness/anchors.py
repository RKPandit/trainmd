"""The single anchor legacy-mapping function (STAGE3_PLAN §0.3; STAGE4 4.0.6).

Arm identity is (arm, PROMPT MAJOR VERSION), enforced structurally — not by convention:

  prompt v1 (react-1 / static-1; Sweep 1, Stage 2 gate, H8):  off | numbers | rule
      Legacy Sweep-1 records use ``on`` for what is v1 ``rule`` (numbers + the decision sentence).
      v1 labels keep their historical bare names, so the frozen reports rebuild byte-for-byte.
  prompt v2 (react-2 / static-2; Stage 4 onward):              off | stats | rule
      ``stats`` is bare statistics (mean, SD, n reference runs — no interval, no evaluative words);
      ``rule`` is stats + one decision sentence. v2 labels are suffixed ``.v2`` (``off.v2``,
      ``stats.v2``, ``rule.v2``), so a v2 arm can never share a key with a v1 arm — H8's rule (v1)
      and Stage 4's rule (v2) are different treatments and are never pooled. Only ``off`` is
      comparable across versions (no band line in either), and even it is kept as two keys: any
      cross-version comparison must be made explicitly.

This is the ONE place the mapping lives; analysis normalizes ``conditions.anchor`` exactly once, at
load, together with the record's ``prompt.prompt_version``, so no downstream filter ever sees a
legacy value (the bug class where a filter for ``"on"`` runs AFTER normalization and silently
matches nothing — docs/DECISIONS.md 2026-09-15). ``on`` and ``numbers`` exist only in v1: a v2
record carrying either is an error, never silently mapped onto a v2 arm.

Records on disk are never rewritten; the mapping is applied only in analysis.
"""
from __future__ import annotations

import re

ARMS_BY_PROMPT_MAJOR: dict[int, tuple[str, ...]] = {
    1: ("off", "numbers", "rule"),
    2: ("off", "stats", "rule"),
}
CURRENT_PROMPT_MAJOR = 2
_LEGACY_V1 = {"on": "rule"}
_VERSION_RE = re.compile(r"^(?:react|static)-(\d+)(?:-|$)")


def prompt_major(prompt_version: str | None) -> int:
    """The prompt MAJOR version from ``react-N-<arm>`` / ``static-N-<arm>``; absent → 1.

    Every record before prompt v2 is v1 (sweep1's records may carry no prompt_version at all).
    An unrecognized non-empty version string is an error, never a silent default.
    """
    if not prompt_version:
        return 1
    m = _VERSION_RE.match(prompt_version)
    if not m:
        raise ValueError(f"unrecognized prompt_version {prompt_version!r}")
    return int(m.group(1))


def normalize_anchor(anchor: str | None, prompt_version: str | None = None) -> str | None:
    """The analysis arm key for ``anchor`` under ``prompt_version``'s major version.

    v1: legacy ``on`` → ``rule``; labels unchanged (``off`` / ``numbers`` / ``rule``).
    v2+: ``off`` / ``stats`` / ``rule`` → ``off.v2`` / ``stats.v2`` / ``rule.v2``.
    An arm that does not exist in the record's version raises (``on`` / ``numbers`` under v2,
    ``stats`` under v1) — nothing is mapped across versions.
    """
    if anchor is None:
        return None
    major = prompt_major(prompt_version)
    arms = ARMS_BY_PROMPT_MAJOR.get(major)
    if arms is None:
        raise ValueError(f"no anchor arms defined for prompt major version {major}")
    if major == 1:
        arm = _LEGACY_V1.get(anchor, anchor)
        if arm not in arms:
            raise ValueError(f"anchor {anchor!r} is not a prompt-v1 arm {arms} (or legacy 'on')")
        return arm
    if anchor not in arms:
        raise ValueError(f"anchor {anchor!r} is not a prompt-v{major} arm {arms}")
    return f"{anchor}.v{major}"


def arm_version(arm_key: str) -> int:
    """The prompt major version an analysis arm key belongs to (``rule.v2`` → 2, ``rule`` → 1)."""
    base, _, v = arm_key.partition(".v")
    return int(v) if v else 1


def arm_base(arm_key: str) -> str:
    """The arm name without its version suffix (``rule.v2`` → ``rule``)."""
    return arm_key.partition(".v")[0]


def arm_key(base: str, major: int) -> str:
    """The analysis key for a base arm name at a prompt major version (inverse of the above)."""
    return base if major == 1 else f"{base}.v{major}"
