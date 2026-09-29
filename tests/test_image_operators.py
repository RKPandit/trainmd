"""Part 3 image-workload operators (operators/image/; design docs/PART3_DESIGN_DRAFT.md §2–3).

Fast tests: protocol, the rule-v2 ladders, the config each operator writes, the shared identification specs (the
workload-1 functions themselves), the LR-schedule fault's own concept, workload-scoped uniqueness, code paths that
resolve against both image train.py files, W1-safe ids, the case design.

Integration tests (CLAUDE.md operator rule — "clean run passes verification AND mutated run fails it, on 3
seeds"): verification is the EVALUATOR's own path — ``run_hidden_seeds`` trains the config fresh on the hidden-eval
seeds 100–102 and ``compute_recovery_verdict`` applies the mean-of-seeds rule — so "passes" and "fails" mean
exactly what they mean for a submitted repair. Plus: the metric tier's model is untouched (checkpoint bitwise
identical to clean), the neutral-key twins train identically to their descriptive operators, and the crash log's
error block sits where the operator's evidence says. Native amd64 only (the canonical platform; CI dispatch task
image-step4 on AMD).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from random import Random

import pytest
import yaml

from operators.base import IncidentOperator
from operators.registry import OPERATOR_REGISTRY, all_operator_ids, get_operator, workload_group

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "workloads" / "image_fmnist"
NEUTRAL = ROOT / "workloads" / "image_fmnist_neutral"
STRENGTHS = ("mild", "moderate", "severe")

# id -> (workload-1 counterpart whose identification spec it shares, or None for its own concept)
SHARED = {
    "silent.pixel_tag_leakage.v1": "silent.data_leakage.v1",
    "silent.pixel_tag_leakage_neutral.v1": "silent.data_leakage.v1",
    "silent.label_flip.v1": "silent.label_corruption.v1",
    "silent.confident_subset.v1": "silent.metric_inflation.v1",
    "silent.confident_subset_neutral.v1": "silent.metric_inflation.v1",
    "crash.channel_mismatch.v1": "crash.shape_mismatch.v1",
    "silent.decay_unit.v1": None,
}
# id -> {strength: {config key: value}} — the rule-v2 ladders (docs/audits/part3_calibration.md, DECISIONS
# 2026-09-29) as the operator must write them.
LADDERS = {
    "silent.pixel_tag_leakage.v1": {s: {"data.corner_tag": True, "data.corner_tag_noise": p}
                                    for s, p in zip(STRENGTHS, (0.20, 0.15, 0.05))},
    "silent.pixel_tag_leakage_neutral.v1": {s: {"data.opt_t": True, "data.opt_t_level": p}
                                            for s, p in zip(STRENGTHS, (0.20, 0.15, 0.05))},
    "silent.label_flip.v1": {s: {"data.flip_fraction": f} for s, f in zip(STRENGTHS, (0.25, 0.35, 0.45))},
    "silent.decay_unit.v1": {s: {"sched.decay_every": 1, "sched.decay_gamma": g, "sched.interval_unit": "steps"}
                             for s, g in zip(STRENGTHS, (0.97, 0.90, 0.80))},
    "silent.confident_subset.v1": {s: {"eval.confident_fraction": q} for s, q in zip(STRENGTHS, (0.85, 0.80, 0.70))},
    "silent.confident_subset_neutral.v1": {s: {"eval.opt_q": q} for s, q in zip(STRENGTHS, (0.85, 0.80, 0.70))},
    "crash.channel_mismatch.v1": {s: {"net.in_ch": c} for s, c in zip(STRENGTHS, (2, 3, 4))},
}
FAULTY = sorted(LADDERS)


def _get(cfg: dict, path: str):
    for k in path.split("."):
        cfg = cfg[k]
    return cfg


def _workspace(tmp: Path, family: str) -> Path:
    ws = tmp / "ws"
    ws.mkdir(parents=True)
    for f in ("train.py", "config.yaml"):
        shutil.copy2(ROOT / "workloads" / family / f, ws / f)
    return ws


# ---------------------------------------------------------------------------------------------------------------
# Fast
# ---------------------------------------------------------------------------------------------------------------

def test_image_group_is_exactly_the_design():
    img = all_operator_ids("image_fmnist")
    assert sorted(o for o in img if not o.startswith("control.")) == FAULTY
    assert len([o for o in img if o.startswith("control.benign_img_")]) == 7
    assert "control.healthy_image.v1" in img
    assert not set(img) & set(all_operator_ids())            # workload 1's default enumeration is untouched
    for o in img:
        assert workload_group(o) == "image_fmnist"
        assert isinstance(get_operator(o), IncidentOperator)


@pytest.mark.parametrize("op_id", FAULTY)
@pytest.mark.parametrize("strength", STRENGTHS)
def test_apply_writes_the_rule_v2_ladder(tmp_path, op_id, strength):
    op = get_operator(op_id)
    ws = _workspace(tmp_path, op.WORKLOAD_FAMILY)
    before = yaml.safe_load((ws / "config.yaml").read_text())
    man = op.apply(ws, Random(0), strength)
    after = yaml.safe_load((ws / "config.yaml").read_text())
    want = LADDERS[op_id][strength]
    assert {m.key_path: m.mutated_value for m in man.mutations} == want
    for k, v in want.items():
        assert _get(after, k) == v
    for m in man.mutations:
        try:
            assert _get(before, m.key_path) == m.original_value
        except KeyError:
            assert m.original_value is None
    with pytest.raises(ValueError):
        op.apply(ws, Random(0), "extreme")


@pytest.mark.parametrize("op_id", sorted(SHARED))
def test_identification_spec(op_id):
    op = get_operator(op_id)
    twin = SHARED[op_id]
    if twin is None:                                         # the LR-schedule fault: its OWN concept
        assert [sorted(g) for g in op.core_tokens()] == [["learning_rate", "lr"], ["anneal", "decay", "schedul"]]
        return
    ref = get_operator(twin)
    # The shared BASE concept is the workload-1 function itself. Label flip and channel mismatch add their OWN
    # implementation-derived alternatives (author 2026-09-29); every other operator shares the alternatives too.
    own_alts = op_id in ("silent.label_flip.v1", "crash.channel_mismatch.v1")
    methods = ["accepted_classes", "core_tokens", "off_concept_vetoes", "core_token_alternative_vetoes"]
    methods += [] if own_alts else ["core_token_alternatives"]
    for m in methods:
        a, b = getattr(type(op), m, None), getattr(type(ref), m, None)
        assert a is b, f"{op_id}.{m} is not {twin}'s function"
    if own_alts:
        assert type(op).core_token_alternatives is not getattr(type(ref), "core_token_alternatives", None)


def _ident(label: str, op_id: str) -> bool:
    from harness.scoring import score_identification
    card = {"operator_id": op_id, "accepted_classes": sorted(get_operator(op_id).accepted_classes())}
    return score_identification({"diagnosis": {"operator_class": label}}, card)["correct"]


# MUST-PASS labels (the author's three, 2026-09-29) and MUST-FAIL near-misses for the image concepts; plus
# workload-1 behaviour that must not move.
@pytest.mark.parametrize("label,op_id,ok", [
    # the author's three must-pass labels
    ("label_swap", "silent.label_flip.v1", True),
    ("channel_mismatch", "crash.channel_mismatch.v1", True),
    ("learning_rate_too_low", "silent.decay_unit.v1", True),
    # label flip: base concept + swap / partner / class-pair terms
    ("noisy_labels", "silent.label_flip.v1", True),
    ("swapped_labels", "silent.label_flip.v1", True),
    ("labels_replaced_by_partner_class", "silent.label_flip.v1", True),
    ("class_pair_label_swapping", "silent.label_flip.v1", True),
    ("class_imbalance", "silent.label_flip.v1", False),             # near-miss: class, no swap
    ("label_smoothing", "silent.label_flip.v1", False),             # near-miss: label, no swap / corruption
    ("memory_swap", "silent.label_flip.v1", False),                 # near-miss: swap, no label / class
    ("no_label_swap", "silent.label_flip.v1", False),               # negated
    # channel mismatch: base shape concept + input-channel terms
    ("input_shape_mismatch", "crash.channel_mismatch.v1", True),
    ("wrong_in_ch", "crash.channel_mismatch.v1", True),
    ("conv_input_channels_wrong", "crash.channel_mismatch.v1", True),
    ("wrong_number_of_channels", "crash.channel_mismatch.v1", True),
    ("channel_normalization", "crash.channel_mismatch.v1", False),  # near-miss: channel, no disagreement term
    ("color_channels", "crash.channel_mismatch.v1", False),
    ("conv_kernel_size_wrong", "crash.channel_mismatch.v1", False),
    # LR schedule: learning rate + (schedule | decay | too low | vanishing)
    ("lr_decay_too_aggressive", "silent.decay_unit.v1", True),
    ("learning_rate_schedule_counts_steps", "silent.decay_unit.v1", True),
    ("scheduler_decays_learning_rate_per_step", "silent.decay_unit.v1", True),
    ("vanishing_learning_rate", "silent.decay_unit.v1", True),
    ("lr_too_low", "silent.decay_unit.v1", True),
    ("weight_decay", "silent.decay_unit.v1", False),                # near-miss: decay of a different quantity
    ("weight_decay_too_high", "silent.decay_unit.v1", False),
    ("weight_decay_and_lr_misconfigured", "silent.decay_unit.v1", False),
    ("learning_rate_too_high", "silent.decay_unit.v1", False),      # near-miss: wrong direction
    ("vanishing_gradients", "silent.decay_unit.v1", False),         # near-miss: vanishing, not the rate
    ("batch_size_too_low", "silent.decay_unit.v1", False),
    ("learning_rate", "silent.decay_unit.v1", False),               # the rate alone
    ("lr_not_too_low", "silent.decay_unit.v1", False),              # negated
    # ambiguity across image concepts is still rejected
    ("leakage_and_lr_decay", "silent.decay_unit.v1", False),
    ("label_swap_and_channel_mismatch", "silent.label_flip.v1", False),
    # other image operators (shared concepts)
    ("pixel_tag_leakage", "silent.pixel_tag_leakage.v1", True),
    ("target_leakage", "silent.pixel_tag_leakage_neutral.v1", True),
    ("inflated_validation_accuracy", "silent.confident_subset.v1", True),
    ("evaluation_on_confident_subset", "silent.confident_subset_neutral.v1", True),
    # workload 1 unchanged by any of the above
    ("learning_rate_too_high", "silent.lr_warmup.v1", True),
    ("lr_decay_too_fast", "silent.lr_warmup.v1", True),
    ("label_swap", "silent.label_corruption.v1", False),
    ("channel_mismatch", "crash.shape_mismatch.v1", False),
])
def test_identification_is_workload_scoped(label, op_id, ok):
    assert _ident(label, op_id) is ok


@pytest.mark.parametrize("op_id", FAULTY)
@pytest.mark.parametrize("family", ["image_fmnist", "image_fmnist_neutral"])
def test_code_path_resolves_on_its_family(tmp_path, op_id, family):
    from harness.evidence_code import code_path_refs
    op = get_operator(op_id)
    if op.WORKLOAD_FAMILY != family:
        pytest.skip("the operator's keys are read only by its own family")
    refs = code_path_refs(op.CODE_PATH, _workspace(tmp_path, family))
    assert refs and all(r["kind"] == "code_span" for r in refs)


@pytest.mark.parametrize("op_id", sorted(all_operator_ids("image_fmnist")))
def test_ids_are_w1_safe_in_both_image_families(op_id):
    segs = [s.lower() for s in op_id.split(".") if s not in ("v1", "v2", "v3")]
    for fam in (IMAGE, NEUTRAL):
        for f in ("train.py", "config.yaml"):
            text = (fam / f).read_text().lower()
            assert not [s for s in segs if s in text], f"{op_id}: a segment occurs in {fam.name}/{f}"


def test_benign_edits_only_touch_existing_or_documented_keys(tmp_path):
    from operators.image.controls import IMAGE_BENIGN_OPERATORS
    clean = yaml.safe_load((IMAGE / "config.yaml").read_text())
    for cls in IMAGE_BENIGN_OPERATORS:
        for k, v in cls.EDITS.items():
            try:
                present = _get(clean, k)
            except KeyError:
                present = None
            assert (cls.FORM == "added") == (present is None), f"{cls.id}: FORM {cls.FORM} but {k} = {present}"
            assert present != v
        op = cls()
        assert op.evidence() == [] and op.oracle_repair() is None and op.admissible_repairs().repair_type == "none"


def test_case_design():
    from harness.seed_sets import CONFIRMATORY_BENIGN_IMAGE
    from scripts.build_all_cases import case_design_tuples
    img = case_design_tuples("image_fmnist")
    assert len(img) == 230 and len(set(img)) == 230
    assert len(case_design_tuples()) == 200                  # workload 1 unchanged
    benign = [t for t in img if t[0].startswith("control.benign_img_")]
    assert sorted(t[2] for t in benign) == sorted(CONFIRMATORY_BENIGN_IMAGE)
    assert all(OPERATOR_REGISTRY[o]().WORKLOAD_FAMILY.startswith("image_fmnist") for o, _, _ in img)


# ---------------------------------------------------------------------------------------------------------------
# Integration (native amd64): the evaluator's verification on hidden-eval seeds 100–102
# ---------------------------------------------------------------------------------------------------------------

_VERIFY_CACHE: dict = {}


def _require_native_image_data():
    if not (IMAGE / ".data").exists() or not (IMAGE / ".hidden_data").exists():
        pytest.skip("image data not prepared (python workloads/image_fmnist/data_prep.py)")
    from harness.platform_guard import require_native_amd64
    try:
        require_native_amd64(context="image operator integration tests")
    except SystemExit:
        pytest.skip("native amd64 only (the canonical platform)")


def _stats() -> dict:
    return yaml.safe_load((IMAGE / "reference" / "stats.yaml").read_text())


def _config(op_id: str | None, strength: str, tmp: Path) -> tuple[dict, Path]:
    family = get_operator(op_id).WORKLOAD_FAMILY if op_id else "image_fmnist"
    ws = _workspace(tmp / (op_id or "clean") / strength, family)
    if op_id:
        get_operator(op_id).apply(ws, Random(0), strength)
    return yaml.safe_load((ws / "config.yaml").read_text()), ROOT / "workloads" / family


def _verify(op_id: str | None, strength: str, tmp: Path):
    """(verdict, per-seed results) of the evaluator's verification of this config (cached per process)."""
    from harness.evaluator.verify_repair import compute_recovery_verdict, run_hidden_seeds
    from harness.seed_sets import HIDDEN_EVAL
    key = (op_id, strength)
    if key not in _VERIFY_CACHE:
        cfg, wd = _config(op_id, strength, tmp)
        per_seed = run_hidden_seeds(cfg, wd, sorted(HIDDEN_EVAL))
        st = _stats()
        v = st["metric_visible_val_acc"]
        layer = get_operator(op_id).layer if op_id else "control"
        verdict = compute_recovery_verdict(per_seed, st["metric_hidden_test_acc"]["tolerance_lower"], layer,
                                           v["mean"] - 2 * v["std"], v["mean"] + 2 * v["std"])
        _VERIFY_CACHE[key] = (verdict, per_seed)
    return _VERIFY_CACHE[key]


