#!/usr/bin/env python3
"""Sonnet 5 thinking VOLUME per effort level, and the pre-declared rule that fixes Part 2's "thinking on" level
(STAGE4_PLAN Part 2, item A; approved by the author 2026-09-27). Reads NO scores — token counts only.

Anthropic returns no thinking-token breakout (thinking is billed inside output_tokens), so thinking volume per
call is ESTIMATED as   output_tokens − r × visible_chars,   where visible_chars is the length of the call's tool
arguments (JSON) plus text, and r (output tokens per visible character) is the median over Sonnet 5's
thinking-DISABLED calls, which have no thinking by construction.

RULE (declared before the probe ran): among effort levels {high, xhigh}, choose the LOWEST with
  (a) thinking blocks in ≥ 9 of 10 static trials, AND
  (b) median estimated thinking per call ≥ 4 × the medium level's median;
if neither qualifies, choose xhigh and state the measured contrast.

    python scripts/thinking_volume.py --sweeps stage4_part2_pilot stage4_part2_probe
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5"
LEVELS = ("high", "xhigh")
MIN_TRIALS_WITH_THINKING = 9          # of 10 static trials
MIN_RATIO_TO_MEDIUM = 4.0


def visible_chars(call: dict) -> int:
    return len(json.dumps([tc.get("arguments") for tc in call.get("tool_calls") or []])) + len(call.get("response_text") or "")


def load(root: Path, sweeps: set[str]) -> list[dict]:
    out = []
    for f in sorted((root / "results").glob("*/trials/static_*.yaml")):
        head = f.read_text()[:4000]
        if not any(f"sweep_name: {s}" in head for s in sweeps):
            continue
        r = yaml.safe_load(f.read_text())
        c = r.get("conditions") or {}
        if (r.get("model") or {}).get("model_id") != MODEL or c.get("agent_type") != "static" \
                or r.get("status") != "completed":
            continue
        out.append(r)
    return out


def level_of(r: dict) -> str:
    c = r.get("conditions") or {}
    return "off" if c.get("thinking") == "disabled" else (c.get("effort") or "default")


def summarize(recs: list[dict]) -> tuple[float, dict]:
    calls_by = {}
    for r in recs:
        calls_by.setdefault(level_of(r), []).append(r)
    cal = [c["usage"]["output_tokens"] / visible_chars(c)
           for r in calls_by.get("off", []) for c in r.get("llm_transcript") or [] if visible_chars(c) > 0]
    if not cal:
        raise SystemExit("no thinking-disabled Sonnet 5 calls to calibrate on")
    ratio = st.median(cal)
    table = {}
    for lvl, rs in calls_by.items():
        calls = [c for r in rs for c in r.get("llm_transcript") or []]
        est = [max(0.0, c["usage"]["output_tokens"] - ratio * visible_chars(c)) for c in calls]
        table[lvl] = {"trials": len(rs),
                      "trials_with_thinking": sum(1 for r in rs if any((c.get("reasoning_blocks") or 0) > 0
                                                                       for c in r.get("llm_transcript") or [])),
                      "calls": len(calls),
                      "output_tok_per_trial": sum(c["usage"]["output_tokens"] for c in calls) / len(rs),
                      "est_thinking_median": st.median(est) if est else 0.0,
                      "est_thinking_mean": st.mean(est) if est else 0.0,
                      "truncations": sum(1 for c in calls if c.get("stop_reason") == "max_tokens"),
                      "cost_per_trial": sum((r.get("usage") or {}).get("estimated_cost_usd") or 0 for r in rs) / len(rs)}
    return ratio, table


def choose(table: dict) -> tuple[str, str]:
    """Apply the declared rule. Returns (level, reason)."""
    med = table.get("medium", {}).get("est_thinking_median")
    if not med:
        raise SystemExit("no medium-level Sonnet 5 static trials to compare against")
    for lvl in LEVELS:
        t = table.get(lvl)
        if t is None:
            raise SystemExit(f"no {lvl} trials — run the probe first")
        ok_a = t["trials_with_thinking"] >= MIN_TRIALS_WITH_THINKING * t["trials"] / 10
        ok_b = t["est_thinking_median"] >= MIN_RATIO_TO_MEDIUM * med
        if ok_a and ok_b:
            return lvl, (f"{lvl}: thinking in {t['trials_with_thinking']}/{t['trials']} trials and median "
                         f"{t['est_thinking_median']:.0f} ≥ {MIN_RATIO_TO_MEDIUM:g} × medium's {med:.0f}")
    x = table["xhigh"]
    return "xhigh", (f"neither level qualifies; xhigh by rule — measured contrast: median {x['est_thinking_median']:.0f} "
                     f"vs medium's {med:.0f} ({x['est_thinking_median'] / med:.1f}×), thinking in "
                     f"{x['trials_with_thinking']}/{x['trials']} trials")


def render(ratio: float, table: dict, decision: tuple[str, str]) -> str:
    order = [lv for lv in ("off", "medium", "high", "xhigh") if lv in table]
    L = ["| Sonnet 5 level | static trials | with thinking | calls | output tok / trial | est. thinking / call "
         "(median, mean) | truncations | $ / trial |", "|---|---|---|---|---|---|---|---|"]
    for lv in order:
        t = table[lv]
        L.append(f"| {lv} | {t['trials']} | {t['trials_with_thinking']}/{t['trials']} | {t['calls']} | "
                 f"{t['output_tok_per_trial']:.0f} | {t['est_thinking_median']:.0f}, {t['est_thinking_mean']:.0f} | "
                 f"{t['truncations']} | {t['cost_per_trial']:.4f} |")
    L += ["", f"Calibration: {ratio:.3f} output tokens per visible character (median over thinking-disabled calls).",
          f"**Chosen level: {decision[0]}** — {decision[1]}."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweeps", nargs="+", default=["stage4_part2_pilot", "stage4_part2_probe"])
    ap.add_argument("--project-root", type=Path, default=ROOT)
    a = ap.parse_args()
    ratio, table = summarize(load(a.project_root, set(a.sweeps)))
    print(render(ratio, table, choose(table)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
