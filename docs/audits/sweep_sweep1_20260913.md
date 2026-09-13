# Sweep sweep1 — 2026-09-13

records=324 excluded_trusted=0 excluded_superseded=0

n_cases=27 (6 per faulty operator × 4 + 3 controls; 12 trials/case). Primary contrasts below use case-clustered uncertainty — trials within a case are not independent.

## Post-hoc scoring corrections

Three Sweep-1 corrections, disclosed, originals kept (see docs/DECISIONS.md, 2026-09-13). Corrections 1–2 were scoring/schema **artifacts, not model behaviour**; correction 3 is **model-side output folding, not a harness bug** — a well-formed repair the model misplaced. All three *removed* a harness-imposed penalty; none changed ground truth.

- **Identification** re-scored with root-token matching (`root_token_v1`): correct synonyms outside the enumerated `accepted_classes` now credited; two-fault / `none`-on-faulty rejected. Touches **H3, H4** only.
- **Shape recovery**: `null` = unset an absent-when-clean key (oracle-equivalent to the reference value).
- **Correction #3 (folded repair recovery, `parser_fix_v1`)**: MODEL-SIDE output folding — some models emitted the repair as text inside the `rationale` string instead of the structured `repair_spec` field. This is **not** a harness parser bug (the structured tool_use input was recorded faithfully); we now RECOVER a single well-formed `{repair_type, patches}` object the model misplaced (strict, no key scraping) and flag it. Recovery moves recovery on every faulty operator that had folded repairs.
- **Unchanged:** detection and evidence → **H1, H2, H6, controls** do not move.

### Repair submission channel (structured vs folded-recovery)

Folding rate: **31/324 (9.6%)** of submissions had the repair folded into a string field and recovered via `parser_fix_v1`; 199 submitted the repair in the correct structured field. (A tool-use-reliability finding — see FINDINGS.)

| operator | agent | anchor | structured repair | folded→recovered |
|---|---|---|---|---|
| control.healthy.v1 | react | on | 2 | 0 |
| control.healthy.v1 | static | on | 2 | 0 |
| crash.shape_mismatch.v1 | react | off | 15 | 3 |
| crash.shape_mismatch.v1 | react | on | 15 | 3 |
| crash.shape_mismatch.v1 | static | off | 16 | 2 |
| crash.shape_mismatch.v1 | static | on | 12 | 6 |
| silent.data_leakage.v1 | react | off | 4 | 0 |
| silent.data_leakage.v1 | react | on | 15 | 2 |
| silent.data_leakage.v1 | static | on | 16 | 1 |
| silent.label_corruption.v1 | react | off | 4 | 7 |
| silent.label_corruption.v1 | react | on | 16 | 1 |
| silent.label_corruption.v1 | static | off | 1 | 0 |
| silent.label_corruption.v1 | static | on | 18 | 0 |
| silent.lr_warmup.v1 | react | off | 15 | 3 |
| silent.lr_warmup.v1 | react | on | 14 | 3 |
| silent.lr_warmup.v1 | static | off | 16 | 0 |
| silent.lr_warmup.v1 | static | on | 18 | 0 |

### Identification: original vs corrected (per operator)

| operator | n | identification_original | identification_corrected |
|---|---|---|---|
| control.healthy.v1 | 36 | 0.8889 | 0.8889 |
| crash.shape_mismatch.v1 | 72 | 0.3472 | 0.9861 |
| silent.data_leakage.v1 | 72 | 0.0141 | 0.4366 |
| silent.label_corruption.v1 | 72 | 0.0 | 0.6389 |
| silent.lr_warmup.v1 | 72 | 0.0 | 0.9437 |

## Primary contrasts — case-clustered (Stage 0 claim tightening)

n_trials=324, n_cases=27. Method: case-level nonparametric bootstrap, 10000 resamples, 95% percentile. No bare point estimates for primary contrasts.

**H1 — anchor-off detection gap (negative − positive symptom), pooled:** 0.556 [0.327, 0.774] (neg 0.639 on 12 cases − pos 0.083 on 6 cases). **Nearest-σ matched** mean paired gap: 0.528. *Symptom direction is perfectly confounded with operator identity (all positive = data_leakage); the matched contrast narrows σ but does NOT touch that confound — only a second positive-symptom operator can.*

