"""Regression guard: committed workspace-copied source contains no operator-id segment.

W1 (workspace_no_hidden_tokens) scans a built case's workspace files for the
operator-id SEGMENTS (e.g. "silent", "control") as case-insensitive SUBSTRINGS —
so a comment in train.py mentioning "silently" fails W1 on every silent-tier case
(the collision that surfaced 2026-09-14; same class as L3's data_corruption naming
bug). This test scans the SOURCE files themselves (before any build), so prose that
would reintroduce the collision is caught at commit time, not case-build time.

If this fails: reword the offending comment to avoid the token (e.g. "quietly"
instead of "silently"). See docs/DECISIONS.md (W1 segment scan is prose-sensitive).
"""
from __future__ import annotations

from pathlib import Path

from operators.registry import all_operator_ids

_WORKLOAD = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"
# Mirrors harness.build_case._WORKLOAD_FILES (the files copied into every workspace).
_COPIED = ["train.py", "config.yaml", "datautil.py"]
_VERSION_SEGMENTS = {"v1", "v2", "v3"}


def _operator_id_segments() -> set[str]:
    segs: set[str] = set()
    for op_id in all_operator_ids():
        for seg in op_id.split("."):
            if seg and seg not in _VERSION_SEGMENTS:
                segs.add(seg.lower())
    return segs


def test_workload_source_has_no_operator_id_segment():
    segments = _operator_id_segments()
    violations = []
    for fname in _COPIED:
        for i, line in enumerate((_WORKLOAD / fname).read_text().splitlines(), 1):
            low = line.lower()
            for seg in segments:
                if seg in low:
                    violations.append(f"{fname}:{i} contains operator-id segment {seg!r}: {line.strip()[:90]}")
    assert not violations, (
        "Operator-id segment(s) in workspace-copied source — W1 will fail on the "
        "corresponding tier's cases. Reword the prose to avoid the token:\n"
        + "\n".join(violations)
    )
