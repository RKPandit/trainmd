"""Image cases refuse to build until the CI stale-reference guard watches the image reference (author, 2026-09-28)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness import reference_guard as rg

ROOT = Path(__file__).resolve().parent.parent


def test_tabular_workloads_are_guarded_including_the_symlinked_neutral_one():
    assert rg.unguarded_files(ROOT, "tabular_adult") == []
    assert rg.unguarded_files(ROOT, "tabular_adult_neutral") == []          # reference/ is a symlink to tabular_adult


def test_image_workloads_are_guarded():
    # Lifted in Part 3 step 4 (DECISIONS 2026-09-29): the guard's pattern now watches the image reference.
    assert rg.unguarded_files(ROOT, "image_fmnist") == []
    assert rg.unguarded_files(ROOT, "image_fmnist_neutral") == []            # reference/ is a symlink to image_fmnist
    rg.require_reference_guard(ROOT, "image_fmnist")


def test_dropping_a_workload_from_the_guard_pattern_restores_the_refusal(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    new = 'workloads/(tabular_adult|image_fmnist)/reference/(stats|data_manifest)\\.yaml'
    assert new in ci
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        ci.replace(new, 'workloads/tabular_adult/reference/(stats|data_manifest)\\.yaml'))
    shutil.copytree(ROOT / "workloads" / "image_fmnist" / "reference", tmp_path / "workloads" / "image_fmnist" / "reference")
    assert rg.unguarded_files(tmp_path, "image_fmnist", ci_root=tmp_path) == [
        "workloads/image_fmnist/reference/stats.yaml", "workloads/image_fmnist/reference/data_manifest.yaml"]
    with pytest.raises(SystemExit, match="refusing to build image_fmnist cases"):
        rg.require_reference_guard(tmp_path, "image_fmnist", ci_root=tmp_path)


def test_build_case_calls_the_precondition_first():
    src = (ROOT / "harness" / "build_case.py").read_text()
    i = src.index("def build_case(")
    body = src[i:]
    assert body.index("require_reference_guard(project_root, workload_name)") < body.index("_get_operator(operator_id)")
