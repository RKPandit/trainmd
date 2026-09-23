"""The committed fixture cases are PUBLIC-ONLY: no hidden directory, no answer-key fields."""
from pathlib import Path

import yaml

FX = Path(__file__).resolve().parent / "fixtures" / "cases_public"
HIDDEN_KEYS = {"operator_id", "accepted_classes", "core_tokens", "oracle_repair", "layer", "strength",
               "mutations", "hidden_sigma_distance", "band_position_hidden", "tolerance_lower"}


def test_fixture_cases_exist():
    assert {p.name for p in FX.iterdir() if p.is_dir()} == {"case_0001", "case_0109"}


def test_no_hidden_material():
    for p in FX.rglob("*"):
        assert "hidden" not in p.name.lower(), p
    for case in (FX / "case_0001", FX / "case_0109"):
        card = yaml.safe_load((case / "card.public.yaml").read_text())
        assert not HIDDEN_KEYS & set(card), sorted(HIDDEN_KEYS & set(card))
        assert card["reference_visible_metric"]["n"] == 30
