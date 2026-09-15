#!/usr/bin/env python3
"""Consistency guard for docs/CURRENT_STATE.md (STAGE3_PLAN §0.2).

CURRENT_STATE.md is the single source of truth. Its machine-checkable facts (§a, a ```yaml```
block) must match the repo, and no LIVE document may reassert a claim the record has superseded.
This guard fails loudly (exit 1), naming every mismatch, so drift can't land silently. Wired into CI.

Checks:
  a. operator list + count      vs operators/registry.py
  b. case count                 vs cases/registry.hidden.yaml
  c. evidence scorer versions   vs harness/scoring.py (+ v2 primary)
  d. canonical image digest     vs docker/IMAGE_DIGEST
  e. latest sweep named         has a sweeps/<name>_manifest.yaml
  f. corrections count          equal in CURRENT_STATE, FINDINGS, LIMITATIONS
  g. statistical-language drift  no live doc asserts "H1 confirmed" / "positive-symptom blindness"
                                 / "27|28 cases" as a present-tense fact (record + historical docs
                                 are allow-listed; a same-line historical cue spares the match)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CS = ROOT / "docs" / "CURRENT_STATE.md"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# --------------------------------------------------------------------------- #
# §a machine-checkable facts
# --------------------------------------------------------------------------- #

def load_declared(cs_path: Path = CS) -> dict:
    """Parse the first ```yaml``` fenced block in CURRENT_STATE.md §a."""
    text = cs_path.read_text()
    m = re.search(r"```yaml\n(.*?)```", text, re.S)
    if not m:
        raise SystemExit(f"check_current_state: no ```yaml``` facts block in {cs_path}")
    return yaml.safe_load(m.group(1)) or {}


def _corrections_count(path: Path) -> int | None:
    """First 'N ... corrections' count in a doc (word-number or digits)."""
    m = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b[^.\n]{0,40}corrections",
                  path.read_text(), re.I)
    if not m:
        return None
    tok = m.group(1).lower()
    return _WORD.get(tok, int(tok) if tok.isdigit() else None)


def check_facts(declared: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    # a. operators
    from operators.registry import all_operator_ids
    reg_ops = sorted(all_operator_ids())
    dec_ops = sorted(declared.get("operators", []))
    if dec_ops != reg_ops:
        errors.append(f"[operators] CURRENT_STATE {dec_ops} != registry {reg_ops}")
    if declared.get("operators_count") != len(reg_ops):
        errors.append(f"[operators_count] CURRENT_STATE {declared.get('operators_count')} != registry {len(reg_ops)}")

    # b. cases
    reg = yaml.safe_load((root / "cases" / "registry.hidden.yaml").read_text())
    if declared.get("case_count") != len(reg):
        errors.append(f"[case_count] CURRENT_STATE {declared.get('case_count')} != registry {len(reg)}")

    # c. scorer versions + v2 primary
    scoring = (root / "harness" / "scoring.py").read_text()
    for v in declared.get("evidence_scorer_versions", []):
        if f'"{v}"' not in scoring:
            errors.append(f"[scorer] version {v!r} declared but not defined in harness/scoring.py")
    if declared.get("evidence_scorer_primary") != "evidence_v2":
        errors.append(f"[scorer] CURRENT_STATE primary {declared.get('evidence_scorer_primary')!r} != 'evidence_v2'")
    if "v2 primary" not in scoring:
        errors.append("[scorer] harness/scoring.py no longer marks evidence_v2 as primary")

    # d. image digest
    dig = (root / "docker" / "IMAGE_DIGEST").read_text().splitlines()[0].strip()
    if declared.get("canonical_image_digest") != dig:
        errors.append(f"[image_digest] CURRENT_STATE {declared.get('canonical_image_digest')} != docker/IMAGE_DIGEST {dig}")

    # e. latest sweep exists
    ls = declared.get("latest_sweep")
    if not (root / "sweeps" / f"{ls}_manifest.yaml").exists():
        errors.append(f"[latest_sweep] {ls!r}: no sweeps/{ls}_manifest.yaml")

    # f. corrections count consistent (CURRENT_STATE == FINDINGS == LIMITATIONS)
    fc = _corrections_count(root / "docs" / "FINDINGS.md")
    lc = _corrections_count(root / "docs" / "LIMITATIONS.md")
    dc = declared.get("corrections_count")
    if not (fc == lc == dc):
        errors.append(f"[corrections_count] CURRENT_STATE {dc}, FINDINGS {fc}, LIMITATIONS {lc} — must match")

    return errors


# --------------------------------------------------------------------------- #
# §g statistical-language drift
# --------------------------------------------------------------------------- #

_FORBIDDEN = [
    (re.compile(r"H1 (?:is )?confirmed", re.I), "H1 confirmed"),
    (re.compile(r"positive-symptom blindness", re.I), "positive-symptom blindness"),
    (re.compile(r"\b2[78] cases\b", re.I), "27/28 cases (present-tense)"),
]
# A same-line historical/superseded cue spares a match (avoids flagging legitimate record mentions).
_NEG = re.compile(r"sweep[ -]?1|refut|failed to replicate|supersede|historical|\bwas\b|"
                  r"pre-regist|\bS1\b|\bL1\b|no live doc", re.I)

# Append-only records + historical docs + the needs-update walkthrough are allow-listed.
_ALLOW = {
    "DECISIONS.md", "RESEARCH_LOG.md", "HYPOTHESES.md", "FINDINGS.md", "LIMITATIONS.md",
    "CITATIONS.md", "TrainMD_Codebase_Walkthrough.md",
    "harness_spec_v0.1.md", "HARDENING_PLAN.md", "G1_GATE_PLAN.md",
}


def _live_docs(root: Path = ROOT) -> list[Path]:
    docs = [p for p in (root / "docs").glob("*.md") if p.name not in _ALLOW]
    for extra in ("README.md", "CLAUDE.md"):
        p = root / extra
        if p.exists():
            docs.append(p)
    return docs


_QUOTES = "\"'“”‘’"  # a quoted occurrence is meta-discussion, not an assertion


def _is_quoted(line: str, m: re.Match) -> bool:
    before = line[m.start() - 1] if m.start() > 0 else ""
    after = line[m.end()] if m.end() < len(line) else ""
    return before in _QUOTES and after in _QUOTES


def check_language(paths: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for p in paths:
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if _NEG.search(line):
                continue
            for pat, label in _FORBIDDEN:
                m = pat.search(line)
                if m and not _is_quoted(line, m):
                    rel = p.relative_to(root) if root in p.parents else p.name
                    errors.append(f"[stat-language] {rel}:{i} asserts {label!r}: {line.strip()[:80]}")
    return errors


# --------------------------------------------------------------------------- #

def main() -> int:
    errors = check_facts(load_declared(), ROOT)
    errors += check_language(_live_docs(ROOT), ROOT)
    if errors:
        print("check_current_state: FAIL — CURRENT_STATE.md is out of sync with the repo:\n",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("\nFix whichever is stale (this page or the source) in the same commit.", file=sys.stderr)
        return 1
    print("check_current_state: OK — CURRENT_STATE.md §a matches the repo; no language drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
