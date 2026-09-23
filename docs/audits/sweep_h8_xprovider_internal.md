# Sweep h8_xprovider — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=h8_xprovider`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key — and the public release never carries it, so this table **cannot be rebuilt from the release**. The release-reproducible report is `sweep_h8_xprovider_generated.md`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.028 [0.000, 0.083]‡ | 1/36 | 1/18 |
| numbers | out_of_band | 0.000 [0, 0.842]† | 0/4 | 0/2 |
| off | in_band | 0.028 [0.000, 0.083]‡ | 1/36 | 1/18 |
| off | out_of_band | 0.000 [0, 0.842]† | 0/4 | 0/2 |
| rule | in_band | 0.056 [0.000, 0.139]‡ | 2/36 | 2/18 |
| rule | out_of_band | 0.500 [0.000, 1.000]‡ | 2/4 | 1/2 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.056 [0.000, 0.167]‡ | 1/18 | 1/18 |
| numbers | out_of_band | 0.000 [0, 0.842]† | 0/2 | 0/2 |
| off | in_band | 0.056 [0.000, 0.167]‡ | 1/18 | 1/18 |
| off | out_of_band | 0.000 [0, 0.842]† | 0/2 | 0/2 |
| rule | in_band | 0.111 [0.000, 0.278]‡ | 2/18 | 2/18 |
| rule | out_of_band | 0.500 [0.000, 1.000]‡ | 1/2 | 1/2 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.000 [0, 0.185]† | 0/18 | 0/18 |
| numbers | out_of_band | 0.000 [0, 0.842]† | 0/2 | 0/2 |
| off | in_band | 0.000 [0, 0.185]† | 0/18 | 0/18 |
| off | out_of_band | 0.000 [0, 0.842]† | 0/2 | 0/2 |
| rule | in_band | 0.000 [0, 0.185]† | 0/18 | 0/18 |
| rule | out_of_band | 0.500 [0.000, 1.000]‡ | 1/2 | 1/2 |

† zero-event rate: `[0, x]` is the exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES (clusters), x = 1 − 0.025^(1/n_cases) — 0 observed events is not 0 uncertainty (e.g. 20 cases ⇒ [0, 0.168], 3 cases ⇒ [0, 0.708]). The point estimate is 0.

‡ 1–2 events: the case-clustered percentile bootstrap interval is unreliable at this count — it understates uncertainty (e.g. 1 of 19 cases: bootstrap upper 0.158 vs exact Clopper–Pearson 0.260). Read as indicative only.

