"""R8 audits cost ESTIMATES (it used to examine only non-estimates — none — and passed vacuously),
and the sweep-level reconciliation compares summed estimates with billed actual_spend_usd."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.audit_index import _r8, _r8b                     # noqa: E402
from harness.pricing import PRICE_TABLE_VERSION, estimate_cost, table_version  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"


def _rec(cost=None, version=PRICE_TABLE_VERSION, commit="HEAD"):
    u = {"input_tokens": 20000, "output_tokens": 900, "cached_tokens": 12000, "cache_write_tokens": 5000,
         "cost_is_estimate": True, "price_table_version": version}
    u["estimated_cost_usd"] = (estimate_cost(HAIKU, 20000, 900, 12000, 5000).cost_usd
                               if cost is None else cost)
    return {"model": {"model_id": HAIKU}, "usage": u, "environment": {"harness_git_commit": commit}}


def test_r8_examines_estimates_and_passes_a_correct_one():
    rec = _rec()
    assert rec["usage"]["cost_is_estimate"] is True       # an ESTIMATE is now examined
    assert _r8(rec) is False and _r8b(rec) is False


@pytest.mark.parametrize("factor", [1.02, 0.97, 1.5])
def test_r8_fails_beyond_one_percent(factor):
    rec = _rec(); rec["usage"]["estimated_cost_usd"] *= factor
    assert _r8(rec) is True


def test_r8_tolerates_within_one_percent():
    rec = _rec(); rec["usage"]["estimated_cost_usd"] *= 1.005
    assert _r8(rec) is False


def _archived_commit():
    from harness.pricing import _history
    return next(iter(_history()["commits"]))


def test_old_record_uses_the_table_at_its_commit_without_git(monkeypatch):
    """Pre-2026-09-23 records carry only their commit; the committed archive resolves the table
    with NO git (the canonical container ships none)."""
    from harness import pricing
    monkeypatch.setattr(pricing, "_table_at_commit", lambda c: None)   # simulate: no git at all
    rec = _rec(version=None, commit=_archived_commit())
    assert _r8b(rec) is False                     # resolved from the archive
    assert _r8(rec) is False


def test_current_price_table_is_archived():
    """Changing _PRICE_TABLE without regenerating harness/price_table_history.json fails here —
    otherwise records stamped with the new version could not be audited in the container."""
    from harness.pricing import _history
    assert PRICE_TABLE_VERSION in _history()["tables"], (
        "run: python scripts/build_price_table_history.py")


def test_archive_is_content_addressed():
    from harness.pricing import _history
    for v, t in _history()["tables"].items():
        assert table_version(t) == v


def test_unreconstructable_table_is_reported_not_passed():
    rec = _rec(version=None, commit="0" * 40)    # commit neither archived nor in history
    assert _r8(rec) is False                     # cannot claim a mismatch...
    assert _r8b(rec) is True                     # ...but it is VISIBLE as unverifiable


def test_recorded_version_must_match_the_reconstructed_table():
    rec = _rec(version="sha256:deadbeefdeadbeef", commit="HEAD")
    assert _r8b(rec) is True


def test_table_version_is_content_addressed():
    assert table_version({"m": {"input": 1.0}}) == table_version({"m": {"input": 1.0}})
    assert table_version({"m": {"input": 1.0}}) != table_version({"m": {"input": 1.01}})


def test_provenance_stamps_the_price_table_version():
    from types import SimpleNamespace
    from harness.provenance import finalize_record
    rec = {"environment": {}, "model": {"model_id": HAIKU}, "budget": {},
           "usage": {"input_tokens": 100, "output_tokens": 10, "cached_tokens": 0,
                     "total_tokens": 0, "max_tokens_truncations": 0}}
    finalize_record(rec, SimpleNamespace(submission=None, transcript=[], budget_total=1,
                                         budget_remaining=1), None, 0.0)
    assert rec["usage"]["price_table_version"] == PRICE_TABLE_VERSION


# ---- sweep-level reconciliation ---------------------------------------------------------------

def _release(root: Path, costs, actual=None, by_provider=None):
    rel = root / "results_release" / "s"; (rel / "trials").mkdir(parents=True)
    for i, (prov, c) in enumerate(costs):
        (rel / "trials" / f"case_0001__r{i}.json").write_text(json.dumps(
            {"conditions": {"provider": prov}, "usage": {"estimated_cost_usd": c}}))
    man = {"actual_spend_usd": actual}
    if by_provider:
        man["actual_spend_by_provider"] = by_provider
    (root / "sweeps").mkdir(); (root / "sweeps" / "s_manifest.yaml").write_text(yaml.dump(man))


def test_reconciliation_pending_until_actual_entered(tmp_path):
    from scripts.check_cost_reconciliation import reconcile
    _release(tmp_path, [("anthropic", 1.0), ("openai", 0.5)])
    r = reconcile(tmp_path, "s")
    assert r["status"] == "PENDING" and r["estimate_usd"] == 1.5


@pytest.mark.parametrize("actual,status", [(1.5, "PASS"), (1.57, "PASS"), (1.43, "PASS"),
                                           (1.60, "FAIL"), (1.40, "FAIL")])
def test_reconciliation_tolerance(tmp_path, actual, status):
    from scripts.check_cost_reconciliation import reconcile
    _release(tmp_path, [("anthropic", 1.0), ("openai", 0.5)], actual=actual)
    assert reconcile(tmp_path, "s")["status"] == status


def test_reconciliation_reports_per_provider_ratios(tmp_path):
    from scripts.check_cost_reconciliation import reconcile
    _release(tmp_path, [("anthropic", 1.0), ("openai", 0.5)], actual=1.5,
             by_provider={"anthropic": 0.95, "openai": 0.55})
    r = reconcile(tmp_path, "s")
    assert r["status"] == "PASS"
    assert r["ratio_by_provider"] == {"anthropic": 0.95, "openai": 1.1}


def test_partial_provider_entry_is_reported_while_total_pending(tmp_path):
    """One provider billed, the other not yet: the total stays PENDING (never a partial sum
    compared against the full estimate), but the entered provider's ratio is reported."""
    from scripts.check_cost_reconciliation import reconcile
    _release(tmp_path, [("anthropic", 1.0), ("openai", 0.5)],
             by_provider={"anthropic": 1.009, "openai": None})
    r = reconcile(tmp_path, "s")
    assert r["status"] == "PENDING"
    assert r["ratio_by_provider"] == {"anthropic": 1.009}
