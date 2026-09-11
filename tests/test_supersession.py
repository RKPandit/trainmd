"""Content-derived build id + superseded-trial detection (spec §5, §7).

Fast unit tests (no training): build_id determinism in both directions,
mark_card_superseded, and the C10 informational validator check.
"""
from __future__ import annotations

from pathlib import Path
from random import Random

import shutil
import tempfile

import yaml

from harness.build_case import _compute_build_id
from harness.provenance import mark_card_superseded
from harness.validate_case import _check_c10
from operators.silent.label_corruption import LabelCorruptionOperator

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


def _manifest_for(tmp_path: Path, strength: str):
    ws = Path(tempfile.mkdtemp(dir=tmp_path))
    for fname in ["config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, ws / fname)
    return LabelCorruptionOperator().apply(ws, Random(0), strength)


class TestBuildIdBothDirections:

    def test_identical_inputs_yield_identical_build_id(self, tmp_path):
        """A no-op rebuild (same inputs) produces the same content-derived id."""
        m1 = _manifest_for(tmp_path, "moderate")
        m2 = _manifest_for(tmp_path, "moderate")
        id1 = _compute_build_id(m1, 42, WORKLOAD_DIR)
        id2 = _compute_build_id(m2, 42, WORKLOAD_DIR)
        assert id1 == id2

    def test_changed_mutation_yields_different_build_id(self, tmp_path):
        """A material change (different strength → different fraction) changes id."""
        m_mod = _manifest_for(tmp_path, "moderate")
        m_sev = _manifest_for(tmp_path, "severe")
        assert _compute_build_id(m_mod, 42, WORKLOAD_DIR) != _compute_build_id(
            m_sev, 42, WORKLOAD_DIR
        )

    def test_changed_seed_yields_different_build_id(self, tmp_path):
        m = _manifest_for(tmp_path, "moderate")
        assert _compute_build_id(m, 42, WORKLOAD_DIR) != _compute_build_id(
            m, 43, WORKLOAD_DIR
        )


class TestMarkCardSuperseded:

    def _case_with_build_id(self, tmp_path: Path, build_id: str) -> Path:
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (case_dir / "card.public.yaml").write_text(
            yaml.dump({"case_id": "case_0001", "case_build_id": build_id})
        )
        return case_dir

    def test_matching_build_id_not_superseded(self, tmp_path):
        case_dir = self._case_with_build_id(tmp_path, "abc123")
        record = {"environment": {"case_build_id": "abc123"}}
        assert mark_card_superseded(record, case_dir) is False
        assert record["card_superseded"] is False

    def test_mismatched_build_id_superseded(self, tmp_path):
        case_dir = self._case_with_build_id(tmp_path, "abc123")
        record = {"environment": {"case_build_id": "OLD999"}}
        assert mark_card_superseded(record, case_dir) is True
        assert record["card_superseded"] is True

    def test_missing_build_id_superseded(self, tmp_path):
        """A trial predating the build-id field is treated as superseded."""
        case_dir = self._case_with_build_id(tmp_path, "abc123")
        record = {"environment": {}}
        assert mark_card_superseded(record, case_dir) is True


class TestC10Check:

    def _write_trial(self, project_root: Path, case_id: str, run_id: str, build_id):
        trials = project_root / "results" / case_id / "trials"
        trials.mkdir(parents=True, exist_ok=True)
        env = {"case_build_id": build_id} if build_id is not None else {}
        (trials / f"{run_id}.yaml").write_text(
            yaml.dump({"run_id": run_id, "environment": env})
        )

    def test_c10_reports_only_mismatched(self, tmp_path):
        project_root = tmp_path
        public_card = {"case_build_id": "CURRENT"}
        self._write_trial(project_root, "case_0001", "match1", "CURRENT")
        self._write_trial(project_root, "case_0001", "stale1", "OLD")
        self._write_trial(project_root, "case_0001", "nobid", None)

        result = _check_c10("case_0001", public_card, project_root)
        assert result.category == "INFO"
        assert result.passed  # informational — never fails
        assert "stale1" in result.detail
        assert "nobid" in result.detail
        assert "match1" not in result.detail

    def test_c10_clean_when_all_current(self, tmp_path):
        public_card = {"case_build_id": "CURRENT"}
        self._write_trial(tmp_path, "case_0002", "m1", "CURRENT")
        result = _check_c10("case_0002", public_card, tmp_path)
        assert result.passed
        assert result.detail == ""
