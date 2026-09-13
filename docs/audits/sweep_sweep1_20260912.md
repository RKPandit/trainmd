# Sweep sweep1 — 2026-09-12

records=324 excluded_trusted=0 excluded_superseded=0

## Scores by (operator, agent, anchor)

| operator | agent | anchor | n | detection | identification | evidence_f1 | recovery |
|---|---|---|---|---|---|---|---|
| control.healthy.v1 | react | off | 9 | 1.0 | 1.0 | 1.0 | 0.0 |
| control.healthy.v1 | react | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.0 |
| control.healthy.v1 | static | off | 9 | 1.0 | 1.0 | 1.0 | 0.0 |
| control.healthy.v1 | static | on | 9 | 0.7778 | 0.7778 | 0.7778 | 0.0 |
| crash.shape_mismatch.v1 | react | off | 18 | 1.0 | 0.2778 | 0.8222 | 0.3889 |
| crash.shape_mismatch.v1 | react | on | 18 | 1.0 | 0.2778 | 0.8333 | 0.3333 |
| crash.shape_mismatch.v1 | static | off | 18 | 1.0 | 0.3333 | 0.7704 | 0.3333 |
| crash.shape_mismatch.v1 | static | on | 18 | 1.0 | 0.5 | 0.8 | 0.3333 |
| silent.data_leakage.v1 | react | off | 18 | 0.1667 | 0.0 | 0.0529 | 0.0 |
| silent.data_leakage.v1 | react | on | 18 | 1.0 | 0.0556 | 0.7697 | 0.7778 |
| silent.data_leakage.v1 | static | off | 18 | 0.0 | 0.0 | 0.0 | 0.0 |
| silent.data_leakage.v1 | static | on | 18 | 1.0 | 0.0 | 0.8348 | 0.7778 |
| silent.label_corruption.v1 | react | off | 18 | 0.6111 | 0.0 | 0.5704 | 0.1667 |
| silent.label_corruption.v1 | react | on | 18 | 1.0 | 0.0 | 0.7815 | 0.8889 |
| silent.label_corruption.v1 | static | off | 18 | 0.0556 | 0.0 | 0.0 | 0.0 |
| silent.label_corruption.v1 | static | on | 18 | 1.0 | 0.0 | 0.7037 | 1.0 |
| silent.lr_warmup.v1 | react | off | 18 | 1.0 | 0.0 | 0.8929 | 0.8333 |
| silent.lr_warmup.v1 | react | on | 18 | 0.9444 | 0.0 | 0.8466 | 0.7778 |
| silent.lr_warmup.v1 | static | off | 18 | 0.8889 | 0.0 | 0.6918 | 0.7778 |
| silent.lr_warmup.v1 | static | on | 18 | 1.0 | 0.0 | 0.7672 | 0.9444 |

## Hypothesis metrics

```
H1_positive_symptom_blindness:
  'on':
    leakage_detection: 1.0
    negative_symptom_detection: 1.0
  'off':
    leakage_detection: 0.0857
    negative_symptom_detection: 0.6389
H3_doing_understanding_gap:
  control.healthy.v1:
    recovery_rate: 0.0
    identification_rate: 0.8889
  crash.shape_mismatch.v1:
    recovery_rate: 0.3472
    identification_rate: 0.3472
  silent.data_leakage.v1:
    recovery_rate: 0.3889
    identification_rate: 0.0141
  silent.label_corruption.v1:
    recovery_rate: 0.5139
    identification_rate: 0.0
  silent.lr_warmup.v1:
    recovery_rate: 0.8333
    identification_rate: 0.0
H4_repeat_agreement:
  mean_repeat_agreement: 0.7037
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
