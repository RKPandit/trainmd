# Stage 4 Part 2 — pre-registration (DRAFT — SUPERSEDED: locked 2026-09-28 in `docs/HYPOTHESES.md`, "Stage 4 Part 2 — PRE-REGISTRATION")

> Drafted 2026-09-28 for review together with #75. On approval it is appended to `docs/HYPOTHESES.md` BEFORE
> any Part 2 trial, as Part 1 was, and the design is then FROZEN (anything found after lock goes to
> LIMITATIONS, not a fix cycle, unless it would make a result wrong). Every confirmatory verdict below will be
> computed mechanically by `harness/prereg_part2.py`, tested on synthetic confirm / refute-by-opposite /
> refute-by-small / inconclusive / untestable / Holm-boundary data BEFORE lock (`tests/test_prereg_part2.py`).

## Carried-forward declarations

- **OpenAI tool schemas are strict in every Part 2 cell** (`strict: true`; schemas strict-compatible) —
  decided 2026-09-27 (`docs/STAGE4_PLAN.md`, Part 2 DECISION).
- **Part 1's GPT-5.6 Luna numbers are affected by argument degeneration (LIMITATIONS L35) — an OBSERVED
  basis, not a missing flag:** recomputed per trial from the transcripts, 90 Part 1 OpenAI submit calls were
  unparseable, every one ending at the output cap (76 static, 14 ReAct), against 0 for Haiku; the tools sent
  were the canonical open schema (code at the recorded commit; Part 1 records predate the per-trial
  `tool_config` block). Luna's submit arguments degenerated in a measurable share of
  trials (runaway whitespace to truncation; garbled keys that swallowed evidence and repair), so its
  end-to-end detection, identification, evidence F1 and recovery under-state its diagnoses
  (`docs/audits/stage4_part1_followup.md`). Therefore **GPT-5.6 Luna medium is RE-RUN in Part 2** under
  strict schemas, and **no Part 2 estimate or contrast uses, reuses or pools Part 1 Luna trials.**
  (Haiku 4.5 reuse from Part 1 is unaffected.)

- **The pilot is excluded from every analysis and is never scored.** The Part 2 pilot
  (`sweeps/stage4_part2_pilot_plan.yaml`: 10 static + 3 ReAct cells per new condition, seed 20260927) runs
  with scoring switched off (`run_trial(score=False)`); its only output is `pilot-report` — cost, token
  volume including thinking / reasoning tokens, reasoning presence past the first tool call, and
  structured-output / strict-mode compliance. No detection, identification, evidence or recovery value is
  computed or shown, so the pilot cannot inform any threshold of this pre-registration. Its trials carry
  `conditions.pilot = true`; the analysis loaders drop them, and `report` / `run_verify` refuse a pilot sweep.

