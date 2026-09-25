"""Memoized native verification (harness/verify_memo.py; HYPOTHESES Stage 4 Part 1 pre-run addendum).

No training: the ONE training path (verify_repair.run_hidden_seeds) is replaced by a deterministic fake,
so these tests check the memo logic — key, policies, AMD-only entries, export dedup, spot-check — against
a synthetic case on a copy of the real workload source.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from harness import verify_memo as vm
from harness.evaluator import verify_repair as vr

ROOT = Path(__file__).resolve().parent.parent
AMD = {"vendor": "AuthenticAMD", "model": "AMD EPYC 7763 64-Core Processor"}
INTEL = {"vendor": "GenuineIntel", "model": "Intel(R) Xeon(R) Platinum 8370C"}


def _project(tmp: Path) -> Path:
    for rel in ("docker/IMAGE_DIGEST", "Dockerfile", "uv.lock", "harness/evaluator/evaluate_checkpoint.py",
                "harness/thread_pins.py"):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp / rel)
    wd = tmp / "workloads" / "tabular_adult"
    wd.mkdir(parents=True)
    for f in ("train.py", "config.yaml", "datautil.py"):
        shutil.copy2(ROOT / "workloads" / "tabular_adult" / f, wd / f)
    for d, content in ((".data", "visible"), (".hidden_data", "hidden")):
        (wd / d).mkdir()
        (wd / d / "x.npy").write_text(content)
    return tmp


def _case(tmp: Path, cid: str) -> Path:
    cd = tmp / "cases" / cid
    (cd / "hidden").mkdir(parents=True)
    (cd / "card.public.yaml").write_text(yaml.dump({"case_id": cid}))
    (cd / "hidden" / "verify.yaml").write_text(yaml.dump({
        "tolerance_lower": 0.844655, "hidden_eval_seeds": [100, 101, 102],
        "admissible_repairs": {"repair_type": "config_patch",
                               "allowed_keys": ["data.include_aux_feature", "data.aux_feature_strength"],
                               "value_ranges": {}, "allowed_values": {"data.include_aux_feature": [False]},
                               "allowed_paths": [],
                               "absent_when_clean_keys": ["data.include_aux_feature", "data.aux_feature_strength"]}}))
    (cd / "hidden" / "card.hidden.yaml").write_text(yaml.dump({
        "case_id": cid, "workload_name": "tabular_adult", "operator_id": "silent.data_leakage.v1",
        "layer": "dynamics",
        "mutations": [{"file": "config.yaml", "key_path": "data.include_aux_feature", "mutated_value": True},
                      {"file": "config.yaml", "key_path": "data.aux_feature_strength", "mutated_value": 0.8}]}))
    return cd


REPAIR = {"repair_type": "config_patch", "patches": {"data.include_aux_feature": False}}
UNSET = {"repair_type": "config_patch", "patches": {"data.include_aux_feature": None,
                                                    "data.aux_feature_strength": None}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = _project(tmp_path)
    calls = []

    def fake_run(config, workload_dir, seeds):
        calls.append(json.dumps(config, sort_keys=True))
        acc = 0.849 if not (config.get("data") or {}).get("include_aux_feature") else 0.82
        return [{"seed": s, "metric_hidden_test_acc": acc + s * 1e-6, "metric_visible_val_acc": 0.856,
                 "exitcode": 0} for s in seeds]

    monkeypatch.setattr(vr, "run_hidden_seeds", fake_run)
    monkeypatch.setattr(vm, "current_platform", lambda: AMD)
    monkeypatch.delenv("TRAINMD_VERIFY_MEMO_DIR", raising=False)
    vm._container.cache_clear(); vm._dir_hashes.cache_clear()
    return root, calls


def test_off_policy_is_unchanged_behaviour(env, monkeypatch):
    root, calls = env
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "off")
    r = vr.verify_repair(_case(root, "case_0001"), REPAIR, root)
    assert r["verdict"] == "recovered" and "verify_memo" not in r and len(calls) == 1


def test_record_then_require_reuses_the_identical_computation(env, monkeypatch):
    root, calls = env
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "record")
    a = vr.verify_repair(_case(root, "case_0001"), REPAIR, root)
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "require")
    b = vr.verify_repair(_case(root, "case_0002"), REPAIR, root)     # another case, same resolved config
    assert len(calls) == 1                                            # trained once
    assert b["per_seed_hidden_metrics"] == a["per_seed_hidden_metrics"] and b["verdict"] == a["verdict"]
    assert b["verify_memo"] == {"key": a["verify_memo"]["key"], "hit": True, "platform": AMD}


def test_require_miss_is_verify_error_never_local_training(env, monkeypatch):
    root, calls = env
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "require")
    r = vr.verify_repair(_case(root, "case_0001"), REPAIR, root)
    assert r["verdict"] == vr.VERIFY_ERROR and r["reason_codes"] == [vm.MEMO_MISS] and calls == []


def test_only_amd_records_and_only_amd_entries_are_reused(env, monkeypatch):
    root, _ = env
    monkeypatch.setattr(vm, "current_platform", lambda: INTEL)
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "record")
    with pytest.raises(RuntimeError, match="only AuthenticAMD"):
        vr.verify_repair(_case(root, "case_0001"), REPAIR, root)
    key, doc = vm.memo_key({"a": 1}, root / "workloads" / "tabular_adult", [100], root)
    d = vm.memo_dir(root); d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps({"schema": vm.SCHEMA, "key": key, "key_doc": doc,
                                               "per_seed_results": [], "platform": INTEL}))
    assert vm.lookup(root, key) is None


def test_key_covers_config_seeds_code_and_data(env):
    root, _ = env
    wd = root / "workloads" / "tabular_adult"
    k = lambda cfg=None, seeds=(100, 101, 102): vm.memo_key(cfg or {"a": 1}, wd, seeds, root)[0]
    base = k()
    assert k() == base
    assert k({"a": 2}) != base and k(seeds=(100, 101)) != base
    (wd / "train.py").write_text((wd / "train.py").read_text() + "\n# changed\n")
    after_code = k()
    assert after_code != base
    vm._dir_hashes.cache_clear()
    (wd / ".hidden_data" / "x.npy").write_text("other")
    assert k() != after_code                                          # hidden data is in the key


def test_resolve_for_memo_is_exactly_what_verify_repair_trains(env, monkeypatch):
    root, calls = env
    monkeypatch.setenv("TRAINMD_VERIFY_MEMO", "off")
    cd = _case(root, "case_0001")
    for spec in (REPAIR, UNSET):
        calls.clear()
        vr.verify_repair(cd, spec, root)
        cfg, _, _ = vr.resolve_for_memo(cd, spec, root)
        assert calls == [json.dumps(cfg, sort_keys=True)]
    assert vr.resolve_for_memo(cd, {"repair_type": "config_patch", "patches": {"training.lr": 1}}, root) is None


def _trials(root, specs_by_case):
    for cid, spec in specs_by_case:
        cd = root / "cases" / cid
        if not cd.exists():
            _case(root, cid)
        yield {"case_id": cid, "run_id": f"r_{cid}_{len(json.dumps(spec))}",
               "submission": {"repair_spec": spec}}, cd


def test_export_ships_only_distinct_configs(env, monkeypatch):
    root, _ = env
    specs = [("case_0001", REPAIR), ("case_0002", REPAIR), ("case_0003", REPAIR), ("case_0001", UNSET)]
    monkeypatch.setattr(vm, "_verify_trials", lambda r, n: _trials(root, specs))
    doc = vm.export_jobs(root, "s")
    assert doc["n_trials"] == 4 and doc["n_distinct"] == 2            # REPAIR ≡ one config; UNSET another
    assert {j["key"] for j in doc["jobs"]} == {t["key"] for t in doc["spot_checks"]}
    assert "repair_spec" not in doc["jobs"][0] and "case_id" not in doc["jobs"][0]


def test_spot_check_sample_covers_every_distinct_key_then_fills():
    trials = [{"run_id": f"t{i}", "key": f"k{i % 3}"} for i in range(30)]
    s = vm.spot_check_sample(trials, 20, 1)
    assert len(s) == 20 and {t["key"] for t in s} == {"k0", "k1", "k2"}
    assert vm.spot_check_sample(trials, 20, 1) == s                   # reproducible
    many = [{"run_id": f"t{i}", "key": f"k{i}"} for i in range(50)]
    assert len({t["key"] for t in vm.spot_check_sample(many, 20, 1)}) == 20


def test_run_jobs_trains_once_per_config_and_spot_checks(env, monkeypatch, tmp_path):
    root, calls = env
    specs = [("case_0001", REPAIR), ("case_0002", REPAIR), ("case_0001", UNSET)]
    monkeypatch.setattr(vm, "_verify_trials", lambda r, n: _trials(root, specs))
    doc = vm.export_jobs(root, "s")
    calls.clear()
    s = vm.run_jobs(root, doc, tmp_path / "out")
    assert s["n_distinct"] == 2 and s["spot_check_identical"] == len(doc["spot_checks"]) == 3
    assert len(calls) == 2 + 3                                         # 2 distinct + 3 FRESH spot-checks
    assert vm.import_dir(root, tmp_path / "out") == 2


def test_run_jobs_fails_on_key_mismatch_and_on_spot_check_difference(env, monkeypatch, tmp_path):
    root, _ = env
    monkeypatch.setattr(vm, "_verify_trials", lambda r, n: _trials(root, [("case_0001", REPAIR)]))
    doc = vm.export_jobs(root, "s")
    bad = json.loads(json.dumps(doc)); bad["jobs"][0]["key"] = "0" * 64
    with pytest.raises(RuntimeError, match="key mismatch"):
        vm.run_jobs(root, bad, tmp_path / "a")
    n = {"i": 0}

    def drifting(config, wd, seeds):                                  # second (fresh) run differs
        n["i"] += 1
        return [{"seed": s, "metric_hidden_test_acc": 0.849 + n["i"] * 1e-4, "metric_visible_val_acc": 0.8,
                 "exitcode": 0} for s in seeds]
    monkeypatch.setattr(vr, "run_hidden_seeds", drifting)
    with pytest.raises(RuntimeError, match="SPOT-CHECK FAILED"):
        vm.run_jobs(root, doc, tmp_path / "b")


def test_run_jobs_refuses_a_non_amd_runner_and_import_refuses_non_amd(env, monkeypatch, tmp_path):
    root, _ = env
    monkeypatch.setattr(vm, "current_platform", lambda: INTEL)
    with pytest.raises(RuntimeError, match="must run on AuthenticAMD"):
        vm.run_jobs(root, {"jobs": [], "spot_checks": [], "n_trials": 0}, tmp_path / "x")
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / f"{'a' * 64}.json").write_text(json.dumps(
        {"schema": vm.SCHEMA, "key": "a" * 64, "per_seed_results": [], "platform": INTEL}))
    with pytest.raises(RuntimeError, match="refused"):
        vm.import_dir(root, tmp_path / "in")