**H6 — ReAct − static evidence F1 (overall, faulty ops):** 0.135 [0.075, 0.204] (n_cases=24). Point meets the pre-registered ≥0.10; the 95% CI lower bound dips below 0.10, so it is not robustly ≥0.10.

**Control detection FPR (anchor-on):** 0.222 [0.000, 0.500] — 4/18 trials from only **2 unique healthy case(s)** (case_0005, case_0006); bootstrapped over the 3 control cases. This is NOT a population false-positive rate; the interval width is the argument for 20+ controls in Sweep 2.

### Recovery — strict (primary) vs semantic (secondary), with id-gap CIs

| operator | n_trials | n_cases | identification | strict recovery | semantic recovery | id − strict (95% CI) | id − semantic (95% CI) |
|---|---|---|---|---|---|---|---|
| crash.shape_mismatch.v1 | 72 | 6 | 0.9861 | 0.75 | 0.9444 | 0.236 [0.208, 0.250] | 0.042 [0.014, 0.069] |
| silent.lr_warmup.v1 | 72 | 6 | 0.9306 | 0.8333 | 0.9028 | 0.097 [0.056, 0.139] | 0.028 [0.000, 0.056] |
| silent.label_corruption.v1 | 72 | 6 | 0.6389 | 0.5139 | 0.5833 | 0.125 [0.056, 0.194] | 0.056 [0.014, 0.111] |
| silent.data_leakage.v1 | 72 | 6 | 0.4306 | 0.3889 | 0.4306 | 0.042 [-0.056, 0.139] | 0.000 [-0.056, 0.069] |

*Strict recovery is the autonomous-success headline; the 9.6% folding is an agent-compliance failure of the system under test, so semantic recovery does not replace strict. On the strict endpoint identification exceeds recovery on 3/4 operators (CI excludes 0); semantic recovery nearly closes it, so most of the strict gap is submission-format compliance + strict admissibility, not inability to name the fault.*

## Scores by (operator, agent, anchor)

| operator | agent | anchor | n | detection | identification | evidence_f1 | recovery/no_unnec |
|---|---|---|---|---|---|---|---|
| control.healthy.v1 | react | off | 9 | 1.0 | 1.0 | 1.0 | 1.0 |
| control.healthy.v1 | react | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.7778 |
| control.healthy.v1 | static | off | 9 | 1.0 | 1.0 | 1.0 | 1.0 |
| control.healthy.v1 | static | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.7778 |
| crash.shape_mismatch.v1 | react | off | 18 | 1.0 | 0.9444 | 0.8222 | 0.8889 |
| crash.shape_mismatch.v1 | react | on | 18 | 1.0 | 1.0 | 0.8333 | 0.9444 |
| crash.shape_mismatch.v1 | static | off | 18 | 1.0 | 1.0 | 0.7704 | 0.9444 |
| crash.shape_mismatch.v1 | static | on | 18 | 1.0 | 1.0 | 0.8 | 1.0 |
| silent.data_leakage.v1 | react | off | 18 | 0.1667 | 0.0 | 0.0529 | 0.0 |
| silent.data_leakage.v1 | react | on | 18 | 1.0 | 0.9444 | 0.7697 | 0.8889 |
| silent.data_leakage.v1 | static | off | 18 | 0.0 | 0.0 | 0.0 | 0.0 |
| silent.data_leakage.v1 | static | on | 18 | 1.0 | 0.7778 | 0.8348 | 0.8333 |
| silent.label_corruption.v1 | react | off | 18 | 0.6111 | 0.5556 | 0.5704 | 0.3889 |
| silent.label_corruption.v1 | react | on | 18 | 1.0 | 1.0 | 0.7815 | 0.9444 |
| silent.label_corruption.v1 | static | off | 18 | 0.0556 | 0.0 | 0.0 | 0.0 |
| silent.label_corruption.v1 | static | on | 18 | 1.0 | 1.0 | 0.7037 | 1.0 |
| silent.lr_warmup.v1 | react | off | 18 | 1.0 | 1.0 | 0.8929 | 0.9444 |
| silent.lr_warmup.v1 | react | on | 18 | 0.9444 | 0.9444 | 0.8466 | 0.9444 |
| silent.lr_warmup.v1 | static | off | 18 | 0.8889 | 0.8333 | 0.6918 | 0.7778 |
| silent.lr_warmup.v1 | static | on | 18 | 1.0 | 0.9444 | 0.7672 | 0.9444 |

