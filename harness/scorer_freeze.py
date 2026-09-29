"""The FROZEN scorer (DECISIONS 2026-09-28): identification root_token_v3, evidence v2.3.

`scorer_fingerprint()` digests everything that decides an identification or evidence score — the method and
primary-version names, the full multi-operator token spec (`token_spec_sha256`), every operator's evidence
specification (evidence refs, alternative sets, CODE_PATH, CRASH_OUTPUT), and the source of the two scoring
modules. The committed values live in `harness/scorer_freeze.yaml`; `tests/test_scorer_freeze.py` fails on
ANY difference. Changing the scorer after the freeze is therefore a deliberate act: update the YAML with
`python -m harness.scorer_freeze --write` AND add a DECISIONS row saying why (after the Part 2 lock, a
finding goes to LIMITATIONS unless a result would be wrong).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FREEZE_FILE = ROOT / "harness" / "scorer_freeze.yaml"
SOURCES = ("harness/scoring.py", "harness/evidence_code.py")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def evidence_spec(group: str | None = None) -> dict:
    from operators.registry import DEFAULT_GROUP, all_operator_ids, get_operator
    out = {}
    for op_id in all_operator_ids(group or DEFAULT_GROUP):
        op = get_operator(op_id)
        sets = op.evidence_sets() if hasattr(op, "evidence_sets") else None
        out[op_id] = {
            "evidence": [dataclasses.asdict(e) for e in op.evidence()],
            "evidence_sets": [[dataclasses.asdict(e) for e in st] for st in sets] if sets else None,
            "code_path": getattr(op, "CODE_PATH", None),
            "crash_output": getattr(op, "CRASH_OUTPUT", None),
        }
    return out


def scorer_fingerprint() -> dict:
    """The top-level token / evidence digests are WORKLOAD 1's (its operator set, unchanged by the Part 3 image
    operators); every other workload group's digests are under ``workload_groups`` (Part 3 re-freeze,
    DECISIONS 2026-09-29)."""
    from harness import scoring
    from operators.registry import DEFAULT_GROUP, WORKLOAD_GROUPS, token_spec_sha256
    return {
        "identification_method": scoring.IDENTIFICATION_METHOD,
        "evidence_primary": scoring.EVIDENCE_SCORER_V2_3,
        "token_spec_sha256": token_spec_sha256(),
        "evidence_spec_sha256": _sha(evidence_spec()),
        "workload_groups": {g: {"token_spec_sha256": token_spec_sha256(g), "evidence_spec_sha256": _sha(evidence_spec(g))}
                            for g in WORKLOAD_GROUPS if g != DEFAULT_GROUP},
        "source_sha256": {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in SOURCES},
    }


def committed() -> dict:
    return yaml.safe_load(FREEZE_FILE.read_text())


def drift() -> list[str]:
    """Differences between the live scorer and the committed freeze (empty = frozen scorer unchanged)."""
    live, frozen = scorer_fingerprint(), committed()["fingerprint"]
    out = []
    for k in live:
        if k == "source_sha256":
            for rel in live[k]:
                if live[k][rel] != frozen[k].get(rel):
                    out.append(f"source {rel} changed")
        elif live[k] != frozen.get(k):
            out.append(f"{k}: frozen {frozen.get(k)!r} vs live {live[k]!r}")
    return out


def main() -> int:
    if "--write" in sys.argv:
        text = FREEZE_FILE.read_text() if FREEZE_FILE.exists() else ""
        header = "".join(ln + "\n" for ln in text.splitlines() if ln.startswith("#"))   # keep the comment header
        doc = (yaml.safe_load(text) or {}) if text else {}
        doc["fingerprint"] = scorer_fingerprint()
        FREEZE_FILE.write_text(header + yaml.dump(doc, default_flow_style=False, sort_keys=False))
        print(f"wrote {FREEZE_FILE} — add a DECISIONS row saying why the frozen scorer changed")
        return 0
    d = drift()
    print("scorer frozen and unchanged" if not d else "SCORER DRIFT:\n  " + "\n  ".join(d))
    return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main())