@pytest.mark.slow_integration
@pytest.mark.image_native
def test_clean_run_passes_verification(tmp_path):
    _require_native_image_data()
    (verdict, mean_hidden, _), per_seed = _verify(None, "clean", tmp_path)
    assert verdict == "recovered", f"clean config fails verification: mean hidden {mean_hidden}, {per_seed}"


@pytest.mark.slow_integration
@pytest.mark.image_native
@pytest.mark.parametrize("op_id", FAULTY)
@pytest.mark.parametrize("strength", STRENGTHS)
def test_mutated_run_fails_verification(tmp_path, op_id, strength):
    _require_native_image_data()
    (verdict, mean_hidden, _), per_seed = _verify(op_id, strength, tmp_path)
    assert verdict == "not_recovered", f"{op_id} {strength} PASSES verification: mean hidden {mean_hidden}"
    if get_operator(op_id).layer == "execution":
        assert all(r["exitcode"] != 0 for r in per_seed)
    else:
        assert all(r["exitcode"] == 0 for r in per_seed), "a non-crash fault must complete"


@pytest.mark.slow_integration
@pytest.mark.image_native
@pytest.mark.parametrize("op_id,twin", [("silent.pixel_tag_leakage_neutral.v1", "silent.pixel_tag_leakage.v1"),
                                        ("silent.confident_subset_neutral.v1", "silent.confident_subset.v1")])