## Hypothesis metrics

```
H1_positive_symptom_blindness:
  'on':
    leakage_detection: 1.0
    negative_symptom_detection: 1.0
  'off':
    leakage_detection: 0.0857
    negative_symptom_detection: 0.6389
H2_detection_vs_sigma_by_anchor:
  status: REFUTED (pre-registered prediction not met)
  preregistered: a single monotone detection-vs-sigma curve with a FITTED 50% threshold
    and interval
  outcome: no threshold was fitted and the pooled detection-vs-sigma curve is non-monotone;
    the pre-registered prediction is not met
  exploratory_followup: "POST-HOC EXPLORATORY (not confirmatory): symptom SIGN appears\
    \ to moderate the magnitude->detection relationship \u2014 within negative-symptom\
    \ faults detection rises with sigma, positive-symptom faults floor regardless.\
    \ To be PRE-REGISTERED and tested prospectively in a later sweep, not claimed\
    \ from this data."
  sigma_axis_note: 'detection is reported primarily against VISIBLE signed sigma (what
    the agent can observe: negative = inflated/positive symptom); hidden sigma is
    benchmark harm, reported separately, not an agent-visible signal'
  by_case:
  - case_id: case_0001
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 68.643519
    hidden_sigma_distance: 44.550802
    symptom_direction: negative
    detection_rate: 1.0
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 1.0
    detection_rate_react: 1.0
    detection_rate_static: 1.0
  - case_id: case_0002
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 19.988757
    hidden_sigma_distance: 15.739426
    symptom_direction: negative
    detection_rate: 0.75
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.5
    detection_rate_react: 1.0
    detection_rate_static: 0.5
  - case_id: case_0004
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -29.154101
    hidden_sigma_distance: 23.121536
    symptom_direction: positive
    detection_rate: 0.5
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.0
    detection_rate_react: 0.5
    detection_rate_static: 0.5
  - case_id: case_0013
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -5.752646
    hidden_sigma_distance: 5.848809
    symptom_direction: positive
    detection_rate: 0.6667
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.3333
    detection_rate_react: 0.8333
    detection_rate_static: 0.5
  - case_id: case_0014
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -3.607804
    hidden_sigma_distance: 5.991736
    symptom_direction: positive
    detection_rate: 0.5
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.0
    detection_rate_react: 0.5
    detection_rate_static: 0.5
  - case_id: case_0015
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -27.789021
    hidden_sigma_distance: 20.541079
    symptom_direction: positive
    detection_rate: 0.5833
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.1667
    detection_rate_react: 0.6667
    detection_rate_static: 0.5
  - case_id: case_0016
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -70.203704
    hidden_sigma_distance: 64.117161
    symptom_direction: positive
    detection_rate: 0.5455
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.0
    detection_rate_react: 0.6
    detection_rate_static: 0.5
  - case_id: case_0017
    operator: silent.data_leakage.v1
    strength: null
    visible_sigma_distance: -70.691138
    hidden_sigma_distance: 56.304813
    symptom_direction: positive
    detection_rate: 0.5
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.0
    detection_rate_react: 0.5
    detection_rate_static: 0.5
  - case_id: case_0018
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 9.750661
    hidden_sigma_distance: 10.793875
    symptom_direction: negative
    detection_rate: 0.6667
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.3333
    detection_rate_react: 0.8333
    detection_rate_static: 0.5
  - case_id: case_0019
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 11.993386
    hidden_sigma_distance: 11.868741
    symptom_direction: negative
    detection_rate: 0.5
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.0
    detection_rate_react: 0.5
    detection_rate_static: 0.5
  - case_id: case_0020
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 18.916005
    hidden_sigma_distance: 15.596014
    symptom_direction: negative
    detection_rate: 0.6667
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.3333
    detection_rate_react: 0.6667
    detection_rate_static: 0.6667
  - case_id: case_0021
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 26.03373
    hidden_sigma_distance: 18.46281
    symptom_direction: negative
    detection_rate: 0.6667
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.3333
    detection_rate_react: 0.8333
    detection_rate_static: 0.5
  - case_id: case_0022
    operator: silent.label_corruption.v1
    strength: null
    visible_sigma_distance: 22.52381
    hidden_sigma_distance: 17.53087
    symptom_direction: negative
    detection_rate: 0.75
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.5
    detection_rate_react: 1.0
    detection_rate_static: 0.5
  - case_id: case_0023
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 37.734127
    hidden_sigma_distance: 24.124939
    symptom_direction: negative
    detection_rate: 0.8333
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 0.6667
    detection_rate_react: 1.0
    detection_rate_static: 0.6667
  - case_id: case_0024
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 68.643519
    hidden_sigma_distance: 44.550802
    symptom_direction: negative
    detection_rate: 1.0
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 1.0
    detection_rate_react: 1.0
    detection_rate_static: 1.0
  - case_id: case_0025
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 68.643519
    hidden_sigma_distance: 44.550802
    symptom_direction: negative
    detection_rate: 1.0
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 1.0
    detection_rate_react: 1.0
    detection_rate_static: 1.0
  - case_id: case_0026
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 68.643519
    hidden_sigma_distance: 44.550802
    symptom_direction: negative
    detection_rate: 1.0
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 1.0
    detection_rate_react: 1.0
    detection_rate_static: 1.0
  - case_id: case_0027
    operator: silent.lr_warmup.v1
    strength: null
    visible_sigma_distance: 68.643519
    hidden_sigma_distance: 44.550802
    symptom_direction: negative
    detection_rate: 1.0
    detection_rate_anchor_on: 1.0
    detection_rate_anchor_off: 1.0
    detection_rate_react: 1.0
    detection_rate_static: 1.0
  by_anchor:
    'on':
      detection_rate: 1.0
      n_trials: 108
      n_cases: 18
    'off':
      detection_rate: 0.4579
      n_trials: 108
      n_cases: 18
H3_doing_understanding_gap:
  control.healthy.v1:
    recovery_rate: 0.0
    identification_rate: 0.8889
    identification_rate_original: 0.8889
  crash.shape_mismatch.v1:
    recovery_rate: 0.9444
    identification_rate: 0.9861
    identification_rate_original: 0.3472
  silent.data_leakage.v1:
    recovery_rate: 0.4306
    identification_rate: 0.4366
    identification_rate_original: 0.0141
  silent.label_corruption.v1:
    recovery_rate: 0.5833
    identification_rate: 0.6389
    identification_rate_original: 0.0
  silent.lr_warmup.v1:
    recovery_rate: 0.9028
    identification_rate: 0.9437
    identification_rate_original: 0.0
H4_repeat_agreement:
  mean_repeat_agreement: 0.8241
  mean_repeat_agreement_original: 0.7037
H6_tools_vs_static:
  control.healthy.v1:
    react_evidence_f1: 0.8889
    static_evidence_f1: 0.8889
    react_minus_static: 0.0
  crash.shape_mismatch.v1:
    react_evidence_f1: 0.8278
    static_evidence_f1: 0.7852
    react_minus_static: 0.0426
  silent.data_leakage.v1:
    react_evidence_f1: 0.4231
    static_evidence_f1: 0.4174
    react_minus_static: 0.0057
  silent.label_corruption.v1:
    react_evidence_f1: 0.6759
    static_evidence_f1: 0.3519
    react_minus_static: 0.324
  silent.lr_warmup.v1:
    react_evidence_f1: 0.8946
    static_evidence_f1: 0.7295
    react_minus_static: 0.1651
H5: Sweep 2 (single model here)
controls:
  detection_fpr: 0.1111
  false_intervention_rate: 0.1111
  n: 36

```
