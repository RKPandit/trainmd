"""Design-invariant tests for the neutral-key data_leakage variant (Part 2).

The ablation is only valid if the ONLY thing an agent can observe that differs
between the descriptive and neutral variant is the config KEY NAME. These tests
enforce that mechanically:

  * the two train.py files differ ONLY at the two config-key-lookup lines;
  * the shared config.yaml / datautil.py are byte-identical (symlinked);
  * the neutral variant INTRODUCES no forbidden hint token vs the clean baseline
    (descriptive inventory printed report-only, per the 2026-09-18 ruling);
  * the two variants' resolved configs differ ONLY in the two key names;
  * the scorer's concept-uniqueness fix lets the two {leak} operators coexist.

No paid trials; the resolved-config test trains twice in-container (native for
authority; the diff is structural).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from random import Random

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WL = ROOT / "workloads" / "tabular_adult"
WL_NEUTRAL = ROOT / "workloads" / "tabular_adult_neutral"

# Tokens that would name the fault concept / mechanism as a knob hint.
_HINT_TOKENS = ["aux", "feature", "leak", "inject", "extra", "add",
                "signal", "proxy", "label", "target"]

# The only lines allowed to differ between the two train.py files.
_KEY_LINE_DELTAS = {
    ('    if dcfg.get("include_aux_feature", False):',
     '    if dcfg.get("opt_c", False):'),
    ('        _p = dcfg.get("aux_feature_strength", 0.0)',
     '        _p = dcfg.get("opt_c_level", 0.0)'),
}


def _hint_tokens_in(text: str) -> set[str]:
    low = text.lower()
    return {t for t in _HINT_TOKENS if t in low}


def _skip_if_no_data():
    if not (WL / ".data").exists() or not (WL_NEUTRAL / ".data").exists():
        pytest.skip("Data not prepared; run `make data && make link-neutral-workload`.")


# --------------------------------------------------------------------------
# Structural invariants (no training)
# --------------------------------------------------------------------------

def test_train_py_differs_only_at_key_lookup():
    """The two train.py files must differ ONLY at the two key-lookup lines."""
    a = (WL / "train.py").read_text().splitlines()
    b = (WL_NEUTRAL / "train.py").read_text().splitlines()
    assert len(a) == len(b), "train.py files have different line counts"
    diffs = {(x, y) for x, y in zip(a, b) if x != y}
    assert diffs == _KEY_LINE_DELTAS, (
        f"train.py differs outside the two key-lookup lines: {diffs - _KEY_LINE_DELTAS}"
    )


def test_shared_files_byte_identical():
    """config.yaml and datautil.py are shared (symlinked) → byte-identical."""
    for fname in ("config.yaml", "datautil.py"):
        assert (WL / fname).read_bytes() == (WL_NEUTRAL / fname).read_bytes(), fname


def test_neutral_introduces_no_hint_token():
    """The neutral variant introduces NO forbidden hint token vs clean tabular_adult;
    the descriptive variant's hint inventory is printed report-only (2026-09-18 ruling).
    """
    introduced = set()
    for fname in ("train.py", "config.yaml", "datautil.py"):
        base = _hint_tokens_in((WL / fname).read_text())
        neu = _hint_tokens_in((WL_NEUTRAL / fname).read_text())
        introduced |= (neu - base)  # tokens the neutral file has that clean does not

    # Config keys the neutral operator writes.
    from operators.silent.data_leakage_neutral import DataLeakageNeutralOperator
    op = DataLeakageNeutralOperator()
    introduced |= _hint_tokens_in(f"{op.ENABLE_KEY} {op.STRENGTH_KEY}")

    assert introduced == set(), f"neutral variant introduces hint tokens: {introduced}"

    # Report-only: what the DESCRIPTIVE variant carries that the neutral does not.
    from operators.silent.data_leakage import DataLeakageOperator
    d = DataLeakageOperator()
    descr_keys = _hint_tokens_in(f"{d.ENABLE_KEY} {d.STRENGTH_KEY}")
    descr_train = _hint_tokens_in("\n".join(
        x for x, y in zip((WL / "train.py").read_text().splitlines(),
                          (WL_NEUTRAL / "train.py").read_text().splitlines()) if x != y))
    print(f"\n[report-only] descriptive hint tokens in config keys: {sorted(descr_keys)}")
    print(f"[report-only] descriptive hint tokens in its train.py key lines: {sorted(descr_train)}")
    print(f"[report-only] neutral introduces: {sorted(introduced)} (must be empty)")


# --------------------------------------------------------------------------
# Scorer concept-uniqueness (no training)
# --------------------------------------------------------------------------

def test_leakage_label_scores_correct_on_both_variants():
    """A 'leakage' label must score correct on BOTH {leak} operators (concept
    uniqueness), while a genuinely ambiguous label is still rejected."""
    from harness.scoring import score_identification
    from operators.registry import get_operator

    for opid in ("silent.data_leakage.v1", "silent.data_leakage_neutral.v1"):
        hidden = {"operator_id": opid,
                  "accepted_classes": list(get_operator(opid).accepted_classes())}
        r = score_identification({"diagnosis": {"operator_class": "leakage"}}, hidden)
        assert r["correct"], f"{opid}: 'leakage' should be correct (path={r['match_path']})"

    r = score_identification(
        {"diagnosis": {"operator_class": "lr_and_leakage"}},
        {"operator_id": "silent.data_leakage.v1", "accepted_classes": []})
    assert not r["correct"], "ambiguous 'lr_and_leakage' must be rejected"


def test_no_variant_agnostic_module_names_descriptive_keys():
    """Variant-agnostic code (harness/, agents/, scripts/) must NOT refer to either
    descriptive data_leakage config key by name — that is exactly where the neutral
    variant would silently diverge from the descriptive one (regression: the hidden-
    eval column and the always-broken knob list both hardcoded include_aux_feature).
    The key names live ONLY in the operator and the descriptive workload's train.py."""
    forbidden = ("include_aux_feature", "aux_feature_strength")
    offenders = []
    for d in ("harness", "agents", "scripts"):
        for py in (ROOT / d).rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            text = py.read_text()
            for tok in forbidden:
                if tok in text:
                    offenders.append(f"{py.relative_to(ROOT)}: {tok}")
    assert not offenders, (
        "descriptive key names leaked into variant-agnostic code:\n" + "\n".join(offenders)
    )