- **Conditions (7; author's decision 2026-09-27, after the pilot):** Haiku 4.5 (reused from Part 1), Sonnet 5
  thinking off, Sonnet 5 thinking on (effort fixed from thinking VOLUME only — `docs/STAGE4_PLAN.md` Part 2,
  item A), GPT-5.6 Luna medium (re-run, strict), GPT-5.6 Luna none, GPT-6 Luna medium, GPT-6 Sol medium.
  Opus 5.5 is dropped.
- **Wording.** Contrasts are **model comparisons** (Haiku 4.5 vs Sonnet 5 off; GPT-6 Luna vs Sol; GPT-5.6 vs
  GPT-6 Luna; Sonnet 5 on vs GPT-6 Sol at matched list price) or **within-model reasoning interventions**
  (Sonnet 5 off vs on; GPT-5.6 Luna none vs medium). No result is described as isolating capability. ReAct vs
  static compares complete agent configurations.
- **Primary endpoints are end-to-end;** validity is reported separately. Every trial counts: an empty or
  unparseable diagnosis is a miss on a faulty case and never a false alarm on a control. Per condition, the
  valid-submission rate and the recorded completion status (record schema 1.3: `tool_config`, per-call
  provider `completion`, per-trial `completion`) are reported beside the primary numbers; the valid-only view
  is descriptive.
- **Faulty cases are reported by distinct fault mechanism.** Pooled faulty-case estimates are the unweighted
  mean over the five mechanisms (`harness.sweep_stats.MECHANISM`); the two leakage variants are one mechanism.
- **Baselines on the same cases.** The "what does the agent add?" table (B0/B1/B2/B3/BF vs every agent row:
  detection, false alarms — healthy and benign separately — identification, cost) is reported for Part 2 as
  for Part 1 (`scripts/agent_value_table.py`). **B1 is the FINAL-EPOCH band detector** (declared 2026-09-27:
  the band describes final accuracy); the every-epoch variant appears only in an appendix.
- **Scorer frozen before the first trial;** Part 2's post-run human audit is the fresh validation of the
  frozen scorer (findings go to LIMITATIONS unless a result would be wrong).

## Sonnet 5 "thinking on" level — fixed by the thinking-VOLUME probe (2026-09-28)

**xhigh, by the pre-declared fallback.** The rule (STAGE4_PLAN Part 2, item A; declared before the probe ran):
the lowest of {high, xhigh} with thinking blocks in ≥ 9/10 static trials AND median estimated thinking ≥ 4×
medium's; otherwise xhigh, with the measured contrast stated. Probe `sweeps/stage4_part2_probe_plan.yaml`: 20
static cells on exactly the 10 slots the pilot ran for Sonnet 5 medium, `max_tokens` 32,768, NO scores
(`conditions.pilot`), $0.64. Result (`scripts/thinking_volume.py`, `sweeps/stage4_part2_probe_thinking_volume.md`;
thinking volume = output tokens − 0.515 × visible characters, the rate calibrated on thinking-disabled calls):

| Sonnet 5 level | trials with thinking | output tok / trial | est. thinking / call (median, mean) | truncations | $ / static trial |
|---|---|---|---|---|---|
| off | 0/10 | 448 | ≈ 0 | 0 | 0.0270 |
| medium | 8/10 | 531 | 241, 217 | 0 | 0.0278 |
| high | 10/10 | 726 | 343, 394 | 0 | 0.0298 |
| **xhigh** | **10/10** | **1,173** | **734, 780** | 0 | **0.0343** |

Neither high (343 = 1.4×) nor xhigh (734 = 3.0×) reached 4× medium's 241, so **xhigh** by the fallback.
**Measured contrast for H12 (off vs xhigh):** thinking in 0/10 vs 10/10 trials; ≈ 0 vs ≈ 734 estimated thinking
tokens per call (median); 448 vs 1,173 output tokens per trial. The estimate is ±≈ 100 tokens (calibration
noise); Anthropic reports no thinking-token count.

## Design (proposed)

- **Cases:** the same certified 200 (build-and-certify run 36177356265, AMD EPYC): 108 faulty (6 operators ×
  3 strengths × seeds 42–47), 20 healthy controls, 72 benign-configuration controls. Arms: prompt v2 `off` /
  `stats` / `rule`.
- **Conditions and request settings** (streamed on Anthropic; strict tool schemas on every OpenAI cell):

  | Condition | Settings | `max_tokens` |
  |---|---|---|
  | Haiku 4.5 | REUSED from Part 1 (same cases, prompt, arms and repeats; re-scored under the frozen scorer, correction #9) | — |
  | Sonnet 5, thinking off | `thinking: disabled` | 32,768 |
  | Sonnet 5, thinking xhigh | `effort: xhigh` (adaptive thinking) | 32,768 |
  | GPT-5.6 Luna, medium | `reasoning.effort: medium`, strict — RE-RUN (not Part 1's) | 8,192 |
  | GPT-5.6 Luna, none | `reasoning.effort: none`, strict | 8,192 |
  | GPT-6 Luna, medium | strict | 8,192 |
  | GPT-6 Sol, medium | strict | 8,192 |

  Within each confirmatory pair the cap is equal, so the pair differs only in the reasoning setting (Sonnet
  off uses ≈ 450 output tokens; its cap never binds).
- **Stage A — static (confirmatory + descriptive): every new condition × the Part 1 static protocol:** faulty
  108 × 3 arms × 2 repeats + controls 92 × 3 arms × 1 = **924 static trials per condition, 5,544 total.**
- **Stage B — ReAct (descriptive only), CONDITIONAL (author, 2026-09-28):** `off` arm × 108 faulty × 1 repeat
  for the four reasoning-intervention conditions = 432 trials. After Stage A, a small Stage B slice runs first
  (Sonnet xhigh ReAct cost is unmeasured) and its cost is projected; Stage B proceeds only if Stage A's ACTUAL
  spend plus that projection fits the $100 cap.
- **Projected cost** (the pilot's / probe's measured $ per static trial; Stage B's Sonnet xhigh ReAct
  figure is an ASSUMPTION — off's ReAct cost × xhigh/off static ratio):

  | Condition | $ / static | Stage A (924) | $ / ReAct | Stage B (108) |
  |---|---|---|---|---|
  | Sonnet 5 off | 0.0270 | 24.95 | 0.0477 | 5.15 |
  | Sonnet 5 xhigh | 0.0343 | 31.69 | ≈ 0.0606 (assumed) | 6.54 |
  | GPT-5.6 Luna medium | 0.00225 | 2.08 | 0.0041 | 0.44 |
  | GPT-5.6 Luna none | 0.0021 | 1.94 | 0.0054 | 0.58 |
  | GPT-6 Luna medium | 0.00115 | 1.06 | — | — |
  | GPT-6 Sol medium | 0.0207 | 19.13 | — | — |
  | **Total** | | **≈ $80.9** | | **≈ $12.7** |

  **Cap $100** (`--max-cost-usd 100`) over A + B. **Operational rule (as Part 1):** after a Stage A slice,
  `scripts/project_sweep_cost.py --cap 100` projects Stage A from its own measured costs; Stage A runs in full
  only if it FITS. Stage B: a slice, then `scripts/project_sweep_cost.py --name <stage B> --cap <100 − Stage A
  actual>`; the rest of Stage B runs only if it fits — otherwise the author decides before any further spend.
- **Pre-run gates:** `validate-all` green; the scorer freeze unchanged (`python -m harness.scorer_freeze`); a
  slice with Sonnet xhigh and both Luna conditions confirming streaming (no SDK refusal), strict parsing and
  completion status recorded; `check-cache` / `check-reasoning` on Stage B's multi-call cells (Stage A is
  single-call static, where they do not apply).
- **Excluded from every analysis:** the pilot and the probe (`conditions.pilot`; the loaders drop them).

## Confirmatory — two within-model reasoning interventions

**Primary measure (both):** off-anchor detection, END-TO-END (an empty or unparseable diagnosis is a miss),
static agent, NON-CRASH faulty cases (shape_mismatch excluded in advance: a crash is detected from the exit
code), aggregated by MECHANISM — D = the unweighted mean over the eligible mechanisms (below) of each
mechanism's detection rate, pooled over strengths and repeats; the two leakage variants are ONE mechanism
(`harness.sweep_stats.MECHANISM`). Candidate mechanisms: data_leakage (36 cases), label_corruption (18),
lr_warmup (18), metric_inflation (18) — **90 case clusters, 180 trials per condition.**

**Estimand:** Δ = D(more reasoning) − D(less reasoning), on the same cases (paired by case).

- **H11 — GPT-5.6 Luna, reasoning none vs medium (both strict).** *Declared direction:* removing reasoning
  LOWERS off-anchor detection: Δ₁₁ = D(medium) − D(none) > 0.
- **H12 — Sonnet 5, thinking off vs xhigh.** *Declared direction:* thinking RAISES off-anchor detection:
  Δ₁₂ = D(xhigh) − D(off) > 0.

**Headroom rule (decided before the run; like H9's).** A mechanism carries a hypothesis's decision only if the
LESS-reasoning condition's off-anchor detection on it has a 95% upper bound **below 0.85** (case-clustered
bootstrap; the exact Clopper–Pearson bound over cases at a rate of 0 or 1). It reads only the less-reasoning
condition's data, so it cannot select mechanisms on the size of the effect under test. **At least 2 eligible
mechanisms are required**; with fewer, the hypothesis is **"no headroom — untestable"** and leaves the Holm
family. D is computed over the eligible mechanisms only; the all-mechanism table is reported beside it.
**Stated in advance: H11 may well be UNTESTABLE.** GPT-5.6 Luna detected most non-crash faults off-anchor in
Part 1 at medium effort (static: leakage 0.94, lr_warmup 0.86, metric_inflation 0.78, label_corruption 0.69);
if reasoning `none` leaves Luna near that level, fewer than two mechanisms will clear the 0.85 upper bound and
H11 is reported as "no headroom — untestable" — an honest outcome, not a failure of the design.

**Decision rule (two-sided).**
1. *Bootstrap:* 10,000 case-level resamples, **stratified by mechanism** (the eligible mechanisms' case IDs
   resampled within mechanism, with replacement; one seeded generator per hypothesis), Δ* computed on all
   static `off` trials of the drawn cases in both conditions (paired).
2. *Two-sided p for Δ = 0:* with L = #{Δ* < 0}, U = #{Δ* > 0} and T = #{Δ* = 0},
   **p = min(1, 2·min(L + T/2, U + T/2)/B)** — ties count half to each tail (paired detection differences are
   discrete, so exact ties are common; counting them in one tail, as H10's continuous f could, would turn an
   all-tie bootstrap — no change at all — into p = 0).
3. *Holm over the testable hypotheses* (m = 2, or 1; family-wise α = 0.05): the smaller p is rejected if
   p ≤ α/m; the other if p ≤ α and the first was rejected.
4. *Verdict:*
   - **CONFIRMING** — rejected and Δ̂ > 0 (the declared direction).
   - **REFUTING (opposite direction)** — rejected and Δ̂ < 0.
   - **REFUTING (shown small)** — not rejected, and the 95% percentile interval of Δ* lies inside
     **(−0.15, +0.15)**, worded as: **"no change larger than 0.15 — small against the 0.50–0.83 Haiku–Luna gap it
     is meant to explain"** — never as "no effect".
   - **INCONCLUSIVE** — everything else (including an interval that merely includes 0 but crosses ±0.15).
5. *Reported, not deciding:* Δ̂ with its 95% interval, the per-mechanism Δ (all four, eligible or not), the
   ReAct `off` contrast (Stage B), and the same contrasts under `stats` / `rule`.

**Power note** (from Part 1's static `off` data at this design: 180 trials, 90 clusters): the SE of one
condition's D is ≈ 0.029 for both Haiku (D 0.17) and Luna (D 0.82). Treating the paired conditions as
independent (conservative), SE(Δ) ≈ 0.041, a 95% half-width ≈ 0.08. The minimum detectable Δ at 80% power is
≈ 0.13 at Holm's first step (α/2) and ≈ 0.12 at its second; a true Δ = 0 is **shown small** (interval inside
±0.15) about 90% of the time, whereas a ±0.10 margin would succeed only about 37% of the time — hence ±0.15
(the H8 equivalence bound). If headroom drops a mechanism, D rests on fewer clusters and these widths grow by
up to ≈ 15–40%.

## Descriptive only — no verdicts

1. **Haiku 4.5 (Part 1) vs GPT-5.6 Luna medium (strict, Part 2)** — off-anchor detection per mechanism: the
   clean re-measurement of Part 1's central gap WITHOUT the formatting under-credit (L35). A **cross-run**
   comparison (Haiku from Part 1, Luna from Part 2 — same cases, prompt, arms, repeats and frozen scorer, but
   different runs and dates); intervals shown, no verdict.
2. **Model comparisons** (paired by case where both models ran it; CIs shown, no decision): Sonnet 5 off vs
   Haiku 4.5 (neither thinks; Haiku from Part 1); GPT-6 Luna vs GPT-5.6 Luna (both medium, strict); GPT-6 Sol
   vs GPT-6 Luna, and Sonnet 5 xhigh vs GPT-6 Sol (matched list price; the providers' effort scales do not
   correspond).
3. **Reference effects per model** — `stats` − `off` and `rule` − `off`, and an H10-style
   f = (stats − off)/(rule − off) over the model's eligible mechanisms (rule − off ≥ 0.30), wherever there is
   headroom; reported with intervals, no verdict.
4. **Benign false alarms** per condition × arm, healthy and benign separately (and by edit form), with paired
   arm contrasts (Newcombe) — no verdict.
5. **Submission validity** — the valid-submission rate, per-trial completion status and truncations (record
   schema 1.3) beside every end-to-end number; the valid-only view is descriptive.
6. Identification (frozen root_token_v3), evidence (frozen v2.3) and recovery (degenerate on these operators,
   L19), per condition and mechanism.
7. **What does the agent add?** — the baseline table (B0, final-epoch B1, B2, B3, BF) vs every Part 2 row on
   the same 200 cases (`scripts/agent_value_table.py`).
8. Cost per condition (billed and uncached-equivalent).

## Fixed from the first trial

- **Scorer FROZEN** — identification root_token_v3, evidence v2.3 (`harness/scorer_freeze.yaml`; the test fails
  on any drift). **Strict** OpenAI tool schemas on every OpenAI cell. **Streaming** on every Anthropic request.
  **Final-epoch B1** in the baseline table (every-epoch variant in an appendix only).
- **Post-run blind human audit** (Part 1's protocol and sheet format; items sampled across conditions and
  mechanisms) is the **fresh validation of the frozen scorer**. Its disagreements go to LIMITATIONS — the scorer
  is not changed after lock unless a result would be wrong.

## Before lock (remaining)

1. `harness/prereg_part2.py` (H11 / H12 exactly as above) + `tests/test_prereg_part2.py` on synthetic data.
2. Plan generation (committed plan, 0 missing cases) and the operational cost projection.
3. The author's approval of this draft (and of the ±0.15 margin, the 0.85 headroom bound and Stage B).

*Dependencies met:* the second human audit returned; the metric_inflation matcher decided and applied
(correction #9); the scorer frozen (#74); the Sonnet "on" level fixed (xhigh, above).
