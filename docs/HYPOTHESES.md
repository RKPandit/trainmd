# TrainMD — Pre-Registered Hypotheses (Sweep 1)

**Status:** pre-registered **before** the first sweep runs. Dated on commit. The point of
writing this first is that a confirmed prediction is credible *because* it was predicted,
and a refuted one is still a publishable finding *because* it was tested honestly. Nothing
here is edited after the sweep starts; results are appended in a separate section.

**The principle behind these hypotheses:** a benchmark paper finds something new when it
reveals a *pattern about how agents fail* — a mechanism, ideally with a cause and an
intervention — not when it reports scores. TrainMD's instrument can see four things a
pass/fail benchmark cannot: symptom *direction* (positive vs negative), effect size in
units of the reference σ, four separate axes (detect / identify / evidence / recover), and
reliability under repeats. Each hypothesis points that resolution at a question other
benchmarks structurally cannot ask.

**Commitment to nulls:** every hypothesis below has a refuting outcome, and a refuted
hypothesis is reported as a finding, not dropped.

---

## Sweep 1 design (fixed before running)

- **Operators:** lr_warmup (silent, easy), label_corruption (silent, subtle),
  shape_mismatch (crash, binary), data_leakage (silent, flagship, positive-symptom) +
  healthy controls.
- **Cases:** each operator × 3 strengths (the σ ladder) × 2 seeds, + 3 controls
  ≈ 27 cases.
- **Factor under test:** reference anchor **on vs off** (the healthy-band line in the
  agent prompt) — one flag, two conditions.
- **Model:** claude-haiku-4-5 only (Sweep 1 is single-model by design; H5 needs Sweep 2).
- **Agents (two):** the **ReAct tool-using agent** and a **static full-context baseline**
  (all artifacts — config, code, metrics, logs — concatenated into one prompt, one LLM
  call, same submit schema, same reference band). The static baseline is the *control
  condition* for tool-mediated investigation (H6); it is the only second agent in
  Sweep 1. No additional strategies (Reflexion, plan-and-execute) — those are Sweep 2.
- **Repeats:** 3 per cell, temperature 1.0.
- **Trials:** ≈ 27 cases × 2 anchor × 3 repeats × 2 agents ≈ 320. Estimated cost
  ≈ $15–20 (the static baseline is one call per case, cheaper than ReAct).
- **Gate before running:** known-answer gate green on all cases; audit-index clean;
  validate-all green; CI full suite green. No trial runs before the gate.
- **Token-budget parity (deliberately NOT enforced):** the static agent sees every
  artifact once; the ReAct agent has a tool/turn budget. They are not equal in tokens and
  are not forced to be — both agents' token usage and cost are reported alongside every
  score so the cost-vs-quality tradeoff is explicit (spec §12 open question, resolved by
  reporting rather than equalizing).
- **Reporting:** all four axes + safety per cell; macro-average per operator; controls
  reported via detection false-positive rate and false-intervention rate; superseded and
  trusted records excluded (counts printed).

Effect size for every case is computed as
`σ-distance = (reference_hidden_mean − faulty_hidden_value) / reference_hidden_std`
(for the crash tier, effect size is treated as ∞ / "crash"). This is the x-axis for H2.

---

## H1 — Positive-symptom blindness (flagship)

**Claim.** Agents diagnose faults whose observable symptoms are *bad* (loss up, accuracy
down) far more reliably than faults whose symptoms are *good* (data leakage: validation
accuracy *up*). Without a baseline for "normal," a positive symptom is read as success and
the fault is rationalized away.

**Prior evidence (n=1):** Haiku located the leaking feature, derived its label dependence,
wrote "could lead to data leakage… however, this might be intentional," and did not submit.
With the reference anchor and room to finish, it diagnosed decisively.

**Predicted direction.** With the anchor **off**: detection and identification on
data_leakage are markedly lower than on the negative-symptom silent operators at comparable
σ-distance. With the anchor **on**: the gap closes substantially.

**Confirming metric.** Detection rate and identification rate, data_leakage vs
(lr_warmup, label_corruption) at matched σ-distance, in each anchor condition. Confirmed
if anchor-off leakage detection is ≥ 30 percentage points below matched negative-symptom
detection **and** the anchor-on gap is ≤ 10 points.

**Refuting outcome.** Leakage detection is comparable to negative-symptom detection with
the anchor off. Reported as: "positive-symptom faults are not harder for current agents
given code access" — itself a useful null.

**Sweep factor.** Operator × anchor on/off × repeats.

**Why new (to verify before write-up).** Existing diagnosis benchmarks (AIOps, DL
debugging) use negative-symptom faults; the positive-symptom case and the anchor
intervention appear unmeasured. **Kill-check required** on "positive-symptom" /
"misleading-metric" agent diagnosis before submission.

---

## H2 — A detection threshold in units of σ

**Claim.** Detection of silent faults degrades sharply as effect size shrinks toward the
reference noise band. There is a measurable floor — a σ-distance below which agents stop
detecting — and it is well above 2σ (the tolerance edge).

**Prior evidence:** 25% label noise (< 1σ effect on Adult) is nearly invisible in aggregate
accuracy; lr_warmup moderate (≈ 40σ) is trivially detected.

**Predicted direction.** Detection rate is a monotone increasing function of σ-distance,
near 0 below ~2σ and near 1 above ~10σ, with the transition somewhere in between.

**Confirming metric.** Detection rate vs σ-distance across all silent cases (both anchor
conditions plotted separately). Confirmed if the fitted threshold (50% detection) lies at a
σ-distance with a defensible interval and the curve is monotone. Report the threshold with
its interval.

**Refuting outcome.** Detection is flat in σ (agents detect via config reading regardless
of symptom size) or non-monotone. Reported as: "detection is driven by configuration
inspection, not metric inspection" — a different but real finding about *how* agents
detect.

**Sweep factor.** Strength ladder (the σ ladder is the independent variable).

**Why new.** The diagnostic sensitivity floor of LLM agents, expressed as an effect size,
appears unquantified. **Kill-check required** on "detection threshold" / "effect size"
agent diagnosis.

---

## H3 — The doing/understanding dissociation

**Claim.** Agents *repair* faults correctly more often than they *name* them correctly:
recovery rate exceeds identification rate, and the gap differs by fault type.

**Prior evidence:** shape_mismatch: 3/3 runs correct fix, 3/3 wrong label. data_leakage:
correct fix, wrong label. **Caveat:** a prompt-anchoring bug (an example class name in the
submit schema) inflated this pattern; it is now removed. Sweep 1 is the honest test.

**Predicted direction.** recovery_rate > identification_rate overall; the gap is largest on
the crash tier (where the fix is mechanical and the category is abstract) and smallest on
lr_warmup (where fix and name are nearly the same word).

**Confirming metric.** Per-operator (recovery_rate − identification_rate), with the
prompt de-anchored. Confirmed if the overall gap is ≥ 15 points and positive on ≥ 3 of 4
operators.

**Refuting outcome.** Identification ≈ recovery once de-anchored, i.e. the earlier pattern
was entirely the prompt bug. Reported as such — an important negative about prompt
contamination in structured-output benchmarks.

**Sweep factor.** Operator × repeats (no extra condition needed).

---

## H4 — Reliability is not accuracy

**Claim.** The same agent on the same case gives *consistent* outcomes on easy cases and
*inconsistent* outcomes on hard ones; diagnostic reliability under repeats is a distinct
property from mean accuracy, and it degrades with difficulty.

**Prior evidence:** two runs of lr_warmup → identical four-axis scores despite different
investigation paths; two runs of data_leakage → no-submission vs decisive diagnosis
(confounded by fixes, but suggestive).

**Predicted direction.** Repeat-to-repeat agreement (fraction of 3 repeats with the same
detection and identification outcome) is ≈ 1.0 on lr_warmup/shape_mismatch and
substantially lower on data_leakage and mild-strength label_corruption.

**Confirming metric.** Per-cell agreement over 3 repeats, by operator and strength.
Confirmed if agreement on hard cells is ≥ 0.2 lower than on easy cells.

**Refuting outcome.** Agreement is uniformly high — Haiku is reliable even when wrong.
Reported as a property of the model (and motivates checking whether *cost* varies while
outcome does not — already observed).

**Sweep factor.** Repeats (already required).

---

## H5 — Does capability increase rationalization? (Sweep 2)

**Claim (speculative).** A more capable model constructs more *plausible* explanations, so
on positive-symptom faults it may rationalize *more* — capability could worsen H1, not
improve it.

**Not testable in Sweep 1** (single model). Sweep 1 is designed so a second model tier can
be added on identical cases and conditions. Predicted direction is deliberately left as a
two-sided question; either result is informative.

**Confirming metric (Sweep 2).** Anchor-off leakage detection for a mid-tier model vs
Haiku. A *decrease* with capability would be the striking result; an increase is the
expected one.

---

## H6 — Tool-mediated investigation vs static full context

**Claim.** The ReAct tool-using agent out-scores a static full-context baseline (all
artifacts in one prompt, one call, same model) on evidence and recovery — *but* the
advantage is smallest, and possibly reversed, on data_leakage, where seeing everything at
once may avoid the distractor paths that step-by-step investigation follows.

