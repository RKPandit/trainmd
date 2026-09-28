"""The Sonnet 5 "thinking on" rule (STAGE4_PLAN Part 2, item A) — encoded strictly."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("tv", ROOT / "scripts" / "thinking_volume.py")
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)


def _t(with_thinking, median, trials=10):
    return {"trials": trials, "trials_with_thinking": with_thinking, "calls": trials, "output_tok_per_trial": 0,
            "est_thinking_median": median, "est_thinking_mean": median, "truncations": 0, "cost_per_trial": 0}


def test_lowest_qualifying_level_wins():
    assert tv.choose({"medium": _t(8, 200), "high": _t(9, 800), "xhigh": _t(10, 2000)})[0] == "high"
    assert tv.choose({"medium": _t(8, 200), "high": _t(10, 799), "xhigh": _t(10, 2000)})[0] == "xhigh"   # 3.995x


def test_both_conditions_are_required():
    assert tv.choose({"medium": _t(8, 200), "high": _t(8, 5000), "xhigh": _t(9, 900)})[0] == "xhigh"    # 8/10 fails (a)
    lvl, why = tv.choose({"medium": _t(8, 200), "high": _t(9, 300), "xhigh": _t(9, 500)})
    assert lvl == "xhigh" and "neither level qualifies" in why and "2.5×" in why


def test_boundaries_are_inclusive():
    assert tv.choose({"medium": _t(8, 100), "high": _t(9, 400), "xhigh": _t(10, 900)})[0] == "high"


def test_refuses_without_probe_or_medium():
    with pytest.raises(SystemExit):                    # high fails the rule and xhigh was never run
        tv.choose({"medium": _t(8, 200), "high": _t(9, 300)})
    with pytest.raises(SystemExit):
        tv.choose({"high": _t(9, 900), "xhigh": _t(9, 900)})


def test_estimate_subtracts_calibrated_visible_output():
    off = {"conditions": {"thinking": "disabled", "agent_type": "static"},
           "llm_transcript": [{"usage": {"output_tokens": 50}, "tool_calls": [{"arguments": {"a": "x" * 91}}]}]}
    n = tv.visible_chars(off["llm_transcript"][0])
    on = {"conditions": {"effort": "medium", "agent_type": "static"},
          "llm_transcript": [{"usage": {"output_tokens": 50 + 300}, "reasoning_blocks": 1,
                              "tool_calls": [{"arguments": {"a": "x" * 91}}]}]}
    ratio, table = tv.summarize([off, on])
    assert ratio == pytest.approx(50 / n)
    assert table["medium"]["est_thinking_median"] == pytest.approx(300)
    assert table["medium"]["trials_with_thinking"] == 1 and table["off"]["est_thinking_median"] == 0
