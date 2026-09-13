# Sweep 1 diagnostics — Pass 2 (2026-09-13)

Read-only over stored transcripts and records (sweep1, non-trusted). No scoring changes, no paid trials.

## Verdict summary

| Q | subject | verdict |
|---|---|---|
| 1 | positive-symptom blindness mechanism | **FINDING** — not "never looked": nearly all read train.py and name the aux feature, but almost none call it *leakage*; the inflated (good-looking) val_acc leads them to declare the run healthy/reasonable. Looked-but-didn't-recognize, with heavy rationalization. |
| 2 | static anchor-off label_corruption ≈ 1/18 | **FINDING (not truncation)** — `label_noise_fraction` is in every static context (no truncation, pos ≈ 2% in), and the response even echoes it; without the reference band the model does not treat the visible knob value as anomalous. A visible knob is missed reasoning-wise, not lost to context length. |
| 3 | 16 shape "no-repair" trials | **ARTIFACT (submission-parsing gap)** — most contain a correct repair (`input_dim: 105`/`null`) in the raw prose that the submit parser dropped (`repair_spec=None`); not the model declining to repair. |
| 4 | confidence calibration | **MIXED** — well-calibrated at the top bin (ECE_det ≈ 0.07); no clean threshold removes the control FPs (max FP conf 0.65 ≥ min true-detect 0.42), and 3/4 FPs carry no confidence at all, so confidence-gating cannot fix controls. |
| 5 | secondaries | evidence is recall-heavy (precision<recall padding) on most operators; distractor rate ≈ 0.24 overall (highest on shape 0.42). σ sign convention stated below. |

## σ sign convention (stated explicitly)

`visible_sigma_distance = (reference_mean − faulty_visible_value) / reference_std`. So **negative σ_visible = the faulty run's visible accuracy is INFLATED above the band (a positive/misleading symptom, e.g. data_leakage); positive σ_visible = deflated below the band (a negative symptom, e.g. lr_warmup / label_corruption).**

## 1. Mechanism of positive-symptom blindness — data_leakage, anchor-off

36 anchor-off data_leakage trials (18 ReAct, 18 static). detected=true: 3; detected=false: 32; no submission: 1.

| agent | case | rep | detected | read train.py | mentions aux | mentions 'leak' | dismissal lang | calls acc high/good |
|---|---|---|---|---|---|---|---|---|
| react | case_0004 | 0 | False | y | y | y | y | y |
| react | case_0004 | 1 | False | y | y | n | n | y |
| react | case_0004 | 2 | False | y | y | n | y | n |
| react | case_0013 | 0 | True | y | y | n | n | y |
| react | case_0013 | 1 | True | y | y | n | y | n |
| react | case_0013 | 2 | False | y | y | n | y | y |
| react | case_0014 | 0 | False | y | y | n | n | n |
| react | case_0014 | 1 | False | y | y | n | y | n |
| react | case_0014 | 2 | False | y | y | n | y | n |
| react | case_0015 | 0 | False | y | y | n | y | y |
| react | case_0015 | 1 | True | y | y | n | y | n |
| react | case_0015 | 2 | False | y | y | n | y | y |
| react | case_0016 | 0 | False | y | y | n | y | y |
| react | case_0016 | 1 | False | y | y | n | n | y |
| react | case_0016 | 2 | None | y | n | n | n | n |
| react | case_0017 | 0 | False | y | y | y | y | y |
| react | case_0017 | 1 | False | y | y | n | y | y |
| react | case_0017 | 2 | False | y | y | n | y | y |
| static | case_0004 | 0 | False | y | y | n | y | n |
| static | case_0004 | 1 | False | y | y | n | n | n |
| static | case_0004 | 2 | False | y | y | n | y | n |
| static | case_0013 | 0 | False | y | y | n | y | n |
| static | case_0013 | 1 | False | y | y | n | y | y |
| static | case_0013 | 2 | False | y | y | y | y | y |
| static | case_0014 | 0 | False | y | y | n | y | n |
| static | case_0014 | 1 | False | y | y | n | y | n |
| static | case_0014 | 2 | False | y | y | n | y | n |
| static | case_0015 | 0 | False | y | y | n | y | n |
| static | case_0015 | 1 | False | y | y | n | y | y |
| static | case_0015 | 2 | False | y | y | n | y | y |
| static | case_0016 | 0 | False | y | y | n | y | y |
| static | case_0016 | 1 | False | y | y | n | y | y |
| static | case_0016 | 2 | False | y | y | n | y | n |
| static | case_0017 | 0 | False | y | y | n | y | y |
| static | case_0017 | 1 | False | y | y | n | y | n |
| static | case_0017 | 2 | False | y | y | n | y | y |

