# Stage 4 Part 2 — static vs ReAct off-arm detection, and what ReAct opened · EXPLORATORY (no verdicts)

> Read-only (author's request, 2026-09-29). Not a pre-registered analysis; Stage B is descriptive; no verdict,
> estimand or rule changes. Beside LIMITATIONS L40 (the "closed menu" of gated fault paths).
> Hypothesis under examination: the STATIC agent is given `train.py` (with every fault's gated code path) in its
> context, while ReAct must choose to open it, so ReAct detects less on the silent faults.
> Method: off arm, non-crash faulty cases present in BOTH sweeps; static detection = mean over its repeats per case,
> then over cases; ReAct = one trial per case. "Opened" is read from the ReAct tool traces: `read_code` on
> `train.py` / `datautil.py`, and `read_config` (or `read_code` on `config.yaml`) for the config. Opening is the
> agent's own choice, so the conditional rates are associations, not effects of opening.

## Per condition × mechanism

| condition | mechanism | n cases | static det | ReAct det | ReAct opened train.py | opened config | ReAct det, train.py opened | ReAct det, not opened |
|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5 [thinking off] | data_leakage | 36 | 0.99 | 0.61 | 0.97 | 1.00 | 0.63 (n=35) | 0.00 (n=1) |
| claude-sonnet-5 [thinking off] | metric_inflation | 18 | 1.00 | 0.39 | 0.50 | 1.00 | 0.78 (n=9) | 0.00 (n=9) |
| claude-sonnet-5 [thinking off] | label_corruption | 18 | 0.92 | 1.00 | 0.94 | 1.00 | 1.00 (n=17) | 1.00 (n=1) |
| claude-sonnet-5 [thinking off] | lr_warmup | 18 | 0.86 | 1.00 | 0.50 | 1.00 | 1.00 (n=9) | 1.00 (n=9) |
| claude-sonnet-5 [thinking off] | **all non-crash** | 90 | 0.95 | 0.72 | 0.78 | 1.00 | 0.79 (n=70) | 0.50 (n=20) |
| claude-sonnet-5 [xhigh] | data_leakage | 36 | 0.94 | 0.81 | 1.00 | 1.00 | 0.81 (n=36) | — (n=0) |
| claude-sonnet-5 [xhigh] | metric_inflation | 18 | 0.97 | 0.39 | 0.50 | 1.00 | 0.78 (n=9) | 0.00 (n=9) |
| claude-sonnet-5 [xhigh] | label_corruption | 18 | 0.81 | 1.00 | 1.00 | 1.00 | 1.00 (n=18) | — (n=0) |
| claude-sonnet-5 [xhigh] | lr_warmup | 18 | 0.94 | 1.00 | 0.89 | 1.00 | 1.00 (n=16) | 1.00 (n=2) |
| claude-sonnet-5 [xhigh] | **all non-crash** | 90 | 0.92 | 0.80 | 0.88 | 1.00 | 0.89 (n=79) | 0.18 (n=11) |
| gpt-5.6-luna [medium strict] | data_leakage | 36 | 0.99 | 0.81 | 1.00 | 1.00 | 0.81 (n=36) | — (n=0) |
| gpt-5.6-luna [medium strict] | metric_inflation | 18 | 1.00 | 0.94 | 1.00 | 1.00 | 0.94 (n=18) | — (n=0) |
| gpt-5.6-luna [medium strict] | label_corruption | 18 | 0.56 | 1.00 | 1.00 | 1.00 | 1.00 (n=18) | — (n=0) |
| gpt-5.6-luna [medium strict] | lr_warmup | 18 | 0.97 | 0.94 | 1.00 | 1.00 | 0.94 (n=18) | — (n=0) |
| gpt-5.6-luna [medium strict] | **all non-crash** | 90 | 0.90 | 0.90 | 1.00 | 1.00 | 0.90 (n=90) | — (n=0) |
| gpt-5.6-luna [none strict] | data_leakage | 36 | 1.00 | 0.11 | 1.00 | 1.00 | 0.11 (n=36) | — (n=0) |
| gpt-5.6-luna [none strict] | metric_inflation | 18 | 1.00 | 0.33 | 1.00 | 1.00 | 0.33 (n=18) | — (n=0) |
| gpt-5.6-luna [none strict] | label_corruption | 18 | 0.97 | 0.44 | 0.94 | 1.00 | 0.47 (n=17) | 0.00 (n=1) |
| gpt-5.6-luna [none strict] | lr_warmup | 18 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 (n=18) | — (n=0) |
| gpt-5.6-luna [none strict] | **all non-crash** | 90 | 0.99 | 0.40 | 0.99 | 1.00 | 0.40 (n=89) | 0.00 (n=1) |

Leakage's gated derivation lives in `datautil.py` (`_derived_column`):

| condition | opened datautil.py (leakage cases) | ReAct detection if opened | if not |
|---|---|---|---|
| claude-sonnet-5 [thinking off] | 36/36 | 0.61 | — |
| claude-sonnet-5 [xhigh] | 36/36 | 0.81 | — |
| gpt-5.6-luna [medium strict] | 36/36 | 0.81 | — |
| gpt-5.6-luna [none strict] | 5/36 | 0.20 | 0.10 |

## Reading (exploratory)

- **Supported for metric inflation under Sonnet:** ReAct opened `train.py` in only half the metric-inflation
  cases. It detected 0.78 when it did and 0.00 when it did not; static, which always has `train.py`, detects
  0.97–1.00.
- **Not supported for leakage:** Sonnet and Luna-medium ReAct opened `train.py` and `datautil.py` in every
  leakage case and still detected only 0.61–0.81. Seeing the path is not sufficient there; static's advantage on
  leakage has another source.
- **Luna `none`:** ReAct detection 0.40 against static 0.99, while opening `train.py` in 89/90 cases. Its static
  ceiling is largely the flag-everything policy (`docs/audits/stage4_part2_control_false_alarms.md`, L39), which
  does not carry over to ReAct. ReAct has no control cells, so its false alarms cannot be measured here.
- **Luna `medium`:** equal (0.90 vs 0.90). Label corruption goes the other way for three conditions (ReAct ≥
  static).
