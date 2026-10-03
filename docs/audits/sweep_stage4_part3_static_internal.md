# Sweep stage4_part3_static — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=stage4_part3_static`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key. This table is not part of the release-reproducible report (`sweep_stage4_part3_static_generated.md`), which reads band labels only from per-case metadata; the fields a release contains are listed in its `FIELD_INVENTORY.json`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.088 [0.063, 0.114] | 35/396 | 33/99 |
| off.v2 | out_of_band | 0.350 [0.250, 0.450] | 7/20 | 5/5 |
| rule.v2 | in_band | 0.129 [0.104, 0.154] | 51/396 | 51/99 |
| rule.v2 | out_of_band | 0.600 [0.400, 0.850] | 12/20 | 5/5 |
| stats.v2 | in_band | 0.071 [0.048, 0.096] | 28/396 | 26/99 |
| stats.v2 | out_of_band | 0.400 [0.300, 0.500] | 8/20 | 5/5 |

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.010 [0.000, 0.025]‡ | 2/198 | 2/99 |
| off.v2 | out_of_band | 0.000 [0, 0.522]† | 0/10 | 0/5 |
| rule.v2 | in_band | 0.000 [0, 0.037]† | 0/198 | 0/99 |
| rule.v2 | out_of_band | 0.400 [0.100, 0.700] | 4/10 | 3/5 |
| stats.v2 | in_band | 0.010 [0.000, 0.025]‡ | 2/198 | 2/99 |
| stats.v2 | out_of_band | 0.200 [0.000, 0.400]‡ | 2/10 | 2/5 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.167 [0.121, 0.217] | 33/198 | 32/99 |
| off.v2 | out_of_band | 0.700 [0.500, 0.900] | 7/10 | 5/5 |
| rule.v2 | in_band | 0.258 [0.207, 0.308] | 51/198 | 51/99 |
| rule.v2 | out_of_band | 0.800 [0.600, 1.000] | 8/10 | 5/5 |
| stats.v2 | in_band | 0.131 [0.091, 0.172] | 26/198 | 26/99 |
| stats.v2 | out_of_band | 0.600 [0.300, 0.900] | 6/10 | 4/5 |

## Condition: claude-haiku-4-5-20251001


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.020 [0.000, 0.051]‡ | 2/99 | 2/99 |
| off.v2 | out_of_band | 0.000 [0, 0.522]† | 0/5 | 0/5 |
| rule.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| rule.v2 | out_of_band | 0.600 [0.200, 1.000] | 3/5 | 3/5 |
| stats.v2 | in_band | 0.020 [0.000, 0.051]‡ | 2/99 | 2/99 |
| stats.v2 | out_of_band | 0.400 [0.000, 0.800]‡ | 2/5 | 2/5 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: claude-sonnet-5 (thinking=disabled)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| off.v2 | out_of_band | 0.000 [0, 0.522]† | 0/5 | 0/5 |
| rule.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| rule.v2 | out_of_band | 0.200 [0.000, 0.600]‡ | 1/5 | 1/5 |
| stats.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| stats.v2 | out_of_band | 0.000 [0, 0.522]† | 0/5 | 0/5 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: gpt-5.6-luna (effort=medium, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.020 [0.000, 0.051]‡ | 2/99 | 2/99 |
| off.v2 | out_of_band | 0.400 [0.000, 0.800]‡ | 2/5 | 2/5 |
| rule.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| rule.v2 | out_of_band | 0.600 [0.200, 1.000] | 3/5 | 3/5 |
| stats.v2 | in_band | 0.000 [0, 0.037]† | 0/99 | 0/99 |
| stats.v2 | out_of_band | 0.400 [0.000, 0.800]‡ | 2/5 | 2/5 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Condition: gpt-5.6-luna (effort=none, strict)


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.313 [0.222, 0.404] | 31/99 | 31/99 |
| off.v2 | out_of_band | 1.000 [1.000, 1.000] | 5/5 | 5/5 |
| rule.v2 | in_band | 0.515 [0.414, 0.616] | 51/99 | 51/99 |
| rule.v2 | out_of_band | 1.000 [1.000, 1.000] | 5/5 | 5/5 |
| stats.v2 | in_band | 0.263 [0.182, 0.343] | 26/99 | 26/99 |
| stats.v2 | out_of_band | 0.800 [0.400, 1.000] | 4/5 | 4/5 |

