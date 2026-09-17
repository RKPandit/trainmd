"""Recovery verdict rule (STAGE3 ruling 2026-09-17): recovered iff the MEAN of the
hidden-seed accuracies clears tolerance_lower, not every seed individually. These are
PLATFORM-INDEPENDENT (pure function over per-seed values), so they pin the rule that
the native-only boundary tests (seed 101 at 2.19sigma below the band mean) cannot."""
from harness.evaluator.verify_repair import compute_recovery_verdict

TOL = 0.844655  # native [200-229] mean-2sigma


def _seeds(*accs, exit0=True):
    return [{"exitcode": 0 if exit0 else 1, "metric_hidden_test_acc": a,
             "metric_visible_val_acc": a + 0.008} for a in accs]


def test_all_above_tolerance_recovers():
    v, mean, fails = compute_recovery_verdict(_seeds(0.848, 0.849, 0.850), TOL, "dynamics")
    assert v == "recovered" and fails == 0


def test_one_seed_below_but_mean_above_recovers():
    # THE regression: native seed 101 clean == 0.844317 < TOL, but the mean of the
    # three genuinely-correct-repair seeds clears TOL. Old all-3 rule -> not_recovered.
    per_seed = _seeds(0.849919, 0.844317, 0.851393)
    v, mean, fails = compute_recovery_verdict(per_seed, TOL, "dynamics")
    assert v == "recovered", (v, mean)
    assert fails == 1                      # seed 101 fails the OLD per-seed rule
    assert mean >= TOL


def test_mean_below_tolerance_stays_not_recovered():
    # genuinely degraded model: mean under tolerance -> not recovered
    v, mean, fails = compute_recovery_verdict(_seeds(0.830, 0.840, 0.835), TOL, "dynamics")
    assert v == "not_recovered" and fails == 3


def test_crashed_seed_blocks_recovery():
    per_seed = _seeds(0.849, 0.850, 0.851)
    per_seed[1]["exitcode"] = 1            # a seed that did not run
    v, _, _ = compute_recovery_verdict(per_seed, TOL, "dynamics")
    assert v == "not_recovered"


def test_metric_tier_requires_mean_visible_in_band():
    vlo, vhi = 0.851904, 0.860692          # native visible band
    # hidden mean fine, but mean visible still ABOVE band (bias not repaired)
    per = [{"exitcode": 0, "metric_hidden_test_acc": 0.849,
            "metric_visible_val_acc": 0.90} for _ in range(3)]
    v, _, _ = compute_recovery_verdict(per, TOL, "metric", vlo, vhi)
    assert v == "not_recovered"
    # visible back inside band -> recovered
    for r in per: r["metric_visible_val_acc"] = 0.856
    v, _, _ = compute_recovery_verdict(per, TOL, "metric", vlo, vhi)
    assert v == "recovered"
