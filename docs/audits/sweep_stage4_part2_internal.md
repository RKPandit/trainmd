# Sweep stage4_part2 — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=stage4_part2`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key. This table is not part of the release-reproducible report (`sweep_stage4_part2_generated.md`), which reads band labels only from per-case metadata; the fields a release contains are listed in its `FIELD_INVENTORY.json`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.154 [0.144, 0.163] | 75/486 | 75/81 |
| off.v2 | out_of_band | 0.136 [0.091, 0.167] | 9/66 | 9/11 |
| rule.v2 | in_band | 0.113 [0.084, 0.146] | 55/486 | 43/81 |
| rule.v2 | out_of_band | 0.061 [0.015, 0.106] | 4/66 | 4/11 |
| stats.v2 | in_band | 0.126 [0.109, 0.140] | 61/486 | 61/81 |
| stats.v2 | out_of_band | 0.136 [0.091, 0.167] | 9/66 | 9/11 |

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/162 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/22 | 0/11 |
| rule.v2 | in_band | 0.000 [0, 0.045]† | 0/162 | 0/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/22 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/162 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/22 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.231 [0.216, 0.244] | 75/324 | 75/81 |
| off.v2 | out_of_band | 0.205 [0.136, 0.250] | 9/44 | 9/11 |
| rule.v2 | in_band | 0.170 [0.127, 0.219] | 55/324 | 43/81 |
| rule.v2 | out_of_band | 0.091 [0.023, 0.159] | 4/44 | 4/11 |
| stats.v2 | in_band | 0.188 [0.164, 0.210] | 61/324 | 61/81 |
| stats.v2 | out_of_band | 0.205 [0.136, 0.250] | 9/44 | 9/11 |

## Condition: claude-sonnet-5 (effort=xhigh)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

## Condition: claude-sonnet-5 (thinking=disabled)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

## Condition: gpt-5.6-luna (effort=medium, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.062 [0.012, 0.123] | 5/81 | 5/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

## Condition: gpt-5.6-luna (effort=none, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.926 [0.864, 0.975] | 75/81 | 75/81 |
| off.v2 | out_of_band | 0.818 [0.545, 1.000] | 9/11 | 9/11 |
| rule.v2 | in_band | 0.519 [0.420, 0.630] | 42/81 | 42/81 |
| rule.v2 | out_of_band | 0.364 [0.091, 0.636] | 4/11 | 4/11 |
| stats.v2 | in_band | 0.753 [0.654, 0.840] | 61/81 | 61/81 |
| stats.v2 | out_of_band | 0.818 [0.545, 1.000] | 9/11 | 9/11 |

## Condition: gpt-6-luna (effort=medium, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.062 [0.012, 0.123] | 5/81 | 5/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

## Condition: gpt-6-sol (effort=medium, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.037 [0.000, 0.086] | 3/81 | 3/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

