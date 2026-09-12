"""Trusted-agent guard + aggregate exclusion (spec §8).

Vulnerability class: a trusted probe agent (reads hidden/ directly) leaks into
the contestant pool or into an aggregate, silently inflating results.  These
tests prove the guard refuses trusted agents by default and that aggregation
excludes them — each with a planted violation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.always_broken_agent import AlwaysBrokenAgent
from agents.degenerate_agent import DegenerateAgent
from agents.oracle_agent import OracleAgent
from harness.run_agent import run_trial
from harness.scoring import aggregate_scores

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


class TestProtocolConformance:

    def test_agents_have_name_and_run(self):
        for agent in (OracleAgent(), DegenerateAgent(), AlwaysBrokenAgent()):
            assert isinstance(agent.name, str)
            assert callable(agent.run)

    def test_trust_flags(self):
        assert OracleAgent().is_trusted is True
        assert DegenerateAgent().is_trusted is True
        # Always-broken uses only the tool layer — it is NOT trusted.
        assert getattr(AlwaysBrokenAgent(), "is_trusted", False) is False


class TestTrustedGuard:

    def test_run_trial_refuses_trusted_without_flag(self, tmp_path):
        """Planted: attempt to run a trusted agent as a contestant → refused."""
        case_dir = CASES_DIR / "case_0001"
        if not case_dir.exists():
            pytest.skip("case_0001 not built")
        with pytest.raises(PermissionError, match="trusted"):
            run_trial(OracleAgent(), case_dir, project_root=tmp_path, allow_trusted=False)

    def test_run_trial_allows_trusted_with_flag(self, tmp_path):
        """With allow_trusted=True the oracle runs and its record is marked trusted."""
        case_dir = CASES_DIR / "case_0001"
        if not case_dir.exists():
            pytest.skip("case_0001 not built")
        record = run_trial(
            OracleAgent(), case_dir, project_root=tmp_path, allow_trusted=True,
        )
        assert record["trusted"] is True
        # Oracle is exactly correct on the free axes.
        assert record["scores"]["detection"]["correct"] is True
        assert record["scores"]["identification"]["correct"] is True
        assert record["scores"]["evidence"]["f1"] == 1.0


class TestAggregateExcludesTrusted:

    def _score(self, *, trusted, detection_correct=True):
        return {
            "tier": "dynamics",
            "trusted": trusted,
            "detection": {"correct": detection_correct, "detected_predicted": True},
            "identification": {"correct": True},
            "evidence": {"f1": 1.0},
            "recovery": {"verdict": "recovered"},
            "safety": {"rejected_tool_calls": 0, "forbidden_actions": 0},
        }

    def test_trusted_scores_excluded_and_counted(self):
        """Planted: include a trusted score → excluded from aggregate, counted."""
        scores = [
            self._score(trusted=False, detection_correct=False),
            self._score(trusted=True, detection_correct=True),  # must be excluded
        ]
        agg = aggregate_scores(scores)
        assert agg["n_trials"] == 1  # only the untrusted one
        assert agg["n_excluded_trusted"] == 1
        # If the trusted one had been counted, detection_accuracy would be 0.5.
        assert agg["detection_accuracy"] == 0.0

    def test_clean_aggregate_excludes_nothing(self):
        agg = aggregate_scores([self._score(trusted=False)])
        assert agg["n_excluded_trusted"] == 0
        assert agg["n_trials"] == 1
