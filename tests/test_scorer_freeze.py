"""The scorer is FROZEN (DECISIONS 2026-09-28): root_token_v3 identification + evidence v2.3. Any change to the
method names, the token spec, any operator's evidence specification, or the two scoring modules fails here
until `harness/scorer_freeze.yaml` is deliberately rewritten (with a DECISIONS row)."""
from __future__ import annotations

from harness import scorer_freeze as sf


def test_frozen_scorer_is_unchanged():
    assert sf.drift() == [], (
        "The FROZEN scorer changed. If deliberate: python -m harness.scorer_freeze --write AND add a DECISIONS "
        "row (after the Part 2 lock, findings go to LIMITATIONS unless a result would be wrong).")


def test_frozen_versions_are_the_declared_ones():
    fp = sf.committed()["fingerprint"]
    assert fp["identification_method"] == "root_token_v3"
    assert fp["evidence_primary"] == "evidence_v2.3"


def test_drift_is_detected(monkeypatch):
    live = sf.scorer_fingerprint()
    monkeypatch.setattr(sf, "scorer_fingerprint",
                        lambda: {**live, "token_spec_sha256": "0" * 64,
                                 "source_sha256": {**live["source_sha256"], "harness/scoring.py": "x"}})
    d = sf.drift()
    assert any("token_spec_sha256" in x for x in d) and any("scoring.py" in x for x in d)


def _rescore_module():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rescore_p1", Path(__file__).resolve().parent.parent / "scripts" / "rescore_stage4_part1.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rescore_apply_refuses_a_drifted_scorer(monkeypatch):
    import pytest
    mod = _rescore_module()
    monkeypatch.setattr("sys.argv", ["rescore", "--apply"])
    monkeypatch.setattr(sf, "drift", lambda: ["token_spec_sha256 changed"])
    monkeypatch.setattr(mod, "_run", lambda apply: pytest.fail("must not run"))
    with pytest.raises(SystemExit, match="FROZEN scorer"):
        mod.main()


def test_rescore_apply_holds_the_sweep_lock(monkeypatch, tmp_path):
    from harness import results_lock as rl
    mod = _rescore_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["rescore", "--apply"])
    monkeypatch.setattr(sf, "drift", lambda: [])
    seen = {}
    monkeypatch.setattr(mod, "_run", lambda apply: seen.update(apply=apply, holder=rl.holder(tmp_path)) or 0)
    assert mod.main() == 0
    assert seen["apply"] is True and seen["holder"]["sweep"] == "rescore_stage4_part1"
    assert rl.holder(tmp_path) is None                               # released afterwards