**Prior evidence.** The ReAct agent burned turns on the `input_dim` red herring (another
operator's hook) and the reference-seeds list before reaching the aux feature; a static view
of `train.py` and the config has no path to wander down. Conversely, ReAct's targeted
metric queries (epochs 15–19) found evidence a single-shot read might skim past.

**Predicted direction.** Two-sided by design. Overall: ReAct ≥ static on evidence F1 and
recovery. On data_leakage specifically: the ReAct advantage shrinks to ≈ 0 or reverses.

**Confirming metric.** Per-operator (ReAct − static) on each axis, anchor condition held
fixed. Confirmed (tools help) if ReAct is ≥ +10 points on evidence F1 averaged over
operators. The leakage sub-claim is confirmed if the ReAct − static gap on data_leakage is
≤ 0 while the gap on the negative-symptom operators is > 0.

**Refuting outcome.** static ≈ ReAct everywhere — tool-mediated investigation does not
help at this scale, a real negative about the cost of agentic diagnosis. Reported with the
cost ratio, which then becomes the headline: equal quality at a fraction of the cost.

**Sweep factor.** Agent (ReAct vs static) × operator × anchor × repeats.

**Why this is the control, not an extra.** RQ2 ("does tool use matter?") is unanswerable
with one agent — every ReAct score could be explained by model capability alone. The static
baseline isolates the effect of investigation. It is the missing half of a comparison the
benchmark already claims to make, which is why it is the only second agent in Sweep 1.

---

## H8 — Neutral-key ablation: is leakage identification understanding or name-reading? (Sweep 3)

**Pre-registered 2026-09-19, before any Sweep-3 trial. Locks the hypothesis, thresholds, and
interpretation. The paid trial is a separate step.**

**Context.** Part 1 measured that a trivial config-delta baseline (**B2**) matches the
anchored LLM on **detection and recovery** — at *better* specificity — on this workload's
config-knob operators. The **only surviving measured agent value** is **identifying** faults
whose config-knob name does not name the concept (`data_leakage`, `metric_inflation`). H8 is
the decisive test of that surviving headline: is the identification **fault-mechanism
understanding**, or **key-name reading**?

**Design — paired, within-sweep.** Two mechanically identical variants:
`silent.data_leakage.v1` (descriptive keys `include_aux_feature`/`aux_feature_strength`) and
`silent.data_leakage_neutral.v1` (neutral keys `opt_c`/`opt_c_level`). Same derivation
function (`datautil._derived_column`), identical hidden faulty values at every strength/seed,
admissible repairs identical up to key names. The only thing an agent can observe that differs
is the config key name.

**WITHIN-SWEEP constraint (design, not incidental).** The descriptive variant's train.py was
**de-revealed** during the Part-2 refactor (the derivation moved to `datautil._derived_column`;
the `_compute_aux_column` name + docstring + comment were removed). Its Sweep-3 identification
is therefore **NOT comparable to Sweep-1/2's 0.83–0.96**. **H8 compares neutral vs descriptive
inside Sweep 3 only — never vs a frozen number.**

**Cells.** 2 variants × 3 strengths × **6 confirmatory seeds** (42–47) × 3 anchor arms
(off/stats/rule) × 2 agents × 2 repeats = **432 faulty cells**, plus controls in the static
protocol × 3 arms × 1 repeat. **Cost estimate ≈ $25–35** (refine with
`harness/sweep.estimate_cost`).

**POWER NOTE (pre-registered, stated before the thresholds).** The case-clustered CI resamples
the **case** as the unit; the 2 repeats × 2 agents add trials within a case, not clusters, so
the confirmatory **seed count sets the power.** The design was **raised from 2 to 6
confirmatory seeds** (18 cases per variant per arm) precisely because a 2-seed design (6
clusters) is underpowered: simulated at 2 seeds it gives a 95% CI half-width ≈0.25 and a
minimum detectable difference (MDD) ≈0.45 — it could detect the REFUTING outcome but could not
establish the CONFIRMING one, and a design that cannot return a positive answer is not worth
running for the decisive test. At **6 seeds** the same simulation (case-clustered bootstrap, 18
clusters) gives a **median 95% CI half-width ≈0.15** (0.14–0.16) and an **MDD (80% power) ≈0.25**:
- half-width ≈0.15 **meets the 0.15 equivalence bound** (borderline) → **equivalence at
  |Δ| ≤ 0.15 becomes establishable**, so the confirming branch is a genuine equivalence claim.
- MDD ≈0.25 **at/below the 0.30 refuting threshold** → the design can now detect a moderate
  refuting gap, and a gap in (0.15, ~0.25) may still land INCONCLUSIVE by power.
Cases are free CPU (108 faulty cases build in CI); only the paid trial scales (~$10 → ~$25–35).
Scaling further (8 seeds) barely improves it (half-width ≈0.14, MDD ≈0.25), so 6 is the pick.

**H8.** The anchored LLM's identification on `data_leakage` is driven by fault mechanism, not
key legibility.

**Confirming metric.** Per-operator identification rate (`scores.identification.correct`),
**case-clustered 95% CI** (case-level bootstrap, 10k resamples; `harness/sweep_stats.py`),
reported **per anchor arm**.

- **CONFIRMING (equivalence).** Neutral identification within **0.15** of descriptive in the
  same arm AND the case-clustered 95% CI on the difference falls within **[−0.15, +0.15]**
  (equivalence established — feasible at 6 seeds, half-width ≈0.15 per the power note). Read as:
  the agent reads the mechanism; the surviving headline stands. If the point estimate is within
  0.15 but the CI **narrowly** exceeds ±0.15 (the half-width is borderline), report the weaker
  **"no evidence of a substantial gap"** rather than claim equivalence.
- **REFUTING.** Neutral **> 0.30 below** descriptive with the CI excluding zero ⇒
  identification was substantially name-reading; the surviving headline shrinks to **"config
  legibility,"** and the agent's measured value over B2 collapses further.
- **INCONCLUSIVE.** A gap in (0.15, 0.30], or a CI spanning both thresholds ⇒ reported as such;
  no side is picked. (Per the power note, a true gap up to ≈0.25 may still land here.)
- **Per anchor arm.** The **off arm may floor on both variants** (Sweep-1 leakage detection
  0.042 off-anchor); if it floors, H8 is answered by the **stats and rule arms**, and that is
  stated.

**Secondary (pre-registered).**
- **Detection + recovery are expected UNCHANGED between variants** (B2 detects 6/6 on both; the
  fault is identical). A difference there would indicate an **instrument problem, not a finding**
  — stated in advance.
- **Evidence F1 by variant.** The neutral evidence set cites the neutral keys; a drop would
  mean the agent cites config keys it cannot interpret.
- **B0–B4 baselines** reported as the floor on every case, both variants.
- **Per-provider structured-output folding rate (Sweep-3 secondary).** The fraction of submits
  whose structured `repair_spec` was folded into a sibling string field
  (`recover_folded_repair_spec`), reported **per provider** (Anthropic Haiku vs OpenAI GPT-5.6
  Luna) over the **full Sweep-3 cell count**, each with a case-clustered CI. Prior: Haiku ≈ 9.6%.
  This is a genuine measurement only at the full n — the adapter smoke's 0/10 on one easy case is
  NOT an estimate (≈26% 95% upper bound, consistent with Luna at or above Haiku's rate). Reported
  descriptively (folding is a transport/robustness property, not a diagnosis-quality axis); a large
  per-provider gap is a caveat on cross-provider score comparisons, not a finding about either model.

**Isolation evidence (why the contrast is clean).**
- **Identical hidden faulty values** at every strength/seed — descriptive == neutral to 6
  decimals (mechanical equivalence). All six seeds measured on **CI run 35424537626** (native
  amd64, the full 128-case build; `case_margins` step, which asserts descriptive == neutral
  across the whole design). The descriptive `case_0019–0036` and neutral `case_0037–0054`
  faulty values match to 6 decimals at every (strength, seed) — verified in that run's log:

  | strength | seed 42 | seed 43 | seed 44 | seed 45 | seed 46 | seed 47 |
  |----------|---------|---------|---------|---------|---------|---------|
  | mild     | 0.822203 | 0.823087 | 0.827805 | 0.823235 | 0.822940 | 0.825151 |
  | moderate | 0.803922 | 0.802742 | 0.799499 | 0.801563 | 0.800383 | 0.802595 |
  | severe   | 0.719151 | 0.728291 | 0.725048 | 0.717971 | 0.705735 | 0.730060 |

  (These differ ≤~1e-3 from the earlier illustrative 42/43 values measured on run 35385887096
  — expected cross-microarchitecture drift, LIMITATIONS L18. The **descriptive == neutral**
  identity is exact *within a run* because both variants train on the same runner from the same
  derivation `datautil._derived_column`; that identity, not the absolute digits, is the isolation
  evidence.)

- **Zero hint tokens** in the neutral workspace vs `['aux','feature']` in the descriptive
  (`tests/test_neutral_variant.py::test_neutral_introduces_no_hint_token`).
- **No harness module** outside the operator branches on either key name
  (`test_no_variant_agnostic_module_names_descriptive_keys`).
- **Admissible repairs identical up to key names**
  (`test_admissible_repairs_identical_up_to_key_names`).
- **B2 detect 6/6, identify 0/6** on both variants (config-diff is name-blind; the config leaf
  carries no `leak` token).

**Sweep factor.** Config-key naming (descriptive vs neutral) × strength × seed × anchor × agent,
mechanism held identical.

---

## Secondary observations to record (not hypotheses, but report them)

- **Cost ratio ReAct : static** per operator (tokens and $). "ReAct is 3× the cost for
  N points of evidence" is a result in its own right.
- **Investigation cost by difficulty:** tokens/cost per trial by operator and strength
  (hard cases cost 2–3× in prior trials). Report the ratio.
- **Evidence padding:** precision < recall pattern (agents cite extra, plausible-but-
  unnecessary refs). Report per operator.
- **Cross-operator distraction:** how often agents cite or investigate knobs belonging to
  *other* operators (the input_dim red herring). Report as a distractor rate.
- **Always-broken / knob-scanner baselines:** what "always cry fault" and "diff the config"
  achieve on each axis — the floor any real agent must beat.

---

## What would make Sweep 1 a strong paper vs a weak one

- **Strong:** H1 confirmed with the anchor intervention (finding + cause + fix), plus an
  H2 threshold curve, plus H6 showing *where* tools help and where they don't. That is a
  mechanism, a number, and a cost-quality map — citable.
- **Adequate:** H1 refuted but H2/H3/H4 give a quantitative characterization no prior
  benchmark provides.
- **Weak:** everything near ceiling (Haiku solves all cases in all conditions). Then the
  benchmark's *tabular* tier is saturated for this model — which is itself the finding that
  directs Sweep 2 toward harder operators (imbalance, normalization) and a stronger tier.

---

## Results (appended after Sweep 1 — do not edit above this line)

### Post-hoc scoring corrections

Two Sweep-1 results were **scoring/schema artifacts, not model behaviour**, found in
the diagnostics pass and corrected here **by principle** (never by copying observed model
strings). Both are disclosed; the **original numbers are kept alongside the corrected ones**
in the sweep report and diagnostics. Corrections re-score a free axis / re-verify via the
standard evaluator; ground truth is unchanged. Each corrected record carries an audit trail
(`method`, `token_spec_sha256`) and preserves its pre-correction result
(`identification_original`). See docs/DECISIONS.md (2026-09-13) for the full judgment log.

**Correction 1 — identification (root-token match, `root_token_v1`).** Membership against an
enumerated `accepted_classes` scored correct synonyms (`excessive_learning_rate`,
`auxiliary_feature_leakage`, `excessive_label_noise`) as wrong, driving identification to
≈0 on all three silent operators. Fixed: each operator declares principled `core_tokens`
(defined from the fault's meaning); a label is credited iff it matches the target operator and
is the **unique** operator matched (so `lr_and_leakage` and `none`-on-faulty are rejected). The
exact path is retained. Resolved from operator code — no sealed card edited, nothing superseded.

**Correction 2 — shape recovery (unset repairs).** shape_mismatch/data_leakage/label_corruption
each inject a key absent in the clean config; an agent proposing `null` ("remove the override")
was rejected `VALUE_TYPE_INVALID` although deleting the key is **oracle-equivalent** to the
reference value (verified to recover identically on hidden seeds for all three). Fixed: operators
declare `absent_when_clean_keys`; the validator accepts `null` only on those; the evaluator
deletes the key before rerun.

**Correction 3 — recovering a MODEL-folded repair_spec (`parser_fix_v1`).** This is
**model-side output folding, NOT a harness parser bug.** Some trials emitted the text-tool-calling
idiom (`<parameter name="repair_spec">{…}`) *inside* a native tool_use string field (the
`rationale`) instead of populating the structured `repair_spec` field; our pipeline recorded the
structured tool_use input faithfully and never text-parsed arguments or swallowed a sibling field.
The correction is that we now **recover a single, well-formed repair the model misplaced** — a strict
`json.loads` of one complete `{repair_type, patches}` object (never partial reconstruction, never key
scraping; ambiguous/multiple → not recovered) — and flag it (`submission_parse_warning`,
`method="parser_fix_v1"`). The recovered spec is **not** trusted as admissible: it flows through the
normal `validate_repair`/verify path exactly like a directly-submitted one. The same recovery runs
in the **live** agent path so future sweeps self-heal and flag. Scan: **31/324 (≈9.6%) submissions
were folded and recovered** (0 ambiguous, 0 unparseable), across shape_mismatch (14), label_corruption
(8), lr_warmup (6), data_leakage (3) — see the "structured vs recovered" rates in the report and the
tool-use-reliability observation in FINDINGS.

**Axes / hypotheses this TOUCHES:** Corrections 1–2 touch identification only → **H3**
(doing/understanding gap) and **H4** (repeat agreement on identification); Correction 2 and 3 touch
**recovery** — Correction 3 raises recovery on every faulty operator that had folded repairs (shape
plus the three silent ops).

**Axes / hypotheses this DOES NOT touch:** detection is unchanged (a folded `repair_spec` never
affected the diagnosis axes) → **H1** (positive-symptom blindness), **H2** (detection vs σ), and
**controls** are unchanged by Corrections 1–3. Recovery moves (Corrections 2–3), sharpening **H3**.

**Correction 4 — H1 negative-symptom comparator was pooled (2026-09-15).** Disclosed in FINDINGS
"Post-hoc corrections" #4 and the Stage-2 Results / Deviations sections; revises H1's headline
(leakage-specific; symptom-direction generalization refuted by Stage-2 G1).

**Correction 5 — evidence scorer v1 → v2.1 (bipartite one-to-one) primary (2026-09-15).** Sweep-1
`scores.evidence` had never left **v1** while the docs said "v2 primary" (a provenance mislabel; the
v1→v2 rescore was disclosed 2026-09-13 but never persisted). All records migrate to **evidence_v2.1**,
which fixes v2's union rule (duplicates/shotgun over-credited). Decomposition (v1→v2.1): (a) v1→v2
span-strictness dominates — shape_mismatch **0.807→0.607** (L17); (b) the v2→v2.1 bipartite fix bit
**lr_warmup** (5 sweep-1 trials, ~−0.13), NOT shape_mismatch. **This TOUCHES evidence and H6:**
**H6 (ReAct − static evidence F1) 0.135 → 0.1343**, CI [0.070, 0.206] — the pre-registered **≥ +0.10
criterion still holds** (point ≥ 0.10; CI-lower still dips below 0.10), because shape_mismatch drops
for both agents ~equally so the difference barely moves. stage2gate + all config-key operators are
unchanged (v1=v2=v2.1). Full detail + per-trial table: FINDINGS "Post-hoc corrections" #5.

**Amendments recorded (A–E):**
- **A.** The previously-not-recovered shape trials are split into *unexpressible-but-correct*
  (`input_dim=null` → re-verified) vs *no-repair-proposed* (genuine model failure, stands
  not-recovered); both are shown with the corrected recovery rate.
- **B.** Identification judgment: root-token **accepts** `missing_lr_schedule` (concept = the
  learning rate) and **rejects** `insufficient_regularization`, `seed_mismatch`, and cross-fault
  labels; the accepted fraction of observed strings per operator is reported as validation.
- **C.** H2 is a **two-mechanism** result: detection is **monotone in σ within negative-symptom
  faults** (~0.5 at σ≈10–18, ~1.0 by σ≈44) and **floored regardless of σ for positive-symptom
  faults** (0–0.33 up to σ=64). (Not "does not track σ".)
- **D.** **lr_warmup ladder saturation** (limitation): cases 0001/0024/0025/0026/0027 share
  identical σ (68.6/44.6); only 0023 differs, so lr_warmup contributes ~1 effect-size point and
  leaves an H2 x-axis gap between σ≈18 and σ≈44. Sweep-2: recalibrate mild toward the tolerance
  edge.
- **E.** **Controls FP framing:** the `mean−2σ` band has a structural ~2.3% one-sided out-of-band
  floor under the fitted normal (normality CHECKED at the 30-seed band, §0.5; earlier "~5%" was the
  two-sided figure); the 4 FPs are separated into band-edge misreads vs true out-of-band healthy runs.
  A **3σ band** is added to the Sweep-2 pre-registration candidates. The band is **not** changed now.

### Per-hypothesis verdicts (measured; source `docs/audits/sweep_sweep1_20260913.md`)

**H1 — Positive-symptom blindness · PILOT SUPPORT (confound disclosed).** Pre-registered: anchor-off
leakage detection ≥30 points below matched negative-symptom detection, anchor-on gap ≤10. Measured
(pooled, case-clustered): anchor-off gap (negative − positive) **0.556, 95% CI [0.327, 0.774]**
(pos 0.083 on 6 cases, neg 0.639 on 12 cases); anchor-on **1.000 / 1.000** (gap 0). The pooled
contrast is large and in the predicted direction. **Caveats that keep this from a clean confirm:**
(a) **symptom direction is perfectly confounded with operator identity** — every positive-symptom
case is data_leakage, every negative-symptom case is lr_warmup/label_corruption — so the gap may
reflect symptom direction OR leakage being intrinsically harder; only a *second* positive-symptom
operator can separate them. (b) The pre-registration specified the comparison **"at matched
σ-distance"; that matched analysis was not performed by `hypothesis_metrics()` (it pools all
leakage vs all negative-symptom trials).** A supplementary nearest-σ pairing gives mean paired gap
**0.528**, but it narrows σ only and does **not** touch the operator-identity confound. (c) The
anchor manipulation **confounds a numerical reference with an explicit decision rule** ("values
outside this range are anomalous"), so Sweep 1 shows that **norm + rule** restores detection, not
that a norm alone does. *Verdict: pre-registered pooled contrast large and in the predicted
direction; treated as **pilot evidence pending factorial replication** (a second positive-symptom
operator; a three-arm none/numbers-only/numbers+rule anchor design).*

**H2 — A detection threshold in units of σ · REFUTED (prediction not met).** Pre-registered: a
**single monotone detection-vs-σ curve with a fitted 50% threshold and interval.** Outcome: **no
threshold was fitted, and the pooled detection-vs-σ curve is non-monotone** — the pre-registered
prediction is not met. Reported against **visible signed σ** (what the agent observes; negative =
inflated/positive symptom), with hidden σ shown separately as benchmark harm. *New EXPLORATORY
hypothesis (post-hoc, not confirmatory): symptom **sign** moderates the magnitude→detection
relationship — within negative-symptom faults detection rises with σ (label_corruption 0.33–0.50 at
σ≈11–18; lr_warmup 1.00 by σ≈44), while positive-symptom faults floor 0.00–0.33 regardless of σ (to
σ=64). To be pre-registered and tested prospectively in a later sweep, not claimed from this data.*
The per-case evidence table is retained below.

**H3 — The doing/understanding dissociation · REFUTED (pre-registered direction); a modest
id > recovery dissociation on the PRIMARY (strict) endpoint.** Pre-registered: recovery >
identification. **Primary endpoint = STRICT recovery** (a valid *structured* repair submitted and
verified — autonomous success); **semantic recovery** (strict + repairs recovered post-hoc from
folded output) is the secondary endpoint. The earlier "no dissociation" verdict was computed from
semantic recovery; recomputed here against **strict** as primary, case-clustered:

| operator | identification | strict recovery | semantic recovery | id − strict (95% CI) | id − semantic (95% CI) |
|---|---|---|---|---|---|
| shape_mismatch | 0.986 | **0.750** | 0.944 | **0.236 [0.208, 0.250]** | 0.042 [0.014, 0.069] |
| lr_warmup | 0.931 | **0.833** | 0.903 | **0.097 [0.056, 0.139]** | 0.028 [0.000, 0.056] |
| label_corruption | 0.639 | **0.514** | 0.583 | **0.125 [0.056, 0.194]** | 0.056 [0.014, 0.111] |
| data_leakage | 0.431 | **0.389** | 0.431 | 0.042 [−0.056, 0.139] | 0.000 [−0.056, 0.069] |

*The pre-registered direction (recovery > identification) is **refuted** on both endpoints. On the
**primary strict endpoint** identification exceeds recovery on 3 of 4 operators with a
case-clustered CI that excludes 0 (shape 0.24, lr 0.10, label 0.13) — a real, if modest,
dissociation in the opposite direction. But **semantic recovery nearly closes it** (id − semantic
≈ 0–0.06), so most of the strict gap is submission-format **compliance** (9.6% folding) plus strict
admissibility, not an inability to name the fault. Status set from the primary (strict) endpoint;
both endpoints reported.*

**H4 — Reliability is not accuracy · PARTIALLY CONFIRMED.** Pre-registered: repeat agreement high on
easy cells, lower on hard ones. Measured: mean 3-repeat agreement **0.82**; detection agreement
uniform (0.75–1.00), identification agreement drops to **0.71** on data_leakage vs **0.96** on
lr_warmup. *Outcomes are reproducible; the model's *explanation* of the hardest fault is the least
stable part.*

**H5 — Does capability increase rationalization? · DEFERRED to Sweep 2.** Single model (Haiku 4.5)
here; the cross-capability comparison needs a second, more capable model. *Not evaluable in Sweep 1.*

**H6 — Tool-mediated investigation vs static full context · CONFIRMED overall; leakage sub-claim
NOT formally confirmed.** Pre-registered: ReAct ≥ +0.10 evidence F1 overall; ReAct − static ≤ 0 on
leakage while > 0 on negative-symptom faults. Measured (case-clustered) ReAct − static evidence F1
overall **0.135, 95% CI [0.075, 0.204]** — point meets ≥0.10, but the CI lower bound dips below
0.10, so "overall ≥0.10" is met at the point estimate, not robustly. Per operator: label_corruption
**+0.32**, lr_warmup **+0.17**, shape **+0.04**, data_leakage **+0.006** (control 0); cost ReAct
$10.81 vs static $1.95 (**5.5×**). The **leakage sub-claim required ReAct − static ≤ 0; observed
+0.006 — practically zero but formally NOT confirmed** (a small positive value vs a ≤0 criterion).
*Important: ReAct vs static does **not isolate tool use** — the two arms also differ in call count,
deliberation, context ordering, token budget, and prompt text (the ReAct prompt names learning
rate / batch size / optimizer, which may advantage lr_warmup). A **token-matched deliberative
baseline** is needed to attribute the gap to tools specifically.*

### Secondary observations — measured

Sample: **324 trials from 27 unique cases** (6 per faulty operator × 4 + 3 controls; 12 trials/case).
Primary contrasts use case-level bootstrap CIs (10k resamples, 95% percentile) — see the report's
"Primary contrasts" section.

- **Cost ratio:** ReAct : static ≈ **5.5×** in dollars (7–8× input tokens); ~$0.06–0.08 vs ~$0.012 per trial.
- **Structured-output folding rate:** **31/324 (9.6%)** of submissions placed a well-formed repair in
  the wrong (string) field. This is an **agent-compliance failure of the system under test**, not
  merely a harness penalty: the model produced the right fix but did not submit it in the structured
  field. Recovered post-hoc for the *semantic* endpoint only; it does not count toward *strict*
  autonomous success.
- **Evidence is recall-heavy (padding):** mean precision < recall on control/shape/lr_warmup/data_leakage
  (agents cite the true refs plus extras); label_corruption is the exception (precision > recall).
- **Distractor rate:** ≈ **0.24** of trials reference another operator's knob (mostly ruling-out while
  reading the shared `train.py`; peaks 0.42 on shape_mismatch).
- **Confidence supplied:** only **52/324** trials gave a confidence value (top-heavy; ECE_detection ≈
  0.07); it cannot gate the control false positives (see L7).

---

## Sweep-2 pre-registration candidates & diagnostics plan (forward-looking; not Sweep-1 results)

Collected here as the running list of what a Sweep-2 pre-registration should fix or add. Items
already noted above: recalibrate the lr_warmup mild rung toward the tolerance edge (H2 x-axis gap,
L1/D); a **3σ band** vs the 2σ band (control FP floor, E/L3); a **second positive-symptom operator**
and a **three-arm none/numbers-only/numbers+rule anchor** to break the H1 confounds (L9/L10); a
**token-matched deliberative baseline** for H6 (attribute the gap to tools). New with the metric tier:

- **metric_inflation is now the second positive-symptom operator (H1).** With it, H1 can be tested as
  a property of symptom *direction* rather than operator identity. **But** the two positive-symptom
  operators are **not matched on within-case detectability** (L16): `metric_inflation` reports an
  inflated accuracy while `val_loss` stays on the full split, so an epoch row is internally
  inconsistent (normal loss beside inflated accuracy) — detectable with no external baseline —
  whereas `data_leakage` has no such contradiction. Any anchor-off detection difference between the
  two must be interpreted against this confound.
- **(Diagnostics — Sweep 2, required.)** Tag every rationale/transcript that cites the
  **loss/accuracy inconsistency** as the basis for flagging `metric_inflation`, and report the rate
  **per operator × anchor condition**. If agents detect `metric_inflation` anchor-off *mainly* via
  this mismatch, that is a finding about **consistency checking**, not about positive-symptom
  *magnitude* — and the two must be reported separately, never merged into a single "positive-symptom
  detection" number. This diagnostic gates any H1 claim that leans on the second operator.
- **(Sweep-3 candidate.)** A **matched `metric_inflation` variant that computes the loss on the same
  confidence subset**, removing the internal contradiction, is the clean way to isolate detection of
  inflation *magnitude* from detection of within-case *inconsistency*. Pre-register it once Sweep-2's
  diagnostic shows how much agents rely on the mismatch.
- **Three-arm anchor (off / numbers / rule) — implemented (Stage 2), to run in Sweep 2.** Sweep 1's
  anchor confounded a numeric reference with a decision rule (L10). The arms differ by exactly one
  sentence (`rule` = `numbers` + "Values clearly outside this range, above OR below, are anomalous.").
  **Pre-registered prediction shape:** if the **numbers-only** arm closes the H1 positive-symptom
  detection gap as much as **rule**, detection is restored by a *baseline / norm* alone (baseline
  restoration); if **only rule** closes it, the effect is *instruction following / threshold
  prompting*, not the norm. Report all three arms per operator; legacy Sweep-1 "on" == "rule".
- **Evidence scorer v2 — primary from Sweep 2 (v1 preserved).** IoU ≥ 0.5 + 3× width cap for
  line/code spans, required explicit bounds (unbounded = malformed), alternative sufficient sets
  (default single set), and a *measured* containment window for metric_window. Sweep reports show
  both v1 and v2; the disclosed Sweep-1 delta (shape_mismatch −0.20, others ≈unchanged; metric_window
  rule flipped 0 refs) is a measurement change, not a finding (LIMITATIONS L17; DECISIONS 2026-09-13).
- **H2's σ-axis rests on `label_corruption`, not `lr_warmup` (2026-09-14).** `lr_warmup`'s degradation is
  BIMODAL — a per-seed collapse to the majority baseline whose probability rises with lr, with no stable
  partial regime (S12; L1 rewritten; DECISIONS 2026-09-14). So `lr_warmup` contributes **detection**
  data only (does the agent notice a collapsed run?), NOT σ-magnitude data; it is retired from the
  detection-vs-σ curve. `label_corruption` is the stably-graded negative-symptom operator that carries
  the σ-axis; a second stably-graded operator (train-subset-fraction or excessive weight_decay) is a
  Sweep-2 candidate to add σ-points. Any H2 analysis must not read `lr_warmup`'s cases as graded σ.

---

## Stage-2 gate (pre-registered 2026-09-14 — do not edit above this line; append verdicts only)

Frozen BEFORE any Stage-2 trial ran. Committed before the sweep plan and before the
paid agents phase (git history is the timestamp).

**Design.** Two POSITIVE-symptom operators — `silent.data_leakage.v1`,
`silent.metric_inflation.v1` — plus one NEGATIVE-symptom reference,
`silent.label_corruption.v1` (the *subtle* negative operator; `lr_warmup` is
excluded because it saturates the σ ladder, L1). Cross:
**3 strengths (mild/moderate/severe) × 2 seeds (42, 43) × 3 anchor arms
(off / numbers / rule) × 2 agents (react, static) × 3 repeats**, plus healthy
controls across the three arms. Cases build from the registry to the CURRENT code
(thread-pinned `train.py`; evidence-v2 operator ground truth). The committed plan
file reports the exact cell count and cost estimate before anything runs.
**Evidence is scored under v2 (primary); v1 is reported alongside** (LIMITATIONS L17).

**G1 — Does positive-symptom under-detection REPLICATE on a second mechanism?**
*Prediction:* anchor-off detection on `metric_inflation` is substantially BELOW
anchor-off detection on `label_corruption` at comparable visible σ, in the same
direction as `data_leakage`. *Confirming metric:* anchor-off detection rate per
operator, case-clustered 95% CIs. **CONFIRMED** iff `metric_inflation`'s anchor-off
detection CI **upper** bound lies **below** `label_corruption`'s point estimate.
**REFUTED** if `metric_inflation` detects **at or above** the negative-symptom
operator — which would mean Sweep 1's effect was specific to leakage, not to
symptom direction.

**G2 — Is a bare NORM sufficient, or is the RULE doing the work?** *Two-sided —
there is no confirm/refute here by design.* If the **numbers** arm closes MOST of
the off→rule detection gap, the mechanism is **baseline restoration** (a norm
suffices); if only the **rule** arm closes it, the mechanism is
**instruction-following / threshold-prompting**. *Confirming metric:* detection
rate per arm per operator, and the FRACTION of the off→rule gap closed by
**numbers**, with CIs. Report which of the two interpretations the data supports.

**G3 — Is `metric_inflation`'s detection explained by the WITHIN-CASE loss/accuracy
inconsistency (L16) rather than by inflation magnitude?** *Prediction:* if agents
are using the inconsistency, their rationales will cite it. *Confirming metric:*
the fraction of `metric_inflation` trials whose rationale/transcript cites the
loss-vs-accuracy mismatch, by arm. If that fraction is HIGH in the **anchor-off**
arm, G1's replication is **confounded** and must be reported as such (consistency-
checking detection, not positive-symptom-direction detection).

**Exploratory (NOT a pre-registered claim) — a magnitude boundary.** The
`metric_inflation` ladder spans plausible (~0.88, mild) → implausible (~0.98,
severe) inflation, so report detection **by strength**. If detection rises with
implausibility, that is evidence for a magnitude boundary on positive-symptom
blindness — an exploratory sub-question to pre-register prospectively if observed.

### Deviations from the pre-registration (2026-09-14 — appended; the pre-registered text above is unchanged)

- **Repeats: 3 → 2.** *Reason:* the $25 cost cap. The 3-operator gate at the
  pre-registered 3 repeats is 378 cells (3 ops × 3 strengths × 2 seeds × 2 agents ×
  3 anchor arms × 3 repeats = 324 faulty + 54 control), estimated **~$37**
  (1.5× the committed repeats-2 plan's $24.81; an earlier rougher figure was
  ~$28.7) — above the cap. At **2 repeats** the gate is **252 cells ≈ $24.81**,
  which fits. *Consequence:* wider confidence intervals on every rate (G1/G2), and
  **within-cell repeat-agreement is not computable at n=2** — so any
  agreement-style measure (the H4-type "same detect+identify across repeats")
  is **dropped for this gate** and deferred to Sweep 2. Detection/identification/
  evidence/recovery rates and their case-clustered CIs are unaffected in kind, only
  in width. This deviation is committed BEFORE the plan file and before any trial.
- **Operator set (not a deviation from the gate design, but recorded for the
  artifact):** the plan is restricted via `--operators` to the three
  pre-registered gate operators (`silent.data_leakage.v1`,
  `silent.metric_inflation.v1`, `silent.label_corruption.v1`). `silent.lr_warmup.v1`
  (bimodal, retired from the σ-role — L1/S12) and `crash.shape_mismatch.v1` (crash
  tier, orthogonal to symptom direction) are deliberately excluded; the exclusion +
  reasons are recorded in the plan header's `scope` block.

## Stage-2 gate — Results (2026-09-15 — appended below the pre-registration; the frozen text and the deviation note above are unchanged)

Evidence: `docs/audits/sweep_stage2gate_2026-09-15.md`. 252 cells, claude-haiku-4-5.
Detection/identification/evidence from the (platform-independent) agent phase; recovery from
the canonical in-container verify re-run. Case-clustered 95% CIs (cluster = operator×strength×seed).

- **G1 — REFUTED.** `metric_inflation` anchor-off detection **0.250 [0.083, 0.417]** vs
  `label_corruption` **0.250 [0.083, 0.458]**; `metric_inflation − label_corruption` **+0.001
  [−0.281, +0.250]**. The pre-registered refute clause fired: the second positive-symptom
  mechanism detects **at** the negative-symptom reference. **Consequence:** positive-symptom
  under-detection does **not** generalize to a second mechanism — it is **leakage-specific**
  (`data_leakage` anchor-off **0.042 [0.000, 0.125]**; `data_leakage − label_corruption` **−0.208**).
  The symptom-direction≡blindness reading that this gate was built to test is not supported.
- **G2 — baseline restoration for detection.** The **numbers** arm closes **~94–95%** of the
  off→rule detection gap on all three operators (rule adds only 4–5 pp): a bare numeric norm,
  not the decision rule, does the detection work. The control false-positive comparison — off
  **0.000**, numbers **0.500 [0.000, 0.750]**, rule **0.167 [0.000, 0.500]**; numbers−rule
  **+0.336 [0.000, 0.750]** over **3 control clusters** — is **SUGGESTIVE, NOT ESTABLISHED**:
  the CIs do not exclude "no effect," so "a bare band over-flags healthy runs, the rule reins
  it in" is a hint, not a result (argues for ≥20 controls, L20).
- **G3 — the L16 inconsistency is not used (0/72).** No `metric_inflation` trial cites the
  loss/accuracy inconsistency in any arm; every detection reasons from the config knob
  `eval_subset_fraction`. G1 is therefore **not** confounded by consistency-checking. It does
  surface a **config-legibility** confound (detection is config-knob reading), but that is
  **equal across all three operators**, so it does not bias the G1 cross-operator contrast (L22).
- **Exploratory magnitude sub-question — no boundary readable.** `metric_inflation` off-arm
  detection by strength (mild 0.500 > moderate 0.125 ≈ severe 0.125) runs opposite the "detection
  rises with implausibility" guess, but at n=8 trials / 2 cases per strength and driven by
  knob-inspection incidence (not magnitude perception) it is **uninterpretable — not a null**.
- **Measured secondaries.** Agent-phase cost **$11.71 / 252 cells** (estimate). Evidence
  **v2 == v1** on every trial (Δ 0.000; the v2 machinery is inert on these submissions —
  comparison deferred). Repair **folding: 16** submissions (13 recovered via `parser_fix_v1`).
  Recovery axis **degenerate** on these operators (`not_recovered` 0/138; see FINDINGS/L19) —
  reported for completeness, not a discrimination axis this gate.

---

## Sweep-3 pre-registration addendum (2026-09-17) — superseding H7's detection framing

**Why H7 is re-framed.** H7 (STAGE3_PLAN: "reference context restores **detection**") treats
detection as the axis where the reference/agent adds value. Part 1's non-LLM baselines refute
that as the HEADLINE: on this workload's five config-knob operators, a config-delta baseline B2
— knowing the clean resolved config + the derived-key set — matches the ref-anchored LLM on
detection (30/30 vs 1.00) AND recovery (30/30 vs 0.94) at better specificity (0/20 vs 0.22).
Detection is not where the agent's measured value concentrates; identification of non-legible
faults is. *Integrity caveat: baselines are on the native 50-case set, the LLM on the frozen
superseded set — per-operator DIRECTIONAL only, no cross-set gap CI, resolved by Sweep 3.*

**H7′ (re-pre-registered headline for Sweep 3).** On config-knob faults, the agent's value over
a config-delta baseline is concentrated on IDENTIFICATION (and secondarily evidence) of faults
whose config knob does NOT name the concept (`data_leakage`, `metric_inflation`), and that value
is ANCHOR-DEPENDENT.
- **Prediction.** On a matched native case set: LLM_ref − B2 identification > 0 with a
  case-clustered CI excluding 0, concentrated on `data_leakage` + `metric_inflation`; on
  lr/label/shape the gap ≈ 0. LLM_off − B2 identification ≈ 0 or negative (anchor-dependence).
- **Decisive test — NEUTRAL-KEY (Part 2).** Rename each operator's config knob to a
  concept-neutral token (e.g. `training.lr` → `training.hp_a`). If the anchored LLM's
  identification HOLDS under neutral keys while B2's (config-name match) drops → the LLM edge is
  fault-understanding. If it collapses toward B2 → it was config-legibility. **Pre-registered
  criterion:** LLM_ref identification under neutral keys ≥ (its legible-key identification −
  0.15) ⇒ understanding; else legibility.
- **Code-origin operator.** A fault living in code with NO config knob → B2 is structurally
  blind (0 detection/identification). If the LLM detects/identifies it, the agent's value
  extends BEYOND config-knob faults — the generalization Part 1 explicitly does not make.
- **What would refute H7′.** Neutral keys collapse the LLM's identification to the B2 floor
  (edge was legibility, not understanding); or the matched-set LLM_ref − B2 identification CI
  includes 0 (no measurable edge once the sets match).
---

## H8 — Results (Sweep 3, appended 2026-09-22 — do not edit the pre-registration above)

Source: `docs/audits/sweep_h8_xprovider_generated.md` (regenerated 2026-09-22), n_trials **978**
(one trial per cell after dedup; 6 cells unrun — all Luna × static × neutral), both providers
(Anthropic Haiku, OpenAI GPT-5.6 Luna), 18 cases per variant per arm.

**Verdict rule applied (as pre-registered — TWO-SIDED equivalence on the case-clustered 95% CI):**
confirming iff the whole CI ⊂ ±0.15 (`lo > −0.15 AND hi < +0.15`); refuting iff Δ < −0.30 and the
CI excludes 0 (`hi < 0`); else inconclusive. Δ = neutral − descriptive identification.

**PRIMARY analysis = PAIRED (strength×seed) bootstrap** (report + DECISIONS 2026-09-22): the two
variants are the same fault at matched (strength, seed), so the design pairs them; the paired CI
resamples matched pairs together. The **point estimate is identical** to the table below (which shows the
UNPAIRED contrast); only the CI differs, and the sole verdict change is **Haiku numbers**, which the
paired CI [−0.056, +0.139] resolves from inconclusive to **confirming**. **Counting rule:** the tally is
over the **6 provider-specific cells only**; the `pooled` rows reuse the same trials and are a summary,
never counted as independent confirmations.

| provider | arm | Δ (95% CI, UNPAIRED) | verdict (unpaired) |
|---|---|---|---|
| pooled | numbers | −0.015 [−0.090, +0.061] | confirming |
| pooled | off | −0.015 [−0.084, +0.053] | confirming |
| pooled | rule | −0.058 [−0.135, +0.022] | confirming |
| anthropic (Haiku) | numbers | +0.042 [−0.083, **+0.167**] | inconclusive |
| anthropic (Haiku) | off | −0.014 [−0.084, +0.059] | confirming |
| anthropic (Haiku) | rule | 0.000 [−0.125, +0.128] | confirming |
| openai (Luna) | numbers | −0.072 [**−0.165**, +0.013] | inconclusive |
| openai (Luna) | off | −0.006 [−0.121, +0.106] | confirming |
| openai (Luna) | rule | −0.115 [**−0.207**, −0.026] | inconclusive |

**Honest tally (provider-specific cells only — pooled reuses the same trials and is a summary,
never counted as an independent confirmation):**
- **PAIRED primary:** **4 of 6** provider-specific cells confirming (Haiku off/numbers/rule, Luna off),
  **2 inconclusive** (Luna numbers, Luna rule), **0 refuting**.
- **Unpaired (table above):** **3 of 6** confirming (Haiku off/rule, Luna off), **3 inconclusive**
  (Haiku numbers, Luna numbers, Luna rule), 0 refuting.
- The only cell that differs between the two is **Haiku numbers**. Pooled ×3 all confirming (summary).
  H8 is **not refuted anywhere**.

**The unpaired inconclusives are NOT the same, and the direction matters** (Haiku numbers becomes
confirming under the paired primary; the two that persist are the Luna arms):
- **Haiku numbers — inconclusive in the NON-THREATENING direction.** Δ = **+0.042**; the CI
  excursion is on the **upper** side (+0.167 > +0.15), i.e. it cannot rule out neutral being
  *more than 0.15 BETTER* than descriptive. That does not challenge the mechanism claim — if
  anything it points the wrong way for name-reading. Under the symmetric ±0.15 test it is
  inconclusive, but it is not evidence against H8.
- **Luna numbers — inconclusive, low side but CI includes 0.** Δ = −0.072; the CI reaches
  −0.165 (past the threatening −0.15 edge) yet still includes 0. A possible small gap, unresolved
  at this n.
- **Luna rule — inconclusive in the THREATENING direction.** Δ = −0.115 with CI **[−0.207,
  −0.026] excluding 0**: a **real but modest** neutral-below-descriptive gap on Luna's rule arm —
  statistically non-zero, yet **well short of the −0.30 refutation bound**. Consistent with a
  small config-legibility contribution to Luna's *anchored* identification, not a collapse toward
  the B2 floor.

**Reading (corrected 2026-09-23, STAGE4 4.0.3 — the earlier reading overstated the result).**
**Identification often survives the tested renaming; equivalence is unresolved in two anchored
conditions (Luna numbers, Luna rule); Luna's rule arm shows a measurable decrease** (Δ −0.115, paired CI
[−0.197, −0.032], excluding 0 but far short of the −0.30 refutation bound). Three qualifications bound
what that supports:
- **Renaming two keys tests dependence on THOSE NAMES.** A surviving identification shows the agent does
  not need `include_aux_feature` / `aux_feature_strength` to name the fault. It does **not** establish
  that the agent reads the fault *mechanism*: **code-pattern recognition** (the identical derivation code
  is in both workspaces) and **general leakage heuristics** (a too-good validation metric reads as
  leakage whatever the knob is called) remain **competing explanations** this design does not separate.
  The pre-registered gloss "the agent reads the mechanism" (above) claimed more than the manipulation can
  test; it is kept as registered and corrected here.
