# Sweep sweep1 — 2026-09-13

records=324 excluded_trusted=0 excluded_superseded=0

## Post-hoc scoring corrections

Two Sweep-1 results were scoring/schema **artifacts, not model behaviour**, corrected by principle and disclosed (see docs/DECISIONS.md, 2026-09-13). Original numbers are kept alongside corrected.

- **Identification** re-scored with root-token matching (`root_token_v1`): correct synonyms outside the enumerated `accepted_classes` now credited; two-fault / `none`-on-faulty rejected. Touches **H3, H4** only.
- **Shape recovery**: `null` = unset an absent-when-clean key (oracle-equivalent to the reference value). Touches the shape recovery axis only.
- **Unchanged:** detection, evidence, recovery on non-shape ops → **H1, H2, H6, controls**.

### Identification: original vs corrected (per operator)

| operator | n | identification_original | identification_corrected |
|---|---|---|---|
| control.healthy.v1 | 36 | 0.8889 | 0.8889 |
| crash.shape_mismatch.v1 | 72 | 0.3472 | 0.9861 |
| silent.data_leakage.v1 | 72 | 0.0141 | 0.4366 |
| silent.label_corruption.v1 | 72 | 0.0 | 0.6389 |
| silent.lr_warmup.v1 | 72 | 0.0 | 0.9437 |

## Scores by (operator, agent, anchor)

| operator | agent | anchor | n | detection | identification | evidence_f1 | recovery/no_unnec |
|---|---|---|---|---|---|---|---|
| control.healthy.v1 | react | off | 9 | 1.0 | 1.0 | 1.0 | 1.0 |
| control.healthy.v1 | react | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.7778 |
| control.healthy.v1 | static | off | 9 | 1.0 | 1.0 | 1.0 | 1.0 |
| control.healthy.v1 | static | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.7778 |
| crash.shape_mismatch.v1 | react | off | 18 | 1.0 | 0.9444 | 0.8222 | 0.7222 |
| crash.shape_mismatch.v1 | react | on | 18 | 1.0 | 1.0 | 0.8333 | 0.7778 |
| crash.shape_mismatch.v1 | static | off | 18 | 1.0 | 1.0 | 0.7704 | 0.8333 |
| crash.shape_mismatch.v1 | static | on | 18 | 1.0 | 1.0 | 0.8 | 0.6667 |
| silent.data_leakage.v1 | react | off | 18 | 0.1667 | 0.0 | 0.0529 | 0.0 |
| silent.data_leakage.v1 | react | on | 18 | 1.0 | 0.9444 | 0.7697 | 0.7778 |
| silent.data_leakage.v1 | static | off | 18 | 0.0 | 0.0 | 0.0 | 0.0 |
| silent.data_leakage.v1 | static | on | 18 | 1.0 | 0.7778 | 0.8348 | 0.7778 |
| silent.label_corruption.v1 | react | off | 18 | 0.6111 | 0.5556 | 0.5704 | 0.1667 |
| silent.label_corruption.v1 | react | on | 18 | 1.0 | 1.0 | 0.7815 | 0.8889 |
| silent.label_corruption.v1 | static | off | 18 | 0.0556 | 0.0 | 0.0 | 0.0 |
| silent.label_corruption.v1 | static | on | 18 | 1.0 | 1.0 | 0.7037 | 1.0 |
| silent.lr_warmup.v1 | react | off | 18 | 1.0 | 1.0 | 0.8929 | 0.8333 |
| silent.lr_warmup.v1 | react | on | 18 | 0.9444 | 0.9444 | 0.8466 | 0.7778 |
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
      n: 108
    'off':
      detection_rate: 0.4579
      n: 108
  note: "detection anchor-off tracks symptom_direction, not sigma magnitude \u2014\
    \ see by_case (positive-symptom cases stay near floor even at large sigma_hidden\
    \ when anchor is off)"
H3_doing_understanding_gap:
  control.healthy.v1:
    recovery_rate: 0.0
    identification_rate: 0.8889
    identification_rate_original: 0.8889
  crash.shape_mismatch.v1:
    recovery_rate: 0.75
    identification_rate: 0.9861
    identification_rate_original: 0.3472
  silent.data_leakage.v1:
    recovery_rate: 0.3889
    identification_rate: 0.4366
    identification_rate_original: 0.0141
  silent.label_corruption.v1:
    recovery_rate: 0.5139
    identification_rate: 0.6389
    identification_rate_original: 0.0
  silent.lr_warmup.v1:
    recovery_rate: 0.8333
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
