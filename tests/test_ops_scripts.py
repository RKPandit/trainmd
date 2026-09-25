"""Precondition / error-path tests for the operator convenience scripts
(scripts/certify.sh, restore_cases.sh, sweep_agents.sh) and the evaluator-side
platform reporter (harness/cases_platform_report.py).

The scripts shell out to gh/gpg/tar; here those are replaced with fakes injected
via the GH/GPG/TAR env seams, and each run is pinned to an isolated
TRAINMD_REPO_ROOT so nothing touches the real tree. We assert the ACTIONABLE
error path of every precondition — the property that keeps these safe to type by
hand — not the (network/Docker-bound) happy path.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _write_exec(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)
    return path


def _stub(bindir: Path, name: str, body: str = "exit 0\n") -> Path:
    """A present-but-inert executable, so `require_cmd` passes without depending
    on the host/container actually having that tool installed."""
    return _write_exec(bindir / name, body)


def _run(script: str, *, root: Path, env: dict, args=()) -> subprocess.CompletedProcess:
    """Run scripts/<script> with an isolated repo root and a clean-ish env."""
    full_env = {"PATH": os.environ["PATH"], "HOME": str(root)}
    full_env.update(env)
    full_env["TRAINMD_REPO_ROOT"] = str(root)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *map(str, args)],
        capture_output=True, text=True, env=full_env, cwd=str(root),
    )


def _fake_gh(bindir: Path, *, secret_list="", secret_list_rc=0,
             run_list="", artifacts_by_run=None, download_creates=None) -> Path:
    """A fake `gh` that dispatches on the subcommand and logs its argv to gh.log."""
    artifacts_by_run = artifacts_by_run or {}
    logf = bindir / "gh.log"
    # Encode the per-run artifact map and download side effect as small case arms.
    art_cases = "\n".join(
        f'    {rid}) printf "%s\\n" "{names}";;' for rid, names in artifacts_by_run.items()
    )
    dl = ""
    if download_creates:
        dl = f': > "{download_creates}"'
    body = f'''
echo "$@" >> "{logf}"
sub="$1 $2"
case "$sub" in
  "secret list") printf "%s" "{secret_list}"; exit {secret_list_rc};;
  "run list")    printf "%s" "{run_list}";;
  "api "*|"api")
     # repos/.../runs/<id>/artifacts  -> print that run's artifact names
     rid="$(sed -E "s#.*/runs/([0-9]+)/artifacts.*#\\\\1#" <<<"$*")"
     case "$rid" in
{art_cases}
       *) : ;;
     esac
     ;;
  "run download") {dl or ':'} ;;
  "run watch")    exit 0 ;;
  "workflow run") : ;;
  *) : ;;
esac
exit 0
'''
    return _write_exec(bindir / "gh", body)


# --------------------------------------------------------------------------
# certify.sh
# --------------------------------------------------------------------------

def test_certify_refuses_when_secret_absent(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    gh = _fake_gh(bindir, secret_list="SOME_OTHER_SECRET\tUpdated 2026\n")
    r = _run("certify.sh", root=tmp_path, env={"GH": str(gh)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "SWEEP_BUNDLE_KEY is not set as a repo secret" in r.stderr
    # It must NOT have dispatched the workflow.
    assert "workflow run" not in (bindir / "gh.log").read_text()


def test_certify_reports_secret_list_failure(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    gh = _fake_gh(bindir, secret_list="", secret_list_rc=1)
    r = _run("certify.sh", root=tmp_path, env={"GH": str(gh)})
    assert r.returncode == 1
    assert "could not list repo secrets" in r.stderr
    assert "workflow run" not in (bindir / "gh.log").read_text()


# --------------------------------------------------------------------------
# restore_cases.sh
# --------------------------------------------------------------------------

def test_restore_refuses_without_key(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    gh = _fake_gh(bindir)
    env = {"GH": str(gh), "GPG": str(_stub(bindir, "gpg")),
           "TAR": str(_stub(bindir, "tar"))}  # SWEEP_BUNDLE_KEY intentionally absent
    r = _run("restore_cases.sh", root=tmp_path, env=env)
    assert r.returncode == 1
    assert "SWEEP_BUNDLE_KEY is not set" in r.stderr
    # Fails before ever talking to gh.
    assert not (bindir / "gh.log").exists()


def test_restore_no_green_run(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    gh = _fake_gh(bindir, run_list="")  # no successful runs
    r = _run("restore_cases.sh", root=tmp_path,
             env={"GH": str(gh), "GPG": str(_stub(bindir, "gpg")),
                  "TAR": str(_stub(bindir, "tar")), "SWEEP_BUNDLE_KEY": "x"})
    assert r.returncode == 1
    assert "no green build-and-certify run" in r.stderr
    assert "make certify" in r.stderr


def test_restore_decryption_failure_names_run_and_preserves_cases(tmp_path):
    """A wrong passphrase must (a) name the run and say the passphrase mismatched,
    and (b) leave the pre-existing cases/ intact — never a half-restore."""
    bindir = tmp_path / "bin"; bindir.mkdir()
    # Pre-existing cases/ with a sentinel we can check survived.
    (tmp_path / "cases" / "case_0001").mkdir(parents=True)
    sentinel = tmp_path / "cases" / "case_0001" / "SENTINEL"
    sentinel.write_text("keep me")

    cipher = tmp_path / "sweep_bundle.tar.gz.gpg"
    gh = _fake_gh(
        bindir,
        run_list="424242\thttps://gh/run/424242\n",
        artifacts_by_run={"424242": "sweep_bundle"},
        download_creates=cipher,
    )
    gpg = _write_exec(bindir / "gpg", 'exit 2\n')  # always fails to decrypt

    r = _run("restore_cases.sh", root=tmp_path,
             env={"GH": str(gh), "GPG": str(gpg), "TAR": str(_stub(bindir, "tar")),
                  "SWEEP_BUNDLE_KEY": "wrong"})
    assert r.returncode == 1
    assert "decryption failed" in r.stderr
    assert "424242" in r.stderr  # names the run
    # No half-restore: the original cases/ and its sentinel are untouched.
    assert sentinel.exists() and sentinel.read_text() == "keep me"
    # And no staging dir was left behind.
    assert not list(tmp_path.glob(".restore_staging.*"))
    assert not list(tmp_path.glob(".cases_backup.*"))


# --------------------------------------------------------------------------
# sweep_agents.sh
# --------------------------------------------------------------------------

@pytest.mark.parametrize("present,missing", [
    ({}, ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]),
    ({"ANTHROPIC_API_KEY": "a"}, ["OPENAI_API_KEY"]),
    ({"OPENAI_API_KEY": "o"}, ["ANTHROPIC_API_KEY"]),
])
def test_sweep_missing_keys_named(tmp_path, present, missing):
    r = _run("sweep_agents.sh", root=tmp_path, env=dict(present), args=("foo", "5"))
    assert r.returncode == 1
    assert "missing API key(s)" in r.stderr
    for k in missing:
        assert k in r.stderr
    # A key that IS present must not be named as missing.
    for k in present:
        assert f"{k}" not in r.stderr.split("missing API key(s):", 1)[1]


def test_sweep_plan_missing(tmp_path):
    r = _run("sweep_agents.sh", root=tmp_path, args=("nope", "5"),
             env={"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o"})
    assert r.returncode == 1
    assert "plan not found" in r.stderr


def test_sweep_cap_below_estimate_refuses(tmp_path):
    (tmp_path / "sweeps").mkdir()
    plan = tmp_path / "sweeps" / "foo_plan.yaml"
    plan.write_text(yaml.dump({"header": {"cost_estimate": {"per_cell_total_usd": 24.81}}}))
    env = {"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o",
           "SWEEP_PY": sys.executable}
    r = _run("sweep_agents.sh", root=tmp_path, args=("foo", "5"), env=env)
    assert r.returncode == 1
    assert "below the plan estimate" in r.stderr
    assert "24.81" in r.stderr and "MAX_COST" in r.stderr


def test_sweep_cap_below_estimate_confirm_overrides(tmp_path):
    """CONFIRM=1 turns the refusal into a warning; the run then proceeds far
    enough to try to exec the sweep (which fails fast here — no real uv env),
    proving the guard did NOT block it."""
    (tmp_path / "sweeps").mkdir()
    plan = tmp_path / "sweeps" / "foo_plan.yaml"
    plan.write_text(yaml.dump({"header": {"cost_estimate": {"per_cell_total_usd": 24.81}}}))
    # Make the eventual `uv run ...` a no-op success so we isolate the guard.
    bindir = tmp_path / "bin"; bindir.mkdir()
    _write_exec(bindir / "uv", 'exit 0\n')
    _write_exec(bindir / "caffeinate", 'shift 1; exec "$@"\n')
    env = {"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o",
           "SWEEP_PY": sys.executable, "CONFIRM": "1",
           "PATH": f"{bindir}:{os.environ['PATH']}"}
    r = _run("sweep_agents.sh", root=tmp_path, args=("foo", "5"), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "proceeding (CONFIRM=1)" in r.stderr


# --------------------------------------------------------------------------
# harness/cases_platform_report.py  (aggregate-only; the doctor platform check)
# --------------------------------------------------------------------------

def _make_case(root: Path, name: str, build_cpu: str):
    hidden = root / "cases" / name / "hidden"
    hidden.mkdir(parents=True)
    (hidden / "card.hidden.yaml").write_text(yaml.dump({"build_cpu": build_cpu}))


def test_platform_report_aggregate_only(tmp_path):
    from harness.cases_platform_report import report
    _make_case(tmp_path, "case_0001", "GenuineIntel Intel(R) Xeon(R)")
    _make_case(tmp_path, "case_0002", "AuthenticAMD AMD EPYC 7763")
    _make_case(tmp_path, "case_0003", "VirtualApple VirtualApple @ 2.50GHz")
    out = report(project_root=tmp_path)
    assert out == {
        "total": 3,
        "canonical": 2,
        "non_canonical": 1,
        "vendors": ["AuthenticAMD", "GenuineIntel", "VirtualApple"],
    }
    # Narrow surface: ONLY the aggregate keys, no per-case detail.
    assert set(out) == {"total", "canonical", "non_canonical", "vendors"}


def test_platform_report_no_cases(tmp_path):
    from harness.cases_platform_report import report
    (tmp_path / "cases").mkdir()
    assert report(project_root=tmp_path) == {
        "total": 0, "canonical": 0, "non_canonical": 0, "vendors": [],
    }


# --------------------------------------------------------------------------
# restore_cases.sh — WHICH kind of validation failure (bundle vs local results/)
# --------------------------------------------------------------------------

def _restore_with_validation(tmp_path, classification: str | None, rc: int):
    """Run a full (faked) restore whose validate-all step prints `classification` and exits `rc`."""
    bindir = tmp_path / "bin"; bindir.mkdir()
    cipher = tmp_path / "sweep_bundle.tar.gz.gpg"
    gh = _fake_gh(bindir, run_list="515151\thttps://gh/run/515151\n",
                  artifacts_by_run={"515151": "sweep_bundle"}, download_creates=cipher)
    gpg = _write_exec(bindir / "gpg", 'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
                                      ': > "$out"\n')
    # fake tar: "extract" one case into the staging dir given by -C
    tar = _write_exec(bindir / "tar", 'while [ $# -gt 0 ]; do [ "$1" = "-C" ] && dest="$2"; shift; done\n'
                                      'mkdir -p "$dest/cases/case_0001/workspace"\n')
    line = f'echo "{classification}"' if classification else ":"
    _write_exec(bindir / "make", 'case "$*" in *docker-validate-all*) echo "case_0001: 22/23"; '
                                 f'{line}; exit {rc};; esac\nexit 0\n')
    env = {"GH": str(gh), "GPG": str(gpg), "TAR": str(tar), "SWEEP_BUNDLE_KEY": "k",
           "PATH": f"{bindir}:{os.environ['PATH']}"}
    return _run("restore_cases.sh", root=tmp_path, env=env)


def test_restore_local_results_failure_says_the_bundle_was_fine(tmp_path):
    r = _restore_with_validation(tmp_path, "CLASSIFICATION: case=OK local_results=FAIL", 1)
    assert r.returncode == 1
    assert "NOT because of the bundle" in r.stderr and "LOCAL results/" in r.stderr
    assert "not valid" not in r.stderr


def test_restore_case_defect_says_the_bundle_is_bad(tmp_path):
    r = _restore_with_validation(tmp_path, "CLASSIFICATION: case=FAIL local_results=OK", 1)
    assert r.returncode == 1
    assert "RESTORED CASES themselves" in r.stderr and "515151" in r.stderr


def test_restore_passes_when_validation_passes(tmp_path):
    r = _restore_with_validation(tmp_path, None, 0)
    assert r.returncode == 0, r.stderr
    assert "validate-all PASSED" in r.stdout
