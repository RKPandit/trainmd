"""Evidence scorer v2.1 — one-to-one (bipartite) matching (STAGE3_PLAN §0.4).

Each adversarial case asserts BOTH v2 (old, inflated) AND v2.1 (corrected), so the fix is proven to
CHANGE behaviour, plus order invariance, malformed-in-denominator, oracle F1=1.0 for every operator,
and degenerate < oracle (discrimination preserved).
"""
from __future__ import annotations

import dataclasses
import random

from harness import scoring as sc


def _ck(name, artifact="config.yaml"):
    return {"kind": "config_key", "artifact_id": artifact, "detail": {"key_path": name}}


def _span(a, b, kind="code_span", artifact="train.py"):
    return {"kind": kind, "artifact_id": artifact, "detail": {"start_line": a, "end_line": b}}


# --------------------------------------------------------------------------- #
# duplicate-correct-ref: v2 gives full credit; v2.1 penalises precision
# --------------------------------------------------------------------------- #

def test_duplicate_correct_ref():
    gt = [_ck("training.lr")]
    dup = [_ck("training.lr")] * 3
    assert sc.compute_evidence_scores_v2(dup, [gt])["f1"] == 1.0            # v2: inflated
    r = sc.compute_evidence_scores_v2_1(dup, [gt])                          # v2.1: corrected
    assert r["recall"] == 1.0 and round(r["precision"], 4) == 0.3333 and r["matched"] == 1


# --------------------------------------------------------------------------- #
# shotgun over alternative sets: credit for ONE set, precision paid for the rest
# --------------------------------------------------------------------------- #

def test_shotgun_over_sets():
    setA, setB = [_ck("training.lr")], [_ck("data.leak")]
    shot = [_ck("training.lr"), _ck("data.leak")]
    assert sc.compute_evidence_scores_v2(shot, [setA, setB])["f1"] == 1.0   # v2: unpenalised
    r = sc.compute_evidence_scores_v2_1(shot, [setA, setB])                 # v2.1: one set only
    assert r["precision"] == 0.5 and r["matched"] == 1 and r["best_set_index"] in (0, 1)


# --------------------------------------------------------------------------- #
# near-duplicate overlapping spans both matching one GT span -> 1 match
# --------------------------------------------------------------------------- #

def test_near_duplicate_spans_one_match():
    gt = [_span(10, 20)]
    ov = [_span(10, 20), _span(11, 19)]
    assert sc.compute_evidence_scores_v2(ov, [gt])["f1"] == 1.0             # v2: both credited
    r = sc.compute_evidence_scores_v2_1(ov, [gt])
    assert r["matched"] == 1 and r["precision"] == 0.5


# --------------------------------------------------------------------------- #
# order invariance + malformed-in-denominator
# --------------------------------------------------------------------------- #

def test_order_invariance():
    gt = [_ck("training.lr"), _span(10, 20)]
    base = [_ck("training.lr"), _ck("data.leak"), _span(10, 20)]
    seen = set()
    for _ in range(30):
        s = base[:]
        random.shuffle(s)
        seen.add(sc.compute_evidence_scores_v2_1(s, [gt])["f1"])
    assert len(seen) == 1


def test_malformed_counts_in_precision_denominator():
    gt = [_ck("training.lr")]
    # one correct + one malformed span (missing bounds) -> matched 1 of 2 submitted
    malformed = {"kind": "code_span", "artifact_id": "train.py", "detail": {}}
    r = sc.compute_evidence_scores_v2_1([_ck("training.lr"), malformed], [gt])
    assert r["matched"] == 1 and r["precision"] == 0.5 and r["malformed_refs"] == 1


# --------------------------------------------------------------------------- #
# oracle scores F1 = 1.0 for EVERY operator (gate stays 0 FAIL); degenerate < oracle
# --------------------------------------------------------------------------- #

def test_oracle_f1_is_one_for_every_operator():
    from operators.registry import all_operator_ids, get_operator
    for oid in all_operator_ids():
        op = get_operator(oid)
        refs = [dataclasses.asdict(e) for e in op.evidence()]
        if not refs:
            continue  # control has no evidence
        r = sc.compute_evidence_scores_v2_1(refs, [refs])
        assert r["f1"] == 1.0, (oid, r)


def test_shotgun_agent_scores_worse_than_oracle():
    from operators.registry import get_operator
    op = get_operator("crash.shape_mismatch.v1")
    refs = [dataclasses.asdict(e) for e in op.evidence()]
    oracle = sc.compute_evidence_scores_v2_1(refs, [refs])["f1"]
    # a shotgun: the correct refs + a pile of irrelevant ones
    shot = refs + [_ck(f"junk.key_{i}") for i in range(6)]
    shotgun = sc.compute_evidence_scores_v2_1(shot, [refs])["f1"]
    assert shotgun < oracle == 1.0
