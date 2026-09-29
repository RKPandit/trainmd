# Stage 4 Part 2 — control false alarms by condition · EXPLORATORY (no verdict changes)

> Read-only investigation (author's request, 2026-09-29), after the pre-registered verdicts were computed (H11 and
> H12 both UNTESTABLE by the headroom rule; FINDINGS F24). Nothing here changes a verdict, an estimand or a rule.
> Source: the stored trial records of `stage4_part2` (Stage A, static) and `stage4_part1`; control/faulty from
> `cases/registry.hidden.yaml`; "detected" = the scorer's `detected_predicted`. J = Youden's J = non-crash faulty
> detection − control false-alarm rate (healthy and benign pooled).

## 1. Per condition × arm (Stage A, static)

| sweep | agent | condition | arm | healthy FA | benign FA | faulty det (non-crash) | crash det | J (non-crash det − control FA) |
|---|---|---|---|---|---|---|---|---|
| stage4_part2 | static | claude-sonnet-5 [thinking off] | off | 0/20 (0.00) | 0/72 (0.00) | 171/180 (0.95) | 36/36 (1.00) | +0.95 |
| stage4_part2 | static | claude-sonnet-5 [thinking off] | stats | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | claude-sonnet-5 [thinking off] | rule | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | claude-sonnet-5 [xhigh] | off | 0/20 (0.00) | 0/72 (0.00) | 166/180 (0.92) | 36/36 (1.00) | +0.92 |
| stage4_part2 | static | claude-sonnet-5 [xhigh] | stats | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | claude-sonnet-5 [xhigh] | rule | 0/20 (0.00) | 0/72 (0.00) | 179/180 (0.99) | 36/36 (1.00) | +0.99 |
| stage4_part2 | static | gpt-5.6-luna [medium strict] | off | 0/20 (0.00) | 0/72 (0.00) | 162/180 (0.90) | 36/36 (1.00) | +0.90 |
| stage4_part2 | static | gpt-5.6-luna [medium strict] | stats | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | gpt-5.6-luna [medium strict] | rule | 1/20 (0.05) | 4/72 (0.06) | 179/180 (0.99) | 36/36 (1.00) | +0.94 |
| stage4_part2 | static | gpt-5.6-luna [none strict] | off | 18/20 (0.90) | 66/72 (0.92) | 179/180 (0.99) | 36/36 (1.00) | +0.08 |
| stage4_part2 | static | gpt-5.6-luna [none strict] | stats | 18/20 (0.90) | 52/72 (0.72) | 177/180 (0.98) | 36/36 (1.00) | +0.22 |
| stage4_part2 | static | gpt-5.6-luna [none strict] | rule | 9/20 (0.45) | 37/72 (0.51) | 180/180 (1.00) | 36/36 (1.00) | +0.50 |
| stage4_part2 | static | gpt-6-luna [medium strict] | off | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | gpt-6-luna [medium strict] | stats | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | gpt-6-luna [medium strict] | rule | 1/20 (0.05) | 4/72 (0.06) | 180/180 (1.00) | 36/36 (1.00) | +0.95 |
| stage4_part2 | static | gpt-6-sol [medium strict] | off | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | gpt-6-sol [medium strict] | stats | 0/20 (0.00) | 0/72 (0.00) | 180/180 (1.00) | 36/36 (1.00) | +1.00 |
| stage4_part2 | static | gpt-6-sol [medium strict] | rule | 0/20 (0.00) | 3/72 (0.04) | 180/180 (1.00) | 36/36 (1.00) | +0.97 |

**One condition flags the controls: GPT-5.6 Luna, reasoning `none` (strict).** Off arm: 18/20 healthy and 66/72
benign controls flagged (J = +0.08), against 0/92 for every other condition in the off arm. Its faulty detection
(0.99) is therefore not diagnostic: it flags nearly everything. Luna `medium` (strict) flags 0/92 in the off arm.
(Stage B, ReAct, has no control cells by design.)

## 2. Where `detected: true` comes from — the model, not the adapter

