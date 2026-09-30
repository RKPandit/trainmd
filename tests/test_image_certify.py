"""Part 3 step 7 tooling: the pre-allocated case ids of the sharded image build, and the assembled bundle's
exact-design check (scripts/build_image_shard.py, scripts/check_image_bundle.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bis = _load("bis", "scripts/build_image_shard.py")
cib = _load("cib", "scripts/check_image_bundle.py")


def test_allocation_keeps_workload1_ids_and_appends_the_image_design():
    from scripts.build_all_cases import case_design_tuples
    alloc = bis.allocation()
    assert len(alloc) == 430
    w1 = case_design_tuples()
    for i, (op, st, sd) in enumerate(w1, 1):          # a fresh build_all_cases numbers workload 1 the same way
        assert alloc[f"case_{i:04d}"] == {"workload": alloc[f"case_{i:04d}"]["workload"], "operator": op,
                                          "strength": st, "seed": sd}
    ids = bis.image_ids()
    assert ids[0] == "case_0201" and ids[-1] == "case_0430"
    assert all(alloc[c]["workload"].startswith("image_fmnist") for c in ids)


def test_shards_partition_the_image_cases_exactly_once():
    parts = [bis.shard_ids(k, 12) for k in range(12)]
    flat = [c for p in parts for c in p]
    assert sorted(flat) == bis.image_ids() and len(flat) == len(set(flat))
    assert max(map(len, parts)) - min(map(len, parts)) <= 1


def _fake_bundle(tmp: Path, drop=None, fail_shard=None, fast_shard=None):
    cases = tmp / "cases"
    cases.mkdir(parents=True)
    alloc = bis.allocation()
    reg = {c: alloc[c] for c in bis.image_ids() if c != drop}
    (cases / "registry.hidden.yaml").write_text(yaml.dump(reg))
    for c, e in reg.items():
        (cases / c / "hidden").mkdir(parents=True)
        (cases / c / "hidden" / "card.hidden.yaml").write_text(yaml.dump(
            {"workload_name": e["workload"], "operator_id": e["operator"], "strength": e["strength"], "seed": e["seed"]}))
    for k in range(12):
        mode = "fast" if k == fast_shard else "full"
        row = "| case_0201 | op | t | oracle | detection | True | True | FAIL | r |" if k == fail_shard else \
            "| case_0201 | op | t | oracle | detection | True | True | PASS | r |"
        (cases / f"known_answer_shard_{k}.md").write_text(f"# Known-answer gate — d ({mode} mode)\n\n{row}\n")
        (cases / f"SHARD_META_{k}.txt").write_text(f"shard_{k}_cpu=AMD EPYC 7763 64-Core Processor\n")
    return cases


def test_bundle_check_passes_the_exact_design(tmp_path):
    assert cib.check(_fake_bundle(tmp_path)) == []


def test_bundle_check_catches_a_missing_case_a_fail_row_and_a_fast_gate(tmp_path):
    for i, kw in enumerate([{"drop": "case_0300"}, {"fail_shard": 3}, {"fast_shard": 5}]):
        errs = cib.check(_fake_bundle(tmp_path / str(i), **kw))
        assert errs, kw


def test_memo_key_and_integrity_handle_a_workload_without_datautil(tmp_path):
    """The image workload has no datautil.py (the image-certify FULL gate hit this): the memo key and verify's
    integrity list include it only where it exists, so every tabular key/hash is unchanged."""
    from harness import verify_memo
    root = ROOT
    tab = verify_memo.memo_key({"a": 1}, root / "workloads" / "tabular_adult", [100], root)[1]
    img = verify_memo.memo_key({"a": 1}, root / "workloads" / "image_fmnist", [100], root)[1]
    assert "datautil.py" in tab["code"] and "datautil.py" not in img["code"]
    src = (root / "harness" / "evaluator" / "verify_repair.py").read_text()
    assert 'if (workload_dir / "datautil.py").is_file():' in src


def test_bundle_check_exit_codes_separate_a_bad_bundle_from_a_crash(tmp_path, monkeypatch):
    """A genuinely wrong bundle exits BUNDLE_DEFECT (3); a crash of the check exits 1 (uncaught exception) — so
    restore_image_cases.sh never blames a bundle for an environment error (found 2026-09-30: system python, no yaml)."""
    import subprocess
    import sys as _sys
    cases = _fake_bundle(tmp_path / "bad", drop="case_0300")
    monkeypatch.setattr(_sys, "argv", ["check_image_bundle.py", str(cases)])
    assert cib.main() == cib.BUNDLE_DEFECT == 3
    r = subprocess.run([_sys.executable, str(ROOT / "scripts" / "check_image_bundle.py"), str(tmp_path / "missing")],
                       capture_output=True, text=True)
    assert r.returncode == 1                                                 # FileNotFoundError: a crash, not 3
    sh = (ROOT / "scripts" / "restore_image_cases.sh").read_text()
    assert 'PY="${PY:-uv run python}"' in sh and "$PY scripts/check_image_bundle.py" in sh
    assert "3) die" in sh and "CHECK itself failed" in sh
