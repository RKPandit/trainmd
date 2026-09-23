"""The export hidden-value wall is widened by PROVENANCE, never by value.

A formatted hidden value may collide with an unrelated public number (accuracies share the k/N grid;
a cost can equal a 6-dp std). A match is exempt only when it sits in a field whose value derives
entirely from public inputs: usage token counts / cost, or a value `query_metrics` returned for an
agent-visible series (plus the cost columns of the sweep-level index/progress files) — or free
text that echoes a value already public in the SAME record. Anything else still blocks. Each test builds a tiny synthetic project in tmp and runs
the real exporter against it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_release import export  # noqa: E402

HIDDEN_FAULTY = 0.849771      # the observed case_0116 coincidence (== 5764/6783)
HIDDEN_STD = 0.001796         # the observed shared-hidden-std / trial-cost coincidence
SWEEP = "demo"


def _project(tmp_path: Path, trial_overrides: dict, progress_rows=None, extra_trials=()) -> Path:
    root = tmp_path / "proj"
    hid = root / "cases" / "case_0001" / "hidden"
    hid.mkdir(parents=True)
    (hid / "verify.yaml").write_text(yaml.dump({
        "tolerance_lower": 0.844655, "faulty_value": HIDDEN_FAULTY,
        "reference_metric_mean": 0.853011, "reference_metric_std": HIDDEN_STD,
        "hidden_eval_seeds": [100, 101, 102]}))
    (hid / "card.hidden.yaml").write_text(yaml.dump({
        "operator_id": "silent.data_leakage.v1", "layer": "dynamics", "strength": "mild",
        "seed": 42, "case_build_id": "b1", "symptom_direction": "positive",
        "visible_sigma_distance": 1.5, "hidden_sigma_distance": 2.5,
        "band_position_visible": "in_band", "band_position_hidden": "below_band"}))
    (root / "cases" / "case_0001" / "card.public.yaml").write_text(yaml.dump({"case_id": "case_0001"}))
    rec = {
        "case_id": "case_0001", "run_id": "r1",
        "conditions": {"sweep_name": SWEEP, "anchor": "off", "agent_type": "static"},
        "submission": {"diagnosis": {"detected": True, "operator_class": "data_leakage"}},
        "tool_transcript": [], "llm_transcript": [],
        "scores": {"detection": {"correct": True}},
        "usage": {"input_tokens": 1000, "output_tokens": 200, "estimated_cost_usd": 0.0123},
        "status": "ok",
    }
    for dotted, value in trial_overrides.items():
        node = rec
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    trials = root / "results" / "case_0001" / "trials"
    trials.mkdir(parents=True)
    (trials / "t1.yaml").write_text(yaml.dump(rec))
    for i, overrides in enumerate(extra_trials, start=2):   # further records of the same case
        other = json.loads(json.dumps(rec))
        other["run_id"] = f"r{i}"
        other["tool_transcript"], other["llm_transcript"] = [], []
        other.update(overrides)
        (trials / f"t{i}.yaml").write_text(yaml.dump(other))
    if progress_rows is not None:
        (root / "sweeps").mkdir()
        (root / "sweeps" / f"{SWEEP}_progress.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in progress_rows))
    return root


def _query(series: str, value: float) -> list:
    return [{"tool_name": "query_metrics", "arguments": {"series": series},
             "result": {"status": "ok", "series": series,
                        "values": [{"epoch": 0, "value": value}, {"epoch": 1, "value": 0.849182}]}}]


# ---- the two observed coincidences pass ---------------------------------------------------------

def test_cost_equal_to_hidden_std_is_exempt(tmp_path):
    """Observed: a trial's estimated_cost_usd == the shared hidden std (also lands in index.csv)."""
    root = _project(tmp_path, {"usage.estimated_cost_usd": HIDDEN_STD},
                    progress_rows=[{"cell_id": "c1", "status": "ok", "cost_usd": HIDDEN_STD}])
    r = export(root, SWEEP)
    assert r["n_trials"] == 1
    assert f"{HIDDEN_STD}" in (r["out_dir"] / "index.csv").read_text()   # really present, exempted


def test_queried_visible_metric_equal_to_hidden_value_is_exempt(tmp_path):
    """Observed: epoch-0 metric_visible_val_acc == case_0116's hidden faulty test accuracy (k/N grid)."""
    root = _project(tmp_path, {"tool_transcript": _query("metric_visible_val_acc", HIDDEN_FAULTY)})
    assert export(root, SWEEP)["n_trials"] == 1


