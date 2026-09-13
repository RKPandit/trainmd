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

**Axes / hypotheses this TOUCHES:** identification only → **H3** (doing/understanding gap: the
recovery−identification comparison) and **H4** (repeat agreement on identification). Shape
recovery re-verify touches the shape operator's recovery only.

**Axes / hypotheses this DOES NOT touch:** detection, evidence, and recovery on non-shape
operators are unchanged → **H1** (positive-symptom blindness), **H6** (tools vs static),
**controls** (detection FPR / false-intervention), and **H2** (detection vs σ) are all
**unchanged**. H2's numbers do not move.

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

_(Per-hypothesis H1–H6 results table to follow — filled with the dated sweep numbers.)_
