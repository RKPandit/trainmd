"""Release FIELD INVENTORY + doc-claim cross-check (DECISIONS 2026-09-23).

Both directions: the checker FAILS on the three historically wrong release-content claims (quoted
verbatim from before their correction) and PASSES a true absence claim; a stale inventory fails.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import check_release_claims as crc
from scripts import release_field_inventory as rfi

ROOT = Path(__file__).resolve().parent.parent


def _release(root: Path, name="s", band_hidden=True):
    rel = root / "results_release" / name
    (rel / "trials").mkdir(parents=True)
    (rel / "cases").mkdir()
    scores = {"identification": {"accepted_classes": ["x"], "correct": True}, "band_position": "in"}
    if band_hidden:
        scores["band_position_hidden"] = "in"
    (rel / "trials" / "c1__r1.json").write_text(json.dumps({"case_id": "c1", "scores": scores}))
    (rel / "trials" / "c1__r2.json").write_text(json.dumps({"case_id": "c1", "scores": {}}))
    (rel / "cases" / "c1.json").write_text(json.dumps({"operator_id": "op", "hidden_sigma_distance": 1.0,
                                                       "band_position_visible": "in"}))
    (rel / "index.csv").write_text("case_id,run_id\nc1,r1\nc1,r2\n")
    (rel / "release_meta.json").write_text(json.dumps({"sweep": name, "n_trials": 2}))
    rfi.write(rel)
    (root / "docs").mkdir(exist_ok=True)
    return rel


def _doc(root: Path, text: str, name="CLAIMS.md"):
    (root / "docs" / name).write_text(text)


# ---- inventory ----------------------------------------------------------------------------------

def test_inventory_counts_every_key_path_per_file(tmp_path):
    rel = _release(tmp_path)
    inv = json.loads((rel / rfi.INVENTORY_NAME).read_text())
    assert inv["files"] == {"trials": 2, "cases": 1}
    t = inv["fields"]["trials"]
    assert t["scores"] == 2 and t["scores.band_position_hidden"] == 1
    assert t["scores.identification.accepted_classes"] == 1
    assert inv["fields"]["cases"]["hidden_sigma_distance"] == 1
    assert inv["fields"]["index.csv"] == {"case_id": 2, "run_id": 2}


def test_list_elements_are_collapsed_and_values_never_recorded():
    assert rfi.key_paths({"a": [{"b": 1}, {"c": {"d": "SECRET"}}]}) == {"a", "a[].b", "a[].c", "a[].c.d"}


def test_stale_inventory_fails(tmp_path):
    rel = _release(tmp_path)
    (rel / "trials" / "c2__r1.json").write_text(json.dumps({"case_id": "c2", "new_field": 1}))
    assert not rfi.is_current(rel)
    assert any("stale" in p for p in crc.check(tmp_path))


# ---- claims: the three historical errors are caught (verbatim pre-correction wording) ------------

def test_catches_the_band_position_hidden_claim(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "_Hidden-band stratification is internal-only by design and is not part of this "
                   "report: the release never carries hidden band labels, so that table cannot be "
                   "rebuilt from the release._\n")
    probs = crc.check(tmp_path)
    assert len(probs) == 1 and "band_position_hidden" in probs[0] and "CLAIMS.md:1" in probs[0]


def test_catches_the_accepted_classes_claim(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "Generic words such as `accepted_classes` are never exported.\n")
    assert any("accepted_classes" in p for p in crc.check(tmp_path))


def test_catches_a_code_comment_claim(tmp_path):
    _release(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "exporter.py").write_text(
        "# The HIDDEN band label is never exported (it encodes the hidden test metric).\n")
    assert any("exporter.py:1" in p for p in crc.check(tmp_path))


def test_catches_hidden_sigma_distance_claim(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "- The release does not include `hidden_sigma_distance`.\n")
    assert any("hidden_sigma_distance" in p for p in crc.check(tmp_path))


# ---- claims: true statements pass --------------------------------------------------------------

def test_true_absence_claim_passes(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "The hidden seeds' metric values (`per_seed_hidden_metrics`) are never exported.\n")
    assert crc.check(tmp_path) == []


def test_presence_statements_and_non_release_uses_pass(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "Per-trial `scores` hold `band_position_hidden` (see FIELD_INVENTORY.json).\n\n"
                   "The table is not part of the release-reproducible report, which reads "
                   "`band_position_visible` only.\n")
    assert crc.check(tmp_path) == []


def test_decisions_log_is_exempt(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "| date | contradicting the statement that `accepted_classes` is never exported |\n",
         name="DECISIONS.md")
    assert crc.check(tmp_path) == []


def test_list_items_are_separate_statements(tmp_path):
    _release(tmp_path)
    _doc(tmp_path, "- the hidden TEST SET never ships.\n- the grading keys: `accepted_classes`, oracle.\n")
    assert crc.check(tmp_path) == []


# ---- the real repository -----------------------------------------------------------------------

def test_repository_inventories_are_current_and_claims_agree():
    assert crc.check(ROOT) == []