def test_neutral_twin_trains_identically(tmp_path, op_id, twin):
    _require_native_image_data()
    _, a = _verify(op_id, "mild", tmp_path)
    _, b = _verify(twin, "mild", tmp_path)
    assert a == b


def _run_training(config: dict, workload: Path, seed: int, out: Path) -> int:
    from harness.thread_pins import pinned_thread_env
    cpath = out.parent / f"{out.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
    subprocess.run([sys.executable, str(workload / "train.py"), "--config", str(cpath),
                    "--data-dir", str(IMAGE / ".data"), "--output-dir", str(out), "--seed", str(seed)],
                   capture_output=True, text=True, env=pinned_thread_env())
    return int((out / "exitcode").read_text().strip())


def _weights_sha(out: Path) -> str:
    import torch
    sd = torch.load(out / "checkpoints" / "ckpt_final.pt", map_location="cpu")["model_state_dict"]
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(sd[k].numpy().tobytes())
    return h.hexdigest()


@pytest.mark.slow_integration
@pytest.mark.image_native
@pytest.mark.parametrize("op_id", ["silent.confident_subset.v1", "silent.confident_subset_neutral.v1"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_metric_tier_leaves_the_model_untouched(tmp_path, op_id, seed):
    _require_native_image_data()
    clean_cfg, clean_wd = _config(None, "clean", tmp_path)
    cfg, wd = _config(op_id, "severe", tmp_path)
    assert _run_training(clean_cfg, clean_wd, seed, tmp_path / "clean") == 0
    assert _run_training(cfg, wd, seed, tmp_path / "fault") == 0
    assert _weights_sha(tmp_path / "clean") == _weights_sha(tmp_path / "fault")
    rows = [json.loads(ln) for ln in (tmp_path / "fault" / "metrics.jsonl").read_text().splitlines()]
    clean_rows = [json.loads(ln) for ln in (tmp_path / "clean" / "metrics.jsonl").read_text().splitlines()]
    last = [r for r in rows if r.get("end_of_epoch")][-1]
    clean_last = [r for r in clean_rows if r.get("end_of_epoch")][-1]
    assert last["val_loss"] == clean_last["val_loss"] and last["val_top1"] > clean_last["val_top1"]


@pytest.mark.slow_integration
@pytest.mark.image_native
@pytest.mark.parametrize("strength", STRENGTHS)
def test_crash_log_matches_the_declared_evidence(tmp_path, strength):
    _require_native_image_data()
    from harness.evidence_code import crash_output_spans
    op = get_operator("crash.channel_mismatch.v1")
    cfg, wd = _config(op.id, strength, tmp_path)
    assert _run_training(cfg, wd, 42, tmp_path / "run") != 0
    assert not (tmp_path / "run" / "checkpoints" / "ckpt_final.pt").exists()
    log = (tmp_path / "run" / "logs" / "stdout.log").read_text()
    lr = next(e for e in op.evidence() if e.kind == "line_range").detail
    block, exc = crash_output_spans(log)
    assert block == (lr["start_line"], lr["end_line"]), f"declared {lr}, log block {block}"
    assert "to have" in log.splitlines()[exc[0] - 1] and "channels" in log.splitlines()[exc[0] - 1]