**ReAct counts (n=18):** read train.py=18, mentions aux=17, mentions 'leak'=2, dismissal language=13, calls acc high/good=11.

**static counts (n=18):** read train.py=18, mentions aux=18, mentions 'leak'=1, dismissal language=17, calls acc high/good=8.

**Non-detection mechanism (n=32 detected=false):** (a) never looked = 0; (b) looked, didn't name leakage = 29; (c) saw aux/leak, still detected=false = 3.

**Representative rationales / reasoning (verbatim, ≤40 words):**

> (react, case_0004) Interesting! The resolved config shows `input_dim: 106` but the data section shows `include_aux_feature: true`. This suggests: 1. Aux feature should have been added 2. But input_dim is 106, not 107 This is INCONSISTENT! If aux_feature is added, input_dim should be…

> (react, case_0004) Perfect. The training run completed successfully with exit code 0. Based on my comprehensive investigation: 1. **Metrics**: Training loss and validation accuracy show normal, healthy training dynamics 2. **Configuration**: All hyperparameters are reasonable 3. **Logs**: No errors or warnings, successful…

> (react, case_0004) Based on my comprehensive investigation, I have found: ## Investigation Summary 1. **Configuration Parameters**: The training configuration looks reasonable: - Learning rate: 0.01 (standard for Adam optimizer) - Batch size: 256 (appropriate for tabular data) - Optimizer: Adam with weight_decay=0.0001…

> (react, case_0013) Based on my comprehensive investigation, here are my findings: ## Summary of Investigation **Configuration Analysis:** - Learning rate: 0.01 (reasonable for Adam optimizer on tabular data) - Batch size: 256 (reasonable for Adult dataset) - Optimizer: Adam with weight_decay=0.0001 (standard)…

> (react, case_0014) Perfect. Let me review my findings: 1. **Config inspection:** - Learning rate: 0.01 (reasonable for Adam) - Batch size: 256 (reasonable) - Optimizer: Adam with weight_decay 0.0001 - Model: MLP with hidden dims [64, 32], no dropout, ReLU activation -…


