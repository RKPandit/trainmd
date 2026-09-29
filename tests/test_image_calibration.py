"""Part 3 calibration logic (scripts/calibrate_image_faults.py) and the image workload's gated fault paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cal", ROOT / "scripts" / "calibrate_image_faults.py")
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
from workloads.image_fmnist import train as T  # noqa: E402

B = {"visible_mean": 0.886, "hidden_mean": 0.8855, "tolerance_lower": 0.8683, "positive_bar": 0.9216,
     "degradation_bar": 0.8501}


def _rows(vis, hid):
    return [{"seed": i, "exitcode": 0, "visible": v, "hidden": h} for i, (v, h) in enumerate(zip(vis, hid))]


def test_positive_silent_needs_both_halves_on_every_seed():
    assert cal.judge("silent_positive", _rows([0.95] * 6, [0.80] * 6), B)[0] is True
    assert cal.judge("silent_positive", _rows([0.95] * 5 + [0.92], [0.80] * 6), B)[0] is False   # one seed short
    assert cal.judge("silent_positive", _rows([0.95] * 6, [0.80] * 5 + [0.86]), B)[0] is False


def test_metric_tier_keeps_hidden_healthy():
    assert cal.judge("metric", _rows([0.95] * 6, [0.88] * 6), B)[0] is True
    assert cal.judge("metric", _rows([0.95] * 6, [0.86] * 6), B)[0] is False


def test_negative_silent_hidden_bar():
    assert cal.judge("silent_negative", _rows([0.8] * 6, [0.84] * 6), B)[0] is True
    assert cal.judge("silent_negative", _rows([0.8] * 6, [0.84] * 5 + [0.851]), B)[0] is False


def _c(label, passes, mean_hidden):
    return {"label": label, "passes": passes, "mean_hidden": mean_hidden}


def test_ladder_weakest_passing_is_mild_strongest_is_severe_and_graded():
    cands = [_c("a", False, 0.87), _c("b", True, 0.84), _c("c", True, 0.80), _c("d", True, 0.70), _c("e", True, 0.60)]
    lad = cal.ladder(cands, "hidden", B)
    assert (lad["mild"], lad["severe"], lad["graded"]) == ("b", "e", True)
    assert lad["moderate"] == "d"                     # effect closest to the midpoint of mild and severe


def test_ladder_not_graded_when_effect_is_not_monotone_or_too_few_pass():
    cands = [_c("a", True, 0.80), _c("b", True, 0.84), _c("c", True, 0.60)]
    assert cal.ladder(cands, "hidden", B)["graded"] is False
    assert cal.ladder([_c("a", True, 0.8), _c("b", True, 0.7)], "hidden", B)["graded"] is False
    assert cal.ladder([_c("a", False, 0.9)], "hidden", B)["graded"] is False


def test_label_swaps_are_nested_and_use_partners():
    y = np.arange(1000) % 10
    small, big = T._swap_partner_labels(y, 0.1), T._swap_partner_labels(y, 0.3)
    ch_s, ch_b = set(np.flatnonzero(small != y)), set(np.flatnonzero(big != y))
    assert len(ch_s) == 100 and len(ch_b) == 300 and ch_s <= ch_b
    assert all(small[i] == T._PARTNER[y[i]] for i in ch_s)
    assert all(T._PARTNER[T._PARTNER[c]] == c for c in range(10))                 # pairs are symmetric


def test_patch_is_fixed_by_split_and_encodes_the_class():
    X = np.zeros((50, 28, 28), dtype=np.uint8)
    y = np.arange(50) % 10
    a, b = T._patch_images(X, y, 0.0, "train"), T._patch_images(X, y, 0.0, "train")
    assert np.array_equal(a, b) and np.all(a[:, :4, :4] == (25 * (y + 1))[:, None, None])
    assert np.all(a[:, 4:, :] == 0) and np.all(X == 0)                            # only the patch; input untouched
    noisy = T._patch_images(X, y, 1.0, "train")
    assert not np.all(noisy[:, 0, 0] == 25 * (y + 1))


def test_clean_schedule_is_constant_and_the_step_unit_decays_per_step():
    assert T._lr_now(0.05, {"epochs": 8}, step=500, epoch=3) == 0.05
    s = {"decay_every": 1, "decay_gamma": 0.9, "interval_unit": "steps"}
    assert T._lr_now(0.05, s, step=10, epoch=0) == pytest.approx(0.05 * 0.9 ** 10)
    assert T._lr_now(0.05, {**s, "interval_unit": "epochs"}, step=10, epoch=0) == 0.05


def test_neutral_family_differs_only_in_the_key_strings():
    a = (ROOT / "workloads" / "image_fmnist" / "train.py").read_text()
    b = (ROOT / "workloads" / "image_fmnist_neutral" / "train.py").read_text()
    assert b == (a.replace('"corner_tag_noise"', '"opt_t_level"').replace('"corner_tag"', '"opt_t"')
                  .replace('"confident_fraction"', '"opt_q"'))
    for word in ("corner", "confident", "flip"):
        assert word not in b.replace("flip_fraction", "")          # neutral code carries no descriptive key name