- **Haiku's off-arm "confirming" is equivalent FAILURE.** Identification is ~6% in both variants
  (neutral 0.056, descriptive 0.069). This is the case the pre-registration anticipated — *"the off arm
  may floor on both variants … if it floors, H8 is answered by the stats and rule arms"* — so, applying
  the registered rule (not a post-hoc one), that cell answers nothing and supports **no** understanding
  claim. The count, stated both ways: **4 of 6** provider-specific cells meet the equivalence criterion as run; by the pre-registration's own floor clause Haiku-off does not answer H8, so **3 of 5 answering cells confirm** (Haiku numbers, Haiku rule, Luna off) and **2 are inconclusive** (Luna numbers, Luna rule).
- **Power.** Per the pre-registered power note (6 cases/arm, CI half-width ≈0.15–0.25), "confirming" is
  the weaker *"no evidence of a substantial gap"*, and inconclusive-by-power on anchored arms was
  anticipated.

**Secondary (as pre-registered, expected UNCHANGED between variants — instrument check).**
Detection and semantic recovery per variant × arm × provider track closely between descriptive and
neutral (report's H8-secondary table), e.g. Luna-off detection 0.819 vs 0.814, recovery 0.792 vs
0.771; Haiku-rule detection 0.986 vs 0.986. No variant-driven detection/recovery divergence → the
neutral instrument is behaving as designed (same fault, same detectability); the identification
contrast is not an instrument artifact.

**Lesson for a future replication (NOT a rule change now).** H8's mechanism claim is only threatened
by neutral ≪ descriptive, so a **one-sided** equivalence test (gate confirming on `lo > −0.15`
alone, let the upper bound float) is the correct pre-registration — it would not penalize the
non-threatening Haiku-numbers upper-side excursion. **We do NOT switch to it now:** H8 was
pre-registered as two-sided equivalence, and changing the test after seeing which cells the switch
rescues is precisely the post-hoc move pre-registration exists to prevent. The symmetric rule is
kept and the tally recorded as-is; the one-sided design is logged as the improvement for the next
sweep.

---

## H8 sweep — H7 replication, secondaries, controls (appended 2026-09-22)

All numbers from `docs/audits/sweep_h8_xprovider_generated.md` (n_trials 978 deduped, both
providers) unless a crash/compliance count is cited to the sweep progress file
(`sweeps/h8_xprovider_progress.jsonl`), which the report does not carry.

**H7 (reference-context dependence, now measured PER MODEL): FAILED TO REPLICATE as a general
effect.** Anchor-off descriptive-leakage detection is **Haiku 0.083, Luna 0.819** (detection by
operator × arm, `silent.data_leakage.v1` off column, anthropic vs openai facets). The reference
band (anchored arms) therefore adds **~90 points for Haiku** (0.083 → rule 0.986 / numbers 0.972)
but only **~17 points for Luna** (0.819 → rule 0.986 / numbers 0.986). Sweep-1/gate H7 — "agents
need a numeric reference to detect the silent fault" — holds for Haiku and largely does **not** for
Luna, which detects leakage off-anchor at 0.82. Stated as **"failed to replicate," never
"refuted"** — n = 2 models, one workload, one mechanism family; model dependence is established, its
cause is not.

**Pre-registered secondary (detection UNCHANGED between variants): NOT met under anchoring.** On the
anchored arms neutral detection runs **6–9 points below descriptive** on both providers — anthropic
numbers 0.972 → 0.917 (−0.055), openai numbers 0.986 → 0.914 (−0.072), openai rule 0.986 → 0.900
(−0.086); anthropic rule is unchanged (0.986 = 0.986). Two of these anchored-arm detection gaps have
95% CIs excluding zero (independent computation on the same records; the report's H8-secondary table
carries point detection per variant, not the neutral−descriptive detection-contrast CI). Per the
pre-registration a between-variant difference triggers the **instrument check** — and the isolation
evidence (identical hidden faulty values to 6 decimals, name-blind harness, zero hint tokens in the
neutral workspace, admissible repairs identical up to key names) **rules OUT an instrument cause**.
So this is reported as an **exploratory observation, not a finding and not an instrument fault:** the
config key name affects detection *confidence under anchoring* even where it does not affect
*identification* (H8). (This refines the one-line "detection tracks closely" instrument-check note in
the H8 primary results above, which held for the off arm and Haiku-rule but not the other anchored
arms.)

**Controls — first FPR measured on 20 unique controls; still imprecise (corrected 2026-09-23).**
Detection false-positive rate on **20 unique control cases** (× 2 providers = 40 static control
trials per arm): **numbers 0.025 [0.000, 0.075], off 0.025 [0.000, 0.075], rule 0.100 [0.000,
0.225]** (control FPR table, pooled). **Precision, stated rather than asserted:** at the observed
case level the FP counts are 1 of 20 cases (numbers, off) and 3 of 20 (rule), whose exact Clopper–Pearson
intervals are **[0.001, 0.249]** and **[0.032, 0.379]** — half-widths ≈ **±0.12** and **±0.17**. (The
table's bootstrap intervals, [0, 0.075] and [0, 0.225], understate this: numbers/off rest on a single FP
case, where the percentile bootstrap is unreliable — flagged ‡, LIMITATIONS L30. Zero-event strata carry
the exact interval over unique cases, e.g. numbers in-band 0/38 over 19 cases → [0, 0.176], correction #6.)
That cannot tell a 2% FPR from a 25% one, and the numbers − rule contrast
(−0.075 [−0.200, 0.000]) touches zero, so **no arm difference is established**. The earlier label
"first adequately-powered" is withdrawn: 20 meets the L20 *count* threshold, but the resulting
precision does not support the word "adequate".

**The out-of-band control does NOT drive the anchored false positives** (the earlier narrative said
it did; its own table contradicts that). §5.1 visible-band stratification (pooled), FP trials per
stratum:
- **rule:** in-band **3/38**, out-of-band **1/2** → **3 of its 4 FPs are on IN-BAND controls.**
- **numbers:** in-band 0/38, out-of-band 1/2 → its single FP is the out-of-band control.
- **off:** in-band 1/38, out-of-band 0/2 → its single FP is in-band.

Across the two anchored arms the out-of-band control accounts for **2 of 5** false positives and
in-band controls for **3 of 5**, all three in the rule arm. So the rule arm's higher FPR (0.100 vs
0.025) comes mainly from **ordinary in-band healthy runs** — the more consequential pattern, since it
is not an artifact of one borderline case — though at this n it is suggestive, not established. This
supersedes the under-powered Sweep-1 (2 clusters) and Stage-2 (3 clusters, L20) FPRs.

**Luna secondaries.**
- **The rule arm does not help Luna.** Luna neutral identification is **0.843 on rule vs 0.900 on
  numbers** (H8 table, openai rows) — the higher-anchor arm is not the better one for Luna, unlike
  Haiku. (ReAct−static evidence F1 is also **−0.051 [−0.085, −0.015] for Luna** vs **+0.057 [0.023,
  0.094] for Haiku** — tool-mediated investigation helps Haiku and slightly hurts Luna here.)
- **Structured-output compliance (Luna static).** ~**6% of first-attempt Luna static trials crashed**
  the harness by calling `submit()` without the required `evidence_refs` (≈31 of ~492 Luna trials;
  progress file); **~80% recovered on the built-in retry** (25 of 31 completed on the second
  attempt) and **6 cells were lost** — all **neutral × Luna × static** (n = 6; the loss cannot be
  separated from that structural corner at this count). Reported alongside the pre-registered
  per-provider folding rate as a Luna transport/robustness property, not a diagnosis-quality axis.

**Correction #7 (appended 2026-09-25; the text above is left as written).** H8's evidence numbers above
are under evidence scorer v2.1. Under v2.2 (each operator's code path admitted as an evidence set;
DECISIONS 2026-09-25, FINDINGS correction #7) ReAct − static evidence F1 is **−0.035 [−0.069, 0.001]
for Luna** (interval now includes 0) and **+0.064 [0.028, 0.104] for Haiku**. No H8 detection or
identification number, and no H8 verdict, changes.

## Stage 4 Part 1 — PRE-REGISTRATION (locked 2026-09-25 — do not edit above this line; append verdicts only)

> Approved by the author 2026-09-25 (thresholds 0.85 / 0.20 / 0.30 / 0.5; benign controls 72) and
> appended here BEFORE any Part 1 trial. The verdicts are computed mechanically by
> `harness/prereg_part1.py` (tested before the run: `tests/test_prereg_part1.py`). **The design is FROZEN
> from this point:** anything found after lock goes into LIMITATIONS, not a fix cycle, unless it would
> make a result wrong. Tooling bugs that could load wrong data are still fixed. Draft history:
> `docs/PREREG_STAGE4_PART1_DRAFT.md` (superseded by this section).

### Design (fixed before running)

- **Models (unchanged from H8, so operator generality is not confounded with a model change):**
  `claude-haiku-4-5-20251001` (a dated snapshot; no thinking; temperature 1.0) and `gpt-5.6-luna`
  (effort fixed at medium; the model is an ALIAS, not a pinned snapshot — no dated Luna id exists, so
  provenance rests on the API-reported model string recorded per call; LIMITATIONS L26).
- **Cases:** the certified **200-case** design — build-and-certify run **36177356265**, built on the
  reference platform (AMD EPYC 7763; bundle `build_cpu_vendor=AuthenticAMD`; DECISIONS 2026-09-25
  "ENFORCING … native AMD EPYC"); its original 152 cases reproduce the earlier AMD certify runs
  35947111127 (EPYC 7763), 36057507382 (EPYC 9V74) and 36136154151 exactly on all 152 margin-table rows;
  restored locally (`make restore-cases RUN_ID=36177356265`): 200/200 pass all 23 checks, every hidden
  card `build_cpu: AuthenticAMD`. **108 faulty** = 6 operators (`silent.lr_warmup.v1`,
  `silent.label_corruption.v1`, `silent.data_leakage.v1`, `silent.data_leakage_neutral.v1`,
  `silent.metric_inflation.v1`, `crash.shape_mismatch.v1`) × 3 strengths × 6 confirmatory seeds
  (42–47); **20 healthy controls** (seeds 50–69); **72 benign-configuration controls** (6 types × 12;
  seeds 70–93 ∪ 110–157, paired to types block by block; case_0129–0200).
- **Arms:** prompt v2 — `off` / `stats` / `rule` (arm identity includes the prompt version; v1 and v2
  arms are never pooled). **Only `off` is comparable across H8 and Part 1, and only approximately**:
  agents now see four extra inert lines in `train.py` (the `grad_clip_norm` path).
- **Agents:** ReAct and static. Faulty cases: both agents × 3 arms × 2 providers × 2 repeats. Controls
  (healthy + benign): static only × 3 arms × 2 providers × 1 repeat (the reduced control protocol).
- **Cells:** 108 × 3 × 2 × 2 × 2 = **2,592 faulty** + 92 × 3 × 2 = **552 control** = **3,144
  confirmatory**, + **72 exploratory** (the no-passback arm below) = **3,216** scheduled. Plan command:
  `python -m harness.sweep plan --name <part1> --seeds 42 43 44 45 46 47 --control-seeds 50 … 69
  --benign-seeds 70 … 93 110 … 157 --repeats 2 --providers anthropic:claude-haiku-4-5-20251001
  openai:gpt-5.6-luna --exploratory-no-passback gpt-5.6-luna` (the planner schedules the benign
  controls — `tests/test_part1_planner.py::test_part1_plan_schedules_all_72_benign_controls`).
- **Protocol changes vs H8, all declared:** prompt caching on Anthropic ReAct cells (transport-only;
  billed and uncached-equivalent cost both reported); reasoning preserved across tool calls on both
  providers (H8's Luna ReAct discarded it — LIMITATIONS L32 — so **Part 1 Luna ReAct is not comparable
  with H8's**; Luna static and all Haiku cells are unaffected); a submit is always accepted, with
  compliance recorded separately (missing fields scored empty).
- **Evidence scorer: v2.2** (fixed before the plan is generated; DECISIONS 2026-09-25, FINDINGS
  correction #7): v2.1's one-to-one matching plus each faulty operator's **code-path evidence set** —
  its config keys + the workload code that implements its fault (the first read of its own key and
  the block that read gates; its mechanism function), declared in the operator's own module
  (`CODE_PATH`) and resolved with `ast` against each case's workspace. Derived from the implementation
  for every operator, never from observed citations
  (`tests/test_evidence_code.py::test_code_path_is_derived_from_the_implementation`). Code is credited
  as `code_span` only (a `line_range` citation of code is not); a cited span must overlap a
  ground-truth span at IoU ≥ 0.5 and be ≤ 3× its width. Detection and identification do not depend on
  the evidence scorer.
- **Cost estimate:** from H8's measured per-trial costs (Haiku static ≈ $0.014, Haiku ReAct with caching
  ≈ $0.040 [H8 simulation], Luna static ≈ $0.003, Luna ReAct ≈ $0.004 before the reasoning replay, which
  adds replayed reasoning to Luna's input): ≈ **$43.5** confirmatory (≈ $41 + ≈ $2.5 for the 48 added benign cases at 6 static trials ≈ $0.051
  per case) + ≈ **$0.3** exploratory (72 Luna
  ReAct trials in H8's own condition; budgeted ≤ $1); cap **$60** (`--max-cost-usd`), with the agents
  phase's cost cap, circuit breaker, cache check and reasoning check active.

### Analysis fixed in code BEFORE the run

Every confirmatory verdict below is computed mechanically by `harness/prereg_part1.py` (thresholds are
module constants that match this document) and rendered in the generated report's "Pre-registered
verdicts" section. It is tested on synthetic data before any Part 1 trial — for each hypothesis a
dataset that must CONFIRM, one that must REFUTE, and the named edge cases (lr_warmup at Haiku's ceiling
→ "no headroom — untestable"; fewer than two decision-carrying operators → INCONCLUSIVE; a Δ interval
that merely includes 0 → INCONCLUSIVE; a near-0.5 f → INCONCLUSIVE; an unadjusted p < 0.05 that fails
Holm → INCONCLUSIVE) — and the paired interval is checked against Newcombe's published Table III
(`tests/test_prereg_part1.py`).

### Pre-run gates (all must pass before the full run)

1. Sweep preconditions: `validate-all` green on the 200 cases.
2. A slice (`run --phase agents --max-trials N`, ≥ 5 Anthropic ReAct and ≥ 5 Luna ReAct multi-call
   trials): `python -m harness.sweep check-cache --name <part1>` → `passed`, and
   `python -m harness.sweep check-reasoning --name <part1>` → `passed` (prior Luna reasoning replayed on
   every later call and recurring after the first tool call). The agents phase also stops by itself if
   either check fails mid-run. The exploratory no-passback cells are exempt from the reasoning check
   (they drop reasoning by design; `tests/test_part1_planner.py::test_reasoning_check_exempts_only_the_no_passback_arm`)
   and do not count toward its ≥ 5 trials.

### H9 — Model dependence generalizes beyond leakage (CONFIRMATORY)

**Hypothesis.** The off-anchor detection gap between the two models found on leakage in H8 (Luna 0.82
vs Haiku 0.08 — FINDINGS F14) is a property of diagnosing non-crash faults, not of leakage.

**Estimand.** For each operator in scope, Δ_op = detection(Luna, `off`) − detection(Haiku, `off`),
pooled over agents, strengths and repeats; case-clustered 95% CI (case-level bootstrap, 10k resamples;
both models ran every case, so the resampling is paired by case). **In scope: every NON-CRASH
operator** — lr_warmup and label_corruption (silent / dynamics layer), **metric_inflation (metric
layer — in scope although it is not a silent-layer operator)**, and leakage (`data_leakage` +
`data_leakage_neutral`, pooled, as the within-Part-1 replication of F14). The three **non-leakage**
operators are the candidates to carry the decision. **Excluded:** shape_mismatch — a crash, detected
from the exit code by both models (stated in advance; it cannot carry a model gap).

**Headroom rule (decided before the run).** A non-leakage operator **carries the H9 decision only if
Haiku's off-anchor detection has a 95% upper bound below 0.85** in Part 1 (case-clustered
bootstrap upper bound; the exact Clopper–Pearson bound over cases if Haiku's rate is 0 or 1).
Otherwise it is reported as **"no headroom — untestable"**, never as confirming or refuting — Luna
cannot exceed a near-ceiling Haiku by a testable margin. **lr_warmup is expected to fail the rule**:
Haiku detected it 0.94 off-anchor in Sweep 1. The rule reads **Haiku's data only**, so it cannot
select operators on the size of the gap it is about to test. **At least 2 decision-carrying non-leakage
operators are required**; with fewer, H9 is **INCONCLUSIVE**.

- **CONFIRMING:** Δ_op's lower bound > 0 on **every** decision-carrying operator → model
  dependence is a property of diagnosis; proceed to Part 2 at full scope.
- **REFUTING:** the gap is shown SMALL, not merely non-significant — Δ_op's upper bound
  **< 0.20** on **every** decision-carrying operator, **while leakage's Δ lower bound is
  > 0** (the H8 gap replicates on the same models and run) → the finding is leakage-specific; the
  paper's claim narrows; Part 2 reduced to leakage.
- **INCONCLUSIVE:** everything else — including any Δ interval that merely includes 0 without an
  upper bound below 0.20; reported per operator, no side picked.
- **Multiplicity:** none needed. Both rules are intersection–union tests: every decision-carrying
  operator must pass individually at 95%, which is conservative for the joint claim. No pooling
  across operators.
- **Power note:** 18 case clusters per operator × model; H8's simulation at 18 clusters gives a 95% CI
  half-width ≈ 0.15, so gaps below ≈ 0.25 may land inconclusive, and a REFUTING verdict needs the true
  gap near 0 (an upper bound < 0.20 with half-width ≈ 0.15 needs Δ ≲ 0.05).

### H10 — Bare statistics close most of the off→rule detection gap, per model (CONFIRMATORY)

*(Replaces the earlier symptom-type ordering, which lr_warmup's ceiling would have driven rather than
symptom type — label_corruption and metric_inflation both start at 0.25 off-anchor in the Stage 2 gate.
The ordering moves to Secondary, below.)*

**Hypothesis.** Showing only the reference statistics (`stats`: mean, SD, n — no evaluative words)
recovers most of the detection that the full `rule` arm (statistics + "values more than 2 SD from this
mean are anomalous") recovers. In H8 the normative v1 `numbers` arm (whose wording was evaluative)
closed ≈ 0.95 of the off→rule gap — 0.987 on `data_leakage` and 0.939 on `data_leakage_neutral`, pooled
over providers (`docs/audits/sweep_h8_xprovider_generated.md`); H10 tests whether that holds **without evaluative words**.

**Estimand.** Per model, f = (detect(`stats`) − detect(`off`)) / (detect(`rule`) − detect(`off`)),
detection pooled over the **eligible operators** — faulty operators whose own rule − off detection gap
for that model is **≥ 0.30** (fixed from the full-sample point estimates; no gap, nothing to close) —
and over agents, strengths and repeats. f̂ is f on the full sample. A model with no eligible operator
is **UNTESTABLE**.

**Decision rule — exactly as `harness/prereg_part1.py::h10_verdict` computes it:**

1. *Bootstrap.* Take the eligible trials of the model and the sorted list of their case IDs (n cases).
   For each of **B₀ = 10,000** resamples, draw n case IDs with replacement
   (`random.Random(20260913).choice`, one generator per model, in resample order) and compute f on all
   trials of the drawn cases. A resample in which an arm has no trials or rule − off = 0 is dropped;
   **B** = the number kept (reported).
2. *Two-sided bootstrap p-value for f = 0.5.* With L = the number of kept resamples with f* < 0.5
   (f* = 0.5 counts in the upper tail): **p = min(1, 2 · min(L, B − L) / B)**.
3. *Holm over the models tested* (m = 2, or 1 if one model is UNTESTABLE; α = 0.05). Sort the models by
   p ascending (ties by provider name); the i-th smallest (i = 1 … m) is rejected if p ≤ α / (m − i + 1)
   and every smaller one was rejected; testing stops at the first non-rejection.
4. *Verdict.* **CONFIRMING** — rejected and f̂ > 0.5. **REFUTING** — rejected and f̂ < 0.5.
   **INCONCLUSIVE** — not rejected (or f̂ = 0.5 exactly).
5. *Reported, not deciding:* the 95% percentile interval of the kept f* (the ⌊0.025·B⌋-th and
   (⌊0.975·B⌋ − 1)-th order statistics, 0-indexed), beside the verdict.

- **Multiplicity:** Holm over the two models (step 3). A test that the rule stated here and the code
  agree on synthetic confirm / refute / inconclusive / Holm-boundary data:
  `tests/test_prereg_part1.py::test_h10_document_rule_matches_code`.

### Benign-configuration controls — does anchoring change benign false positives? (CONFIRMATORY, two-sided)

**Hypothesis (two-sided; both mechanisms stated).** Showing the agent a reference band changes how
often it flags a legitimate, benign configuration change as a fault, relative to no reference (`off`).
Two mechanisms pull in opposite directions: an **in-band reference may REASSURE** (the visible metric is
inside the healthy range, so the agent is less likely to call a benign change a fault — fewer false
positives); and the `rule` arm's **"anomalous" sentence may PRIME flagging** — in H8, 3 of the rule
arm's 4 control false positives were on IN-BAND controls (FINDINGS; HYPOTHESES H8 results), which the
reassurance account does not predict. The claim is therefore **two-sided: increase or decrease**.

**Estimand (paired arm contrast; no level threshold).** On the **72 benign cases**, per provider and
for each anchored arm: Δ_arm = FPR(arm) − FPR(`off`), arm ∈ {`stats`, `rule`}, where a false positive is
`detection.correct = false` on a benign case (the agent reports a fault). Under the reduced control
protocol every benign case contributes exactly one static trial per arm per provider, so the contrast is
**paired by case** — **72 clusters, one pair each**. Δ = (b − c) / 72, where b = cases flagged under the
anchored arm but not under `off`, c = the reverse. **Four confirmatory contrasts:** {Anthropic, OpenAI}
× {`stats` − `off`, `rule` − `off`}.

- **CI method:** Newcombe's score-based interval for a paired difference of proportions (Newcombe 1998,
  method 10 — Wilson limits for each marginal, continuity-corrected φ), two-sided 95%; it reproduces
  the paper's Table III (`tests/test_prereg_part1.py::test_newcombe_method10_matches_published_table`)
  and stays valid at the 0–2 discordant-pair counts expected here, where the percentile bootstrap is not
  (LIMITATIONS L30). The exact two-sided McNemar p on (b, c) is reported beside it. No resampling.
- **Decision rule, per contrast:** **INCREASE** if the exact McNemar test rejects under
  Holm and b > c; **DECREASE** if it rejects and b < c; otherwise **INCONCLUSIVE**. Per provider:
  INCREASE or DECREASE if any of its two contrasts is; **MIXED** if one of each. The Newcombe
  interval is reported beside every contrast; where it and the Holm-adjusted test disagree (e.g. b = 5,
  c = 0: interval excludes 0, p = 0.0625), **the test decides**.
- **Multiplicity:** **Holm over the four contrasts** (exact two-sided McNemar p, family-wise α = 0.05).
- **Power (why 72).** A lone effect must clear α/4 = 0.0125 under Holm: with no reverse discordance
  (c = 0) that takes **b ≥ 8** (p = 0.0078); at the last Holm step (α), b ≥ 6. Simulated (20,000 runs;
  exact two-sided McNemar per contrast, Holm over the four; `off` FPR 0.05 — H8's healthy-control `off`
  FPR was 1/40 = 0.025 pooled, i.e. 0 or 0.05 per provider; each arm's flags independent per case):

  | benign cases | anchored FPR | power, one contrast elevated | power, all four elevated | P(≥ 1 INCREASE for that provider), all four elevated |
  |---|---|---|---|---|
  | 24 | 0.20 / 0.30 / 0.40 | 0.04 / 0.22 / 0.54 | 0.04 / 0.28 / 0.66 | 0.07 / 0.41 / 0.79 |
  | 48 | 0.20 / 0.30 / 0.40 | 0.27 / 0.71 / 0.95 | 0.33 / 0.83 / 0.99 | 0.45 / 0.91 / 1.00 |
  | **72 (adopted)** | 0.20 / 0.30 / 0.40 | **0.50 / 0.93 / 1.00** | **0.61 / 0.97 / 1.00** | **0.73 / 0.99 / 1.00** |

  At 72 cases a DECREASE from an `off` FPR of 0.30 to 0.05 is detected with power ≈ 0.93 (from 0.20:
  ≈ 0.49); from an `off` FPR near 0.05 there is no room to fall. INCONCLUSIVE remains the expected
  outcome for effects below ≈ 0.20 and is not evidence of no effect. The expansion from 24 to 72 cases
  was decided from this table before any Part 1 trial (DECISIONS 2026-09-25).
- **Descriptive (not tested):** the pooled benign FPR per arm × provider over the 72 cases with an
  **exact Clopper–Pearson** interval (clustered: one trial per case per arm × provider, so n = 72),
  reported beside the healthy-control FPR (20 cases) and the benign − healthy difference.
- **EXPLORATORY (with cluster counts):** per-type rates (6 types × **12 cases** each); the edit-form split
  — new key: **12 cases, one knob** (`training.grad_clip_norm`, non-binding: byte-identical to a clean run
  except one config line); changed value: 60 cases, 5 knobs.
- **Qualification facts (recorded before the run):** all six types qualified on development seeds; the
  learning-rate change is "**equivalent within the declared margin, with a small detectable decrease**"
  (−0.460 σ_ref, 90% CI [−0.907, −0.012] σ_ref). Visible band position of the 72 cases actually built
  (run 36177356265, AMD): **68 inside, 2 below, 2 above** — original 24: 23 inside, 1 below (case_0144,
  dropout, −2.70σ; ep25 case_0136 inside at +1.99σ); new 48: 45 inside, 1 below (case_0190, dropout,
  −2.37σ), 2 above (case_0160, ep25, +2.06σ; case_0165, dropout, +2.53σ). Per type below/inside/above:
  bs128 0/12/0, ep25 0/11/1, wd5e4 0/12/0, do01 2/9/1, lr005 0/12/0, clip1 0/12/0.
- **Comparators:** B2 and the form-only comparator `bform` on every benign case; B2+ ("config-diff with
  perfect knob semantics") as an upper bound — its fallback rate on the benign knobs and its benign FPR.

### Secondary (pre-registered, descriptive)

- **Band benefit by symptom type (the former H10 ordering; no verdict):** per model × operator × arm,
  the raw benefit B = detect(arm) − detect(`off`) and the **headroom-normalised** benefit
  B / (1 − detect(`off`)), grouped by symptom direction (positive: leakage ×2, metric_inflation;
  negative: lr_warmup, label_corruption; crash: shape_mismatch). Computed mechanically
  (`band_benefit_descriptive`); interpreted with the ceilings stated, never as a test.

- Detection, identification, evidence F1 and recovery per operator × arm × agent × provider
  (case-clustered CIs); identification per operator with the `root_token_v2` matcher.
- **Evidence F1 under v2.2** (the code path is an accepted set; see Design). Disclosed limits, fixed
  before the run: partial spans below the 0.5 overlap and `line_range` citations of code stay
  uncredited. H8's evidence numbers are compared only as rescored under v2.2 (correction #7).
- **Multiplicity for all secondary and exploratory outputs:** none applied; every interval is a
  per-comparison 95% interval, reported as descriptive, and no secondary result is promoted to a claim.
- ReAct − static evidence F1 per provider (no H8 comparison for Luna ReAct — see the exploratory arm).
- Submit compliance (missing / ignored fields) per provider, reported separately from diagnosis.
- Luna reasoning tokens per call; Haiku ReAct cache-read share; billed and uncached-equivalent cost.
- **Post-run second audit (~30 items):** stratified across lr, label-corruption, metric-inflation and
  shape-mismatch faults and the benign controls, same rubric and declared mapping; optionally a second
  annotator on a 20-item overlap (LIMITATIONS L33).

### EXPLORATORY — Luna ReAct with reasoning pass-back OFF (quantifies H8's defect only)

**Purpose — it exists only for this:** to measure directly the handicap H8's adapter defect imposed on
Luna ReAct (LIMITATIONS L32: prior reasoning was dropped between tool calls). **Not confirmatory**, not
part of H9 / H10 / the benign contrast, and **never pooled** with any scheduled arm: its records carry
`conditions.reasoning_passback = false`, form their own cells in the analysis, and are excluded from
every primary table (`tests/test_part1_planner.py::test_exploratory_twin_is_a_separate_cell_and_never_pooled`).

- **Cells:** the 36 leakage cases (`data_leakage` + `data_leakage_neutral`, 3 strengths × 6 seeds) ×
  `off` × ReAct × `gpt-5.6-luna` × 2 repeats = **72**, at the same medium effort, with reasoning items
  removed from each assistant turn before the next request (H8's condition; the API call is otherwise
  identical to Part 1's, and the model's context matches H8's). Cost ≈ $0.3 at H8's measured Luna ReAct cost; budgeted ≤ $1.
- **Estimand (descriptive):** pass-back ON (the Part 1 twin cells) − OFF for detection,
  identification and evidence F1 (v2.2), paired by case, case-clustered bootstrap 95% CI (36 clusters).
  Reported in the generated report's own EXPLORATORY section. It bounds how much of H8's Luna ReAct
  evidence (and the ReAct − static reversal) the defect explains; it re-scores nothing in H8.

### Pre-lock tooling items (all closed at lock)

- ~~The sweep planner does not yet schedule the benign controls.~~ **Closed** (2026-09-25):
  `--benign-seeds 70 … 93 110 … 157` schedules the 72 benign cases static-only under the reduced control protocol,
  with the type ↔ seed pairing taken from the case builder's own function (`benign_design`).
- ~~Analysis tooling.~~ **Closed** (2026-09-25): H9 (with the headroom rule), H10 and the benign
  contrast output their verdicts mechanically (`harness/prereg_part1.py`; see "Analysis fixed in code
  BEFORE the run").
- ~~B2+ report over the certified benign cases.~~ **Closed** (2026-09-25): from the certified run
  36177356265, committed as `docs/audits/b2plus_report_part1_200.md` (the 24-case version from run
  36136154151 is kept as `docs/audits/b2plus_report_20260925.md`). B2+ flags **72/72 benign cases**
  (benign FPR 1.00; fallback to a bare leaf name 60/72, an answer-key fault concept 12/72 — every
  learning-rate change named `lr_warmup`) and 0/20 healthy controls.
