# Sweep 1 diagnostics — 2026-09-12

Read-only over 324 sweep1 trials. No scores or ground truth modified.

## Verdict summary — finding vs artifact

| Q | subject | verdict | one-line basis |
|---|---|---|---|
| 1 | identification = 0.0 on silent operators | **ARTIFACT** (accepted-set coverage) | submitted strings are correct synonyms outside the enumerated `accepted_classes`; not a model failure — do NOT fix scores yet |
| 2 | shape_mismatch recovery ≈ 0.35 | **ARTIFACT** (schema-expressibility) | non-recovered trials propose `input_dim=None` (can't express "unset the override") or malformed patches, not wrong numbers |
| 3 | H2 detection vs σ-distance | **FINDING** | detection anchor-off tracks `symptom_direction`, not σ magnitude; positive-symptom cases stay near floor even at σ_hidden=56 |
| 4 | H4 repeat agreement | **MIXED** | det/id agreement is high & stable everywhere except shape_mismatch id (0.21), which is entangled with the Q1/Q2 artifacts |
| 5 | termination | (neutral) | 322 submitted, 2 max_turns; no anomaly |
| 6 | control false positives | **FINDING** | all 4 FPs are anchor-on, at values hugging the band edge; removing the numeric band produces spurious detections |
| 7 | cost | (neutral) | ReAct $10.81 vs static $1.95; ~5.5× token/$ ratio |

**Generator fixes shipped alongside this audit** (harness/sweep.py; not scores/ground-truth):
H2 restored to `hypothesis_metrics()` (was silently omitted); control-tier group column
in `report()` now shows `no_unnecessary_repair` instead of a hardcoded 0.0.

---

## POST-HOC CORRECTIONS APPLIED — 2026-09-13 (disclosed, principle-based)

The Q1 and Q2 artifacts below were **corrected by principle** (see docs/DECISIONS.md and
HYPOTHESES "Post-hoc scoring corrections"). Ground truth was not edited. Original numbers are
kept (the tables further down are the pre-correction diagnostics; the corrected numbers follow).

### Q1 → corrected: root-token identification (`root_token_v1`)

Re-scored the free identification axis for all trials via root-token matching + single-operator
uniqueness (resolved from operator code; audit trail `method`/`token_spec_sha256` per record;
prior result preserved as `identification_original`). **190 trials flipped wrong→correct, 0
correct→wrong.**

**Validation — fraction of the OBSERVED Sweep-1 strings the principled rule accepts** (this is
validation, not design; the token sets were defined from each fault's meaning):

| operator | n (submitting) | accepted | fraction | examples newly accepted via token path |
|---|---|---|---|---|
| lr_warmup | 71 | 67 | 0.944 | excessive_learning_rate×36, learning_rate_too_high×18 |
| label_corruption | 72 | 46 | 0.639 | excessive_label_noise×23, label_noise_injection×5 |
| data_leakage | 71 | 31 | 0.437 | label_leakage_via_aux_feature×8, auxiliary_feature_leakage×8 |
| shape_mismatch | 72 | 71 | 0.986 | input_dimension_mismatch×18, config_input_dim_mismatch×12 |
| control | 36 | 32 | 0.889 | (exact `none`/healthy; 4 misses are the anchor-on FPs) |

The residual misses are **genuine**, not coverage gaps: label_corruption/data_leakage misses are
mostly the `none` non-detections plus (leakage) **mechanism-only** labels naming the knob without
the concept — `aux_feature_enabled`, `aux_feature_too_strong`, `aux_feature_signal_injection`,
`aux_feature_strength_too_high` — which are identification MISSES by design (the concept is
*leakage*; naming the knob is credited on the EVIDENCE axis, not identification). See DECISIONS
judgment log. lr_warmup's 4 misses include `insufficient_regularization` (a different mechanism),
correctly rejected; `missing_lr_schedule` is accepted (concept = the learning rate).

### Q2 → corrected: "unset" repairs for absent-when-clean keys (amendment A split)

Of the 72 shape_mismatch trials, the previously-not-recovered set splits into:

| category | n | disposition |
|---|---|---|
| recovered (input_dim=105) | 25 | already recovered — unchanged |
| **unexpressible-but-correct** (patch `model.input_dim: null`) | 29 | re-verified with unset support (delete the injected override → model derives 105, oracle-equivalent) |
| no repair proposed (empty/malformed) | 16 | genuine model failure — stands not-recovered |
| other (disallowed key, e.g. `model={...}`) | 2 | stands not-recovered |

Haiku's "remove the override" (`input_dim: null`) was the **more faithful** repair than guessing
the literal 105. Re-verifying the 29 unexpressible trials via the standard evaluator path (unset →
delete the override): **29/29 recovered, 0 still rejected** on the hidden seeds — confirming
oracle-equivalence in practice. **Corrected shape recovery = (25 + 29) / 72 = 54/72 = 0.750**
(original 25/72 = 0.347, kept). The 18 remaining (16 no-repair + 2 disallowed-key) are **genuine
model failures** that correctly stand as not-recovered.

### Downstream: H3 (doing/understanding) and H4 (reliability) — both kept

The identification correction touches **H3** and **H4** only (detection, evidence, controls, H2 are
untouched). Corrected numbers are in the regenerated `sweep_sweep1_2026-09-13.md`
(`identification_rate` + `identification_rate_original`; `mean_repeat_agreement` 0.7037 → 0.8241).
Per-operator H4 (3-repeat agreement on detect+identify), original vs corrected:

| operator | H4 agreement original | H4 agreement corrected |
|---|---|---|
| control | 0.75 | 0.75 |
| data_leakage | 0.833 | 0.708 |
| label_corruption | 0.833 | 0.833 |
| lr_warmup | 0.917 | 0.833 |
| shape_mismatch | 0.208 | 0.958 |

Two real effects the artifact had masked: **shape_mismatch id agreement jumps 0.21 → 0.96** (the low
value was entirely the enumerated-set artifact, not instability); **data_leakage dips 0.83 → 0.71**
(now that leakage labels are credited, the model's identification of leakage is genuinely less
*consistent* across repeats than the all-miss artifact made it look — a true reliability finding,
not noise). H3's doing/understanding gap shrinks wherever identification rose (e.g. lr_warmup id
0.0 → 0.944 against recovery ~0.83).

---

## 1. Identification = 0.0 on silent operators — what the model actually wrote

### lr_warmup (71 trials) — accepted (normalized): `['learning_rate', 'lr_misconfiguration', 'lr_too_high', 'lr_warmup']`

| predicted_class (raw) | normalized | count | in accepted? |
|---|---|---|---|
| `excessive_learning_rate` | `excessive_learning_rate` | 36 | no |
| `learning_rate_too_high` | `learning_rate_too_high` | 18 | no |
| `high_learning_rate` | `high_learning_rate` | 2 | no |
| `training_instability_high_learning_rate` | `training_instability_high_learning_rate` | 2 | no |
| `learning_rate_instability` | `learning_rate_instability` | 2 | no |
| `none` | `none` | 2 | no |
| `excessive_learning_rate_divergence` | `excessive_learning_rate_divergence` | 1 | no |
| `insufficient_regularization` | `insufficient_regularization` | 1 | no |
| `training_lr_too_high_without_schedule` | `training_lr_too_high_without_schedule` | 1 | no |
| `missing_learning_rate_schedule` | `missing_learning_rate_schedule` | 1 | no |
| `learning_rate_divergence` | `learning_rate_divergence` | 1 | no |
| `high_learning_rate_divergence` | `high_learning_rate_divergence` | 1 | no |
| `training_instability_final_epoch_collapse` | `training_instability_final_epoch_collapse` | 1 | no |
| `missing_lr_schedule` | `missing_lr_schedule` | 1 | no |
| `high_learning_rate_without_decay` | `high_learning_rate_without_decay` | 1 | no |

**0/71 matched the accepted set.**

### label_corruption (72 trials) — accepted (normalized): `['data_corruption', 'label_corruption', 'label_noise', 'noisy_labels']`

| predicted_class (raw) | normalized | count | in accepted? |
|---|---|---|---|
| `none` | `none` | 24 | no |
| `excessive_label_noise` | `excessive_label_noise` | 23 | no |
| `label_noise_injection` | `label_noise_injection` | 5 | no |
| `label_noise_corruption` | `label_noise_corruption` | 5 | no |
| `label_noise_misconfiguration` | `label_noise_misconfiguration` | 3 | no |
| `high_label_noise_fraction` | `high_label_noise_fraction` | 2 | no |
| `label_noise_degradation` | `label_noise_degradation` | 2 | no |
| `seed_mismatch_with_reference` | `seed_mismatch_with_reference` | 1 | no |
| `label_noise_too_high` | `label_noise_too_high` | 1 | no |
| `label_noise_injection_fault` | `label_noise_injection_fault` | 1 | no |
| `label_noise_poisoning` | `label_noise_poisoning` | 1 | no |
| `insufficient_regularization` | `insufficient_regularization` | 1 | no |
| `excessive_label_noise_fraction` | `excessive_label_noise_fraction` | 1 | no |
| `high_label_noise` | `high_label_noise` | 1 | no |
| `label_noise_fraction_too_high` | `label_noise_fraction_too_high` | 1 | no |

**0/72 matched the accepted set.**

### data_leakage (71 trials) — accepted (normalized): `['data_contamination', 'data_leakage', 'feature_leakage', 'information_leakage', 'label_leakage', 'leaky_feature', 'target_leakage', 'train_test_leakage']`

| predicted_class (raw) | normalized | count | in accepted? |
|---|---|---|---|
| `none` | `none` | 32 | no |
| `label_leakage_via_aux_feature` | `label_leakage_via_aux_feature` | 8 | no |
| `auxiliary_feature_leakage` | `auxiliary_feature_leakage` | 8 | no |
| `aux_feature_data_leakage` | `aux_feature_data_leakage` | 4 | no |
| `aux_feature_leakage` | `aux_feature_leakage` | 4 | no |
| `aux_feature_label_leakage` | `aux_feature_label_leakage` | 2 | no |
| `aux_feature_enabled` | `aux_feature_enabled` | 2 | no |
| `data_leakage_via_aux_feature` | `data_leakage_via_aux_feature` | 1 | no |
| `target_leakage` | `target_leakage` | 1 | YES |
| `data_leakage_aux_feature` | `data_leakage_aux_feature` | 1 | no |
| `learning_rate_too_high` | `learning_rate_too_high` | 1 | no |
| `aux_feature_strength_too_high` | `aux_feature_strength_too_high` | 1 | no |
| `input_dimension_mismatch_with_aux_feature` | `input_dimension_mismatch_with_aux_feature` | 1 | no |
| `auxiliary_feature_label_leakage` | `auxiliary_feature_label_leakage` | 1 | no |
| `aux_feature_signal_injection` | `aux_feature_signal_injection` | 1 | no |
| `label_leakage_aux_feature` | `label_leakage_aux_feature` | 1 | no |
| `input_dim_mismatch_with_aux_feature` | `input_dim_mismatch_with_aux_feature` | 1 | no |
| `aux_feature_too_strong` | `aux_feature_too_strong` | 1 | no |

**1/71 matched the accepted set.**

**Verdict: ARTIFACT (accepted-set coverage).** Across all three silent operators the
model's submitted `operator_class` strings are semantically correct descriptions of the
fault — `excessive_learning_rate`, `excessive_label_noise`, `auxiliary_feature_leakage`,
`label_leakage_via_aux_feature` — that simply fall outside the enumerated `accepted_classes`
sets. `_normalize_class` only collapses separators/case; it does not do synonym matching, so
correct answers score 0. This is a coverage gap in the accepted sets, **not** a model result.
Per the task, do not fix scores yet — flagged for an accepted-set review. (The `none` counts —
24 label_corruption, 32 data_leakage — are genuine non-detections, separate from the coverage
gap; they align with the anchor-off detection floor in Q3.)

## 2. shape_mismatch recovery — repair patches + verdicts

72 shape_mismatch trials. Recovery verdicts: {'rejected': 47, 'recovered': 25}

| repaired key=value | verdict | reason_codes | count |
|---|---|---|---|
| `model.input_dim=None` | rejected | ['VALUE_TYPE_INVALID'] | 29 |
| `model.input_dim=105` | recovered | [] | 25 |
| `(none/other)` | rejected | ['MALFORMED'] | 16 |
| `model={'input_dim': None}` | rejected | ['KEY_NOT_ALLOWED'] | 1 |
| `model={'type': 'mlp', 'hidden_dims': [64, 32], 'dropout': 0.0, 'activation': 'relu'}` | rejected | ['KEY_NOT_ALLOWED'] | 1 |

**recovery rate = 25/72 = 0.347**. Correct value is input_dim=105.

**Verdict: ARTIFACT (schema-expressibility gap).** The non-recovered trials are not guessing
wrong numbers. The dominant failure (29 trials) is `model.input_dim=None` — the agent
correctly identifies that the injected `input_dim` override should be removed, but the repair
schema has no way to express "unset an override," so it submits `None` and hits
`VALUE_TYPE_INVALID`. 16 more are malformed/empty, 2 use a disallowed key. Only the 25 that
happened to name the exact value 105 recover. So the 0.35 rate reflects (a) the schema's
inability to express an unset and (b) the agent not knowing the true dimension — both harness
affordances, not a diagnostic failure. Report only; do not fix.

## 3. H2 — detection rate vs σ-distance (silent cases)

| case | operator | strength | σ_visible | σ_hidden | symptom | det(all) | det react/static | det anchorOn/Off |
|---|---|---|---|---|---|---|---|---|
| case_0013 | data_leakage | mild | -5.752646 | 5.848809 | positive | 0.67 | 0.83/0.50 | 1.00/0.33 |
| case_0014 | data_leakage | mild | -3.607804 | 5.991736 | positive | 0.50 | 0.50/0.50 | 1.00/0.00 |
| case_0004 | data_leakage | moderate | -29.154101 | 23.121536 | positive | 0.50 | 0.50/0.50 | 1.00/0.00 |
| case_0015 | data_leakage | moderate | -27.789021 | 20.541079 | positive | 0.58 | 0.67/0.50 | 1.00/0.17 |
| case_0017 | data_leakage | severe | -70.691138 | 56.304813 | positive | 0.50 | 0.50/0.50 | 1.00/0.00 |
| case_0016 | data_leakage | severe | -70.203704 | 64.117161 | positive | 0.55 | 0.60/0.50 | 1.00/0.00 |
| case_0019 | label_corruption | mild | 11.993386 | 11.868741 | negative | 0.50 | 0.50/0.50 | 1.00/0.00 |
| case_0018 | label_corruption | mild | 9.750661 | 10.793875 | negative | 0.67 | 0.83/0.50 | 1.00/0.33 |
| case_0002 | label_corruption | moderate | 19.988757 | 15.739426 | negative | 0.75 | 1.00/0.50 | 1.00/0.50 |
| case_0020 | label_corruption | moderate | 18.916005 | 15.596014 | negative | 0.67 | 0.67/0.67 | 1.00/0.33 |
| case_0021 | label_corruption | severe | 26.03373 | 18.46281 | negative | 0.67 | 0.83/0.50 | 1.00/0.33 |
| case_0022 | label_corruption | severe | 22.52381 | 17.53087 | negative | 0.75 | 1.00/0.50 | 1.00/0.50 |
| case_0024 | lr_warmup | mild | 68.643519 | 44.550802 | negative | 1.00 | 1.00/1.00 | 1.00/1.00 |
| case_0023 | lr_warmup | mild | 37.734127 | 24.124939 | negative | 0.83 | 1.00/0.67 | 1.00/0.67 |
| case_0001 | lr_warmup | moderate | 68.643519 | 44.550802 | negative | 1.00 | 1.00/1.00 | 1.00/1.00 |
| case_0025 | lr_warmup | moderate | 68.643519 | 44.550802 | negative | 1.00 | 1.00/1.00 | 1.00/1.00 |
| case_0026 | lr_warmup | severe | 68.643519 | 44.550802 | negative | 1.00 | 1.00/1.00 | 1.00/1.00 |
| case_0027 | lr_warmup | severe | 68.643519 | 44.550802 | negative | 1.00 | 1.00/1.00 | 1.00/1.00 |

Detection rate by condition (silent cases):

| anchor | agent | detection rate | n |
|---|---|---|---|
| on | react | 1.000 | 53 |
| on | static | 1.000 | 54 |
| off | react | 0.604 | 53 |
| off | static | 0.315 | 54 |

**Verdict: FINDING.** Anchor-on detection is at the ceiling (1.00) for both agents, so σ
magnitude is invisible there. The signal lives in the anchor-off column, and it does **not**
track σ. lr_warmup (negative symptom) detects at 1.00 anchor-off across every strength; the
positive-symptom data_leakage cases sit at 0.00–0.33 anchor-off even at the largest gaps
(case_0017: σ_hidden=56, still 0.00 off). Detection anchor-off is governed by
`symptom_direction` — whether the fault pushes the visible metric the "expected" (worse) way —
not by how far the run is from the band. Eyeballing a 50% threshold against σ therefore fails:
the threshold that separates detected from missed is symptom sign, not distance. This is the
core H1/H2 result and is real. (H2 is now emitted by the report generator — see the fix note.)

## 4. H4 — repeat agreement (same detect+identify over 3 repeats)

| operator | strength | agent | anchor | det agree | id agree |
|---|---|---|---|---|---|
| control | mild | react | off | yes | yes |
| control | mild | react | off | yes | yes |
| control | mild | react | off | yes | yes |
| control | mild | react | on | NO | NO |
| control | mild | react | on | NO | NO |
| control | mild | react | on | yes | yes |
| control | mild | static | off | yes | yes |
| control | mild | static | off | yes | yes |
| control | mild | static | off | yes | yes |
| control | mild | static | on | NO | NO |
| control | mild | static | on | yes | yes |
| control | mild | static | on | yes | yes |
| shape_mismatch | mild | react | off | yes | yes |
| shape_mismatch | mild | react | off | yes | NO |
| shape_mismatch | mild | react | on | yes | NO |
| shape_mismatch | mild | react | on | yes | NO |
| shape_mismatch | mild | static | off | yes | yes |
| shape_mismatch | mild | static | off | yes | NO |
| shape_mismatch | mild | static | on | yes | NO |
| shape_mismatch | mild | static | on | yes | NO |
| shape_mismatch | moderate | react | off | yes | NO |
| shape_mismatch | moderate | react | off | yes | NO |
| shape_mismatch | moderate | react | on | yes | NO |
| shape_mismatch | moderate | react | on | yes | NO |
| shape_mismatch | moderate | static | off | yes | NO |
| shape_mismatch | moderate | static | off | yes | NO |
| shape_mismatch | moderate | static | on | yes | NO |
| shape_mismatch | moderate | static | on | yes | NO |
| shape_mismatch | severe | react | off | yes | yes |
| shape_mismatch | severe | react | off | yes | NO |
| shape_mismatch | severe | react | on | yes | yes |
| shape_mismatch | severe | react | on | yes | yes |
| shape_mismatch | severe | static | off | yes | NO |
| shape_mismatch | severe | static | off | yes | NO |
| shape_mismatch | severe | static | on | yes | NO |
| shape_mismatch | severe | static | on | yes | NO |
| data_leakage | mild | react | off | NO | yes |
| data_leakage | mild | react | off | yes | yes |
| data_leakage | mild | react | on | yes | yes |
| data_leakage | mild | react | on | yes | yes |
| data_leakage | mild | static | off | yes | yes |
| data_leakage | mild | static | off | yes | yes |
| data_leakage | mild | static | on | yes | yes |
| data_leakage | mild | static | on | yes | yes |
| data_leakage | moderate | react | off | yes | yes |
| data_leakage | moderate | react | off | NO | yes |
| data_leakage | moderate | react | on | yes | yes |
| data_leakage | moderate | react | on | yes | yes |
| data_leakage | moderate | static | off | yes | yes |
| data_leakage | moderate | static | off | yes | yes |
| data_leakage | moderate | static | on | yes | yes |
| data_leakage | moderate | static | on | yes | yes |
| data_leakage | severe | react | off | yes | yes |
| data_leakage | severe | react | off | NO | NO |
| data_leakage | severe | react | on | yes | NO |
| data_leakage | severe | react | on | yes | yes |
| data_leakage | severe | static | off | yes | yes |
| data_leakage | severe | static | off | yes | yes |
| data_leakage | severe | static | on | yes | yes |
| data_leakage | severe | static | on | yes | yes |
| label_corruption | mild | react | off | yes | yes |
| label_corruption | mild | react | off | NO | yes |
| label_corruption | mild | react | on | yes | yes |
| label_corruption | mild | react | on | yes | yes |
| label_corruption | mild | static | off | yes | yes |
| label_corruption | mild | static | off | yes | yes |
| label_corruption | mild | static | on | yes | yes |
| label_corruption | mild | static | on | yes | yes |
| label_corruption | moderate | react | off | yes | yes |
| label_corruption | moderate | react | off | NO | yes |
| label_corruption | moderate | react | on | yes | yes |
| label_corruption | moderate | react | on | yes | yes |
| label_corruption | moderate | static | off | yes | yes |
| label_corruption | moderate | static | off | NO | yes |
| label_corruption | moderate | static | on | yes | yes |
| label_corruption | moderate | static | on | yes | yes |
| label_corruption | severe | react | off | NO | yes |
| label_corruption | severe | react | off | yes | yes |
| label_corruption | severe | react | on | yes | yes |
| label_corruption | severe | react | on | yes | yes |
| label_corruption | severe | static | off | yes | yes |
| label_corruption | severe | static | off | yes | yes |
| label_corruption | severe | static | on | yes | yes |
| label_corruption | severe | static | on | yes | yes |
| lr_warmup | mild | react | off | yes | yes |
| lr_warmup | mild | react | off | yes | yes |
| lr_warmup | mild | react | on | NO | NO |
| lr_warmup | mild | react | on | yes | yes |
| lr_warmup | mild | static | off | yes | yes |
| lr_warmup | mild | static | off | NO | yes |
| lr_warmup | mild | static | on | yes | yes |
| lr_warmup | mild | static | on | yes | yes |
| lr_warmup | moderate | react | off | yes | yes |
| lr_warmup | moderate | react | off | yes | yes |
| lr_warmup | moderate | react | on | yes | yes |
| lr_warmup | moderate | react | on | yes | yes |
| lr_warmup | moderate | static | off | yes | yes |
| lr_warmup | moderate | static | off | yes | yes |
| lr_warmup | moderate | static | on | yes | yes |
| lr_warmup | moderate | static | on | yes | yes |
| lr_warmup | severe | react | off | yes | yes |
| lr_warmup | severe | react | off | yes | yes |
| lr_warmup | severe | react | on | yes | yes |
| lr_warmup | severe | react | on | yes | yes |
| lr_warmup | severe | static | off | yes | yes |
| lr_warmup | severe | static | off | yes | yes |
| lr_warmup | severe | static | on | yes | yes |
| lr_warmup | severe | static | on | yes | yes |

| operator | det agreement | id agreement | cells |
|---|---|---|---|
| control | 0.75 | 0.75 | 12 |
| data_leakage | 0.88 | 0.92 | 24 |
| label_corruption | 0.83 | 1.00 | 24 |
| lr_warmup | 0.92 | 0.96 | 24 |
| shape_mismatch | 1.00 | 0.21 | 24 |

**Verdict: MIXED.** Detection agreement is high everywhere (0.75–1.00); identification
agreement is high (0.92–1.00) for the silent operators and control, meaning the runs are
reproducible where scoring is meaningful. The one outlier is shape_mismatch id agreement
(0.21) — but that is **entangled with the Q2 artifact**: with 25/72 recovering on the exact
value and the rest scattered across None/malformed, the three repeats of a cell rarely land the
same id, so low agreement there measures the schema-expressibility gap, not run instability. No
easy/hard split by strength is visible; agreement does not degrade with severity. No stability
concern.

## 5. termination_reason distribution (all trials)

| termination_reason | count |
|---|---|
| submitted | 322 |
| max_turns | 2 |

**Non-submitting trials: 2**
- case_0016 (data_leakage) agent=react anchor=off repeat=2 term=max_turns
- case_0024 (lr_warmup) agent=react anchor=on repeat=1 term=max_turns

**Verdict: neutral.** 322/324 submitted cleanly. The 2 max_turns trials are both ReAct
(the tool-loop agent can exhaust its turn budget; the static one-shot agent cannot), on
unrelated cases/conditions — no shared operator, anchor, or repeat. No systemic pattern; not
an artifact requiring action.

## 6. Controls — detection false positives

36 control trials; 4 detection false positives (detected=true on a healthy run).
anchor=on: 4 / anchor=off: 0

| case | agent | anchor | pred_class | confidence | rationale |
|---|---|---|---|---|---|
| case_0005 | react | on | `excessive_learning_rate` | 0.65 | 
Validation accuracy systematically exceeds the healthy upper bound (0.8599) dur |
| case_0005 | static | on | `dropout_disabled` | None | Model lacks dropout regularization (dropout=0.0), leading to overfitting. Valida |
| case_0005 | static | on | `insufficient_dropout_regularization` | None | Final validation accuracy of 0.8546 falls below the healthy range floor (0.8538– |
| case_0006 | react | on | `high_learning_rate_instability` | None | 
Final validation accuracy (0.854784 at epoch 19) falls below the healthy range  |

Control recovery axis: no_unnecessary_repair = 32/36 = 0.889; false_intervention = 4/36 = 0.111

**Verdict: FINDING (confirms the anchor mechanism from Q3).** All 4 control false positives
are anchor-on, zero anchor-off — the mirror image of the silent-case detection story. On a
healthy run whose validation accuracy hugs the band edge (0.8546 vs floor 0.8538), agents given
the numeric reference band over-anchor to it and manufacture a fault (`excessive_learning_rate`,
`insufficient_dropout_regularization`, etc.) at low confidence; agents without the band do not.
So the anchor both rescues detection on true silent faults (Q3) and induces false alarms on
healthy edge cases — a genuine cost/benefit of the reference band, not noise. Note the FP rate
here (4/36) is the same 4 trials as `false_intervention`, since a control "repair" is by
definition unnecessary. **Report label fix shipped:** the report's control recovery column now
displays `no_unnecessary_repair` (0.889 aggregate) instead of the previous hardcoded 0.0.

## 7. Cost — ReAct vs static, tokens + $

| operator | agent | trials | in_tok | out_tok | $ total | $ / trial |
|---|---|---|---|---|---|---|
| control | react | 18 | 978,249 | 27,831 | $1.1174 | $0.0621 |
| control | static | 18 | 140,868 | 12,284 | $0.2023 | $0.0112 |
| data_leakage | react | 36 | 2,452,597 | 82,528 | $2.8652 | $0.0796 |
| data_leakage | static | 36 | 284,076 | 30,204 | $0.4351 | $0.0121 |
| label_corruption | react | 36 | 1,979,322 | 66,243 | $2.3105 | $0.0642 |
| label_corruption | static | 36 | 283,428 | 30,711 | $0.4370 | $0.0121 |
| lr_warmup | react | 36 | 2,024,285 | 61,125 | $2.3299 | $0.0647 |
| lr_warmup | static | 36 | 282,348 | 37,778 | $0.4712 | $0.0131 |
| shape_mismatch | react | 36 | 1,850,720 | 66,773 | $2.1846 | $0.0607 |
| shape_mismatch | static | 36 | 246,132 | 32,105 | $0.4067 | $0.0113 |

| agent | trials | $ total |
|---|---|---|
| react | 162 | $10.8077 |
| static | 162 | $1.9523 |

**Total estimated: $12.7599** (is_estimate; actual_spend_usd pending console figure).

**Verdict: neutral.** ReAct costs ~5.5× static in dollars and ~7–8× in input tokens (the tool
loop re-sends growing context each turn), for roughly flat per-trial cost within an agent
(~$0.06–0.08 ReAct, ~$0.011–0.013 static) across operators — no operator is a cost outlier.
The manifest's `actual_spend_usd` is still null and will be filled from the console figure once
provided; this table is the estimate derived from per-record `usage.estimated_cost_usd`.

