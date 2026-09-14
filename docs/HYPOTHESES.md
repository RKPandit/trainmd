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

**Axes / hypotheses this DOES NOT touch:** detection and evidence are unchanged (a folded
`repair_spec` never affected the diagnosis axes) → **H1** (positive-symptom blindness), **H2**
(detection vs σ), **H6** (tools vs static, evidence_f1), and **controls** (detection FPR /
false-intervention — controls carry no repair to fold) are all **unchanged**. Recovery moves
(Corrections 2–3), which sharpens **H3** but does not alter the detection/evidence findings.

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
- **E.** **Controls FP framing:** a 2σ band has a structural ~5% out-of-band floor by
  construction; the 4 FPs are separated into band-edge misreads vs true out-of-band healthy runs.
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