Five flagged off-arm controls of GPT-5.6 Luna `none` (three healthy, two benign), the model's `submit` call next to
the diagnosis the scorer saw:

| case (control) | band | model's submit: diagnosis | conf. | repair patch | scorer's diagnosis |
|---|---|---|---|---|---|
| case_0109 (healthy) | in band | `detected: true`, `validation_subset_metric_manipulation` | 0.99 | `metrics.eval_subset_fraction: null` | identical |
| case_0110 (healthy) | in band | `detected: true`, `validation_subset_metric_manipulation` | 0.99 | `metrics.eval_subset_fraction: null` | identical |
| case_0111 (healthy) | in band | `detected: true`, `visible_metric_subset_selection` | 0.99 | `metrics.eval_subset_fraction: null` | identical |
| case_0130 (benign bs128) | in band | `detected: true`, `stale_resolved_input_dim_override` | 0.93 | `model.input_dim: null` | identical |
| case_0131 (benign bs128) | in band | `detected: true`, `reported_metric_subset_selection_bias` | 0.98 | `metrics.eval_subset_fraction: null` | identical |

Example rationales (verbatim): "The code supports confidence-selected subset accuracy that inflates the visible metric
when configured; removing that optional setting restores full validation accuracy. The supplied config omits it…";
"The resolved configuration hard-codes model.input_dim=105, while the script explicitly prioritizes that value over the
loaded feature width…".

**The strict adapter cannot introduce it.** `harness/llm/strict_schema.py::from_strict_args` only drops null
top-level fields and null evidence-detail fields and turns patch pairs back into a map; `diagnosis` passes through
unchanged, and `diagnosis.detected` is a REQUIRED boolean in the strict schema (never nullable). The provider's raw
output is used for conversation replay but not persisted, so the recorded `arguments` are post-adapter — which for
`diagnosis`, `confidence` and `rationale` is the model's output verbatim.

**What is flagged:** DORMANT fault code paths. Across all 200 flagged controls of Luna `none` (all arms): 144 name the
metric-subset path, 36 the `input_dim` override, 12 the auxiliary feature, 8 other; the repair unsets
`metrics.eval_subset_fraction` (145) or `model.input_dim` (46); 88 rationales themselves say the path is not
configured / optional / inactive. The workload's `train.py` carries every fault's gated code path (absent keys =
clean), and Luna at reasoning `none` reports the capability as the incident.

## 3. Part 1's non-strict Luna on the same controls

| sweep | agent | condition | arm | healthy FA | benign FA | faulty det (non-crash) | crash det | J (non-crash det − control FA) |
|---|---|---|---|---|---|---|---|---|
| stage4_part1 | static | gpt-5.6-luna [-] | off | 0/20 (0.00) | 0/72 (0.00) | 152/180 (0.84) | 30/36 (0.83) | +0.84 |
| stage4_part1 | static | gpt-5.6-luna [-] | stats | 0/20 (0.00) | 0/72 (0.00) | 161/180 (0.89) | 26/36 (0.72) | +0.89 |
| stage4_part1 | static | gpt-5.6-luna [-] | rule | 1/20 (0.05) | 3/72 (0.04) | 165/180 (0.92) | 31/36 (0.86) | +0.87 |

Part 1's Luna (non-strict tools, the API's default reasoning effort — no effort set) flagged 0/20 healthy and 0/72
benign in the off arm; Part 2's Luna `medium` (strict) also 0/92. So the flag-everything pattern goes with reasoning
`none`, not with strict mode.

## 4. Consequence for H11 (exploratory reading; the verdict stands as computed)

H11's less-reasoning condition IS Luna `none`. Its off-arm detection is ≥ 0.97 on every mechanism (every 95% upper
bound 1.000, against the rule's < 0.85), so no mechanism has headroom and H11 is UNTESTABLE — but that ceiling is produced largely by the
flag-everything policy, not by diagnosis. Likewise its descriptive per-mechanism Δ (e.g. label_corruption −0.42,
medium lower than none) compares a discriminating condition with a non-discriminating one. H12 is not affected
(both Sonnet conditions: 0/92 false alarms in every arm). LIMITATIONS L39.
