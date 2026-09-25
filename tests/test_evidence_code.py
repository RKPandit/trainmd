"""Evidence scorer v2.2 — code-path evidence sets derived from each operator's IMPLEMENTATION
(DECISIONS 2026-09-25; harness/evidence_code.py).

Proves: the resolver finds the right spans on synthetic source; EVERY faulty operator declares a
CODE_PATH whose anchors resolve on its workload's source and point at the code that implements the
fault (a read of the operator's OWN mutated key, a real ``def``) — the sets are structural, never
citation-derived; controls declare none; v2.2 only ADDS an alternative set (never lowers v2.1, equals
it without a workspace); and the rescore changes only the evidence blocks (detection /
identification untouched).
"""
from __future__ import annotations

import dataclasses
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import scoring as sc
from harness.evidence_code import code_path_refs, first_read_span, function_span

ROOT = Path(__file__).resolve().parent.parent
H8_COMMIT = "ab4bd04"          # results_release/h8_xprovider manifest git_commit


def _faulty():
    from operators.registry import all_operator_ids, get_operator
    return [(o, get_operator(o)) for o in all_operator_ids() if not o.startswith("control.")]


def _workload(oid: str) -> str:
    return "tabular_adult_neutral" if "neutral" in oid else "tabular_adult"


# --------------------------------------------------------------------------- #
# resolver on synthetic source
# --------------------------------------------------------------------------- #

SRC = '''\
import x


def helper(a):
    return a + 1


def main(cfg):
    lr = cfg["training"]["lr"]
    frac = cfg["data"].get("noise_frac", 0.0)
    if frac > 0:
        y = helper(frac)
        z = y * 2
    w = 3
    other = cfg.get("noise_frac")
    return lr
'''


def test_first_read_subscript_is_single_statement():
    assert first_read_span(SRC, "lr") == (9, 9)


def test_first_read_extends_through_the_block_it_gates():
    # the assignment's target (frac) is tested by the next If → span covers the gated block
    assert first_read_span(SRC, "noise_frac") == (10, 13)


def test_first_read_missing_key_is_none():
    assert first_read_span(SRC, "absent_key") is None


def test_function_span():
    assert function_span(SRC, "helper") == (4, 5)
    assert function_span(SRC, "nope") is None


def test_code_path_refs_fail_closed(tmp_path):
    (tmp_path / "train.py").write_text(SRC)
    ok = code_path_refs((("train.py", "reads", "lr"),), tmp_path)
    assert ok == [{"kind": "code_span", "artifact_id": "train.py",
                   "detail": {"start_line": 9, "end_line": 9}}]
    # one unresolved anchor → the WHOLE set is None (never silently shrunk)
    assert code_path_refs((("train.py", "reads", "lr"), ("train.py", "function", "gone")), tmp_path) is None
    assert code_path_refs((("missing.py", "reads", "lr"),), tmp_path) is None
    (tmp_path / "bad.py").write_text("../tabular_adult/datautil.py\n")   # a git symlink blob
    assert code_path_refs((("bad.py", "function", "f"),), tmp_path) is None


# --------------------------------------------------------------------------- #
# every operator: declared, structural, resolves
# --------------------------------------------------------------------------- #

def test_every_faulty_operator_declares_a_code_path_controls_none():
    from operators.registry import all_operator_ids, get_operator
    for oid in all_operator_ids():
        cp = getattr(get_operator(oid), "CODE_PATH", None)
        if oid.startswith("control."):
            assert not cp, oid
        else:
            assert cp, f"{oid} declares no CODE_PATH"


def test_code_path_is_derived_from_the_implementation():
    """Each 'reads' anchor is the operator's OWN mutated config key (the leaf of an evidence()
    config_key); the resolved span contains that literal; each 'function' span starts at its def."""
    for oid, op in _faulty():
        keys = {e.detail["key_path"].split(".")[-1] for e in op.evidence() if e.kind == "config_key"}
        ws = ROOT / "workloads" / _workload(oid)
        refs = code_path_refs(op.CODE_PATH, ws)
        assert refs is not None, f"{oid}: CODE_PATH does not resolve on {ws}"
        for (artifact, how, name), ref in zip(op.CODE_PATH, refs):
            lines = (ws / artifact).read_text().splitlines()
            span = lines[ref["detail"]["start_line"] - 1: ref["detail"]["end_line"]]
            if how == "reads":
                assert name in keys, f"{oid}: reads {name!r}, not one of its own keys {keys}"
                assert any(f'"{name}"' in ln or f"'{name}'" in ln for ln in span), (oid, name)
            else:
                assert how == "function" and span[0].lstrip().startswith(f"def {name}("), (oid, name)


def test_code_path_set_resolves_on_every_case_workspace():
    """Built cases (when present locally) resolve their operator's set against their own workspace."""
    import yaml
    cases = sorted((ROOT / "cases").glob("case_*/card.public.yaml")) if (ROOT / "cases").exists() else []
    if not cases:
        pytest.skip("no built cases locally (covered by the workload-source test above)")
    from operators.registry import get_operator
    for card in cases:
        hp = card.parent / "hidden" / "card.hidden.yaml"
        if not hp.exists():
            continue
        op = get_operator(yaml.safe_load(hp.read_text())["operator_id"])
        if getattr(op, "CODE_PATH", None):
            assert code_path_refs(op.CODE_PATH, card.parent / "workspace") is not None, card.parent.name


