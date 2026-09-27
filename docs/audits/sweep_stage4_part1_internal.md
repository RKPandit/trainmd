# Sweep stage4_part1 — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=stage4_part1`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key. This table is not part of the release-reproducible report (`sweep_stage4_part1_generated.md`), which reads band labels only from per-case metadata; the fields a release contains are listed in its `FIELD_INVENTORY.json`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.025 [0.006, 0.049] | 4/162 | 4/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/22 | 0/11 |
| rule.v2 | in_band | 0.099 [0.056, 0.148] | 16/162 | 15/81 |
| rule.v2 | out_of_band | 0.091 [0.000, 0.227]‡ | 2/22 | 2/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/162 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/22 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.049 [0.012, 0.099] | 4/81 | 4/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.148 [0.074, 0.222] | 12/81 | 12/81 |
| rule.v2 | out_of_band | 0.182 [0.000, 0.455]‡ | 2/11 | 2/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| off.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| off.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| rule.v2 | in_band | 0.049 [0.012, 0.099] | 4/81 | 4/81 |
| rule.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |
| stats.v2 | in_band | 0.000 [0, 0.045]† | 0/81 | 0/81 |
| stats.v2 | out_of_band | 0.000 [0, 0.285]† | 0/11 | 0/11 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