**Verdict — FINDING (looked-but-didn't-recognize, with rationalization).** Non-detection is essentially never (a): 0/32 failed to look — every trial read train.py and 35/36 name the aux/auxiliary feature. Yet only 2–3 use the word *leakage*, and the dominant move is to declare the run healthy/reasonable (dismissal language in 13/18 ReAct, 17/18 static; "accuracy good/high" in ~half). The positive symptom (inflated val_acc) reads as evidence of health, so the agent sees the leakage mechanism but reframes it as normal rather than recognizing it as a fault. This is the F1 mechanism, not a tooling gap.

## 2. Static anchor-off label_corruption = anomaly check

| case | rep | det correct | any_truncated | ctx_tokens | knob in context | knob pos (frac) | rationale/response mentions knob |
|---|---|---|---|---|---|---|---|
| case_0002 | 0 | False | False | 7847 | y | 0.023 | y |
| case_0002 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0002 | 2 | False | False | 7847 | y | 0.023 | y |
| case_0018 | 0 | False | False | 7847 | y | 0.023 | y |
| case_0018 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0018 | 2 | False | False | 7847 | y | 0.023 | y |
| case_0019 | 0 | False | False | 7847 | y | 0.023 | y |
| case_0019 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0019 | 2 | False | False | 7847 | y | 0.023 | y |
| case_0020 | 0 | True | False | 7847 | y | 0.023 | y |
| case_0020 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0020 | 2 | False | False | 7847 | y | 0.023 | y |
| case_0021 | 0 | False | False | 7847 | y | 0.023 | y |
| case_0021 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0021 | 2 | False | False | 7847 | y | 0.023 | y |
| case_0022 | 0 | False | False | 7847 | y | 0.023 | y |
| case_0022 | 1 | False | False | 7847 | y | 0.023 | y |
| case_0022 | 2 | False | False | 7847 | y | 0.023 | y |

Static detection: 1/18. ReAct (same cases) detection: 11/18. Knob present in EVERY static context: True. Any truncation among static: False.

**Verdict — FINDING, not a truncation/ordering artifact.** No static trial truncated; `label_noise_fraction` is present in all 18 static contexts and appears early (~2% of the way in, in config.yaml), and the response text even echoes the knob — yet static detects only 1/18 vs ReAct's 11/18 on the same cases. The knob is visible and read; what is missing is treating its value as anomalous WITHOUT the reference band (anchor-off). The one-shot static agent commits in a single pass and does not interrogate the value, whereas ReAct's iterative querying more often surfaces the deviation. So it is a reasoning/anchor effect (a visible knob not recognized as a fault), not "lost in context".

## 3. Shape no-repair trials — repair_spec / diagnosis / rationale

16 shape trials that are neither recovered(105) nor unexpressible-unset (i.e. the Pass-1 'no-repair' + disallowed-key set).

| case | agent | rep | repair_type | patches | category | repair in PROSE (unparsed) | verdict |
|---|---|---|---|---|---|---|---|
| case_0003 | react | 0 | None | `None` | None (no repair_spec) | null | rejected |
| case_0003 | react | 2 | None | `None` | None (no repair_spec) | 105 | rejected |
| case_0003 | static | 2 | None | `None` | None (no repair_spec) | 105 | rejected |
| case_0008 | react | 2 | None | `None` | None (no repair_spec) | null | rejected |
| case_0008 | static | 0 | None | `None` | None (no repair_spec) | 105 | rejected |
| case_0008 | static | 2 | None | `None` | None (no repair_spec) | null | rejected |
| case_0009 | react | 1 | none | `{}` | wrong repair_type (none) | no | rejected |
| case_0009 | static | 0 | None | `None` | None (no repair_spec) | null | rejected |
| case_0010 | react | 2 | None | `None` | None (no repair_spec) | 105 | rejected |
| case_0010 | react | 2 | config_patch | `{}` | empty patches | no | rejected |
| case_0010 | static | 2 | None | `None` | None (no repair_spec) | null | rejected |
| case_0011 | react | 1 | None | `None` | None (no repair_spec) | null | rejected |
| case_0011 | static | 0 | None | `None` | None (no repair_spec) | null | rejected |
| case_0011 | static | 1 | None | `None` | None (no repair_spec) | null | rejected |
| case_0012 | react | 1 | None | `None` | None (no repair_spec) | 105 | rejected |
| case_0012 | static | 0 | None | `None` | None (no repair_spec) | 105 | rejected |

**Categories (structured field):** None (no repair_spec)=14; wrong repair_type (none)=1; empty patches=1

**Repair proposal present in the raw prose but NOT parsed into repair_spec: 14/16.** These are submission-format parsing losses, not the model declining to repair — the proposed value is frequently the correct 105 or null (unset). The stored rationale shows a corrupted close-tag (`</anionale>`) immediately followed by `<parameter name="repair_spec">{...}`, i.e. the submit parser mis-split the tagged fields and dropped the repair.

**Verdict — ARTIFACT (submission-format / parser gap), NOT the model choosing not to repair.** The submit guidance for a CRASH is expressible (the same config_patch schema applies, and the unset correction now accepts `null`), and the model reached the right fix — it repeatedly wrote `model.input_dim: 105` or `null` in its submission — but a malformed close-tag in the submit payload caused the parser to fold the `repair_spec` parameter into the `rationale` string, leaving `repair_spec=None`. These count as not-recovered in scoring (unchanged here, read-only), but the true cause is submission parsing, not diagnostic failure. Recommend hardening the submit parser / prompt format (fix flagged, not applied).

## 4. Confidence calibration

Trials with a confidence value: 52; confidence omitted (None): 272.

| conf bin | n | mean conf | detection acc | identification acc |
|---|---|---|---|---|
| 0.0–0.2 | 0 | — | — | — |
| 0.2–0.4 | 0 | — | — | — |
| 0.4–0.6 | 2 | 0.485 | 1.000 | 0.500 |
| 0.6–0.8 | 3 | 0.717 | 0.667 | 0.667 |
| 0.8–1.0 | 47 | 0.942 | 1.000 | 0.957 |

**ECE (detection):** 0.0748; **ECE (identification):** 0.0171.

**Control false positives:** 4 (detected on healthy). Confidence values: [('case_0005', 'react', 0.65), ('case_0005', 'static', None), ('case_0005', 'static', None), ('case_0006', 'react', None)]. None-confidence among FPs: 3.

True detections with confidence: n=51, min=0.42, mean=0.917.

**No clean threshold:** max FP confidence (0.65) ≥ min true-detection confidence (0.42); any cut that removes the FP also removes true detections.

**Verdict — MIXED / cannot gate FPs on confidence.** Confidence is reasonably calibrated where it exists (almost all values sit in the top bin, ECE_detection ≈ 0.07). But confidence does NOT separate the control false positives from true detections: the one FP with a value (0.65) sits above the lowest true-detection confidence (0.42), and 3 of the 4 FPs carry no confidence at all — so a confidence threshold cannot remove the control FPs without either losing true detections or missing the None-valued FPs outright. Confidence is too sparse (52/324 populated) and too top-heavy to serve as an FP filter in Sweep 1.

## 5. Secondaries

### 5a. Evidence precision vs recall per operator (padding = precision < recall)

| operator | n (evidence scored) | mean precision | mean recall | mean f1 | padding? |
|---|---|---|---|---|---|
| control | 36 | 0.889 | 1.000 | 0.889 | yes |
| shape_mismatch | 72 | 0.683 | 0.993 | 0.806 | yes |
| data_leakage | 71 | 0.409 | 0.446 | 0.420 | yes |
| label_corruption | 72 | 0.569 | 0.477 | 0.514 | no |
| lr_warmup | 71 | 0.782 | 0.850 | 0.811 | yes |

### 5b. Distractor rate (investigating another operator's knob)

A trial is a 'distractor' if its tool arguments OR reasoning reference a knob that belongs to a DIFFERENT operator than the case's: `input_dim` on a non-shape case, `label_noise` on a non-label case, `aux`/`include_aux_feature` on a non-leakage case.

| operator | n | distractor trials | rate |
|---|---|---|---|
| control | 36 | 10 | 0.278 |
| shape_mismatch | 72 | 30 | 0.417 |
| data_leakage | 72 | 18 | 0.25 |
| label_corruption | 72 | 12 | 0.167 |
| lr_warmup | 72 | 9 | 0.125 |
| **all** | 324 | 79 | 0.244 |

**Notes.** Evidence is recall-heavy on most operators (precision < recall → agents cite the true refs plus extra ones = padding), except label_corruption (precision > recall). data_leakage evidence is weak on both axes (≈0.41/0.45), consistent with §1: agents rarely localize the aux feature as the root cause. Distractor rate ≈ 0.24 overall and peaks on shape_mismatch (0.42): there `input_dim` is the case's OWN knob, so the flagged distractors are mentions of `aux` / `label_noise` that appear because the shared `train.py`/`config.yaml` (read in full, especially by static) names every operator's knob — the agent enumerates and rules them out rather than being led astray. Caveat: this metric counts any mention of a foreign knob, so it over-reads ruling-out as distraction. σ_visible sign convention is stated at the top (negative = inflated).

