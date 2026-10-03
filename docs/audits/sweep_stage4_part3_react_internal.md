# Sweep stage4_part3_react — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=stage4_part3_react`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key. This table is not part of the release-reproducible report (`sweep_stage4_part3_react_generated.md`), which reads band labels only from per-case metadata; the fields a release contains are listed in its `FIELD_INVENTORY.json`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.028 [0.013, 0.045] | 11/396 | 10/99 |
| off.v2 | out_of_band | 0.200 [0.000, 0.500] | 4/20 | 2/5 |
| stats.v2 | in_band | 0.078 [0.051, 0.109] | 31/396 | 26/99 |
| stats.v2 | out_of_band | 0.550 [0.300, 0.800] | 11/20 | 5/5 |

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.040 [0.015, 0.071] | 8/198 | 8/99 |
| off.v2 | out_of_band | 0.100 [0.000, 0.300]‡ | 1/10 | 1/5 |
| stats.v2 | in_band | 0.040 [0.015, 0.071] | 8/198 | 8/99 |
| stats.v2 | out_of_band | 0.300 [0.000, 0.700] | 3/10 | 2/5 |

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.015 [0.000, 0.035] | 3/198 | 3/99 |
| off.v2 | out_of_band | 0.300 [0.000, 0.700] | 3/10 | 2/5 |
| stats.v2 | in_band | 0.116 [0.071, 0.162] | 23/198 | 21/99 |
| stats.v2 | out_of_band | 0.800 [0.600, 1.000] | 8/10 | 5/5 |

## Condition: claude-haiku-4-5-20251001


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.081 [0.030, 0.141] | 8/99 | 8/99 |
| off.v2 | out_of_band | 0.200 [0.000, 0.600]‡ | 1/5 | 1/5 |
| stats.v2 | in_band | 0.081 [0.030, 0.141] | 8/99 | 8/99 |
| stats.v2 | out_of_band | 0.400 [0.000, 0.800]‡ | 2/5 | 2/5 |

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: claude-sonnet-5 (thinking=disabled)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| off.v2 | out_of_band | 0.000 [0, 0.522]† | 0/5 | 0/5 |
| stats.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| stats.v2 | out_of_band | 0.200 [0.000, 0.600]‡ | 1/5 | 1/5 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: gpt-5.6-luna (effort=medium, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.020 [0.000, 0.051]‡ | 2/99 | 2/99 |
| off.v2 | out_of_band | 0.200 [0.000, 0.600]‡ | 1/5 | 1/5 |
| stats.v2 | in_band | 0.020 [0.000, 0.051]‡ | 2/99 | 2/99 |
| stats.v2 | out_of_band | 0.600 [0.200, 1.000] | 3/5 | 3/5 |

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: gpt-5.6-luna (effort=none, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.010 [0.000, 0.030]‡ | 1/99 | 1/99 |
| off.v2 | out_of_band | 0.400 [0.000, 0.800]‡ | 2/5 | 2/5 |
| stats.v2 | in_band | 0.212 [0.131, 0.293] | 21/99 | 21/99 |
| stats.v2 | out_of_band | 1.000 [1.000, 1.000] | 5/5 | 5/5 |

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