# ---- anything outside a public-derived field still blocks ---------------------------------------

@pytest.mark.parametrize("field,value", [
    ("submission.diagnosis.operator_class", f"leak_{HIDDEN_FAULTY}"),   # free text a model controls
    ("scores.detection.note", HIDDEN_FAULTY),                          # non-allowlisted numeric field
    ("usage.llm_calls", HIDDEN_STD),                                   # usage key not on the allowlist
])
def test_planted_hidden_value_in_non_allowlisted_field_blocks(tmp_path, field, value):
    root = _project(tmp_path, {field: value})
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


def test_free_text_echo_of_a_same_record_public_value_is_exempt(tmp_path):
    """Observed (case_0116 ×2): the model quotes the epoch-0 visible val_acc it received. The identical
    value is already public in THIS record's query_metrics result, so the echo discloses nothing new."""
    root = _project(tmp_path, {
        "tool_transcript": _query("metric_visible_val_acc", HIDDEN_FAULTY),
        "llm_transcript": [{"response_text": f"Epoch 0: val_acc={HIDDEN_FAULTY}"}]})
    assert export(root, SWEEP)["n_trials"] == 1


def test_free_text_with_no_public_source_in_the_record_blocks(tmp_path):
    root = _project(tmp_path, {
        "llm_transcript": [{"response_text": f"the held-out accuracy is {HIDDEN_FAULTY}"}]})
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


def test_echo_exemption_is_per_record_never_global(tmp_path):
    """The value is public in record r1 but NOT in r2; r2's free-text mention must still block."""
    root = _project(
        tmp_path, {"tool_transcript": _query("metric_visible_val_acc", HIDDEN_FAULTY)},
        extra_trials=[{"llm_transcript": [{"response_text": f"val_acc={HIDDEN_FAULTY}"}]}])
    with pytest.raises(SystemExit, match=r"r2\.json: leaks .*outside any public-derived field"):
        export(root, SWEEP)


def test_echo_does_not_exempt_non_string_fields(tmp_path):
    """Only free TEXT can echo; a harness-written numeric field outside the allowlist still blocks
    even when the same value is public elsewhere in the record."""
    root = _project(tmp_path, {
        "tool_transcript": _query("metric_visible_val_acc", HIDDEN_FAULTY),
        "scores.detection.note": HIDDEN_FAULTY})
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


def test_query_metrics_on_a_non_visible_series_blocks(tmp_path):
    root = _project(tmp_path, {"tool_transcript": _query("metric_hidden_test_acc", HIDDEN_FAULTY)})
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


def test_progress_non_cost_field_blocks(tmp_path):
    root = _project(tmp_path, {}, progress_rows=[{"cell_id": "c1", "status": "ok",
                                                  "error": f"bad {HIDDEN_STD}"}])
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


def test_hidden_value_in_a_key_blocks(tmp_path):
    """A needle that appears in a JSON KEY is in no field value at all, so it is never exempt."""
    root = _project(tmp_path, {"scores.detection": {f"{HIDDEN_FAULTY}": True}})
    with pytest.raises(SystemExit, match="outside any public-derived field"):
        export(root, SWEEP)


# ---- band labels: visible ships, hidden never ---------------------------------------------------

def test_release_ships_visible_band_label_only(tmp_path):
    root = _project(tmp_path, {})
    out = export(root, SWEEP)["out_dir"]
    meta = json.loads((out / "cases" / "case_0001.json").read_text())
    assert meta["band_position_visible"] == "in_band"
    assert "band_position_hidden" not in meta
    assert "below_band" not in (out / "cases" / "case_0001.json").read_text()


def test_release_loader_ignores_a_hidden_band_label(tmp_path):
    """Even a hand-edited release cannot inject a hidden-band stratification."""
    from harness.sweep_stats import case_meta_from_release
    rel = tmp_path / "rel"
    (rel / "cases").mkdir(parents=True)
    (rel / "cases" / "case_0001.json").write_text(json.dumps(
        {"band_position_visible": "in_band", "band_position_hidden": "below_band"}))
    meta = case_meta_from_release(rel)("case_0001")
    assert meta["band_position_visible"] == "in_band"
    assert meta.get("band_position_hidden") is None
