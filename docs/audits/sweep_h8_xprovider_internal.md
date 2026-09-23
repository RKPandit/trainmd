# Sweep h8_xprovider — INTERNAL report (hidden-band stratification)

> INTERNAL-ONLY by design. Generated from local cases by `harness/report_gen.py` (`make report NAME=h8_xprovider`); do NOT hand-edit. The hidden band label is a case-quality label — the agent never sees it and it is never the stratification key — and the public release never carries it, so this table **cannot be rebuilt from the release**. The release-reproducible report is `sweep_h8_xprovider_generated.md`.

## Pooled — all providers


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.028 [0.000, 0.083] | 1/36 | 1/18 |
| numbers | out_of_band | 0.000 [0, 0.527]† | 0/4 | 0/2 |
| off | in_band | 0.028 [0.000, 0.083] | 1/36 | 1/18 |
| off | out_of_band | 0.000 [0, 0.527]† | 0/4 | 0/2 |
| rule | in_band | 0.056 [0.000, 0.139] | 2/36 | 2/18 |
| rule | out_of_band | 0.500 [0.000, 1.000] | 2/4 | 1/2 |

† zero-event rate: `[0, x]` is a one-sided 95% Clopper–Pearson upper bound (0 observed events is not 0 uncertainty — e.g. 0/20 ⇒ ≤0.139, 0/2 ⇒ ≤0.776); only the upper edge is bounded, the point estimate is 0.

## Provider: anthropic


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.056 [0.000, 0.167] | 1/18 | 1/18 |
| numbers | out_of_band | 0.000 [0, 0.776]† | 0/2 | 0/2 |
| off | in_band | 0.056 [0.000, 0.167] | 1/18 | 1/18 |
| off | out_of_band | 0.000 [0, 0.776]† | 0/2 | 0/2 |
| rule | in_band | 0.111 [0.000, 0.278] | 2/18 | 2/18 |
| rule | out_of_band | 0.500 [0.000, 1.000] | 1/2 | 1/2 |

† zero-event rate: `[0, x]` is a one-sided 95% Clopper–Pearson upper bound (0 observed events is not 0 uncertainty — e.g. 0/20 ⇒ ≤0.139, 0/2 ⇒ ≤0.776); only the upper edge is bounded, the point estimate is 0.

## Provider: openai


### Control FP rate stratified by HIDDEN band position

| arm | band | FP rate (95% CI) | n_fp / n_trials | unique FP cases / control cases |
|---|---|---|---|---|
| numbers | in_band | 0.000 [0, 0.153]† | 0/18 | 0/18 |
| numbers | out_of_band | 0.000 [0, 0.776]† | 0/2 | 0/2 |
| off | in_band | 0.000 [0, 0.153]† | 0/18 | 0/18 |
| off | out_of_band | 0.000 [0, 0.776]† | 0/2 | 0/2 |
| rule | in_band | 0.000 [0, 0.153]† | 0/18 | 0/18 |
| rule | out_of_band | 0.500 [0.000, 1.000] | 1/2 | 1/2 |

† zero-event rate: `[0, x]` is a one-sided 95% Clopper–Pearson upper bound (0 observed events is not 0 uncertainty — e.g. 0/20 ⇒ ≤0.139, 0/2 ⇒ ≤0.776); only the upper edge is bounded, the point estimate is 0.

