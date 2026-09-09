"""Tests for build_case idempotency (case deduplication).

Fast tests: verify registry helpers and idempotency guard logic
without running actual training jobs.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.build_case import (
    _find_existing_case,
    _load_registry,
    _next_case_id,
    _save_registry,
)


# ---------------------------------------------------------------------------
# _find_existing_case
# ---------------------------------------------------------------------------

class TestFindExistingCase:

    def test_found(self):
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        result = _find_existing_case(
            registry, "tabular_adult", "silent.lr_warmup.v1", "moderate", 42,
        )
        assert result == "case_0001"

    def test_not_found_different_seed(self):
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        result = _find_existing_case(
            registry, "tabular_adult", "silent.lr_warmup.v1", "moderate", 99,
        )
        assert result is None

    def test_not_found_different_strength(self):
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        result = _find_existing_case(
            registry, "tabular_adult", "silent.lr_warmup.v1", "mild", 42,
        )
        assert result is None

    def test_empty_registry(self):
        result = _find_existing_case(
            {}, "tabular_adult", "silent.lr_warmup.v1", "moderate", 42,
        )
        assert result is None


# ---------------------------------------------------------------------------
# _next_case_id
# ---------------------------------------------------------------------------

class TestNextCaseId:

    def test_empty(self):
        assert _next_case_id({}) == "case_0001"

    def test_sequential(self):
        registry = {"case_0001": {}, "case_0003": {}}
        assert _next_case_id(registry) == "case_0004"


# ---------------------------------------------------------------------------
# _load_registry / _save_registry round-trip
# ---------------------------------------------------------------------------

class TestRegistryIO:

    def test_round_trip(self, tmp_path):
        path = tmp_path / "registry.hidden.yaml"
        data = {
            "case_0001": {
                "workload": "w",
                "operator": "o",
                "strength": "s",
                "seed": 1,
            },
        }
        _save_registry(path, data)
        loaded = _load_registry(path)
        assert loaded == data

    def test_load_missing(self, tmp_path):
        path = tmp_path / "nonexistent.yaml"
        assert _load_registry(path) == {}


# ---------------------------------------------------------------------------
# Idempotency guard (build_case refuses / rebuilds)
# ---------------------------------------------------------------------------

class TestIdempotencyGuard:
    """Test build_case idempotency without running training.

    We pre-populate a registry and case dir, then call build_case which
    will hit the idempotency check before any heavy work.
    """

    def test_existing_tuple_without_force_exits(self, tmp_path):
        """Duplicate tuple without --force must sys.exit, not create a new case."""
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        registry_path = cases_dir / "registry.hidden.yaml"

        # Pre-populate registry with case_0001
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        _save_registry(registry_path, registry)

        # Create the case dir so it looks real
        (cases_dir / "case_0001" / "hidden").mkdir(parents=True)

        from harness.build_case import build_case

        with pytest.raises(SystemExit) as exc_info:
            build_case(
                "tabular_adult", "silent.lr_warmup.v1", "moderate", 42,
                project_root=tmp_path,
                force=False,
            )

        # Message should name the existing case
        assert "case_0001" in str(exc_info.value)
        assert "--force" in str(exc_info.value)

        # No case_0002 should have been created
        assert not (cases_dir / "case_0002").exists()

        # Registry unchanged — still exactly one entry
        loaded = _load_registry(registry_path)
        assert len(loaded) == 1
        assert "case_0001" in loaded

    def test_new_tuple_allocates_next_id(self, tmp_path):
        """A genuinely new tuple should allocate the next sequential ID.

        We only test that the ID allocation is correct; the actual build
        will fail (no workload dir), but the case_id is assigned before
        the workload is accessed, so we can verify it.
        """
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        registry_path = cases_dir / "registry.hidden.yaml"

        # Pre-populate with case_0001 (different tuple)
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        _save_registry(registry_path, registry)

        from harness.build_case import build_case

        # Different seed → new tuple → should try to allocate case_0002
        # It will fail because workload dir doesn't exist, but we can
        # check that case_0002 dir was created (before the failure)
        with pytest.raises(Exception):
            build_case(
                "tabular_adult", "silent.lr_warmup.v1", "mild", 99,
                project_root=tmp_path,
                force=False,
            )

        # case_0002 dir should have been created (even though build failed)
        assert (cases_dir / "case_0002").exists()

    def test_existing_tuple_with_force_reuses_id(self, tmp_path):
        """--force on existing tuple should reuse the same case ID.

        We verify the ID reuse and directory cleanup; the actual build
        will fail (no workload dir), but the idempotency logic runs first.
        """
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        registry_path = cases_dir / "registry.hidden.yaml"

        # Pre-populate with case_0001
        registry = {
            "case_0001": {
                "workload": "tabular_adult",
                "operator": "silent.lr_warmup.v1",
                "strength": "moderate",
                "seed": 42,
            },
        }
        _save_registry(registry_path, registry)

        # Create existing case dir with a marker file
        old_case = cases_dir / "case_0001"
        old_hidden = old_case / "hidden"
        old_hidden.mkdir(parents=True)
        marker = old_hidden / "marker.txt"
        marker.write_text("old content")

        from harness.build_case import build_case

        # --force should rmtree case_0001, then try to rebuild.
        # It will fail because workload dir doesn't exist, but the
        # old content should be gone and case_0002 should NOT exist.
        with pytest.raises(Exception):
            build_case(
                "tabular_adult", "silent.lr_warmup.v1", "moderate", 42,
                project_root=tmp_path,
                force=True,
            )

        # Old marker should be gone (rmtree'd)
        assert not marker.exists()

        # case_0001 was re-created (mkdir in build pipeline)
        assert (cases_dir / "case_0001").exists()

        # case_0002 should NOT exist — force reuses, never allocates new
        assert not (cases_dir / "case_0002").exists()
