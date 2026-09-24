from scripts.compare_stats_exact import diffs


def test_timing_ignored_values_compared():
    a = {"per_seed": [{"seed": 1, "acc": 0.85, "wall_time_sec": 1.0, "epochs": [{"train_loss": 0.3}]}]}
    b = {"per_seed": [{"seed": 1, "acc": 0.85, "wall_time_sec": 9.0, "epochs": [{"train_loss": 0.3}]}]}
    assert diffs(a, b) == []
    b["per_seed"][0]["epochs"][0]["train_loss"] = 0.3000001
    assert diffs(a, b) == [".per_seed[0].epochs[0].train_loss: 0.3 != 0.3000001"]
    assert diffs({"x": 1}, {"x": 1, "y": 2}) == [".y: present in only one file"]