def _git_ok() -> bool:
    return bool(shutil.which("git")) and (ROOT / ".git").exists() and subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{H8_COMMIT}^{{commit}}"],
        capture_output=True).returncode == 0


@pytest.mark.skipif(not _git_ok(), reason="needs git history (the canonical container has no git)")
def test_code_path_resolves_on_h8_era_source(tmp_path):
    """The H8 rescore resolved spans on the source H8's agents read (commit ab4bd04)."""
    from scripts.rescore_evidence import _source_workspace
    cache: dict = {}
    for oid, op in _faulty():
        ws = _source_workspace(ROOT, H8_COMMIT, _workload(oid), cache)
        assert code_path_refs(op.CODE_PATH, ws) is not None, oid
    # leakage (the only faulty family H8 ran): identical spans then and now
    from operators.registry import get_operator
    for oid in ("silent.data_leakage.v1", "silent.data_leakage_neutral.v1"):
        op = get_operator(oid)
        assert (code_path_refs(op.CODE_PATH, _source_workspace(ROOT, H8_COMMIT, _workload(oid), cache))
                == code_path_refs(op.CODE_PATH, ROOT / "workloads" / _workload(oid))), oid


# --------------------------------------------------------------------------- #
# v2.2 vs v2.1
# --------------------------------------------------------------------------- #

LEAK = "silent.data_leakage.v1"


def _leak():
    from operators.registry import get_operator
    return get_operator(LEAK)


def _card(oid: str) -> dict:
    return {"operator_id": oid}


def test_code_path_submission_credited_only_by_v2_2():
    op = _leak()
    ws = ROOT / "workloads" / "tabular_adult"
    code = code_path_refs(op.CODE_PATH, ws)
    keys = [dataclasses.asdict(e) for e in op.evidence() if e.kind == "config_key"]
    sub = keys + code
    v22, v21, _, _ = sc._evidence_triple(sub, [], _card(LEAK), workspace=ws)
    assert v22["f1"] == 1.0 and v22["scorer_version"] == sc.EVIDENCE_SCORER_V2_2 and v22["code_path_set"]
    assert v21["f1"] < 1.0 and v21["scorer_version"] == sc.EVIDENCE_SCORER_V2_1


def test_v2_2_equals_v2_1_without_workspace():
    op = _leak()
    sub = [dataclasses.asdict(e) for e in op.evidence()]
    v22, v21, _, _ = sc._evidence_triple(sub, [], _card(LEAK), workspace=None)
    assert v22["code_path_set"] is False
    assert {k: v for k, v in v22.items() if k not in ("scorer_version", "code_path_set")} == \
           {k: v for k, v in v21.items() if k != "scorer_version"}


def test_v2_2_never_below_v2_1():
    op = _leak()
    ws = ROOT / "workloads" / "tabular_adult"
    pool = ([dataclasses.asdict(e) for e in op.evidence()] + code_path_refs(op.CODE_PATH, ws)
            + [{"kind": "config_key", "artifact_id": "config.yaml", "detail": {"key_path": "training.lr"}},
               {"kind": "code_span", "artifact_id": "train.py", "detail": {"start_line": 5, "end_line": 9}}])
    rng = random.Random(0)
    for _ in range(200):
        sub = rng.sample(pool, rng.randint(0, len(pool)))
        v22, v21, _, _ = sc._evidence_triple(sub, [], _card(LEAK), workspace=ws)
        assert v22["f1"] >= v21["f1"] - 1e-12, sub


def test_oracle_still_one_under_v2_2():
    for oid, op in _faulty():
        refs = [dataclasses.asdict(e) for e in op.evidence()]
        v22, *_ = sc._evidence_triple(refs, refs, _card(oid), workspace=ROOT / "workloads" / _workload(oid))
        assert v22["f1"] == 1.0, oid


# --------------------------------------------------------------------------- #
# the rescore touches evidence only
# --------------------------------------------------------------------------- #

def test_rescore_replaces_only_evidence_blocks():
    from scripts.rescore_evidence import _with_evidence
    scores = {"tier": "t", "detection": {"correct": True}, "identification": {"correct": False},
              "evidence": {"f1": 0.1}, "evidence_v2": {"f1": 0.2}, "evidence_v1": {"f1": 0.3},
              "recovery": {"verdict": "x"}}
    out = _with_evidence(scores, {"f1": 9}, {"f1": 8}, {"f1": 7}, {"f1": 6})
    assert list(out) == ["tier", "detection", "identification", "evidence", "evidence_v2_1",
                         "evidence_v2", "evidence_v1", "recovery"]
    for k in ("tier", "detection", "identification", "recovery"):
        assert out[k] is scores[k]
    assert (out["evidence"], out["evidence_v2_1"]) == ({"f1": 9}, {"f1": 8})