def test_evaluate_checkpoint_is_key_agnostic_for_injected_column():
    """evaluate_checkpoint must add the test-time substitute column whenever the
    model was trained wider than the raw hidden data, regardless of the config key
    name. Regression: it hardcoded `include_aux_feature`, so the neutral `opt_c`
    case crashed at hidden eval (model input_dim=106 vs 105-wide test data)."""
    import numpy as np
    import torch
    from workloads.tabular_adult.train import MLP
    from harness.evaluator.evaluate_checkpoint import evaluate_checkpoint

    n, base = 40, 105
    model = MLP(base + 1, [64, 32], 0.0)  # trained WITH the injected column → input_dim 106
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        np.save(d / "X_test.npy", np.random.RandomState(0).randn(n, base).astype(np.float32))
        np.save(d / "y_test.npy", np.random.RandomState(1).binomial(1, 0.5, n).astype(np.float32))
        ckpt = {"model_config": {"hidden_dims": [64, 32], "dropout": 0.0},
                "input_dim": base + 1, "model_state_dict": model.state_dict()}
        cp = d / "ckpt_final.pt"
        torch.save(ckpt, cp)
        # Neutral-key config: evaluate_checkpoint must still add the column.
        cfg = {"data": {"opt_c": True, "opt_c_level": 0.28},
               "training": {"batch_size": 16}}
        r = evaluate_checkpoint(cp, d, cfg)
    assert 0.0 <= r["metric_hidden_test_acc"] <= 1.0


# --------------------------------------------------------------------------
# Resolved-config invariant (trains twice)
# --------------------------------------------------------------------------

def _train_variant(wl_dir: Path, op, strength: str, seed: int, out: Path) -> dict:
    import shutil
    ws = out / "ws"
    ws.mkdir(parents=True)
    for f in ("train.py", "config.yaml", "datautil.py"):
        shutil.copy2(wl_dir / f, ws / f)
    op.apply(ws, Random(seed), strength)
    cfg = yaml.safe_load((ws / "config.yaml").read_text())
    outdir = out / "run"
    outdir.mkdir(parents=True)
    cfgp = outdir / "config.yaml"
    cfgp.write_text(yaml.dump(cfg))
    r = subprocess.run(
        [sys.executable, str(ws / "train.py"), "--config", str(cfgp),
         "--data-dir", str(wl_dir / ".data"), "--output-dir", str(outdir),
         "--seed", str(seed)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return yaml.safe_load((outdir / "config.resolved.yaml").read_text())


def test_resolved_configs_differ_only_in_key_names():
    """Descriptive vs neutral resolved config must differ ONLY in the two data
    key names (same values, same input_dim, everything else identical)."""
    _skip_if_no_data()
    from operators.silent.data_leakage import DataLeakageOperator
    from operators.silent.data_leakage_neutral import DataLeakageNeutralOperator

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rd = _train_variant(WL, DataLeakageOperator(), "mild", 42, base / "d")
        rn = _train_variant(WL_NEUTRAL, DataLeakageNeutralOperator(), "mild", 42, base / "n")

    d_data = rd.pop("data")
    n_data = rn.pop("data")
    # Everything OUTSIDE the data block must be byte-identical.
    assert json.dumps(rd, sort_keys=True) == json.dumps(rn, sort_keys=True), (
        "resolved configs differ outside the data block"
    )
    # The data block differs ONLY by renaming the two keys (same values).
    assert d_data.pop("include_aux_feature") == n_data.pop("opt_c")
    assert d_data.pop("aux_feature_strength") == n_data.pop("opt_c_level")
    assert d_data == n_data, f"data block differs beyond the two key names: {d_data} vs {n_data}"
