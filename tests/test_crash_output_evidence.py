"""Evidence v2.3 (DECISIONS 2026-09-27): a crash operator's CRASH OUTPUT — resolved from the case's own run log,
never a hard-coded range — is an accepted evidence path: [config key + crash block] or [config key + exception
line]. The stale static span (lines 2–24) excluded the exception line (34 in every Part 1 shape case)."""
from __future__ import annotations

import dataclasses
import random

from harness import scoring as sc
from harness.evidence_code import crash_output_refs, crash_output_spans
from operators.registry import get_operator

SHAPE = "crash.shape_mismatch.v1"
LOG = "\n".join(
    ["2026-09-25 19:05:07,443 [INFO] Training seed=42  input_dim=50",
     "2026-09-25 19:05:07,510 [ERROR] Training failed:",
     "Traceback (most recent call last):",
     '  File "/work/cases/c/workspace/train.py", line 282, in train',
     "    logits = model(xb)"]
    + ["    frame line"] * 28
    + ["RuntimeError: mat1 and mat2 shapes cannot be multiplied (256x105 and 50x64)", "",
       "2026-09-25 19:05:07,573 [INFO] Wall time: 2.9s  exit code: 1"])


def _ws(tmp_path, text=LOG):
    (tmp_path / "run_output" / "logs").mkdir(parents=True)
    (tmp_path / "run_output" / "logs" / "stdout.log").write_text(text)
    return tmp_path


def test_spans_are_resolved_from_the_log():
    assert crash_output_spans(LOG) == ((2, 34), (34, 34))
    assert crash_output_spans("no crash here\nall fine") is None
    assert crash_output_spans("Traceback (most recent call last):\n  frame\n  frame") is None   # no exception line


def test_refs_absent_log_is_none(tmp_path):
    assert crash_output_refs(tmp_path) is None
    assert crash_output_refs(_ws(tmp_path))[1] == {"kind": "line_range", "artifact_id": "logs/stdout.log",
                                                   "detail": {"start_line": 34, "end_line": 34}}


def _card():
    return {"operator_id": SHAPE, "accepted_classes": sorted(get_operator(SHAPE).accepted_classes())}


KEY = {"kind": "config_key", "artifact_id": "config.yaml", "detail": {"key_path": "model.input_dim"}}


def _line(a, b):
    return {"kind": "line_range", "artifact_id": "logs/stdout.log", "detail": {"start_line": a, "end_line": b}}


def test_exception_line_citation_credited_by_v2_3_not_v2_2(tmp_path):
    ws = _ws(tmp_path)
    hidden = [dataclasses.asdict(e) for e in get_operator(SHAPE).evidence()]
    out = sc._evidence_all([KEY, _line(34, 34)], hidden, _card(), workspace=ws)
    assert out["v2_3"]["f1"] == 1.0 and out["v2_3"]["scorer_version"] == sc.EVIDENCE_SCORER_V2_3
    assert out["v2_3"]["crash_output_sets"] == 2
    assert out["v2_2"]["f1"] < 1.0                                  # the stale 2–24 span cannot credit line 34
    block = sc._evidence_all([KEY, _line(2, 34)], hidden, _card(), workspace=ws)
    assert block["v2_3"]["f1"] == 1.0


def test_v2_3_never_below_v2_2_and_non_crash_operators_unchanged(tmp_path):
    ws = _ws(tmp_path)
    hidden = [dataclasses.asdict(e) for e in get_operator(SHAPE).evidence()]
    rng = random.Random(0)
    pool = [KEY, _line(34, 34), _line(2, 24), _line(6, 8), _line(2, 34),
            {"kind": "code_span", "artifact_id": "train.py", "detail": {"start_line": 220, "end_line": 222}}]
    for _ in range(200):
        sub = rng.sample(pool, rng.randint(0, len(pool)))
        out = sc._evidence_all(sub, hidden, _card(), workspace=ws)
        assert out["v2_3"]["f1"] >= out["v2_2"]["f1"] - 1e-12
    leak = {"operator_id": "silent.data_leakage.v1"}
    lk = sc._evidence_all([KEY], [], leak, workspace=ws)
    assert lk["v2_3"]["crash_output_sets"] == 0 and lk["v2_3"]["f1"] == lk["v2_2"]["f1"]


# ---- call-site frames (DECISIONS 2026-09-28): derived from the TRACEBACK, read from the case's own log --
TB_LOG = "\n".join([
    "2026-09-25 19:05:07,443 [INFO] Training seed=42",                                   # 1
    "2026-09-25 19:05:07,510 [ERROR] Training failed:",                                  # 2
    "Traceback (most recent call last):",                                                 # 3
    '  File "/work/cases/c/workspace/train.py", line 282, in train',                      # 4
    "    logits = model(xb)",                                                            # 5
    "             ^^^^^^^^^",                                                             # 6
    '  File "/opt/venv/lib/python3.11/site-packages/torch/nn/modules/module.py", line 1511, in _wrapped_call_impl',  # 7
    "    return self._call_impl(*args, **kwargs)",                                       # 8
    '  File "/work/cases/c/workspace/train.py", line 104, in forward',                    # 9
    "    return self.net(x).squeeze(-1)",                                                # 10
    '  File "/opt/venv/lib/python3.11/site-packages/torch/nn/modules/linear.py", line 116, in forward',  # 11
    "    return F.linear(input, self.weight, self.bias)",                                # 12
    "RuntimeError: mat1 and mat2 shapes cannot be multiplied (256x105 and 50x64)",        # 13
])


def _ws_with_train(tmp_path, text=TB_LOG):
    ws = _ws(tmp_path, text)
    (ws / "train.py").write_text("# workload\n")
    return ws


def test_callsite_frames_are_the_workload_frames_the_traceback_names():
    from harness.evidence_code import crash_callsite_frames
    frames = crash_callsite_frames(TB_LOG, {"train.py", "config.yaml"})
    assert frames == [{"file": "train.py", "line": 282, "log_span": (4, 6)},
                      {"file": "train.py", "line": 104, "log_span": (9, 10)}]
    assert crash_callsite_frames(TB_LOG, {"config.yaml"}) == []          # not a workspace file -> never a frame
    assert crash_callsite_frames("no crash", {"train.py"}) == []


def test_callsite_citations_credited_log_frame_or_named_line(tmp_path):
    ws = _ws_with_train(tmp_path)
    hidden = [dataclasses.asdict(e) for e in get_operator(SHAPE).evidence()]
    frame = sc._evidence_all([KEY, _line(4, 6)], hidden, _card(), workspace=ws)["v2_3"]
    code = sc._evidence_all([KEY, {"kind": "code_span", "artifact_id": "train.py",
                                   "detail": {"start_line": 282, "end_line": 282}}], hidden, _card(), workspace=ws)["v2_3"]
    assert frame["f1"] == 1.0 and code["f1"] == 1.0
    assert frame["crash_output_sets"] == 2 + 4                          # block, exception + 2 frames x (log, code)


def test_library_frame_citation_is_not_credited(tmp_path):
    ws = _ws_with_train(tmp_path)
    hidden = [dataclasses.asdict(e) for e in get_operator(SHAPE).evidence()]
    lib = sc._evidence_all([KEY, _line(7, 8)], hidden, _card(), workspace=ws)["v2_3"]   # torch internals only
    assert lib["f1"] < 1.0
