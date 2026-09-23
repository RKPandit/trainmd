#!/usr/bin/env python3
"""CI guard: release-content CLAIMS in docs must agree with the release FIELD INVENTORIES.

Three documented claims about what a release contains had been wrong — each doc described the release
by intent, nobody checked the artifact (DECISIONS 2026-09-23). This check makes the artifact the
authority:

1. Every ``results_release/<name>/FIELD_INVENTORY.json`` must be current (regenerated from the release
   bytes and compared), so the inventory cannot drift from the release it describes.
2. Every sentence in the scanned docs that states ABSENCE from a release ("never exported", "never
   ships", "does not include", "not in the release", ...) and names a field in backticks fails if any
   inventory shows that field present — the failure names the field, the doc and the line.

Scanned: ``docs/**/*.md``, ``README.md``, and the docstrings/comments of ``scripts/*.py`` and
``harness/*.py`` (code comments describe releases too — two of the three wrong claims lived there).
Exempt: ``docs/DECISIONS.md`` (a dated log that necessarily quotes superseded claims when recording
their correction) and ``*_historical.md`` files. A backticked name is matched against every key-path
SEGMENT in the inventories (``scores.band_position_hidden`` matches `band_position_hidden`), and a
short declared list of PROSE ALIASES maps the phrases the docs actually use for such fields ("hidden
band label" → ``band_position_hidden``). The check is deliberately lexical: an absence claim that
names a field neither in backticks nor by a declared alias is not caught — release-content statements
should therefore reference the inventory rather than enumerate fields by hand.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_field_inventory import INVENTORY_NAME, is_current  # noqa: E402

ABSENCE = re.compile(
    r"never\s+(?:be\s+)?(?:export(?:ed|s)?|ship(?:s|ped)?|releas(?:e|ed|es)|carr(?:y|ies)|includ(?:e|ed|es))"
    r"|not\s+(?:be\s+)?(?:exported|shipped|released)"
    r"|does\s+not\s+(?:ship|include|carry|export)|doesn't\s+(?:ship|include|carry)"
    r"|ships\s+only|exports\s+only|carries\s+only"
    r"|(?:excluded|stripped|omitted|absent)\s+from\s+(?:the|every|each|a|any)\s+release(?![-\w])"
    r"|not\s+(?:in|part\s+of)\s+(?:the|any|a)\s+release(?![-\w])",   # not "release-reproducible"
    re.I)
# Prose names the docs use for inventory fields (lowercase phrase -> key-path segment). Declared, not
# inferred; extend when a new prose name for a released field appears.
PROSE_ALIASES = {
    "hidden band label": "band_position_hidden",
    "hidden band position": "band_position_hidden",
    "hidden-band label": "band_position_hidden",
    "hidden sigma distance": "hidden_sigma_distance",
    "hidden σ distance": "hidden_sigma_distance",
    "accepted classes": "accepted_classes",
}
BACKTICKED = re.compile(r"`([A-Za-z_][A-Za-z0-9_.\[\]]*)`")
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z*_(`\"'])")
EXEMPT_NAMES = {"DECISIONS.md"}
_ITEM_START = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")


def present_fields(root: Path) -> dict[str, list[str]]:
    """segment -> ["<release>:<kind>", ...] for every key-path segment in every inventory."""
    seen: dict[str, set[str]] = {}
    for inv_p in sorted((root / "results_release").glob(f"*/{INVENTORY_NAME}")):
        inv = json.loads(inv_p.read_text())
        for kind, paths in inv["fields"].items():
            for path in paths:
                for seg in re.split(r"\.|\[\]", path):
                    if seg:
                        seen.setdefault(seg, set()).add(f"{inv['sweep']}:{kind}")
    return {k: sorted(v) for k, v in seen.items()}


def _paragraphs(text: str):
    """(first_line_no, paragraph_text) — blank-line separated, lines joined with spaces; a list item
    or table row starts a new unit (it is its own statement)."""
    buf, start = [], None
    for i, line in enumerate(text.splitlines(), 1):
        if buf and _ITEM_START.match(line):
            yield start, " ".join(buf)
            buf, start = [], None
        if line.strip():
            if start is None:
                start = i
            buf.append(line.strip().lstrip("#").strip())
        elif buf:
            yield start, " ".join(buf)
            buf, start = [], None
    if buf:
        yield start, " ".join(buf)


def claims_in(text: str):
    """(line_no, sentence, [backticked names]) for each absence sentence naming a field."""
    for line_no, para in _paragraphs(text):
        for sent in _SENTENCE_END.split(para):
            if ABSENCE.search(sent):
                low = sent.lower()
                names = BACKTICKED.findall(sent) + [f for a, f in PROSE_ALIASES.items() if a in low]
                if names:
                    yield line_no, sent, names


def scanned_files(root: Path) -> list[Path]:
    files = sorted((root / "docs").rglob("*.md")) + [root / "README.md"]
    files += sorted((root / "scripts").glob("*.py")) + sorted((root / "harness").glob("*.py"))
    return [f for f in files if f.exists() and f.name not in EXEMPT_NAMES
            and not f.name.endswith("_historical.md") and f.name != Path(__file__).name]


def check(root: Path) -> list[str]:
    problems = []
    rel = root / "results_release"
    for d in sorted(p for p in rel.iterdir() if (p / "trials").is_dir()) if rel.is_dir() else []:
        if not is_current(d):
            problems.append(f"{d.relative_to(root)}/{INVENTORY_NAME} is stale or missing — run "
                            f"`python scripts/release_field_inventory.py --write --sweep {d.name}`")
    present = present_fields(root)
    for f in scanned_files(root):
        for line_no, sent, names in claims_in(f.read_text()):
            for name in names:
                segs = [s for s in re.split(r"\.|\[\]", name) if s]
                hit = next((s for s in reversed(segs) if s in present), None)
                if hit:
                    problems.append(
                        f"{f.relative_to(root)}:{line_no}: states `{name}` is absent from a release, but "
                        f"the inventory shows `{hit}` present in {', '.join(present[hit])} — "
                        f"«{sent[:160]}»")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    problems = check(a.project_root)
    if problems:
        print("check_release_claims: FAIL —\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print("check_release_claims: OK — inventories current; no doc claims a present field is absent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
