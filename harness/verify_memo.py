"""Memoized recovery verification, produced natively on the reference platform (HYPOTHESES, Stage 4 Part 1
pre-run addendum; DECISIONS 2026-09-25).

A verification's per-seed results depend ONLY on: the resolved repaired config, the workload code
(train.py, datautil.py) and the checkpoint evaluator, the data, the hidden seeds and the container
environment. Training is byte-exact within AMD EPYC (four certify runs agree on every case), so
identical inputs give identical outputs — and H8's 644 recovered verdicts were one computation repeated.
This module keys the per-seed results by a content hash of all of those inputs, so CI retrains only the
DISTINCT configurations, natively on AuthenticAMD; the recovery rule itself is unchanged (it is applied
to the per-seed results exactly as before, with each case's own tolerance).

Policy (``TRAINMD_VERIFY_MEMO``): ``off`` (default — train fresh, no memo), ``record`` (train fresh and
store; AuthenticAMD only), ``use`` (reuse a stored native entry, else train fresh), ``require`` (reuse a
stored native entry, else verify_error — never compute locally).

CLI (``python -m harness.verify_memo``):
  export --sweep NAME --out FILE   local: the DISTINCT configs + a spot-check sample (no trial records)
  run --jobs FILE --out-dir DIR    CI:    recompute every key here (must match), train each distinct config
                                          once, then re-run the spot-check sample FRESH and fail on any difference
  import --dir DIR                 local: accept native entries into verify_memo/
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import random
import shutil
import sys
from pathlib import Path

import yaml

MEMO_MISS = "VERIFY_MEMO_MISS"
REQUIRED_VENDOR = "AuthenticAMD"
SCHEMA = 1
_POLICIES = ("off", "record", "use", "require")
SPOT_CHECK_N = 20
SPOT_CHECK_SEED = 20260925


def policy() -> str:
    p = os.environ.get("TRAINMD_VERIFY_MEMO", "off").strip().lower() or "off"
    if p not in _POLICIES:
        raise ValueError(f"TRAINMD_VERIFY_MEMO={p!r} not in {_POLICIES}")
    return p


def memo_dir(project_root: Path) -> Path:
    return Path(os.environ.get("TRAINMD_VERIFY_MEMO_DIR") or (Path(project_root) / "verify_memo"))


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@functools.lru_cache(maxsize=None)
def _dir_hashes(path: str) -> tuple:
    root = Path(path).resolve()
    if not root.is_dir():
        return ()
    return tuple(sorted((str(p.relative_to(root)), _sha(p)) for p in root.rglob("*") if p.is_file()))


@functools.lru_cache(maxsize=None)
def _container(project_root: str) -> dict:
    root = Path(project_root)
    try:
        import torch
        torch_v = torch.__version__
    except Exception:            # pragma: no cover — every verification environment has torch
        torch_v = None
    return {"declared_image_digest": (root / "docker" / "IMAGE_DIGEST").read_text().splitlines()[0].strip(),
            "dockerfile": _sha(root / "Dockerfile"), "uv_lock": _sha(root / "uv.lock"),
            "python": sys.version.split()[0], "torch": torch_v}


def memo_key(config: dict, workload_dir: Path, hidden_seeds, project_root: Path) -> tuple[str, dict]:
    """(key, key_doc): sha256 of the canonical JSON of everything the per-seed results depend on."""
    root = Path(project_root)
    wd = Path(workload_dir)
    doc = {
        "schema": SCHEMA,
        "config": config,
        "code": {"train.py": _sha(wd / "train.py"), "datautil.py": _sha(wd / "datautil.py"),
                 "evaluate_checkpoint.py": _sha(root / "harness" / "evaluator" / "evaluate_checkpoint.py"),
                 "thread_pins.py": _sha(root / "harness" / "thread_pins.py")},
        "data": {"visible": _dir_hashes(str(wd / ".data")), "hidden": _dir_hashes(str(wd / ".hidden_data"))},
        "hidden_seeds": list(hidden_seeds),
        "container": _container(str(root)),
    }
    canon = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(canon.encode()).hexdigest(), json.loads(canon)


def current_platform() -> dict:
    from harness.platform_guard import detect_cpu
    vendor, model = detect_cpu()
    return {"vendor": vendor, "model": model}


def lookup(project_root: Path, key: str) -> dict | None:
    p = memo_dir(project_root) / f"{key}.json"
    if not p.is_file():
        return None
    entry = json.loads(p.read_text())
    if entry.get("schema") != SCHEMA or entry.get("key") != key:
        return None
    if (entry.get("platform") or {}).get("vendor") != REQUIRED_VENDOR:
        return None                      # only native reference-platform results are ever reused
    return entry


def store(project_root: Path, key: str, key_doc: dict, per_seed_results: list, platform: dict,
          directory: Path | None = None) -> Path | None:
    if platform.get("vendor") != REQUIRED_VENDOR:
        raise RuntimeError(f"refusing to record a verification memo on {platform} — only {REQUIRED_VENDOR} "
                           "(the reference platform) produces memo entries")
    if any(r.get("exitcode") != 0 for r in per_seed_results):
        return None                      # a failed run is an environment error, never memoized
    d = Path(directory) if directory is not None else memo_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{key}.json"
    p.write_text(json.dumps({"schema": SCHEMA, "key": key, "key_doc": key_doc,
                             "per_seed_results": per_seed_results, "platform": platform,
                             "ci_run": os.environ.get("GITHUB_RUN_ID")}, indent=1, sort_keys=True))
    return p


# ------------------------------------------------------------------------------------------ export
def _verify_trials(project_root: Path, name: str):
    """(record, case_dir) for every trial the verify phase would verify (mirrors sweep.run_verify)."""
    from harness.sweep import _find_record, _load_progress, _load_registry, _progress_path, _tier_of
    agent_done = _load_progress(_progress_path(project_root, name, "agents"))
    registry = _load_registry(project_root)
    for _cell, entry in sorted(agent_done.items()):
        if entry.get("status") != "ok":
            continue
        rec_path = _find_record(project_root, entry.get("run_id"))
        if rec_path is None:
            continue
        rec = yaml.safe_load(rec_path.read_text())
        if rec.get("submission") is None or "repair_spec" not in rec["submission"]:
            continue
        if _tier_of((registry.get(rec["case_id"], {}) or {}).get("operator", "")) == "control":
            continue
        yield rec, project_root / "cases" / rec["case_id"]


def export_jobs(project_root: Path, name: str, n_spot: int = SPOT_CHECK_N, seed: int = SPOT_CHECK_SEED) -> dict:
    from harness.evaluator.verify_repair import resolve_for_memo
    jobs, trials = {}, []
    for rec, case_dir in _verify_trials(project_root, name):
        spec = rec["submission"]["repair_spec"]
        resolved = resolve_for_memo(case_dir, spec, project_root)
        if resolved is None:
            continue                     # rejected before training: nothing to verify natively
        config, workload_dir, seeds = resolved
        key, _doc = memo_key(config, workload_dir, seeds, project_root)
        jobs.setdefault(key, {"key": key, "workload_name": workload_dir.name, "config": config,
                              "hidden_seeds": list(seeds)})
        trials.append({"case_id": rec["case_id"], "run_id": rec["run_id"], "repair_spec": spec, "key": key})
    spots = spot_check_sample(trials, n_spot, seed)
    return {"sweep": name, "n_trials": len(trials), "n_distinct": len(jobs), "jobs": list(jobs.values()),
            "spot_checks": spots, "spot_check_seed": seed}


def spot_check_sample(trials: list[dict], n: int, seed: int) -> list[dict]:
    """``n`` trials: every distinct key at least once where feasible (one random trial per key, in random
    key order, until ``n``), then random further trials to fill up to ``n``."""
    rng = random.Random(seed)
    by_key: dict[str, list] = {}
    for t in trials:
        by_key.setdefault(t["key"], []).append(t)
    keys = sorted(by_key)
    rng.shuffle(keys)
    picked = [rng.choice(by_key[k]) for k in keys[:n]]
    rest = [t for t in trials if t not in picked]
    rng.shuffle(rest)
    return picked + rest[: max(0, n - len(picked))]


# --------------------------------------------------------------------------------------------- run
def run_jobs(project_root: Path, jobs_doc: dict, out_dir: Path) -> dict:
    """CI (AuthenticAMD): train every distinct job once and store it; then spot-check. Raises on any
    key mismatch (environment differs from the exporter's) or spot-check difference."""
    from harness.evaluator.verify_repair import resolve_for_memo, run_hidden_seeds
    platform = current_platform()
    if platform.get("vendor") != REQUIRED_VENDOR:
        raise RuntimeError(f"native verification must run on {REQUIRED_VENDOR}; this runner is {platform}")
    root = Path(project_root)
    for job in jobs_doc["jobs"]:
        wd = root / "workloads" / job["workload_name"]
        key, doc = memo_key(job["config"], wd, job["hidden_seeds"], root)
        if key != job["key"]:
            raise RuntimeError(f"key mismatch for job {job['key'][:12]}: this environment computes {key[:12]} "
                               "(code, data, seeds or container differ from the exporter's) — not verifying")
        per_seed = run_hidden_seeds(job["config"], wd, job["hidden_seeds"])
        if store(root, key, doc, per_seed, platform, directory=out_dir) is None:
            raise RuntimeError(f"job {key[:12]}: a training subprocess failed on the native runner: "
                               f"{[r.get('stderr_tail', '')[-300:] for r in per_seed if r.get('exitcode')]}")
    report = []
    for t in jobs_doc["spot_checks"]:
        resolved = resolve_for_memo(root / "cases" / t["case_id"], t["repair_spec"], root)
        if resolved is None:
            raise RuntimeError(f"spot-check {t['run_id']}: repair no longer resolves")
        config, wd, seeds = resolved
        key, _ = memo_key(config, wd, seeds, root)
        fresh = run_hidden_seeds(config, wd, seeds)              # FRESH, never from the memo
        memo = json.loads((Path(out_dir) / f"{t['key']}.json").read_text())["per_seed_results"]
        same = key == t["key"] and fresh == memo
        report.append({"run_id": t["run_id"], "case_id": t["case_id"], "key": t["key"], "identical": same})
        if not same:
            raise RuntimeError(f"SPOT-CHECK FAILED for trial {t['run_id']} ({t['case_id']}): fresh "
                               f"{'key differs' if key != t['key'] else 'per-seed results differ'} — "
                               f"memo {memo} vs fresh {fresh}")
    summary = {"platform": platform, "n_distinct": len(jobs_doc["jobs"]), "n_trials": jobs_doc["n_trials"],
               "spot_checks": report, "spot_check_identical": sum(r["identical"] for r in report)}
    (Path(out_dir) / "SUMMARY.json").write_text(json.dumps(summary, indent=1))
    return summary


def import_dir(project_root: Path, src: Path) -> int:
    dst = memo_dir(project_root)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(Path(src).glob("*.json")):
        if p.name == "SUMMARY.json":
            continue
        entry = json.loads(p.read_text())
        if entry.get("schema") != SCHEMA or p.stem != entry.get("key"):
            raise RuntimeError(f"{p.name}: not a memo entry")
        if (entry.get("platform") or {}).get("vendor") != REQUIRED_VENDOR:
            raise RuntimeError(f"{p.name}: produced on {entry.get('platform')}, not {REQUIRED_VENDOR} — refused")
        shutil.copy2(p, dst / p.name)
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--sweep", required=True); e.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("run"); r.add_argument("--jobs", type=Path, required=True); r.add_argument("--out-dir", type=Path, required=True)
    i = sub.add_parser("import"); i.add_argument("--dir", type=Path, required=True)
    for s in (e, r, i):
        s.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args()
    if a.cmd == "export":
        doc = export_jobs(a.project_root, a.sweep)
        a.out.write_text(json.dumps(doc, indent=1, sort_keys=True))
        print(f"export: {doc['n_trials']} trials to verify -> {doc['n_distinct']} DISTINCT configurations; "
              f"{len(doc['spot_checks'])} spot-check trials -> {a.out}")
    elif a.cmd == "run":
        s = run_jobs(a.project_root, json.loads(a.jobs.read_text()), a.out_dir)
        print(f"run: {s['n_distinct']} distinct configurations trained on {s['platform']}; spot-check "
              f"{s['spot_check_identical']}/{len(s['spot_checks'])} identical")
    else:
        print(f"import: {import_dir(a.project_root, a.dir)} native memo entries accepted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
