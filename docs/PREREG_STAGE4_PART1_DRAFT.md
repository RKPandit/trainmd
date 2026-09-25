# Stage 4 Part 1 — pre-registration (DRAFT for the author's review; NOT yet locked)

> Finalized 2026-09-25 from the "Declared in the Part 1 pre-registration" paragraphs of
> `docs/STAGE4_PLAN.md` Part 1, the v1 plan's H9/H10 wording, and H8's template; revised the same day
> with the author's decisions (benign contrast, evidence scorer v2.2, H9 scope, planner, exploratory
> arm). **Not a pre-registration until the author approves it**; on approval it is appended to
> `docs/HYPOTHESES.md` ("do not edit above this line"), dated on commit, before any Part 1 trial.
> Thresholds marked *(proposed)* are for the author's final review; no **[DECIDE]** items remain.

## Design (fixed before running)

- **Models (unchanged from H8, so operator generality is not confounded with a model change):**
  `claude-haiku-4-5-20251001` (no thinking; temperature 1.0) and `gpt-5.6-luna` (reasoning effort
  medium, pinned).
- **Cases:** the certified 152-case design (build-and-certify run 35947111127; restored locally from run
  36057507382, 152/152 pass all 23 checks): **108 faulty** = 6 operators (`silent.lr_warmup.v1`,
  `silent.label_corruption.v1`, `silent.data_leakage.v1`, `silent.data_leakage_neutral.v1`,
  `silent.metric_inflation.v1`, `crash.shape_mismatch.v1`) × 3 strengths × 6 confirmatory seeds
  (42–47); **20 healthy controls** (seeds 50–69); **24 benign-configuration controls** (6 types × 4,
  seeds 70–93).
- **Arms:** prompt v2 — `off` / `stats` / `rule` (arm identity includes the prompt version; v1 and v2
  arms are never pooled). **Only `off` is comparable across H8 and Part 1, and only approximately**:
  agents now see four extra inert lines in `train.py` (the `grad_clip_norm` path).
- **Agents:** ReAct and static. Faulty cases: both agents × 3 arms × 2 providers × 2 repeats. Controls
  (healthy + benign): static only × 3 arms × 2 providers × 1 repeat (the reduced control protocol).
- **Cells:** 108 × 3 × 2 × 2 × 2 = **2,592 faulty** + 44 × 3 × 2 = **264 control** = **2,856
  confirmatory**, + **72 exploratory** (the no-passback arm below) = **2,928** scheduled. Plan command:
  `python -m harness.sweep plan --name <part1> --seeds 42 43 44 45 46 47 --control-seeds 50 … 69
  --benign-seeds 70 … 93 --repeats 2 --providers anthropic:claude-haiku-4-5-20251001
  openai:gpt-5.6-luna --exploratory-no-passback gpt-5.6-luna` (the planner schedules the benign
  controls — `tests/test_part1_planner.py::test_part1_plan_schedules_all_24_benign_controls`).
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
  adds replayed reasoning to Luna's input): ≈ **$41** confirmatory + ≈ **$0.3** exploratory (72 Luna
  ReAct trials in H8's own condition; budgeted ≤ $1); cap **$60** (`--max-cost-usd`), with the agents
  phase's cost cap, circuit breaker, cache check and reasoning check active.

## Pre-run gates (all must pass before the full run)

1. Sweep preconditions: `validate-all` green on the 152 cases.
2. A slice (`run --phase agents --max-trials N`, ≥ 5 Anthropic ReAct and ≥ 5 Luna ReAct multi-call
   trials): `python -m harness.sweep check-cache --name <part1>` → `passed`, and
   `python -m harness.sweep check-reasoning --name <part1>` → `passed` (prior Luna reasoning replayed on
   every later call and recurring after the first tool call). The agents phase also stops by itself if
   either check fails mid-run. The exploratory no-passback cells are exempt from the reasoning check
   (they drop reasoning by design; `tests/test_part1_planner.py::test_reasoning_check_exempts_only_the_no_passback_arm`)
   and do not count toward its ≥ 5 trials.

## H9 — Model dependence generalizes beyond leakage (CONFIRMATORY)

**Hypothesis.** The off-anchor detection gap between the two models found on leakage in H8 (Luna 0.82
vs Haiku 0.08 — FINDINGS F14) is a property of diagnosing non-crash faults, not of leakage.

**Estimand.** For each operator in scope, Δ_op = detection(Luna, `off`) − detection(Haiku, `off`),
pooled over agents, strengths and repeats; case-clustered 95% CI (case-level bootstrap, 10k resamples;
exact Clopper–Pearson for any 0- or 100%-rate cell). **Operators in scope: every NON-CRASH operator** —
lr_warmup and label_corruption (silent / dynamics layer), **metric_inflation (metric layer — in scope
although it is not a silent-layer operator)**, data_leakage_neutral, and data_leakage (the
within-Part-1 replication of F14). The three **non-leakage** operators in scope — lr_warmup,
label_corruption, metric_inflation — carry the decision. **Excluded:** shape_mismatch — a crash,
detected from the exit code by both models (stated in advance; it cannot carry a model gap).

- **CONFIRMING (proposed):** Δ_op > 0 with the CI excluding 0 on **every** non-leakage operator in scope
  (lr_warmup, label_corruption, metric_inflation) → model dependence is a property of diagnosis;
  proceed to Part 2 at full scope.
- **REFUTING (proposed):** the CI includes 0 on **every** non-leakage operator in scope while leakage's
  excludes it → the finding is leakage-specific; the paper's claim narrows; Part 2 reduced to leakage.
- **INCONCLUSIVE:** any mixed pattern; reported per operator, no side picked.
- **Power note:** 18 case clusters per operator × model; H8's simulation at 18 clusters gives a 95% CI
  half-width ≈ 0.15, so gaps below ≈ 0.25 may land inconclusive. An operator that floors or ceilings for
  BOTH models off-anchor cannot show a gap — reported as such, not as refuting.

## H10 — The reference band's benefit tracks symptom type, per model (CONFIRMATORY)

**Estimand.** Band benefit B_op,model,arm = detection(arm) − detection(`off`) for arm ∈ {`stats`,
`rule`}, per operator and model; case-clustered CIs.

**Pre-registered ordering (proposed):** within each model, benefit is largest on POSITIVE-symptom silent
faults (the visible metric moves the "good" way: data_leakage, data_leakage_neutral, metric_inflation),
smaller on NEGATIVE-symptom silent faults (lr_warmup, label_corruption), and smallest on the crash
(shape_mismatch). **CONFIRMING:** for a model, the mean benefit over positive-symptom operators exceeds
the mean over negative-symptom operators with the case-clustered CI of the difference excluding 0,
tested separately for `stats` and `rule`. **REFUTING:** the difference's CI excludes 0 in the
OPPOSITE direction. Otherwise **INCONCLUSIVE**. Reported per model; a model that already detects a
class off-anchor (e.g. Luna on leakage) has little benefit to show — stated as a ceiling, not a failure.

## Benign-configuration controls — does anchoring increase benign false positives? (CONFIRMATORY)

**Hypothesis (direction declared).** Showing the agent a reference band — `stats` or `rule` — makes it
flag a legitimate, benign configuration change as a fault MORE often than with no reference (`off`).

**Estimand (paired arm contrast; no level threshold).** On the **24 benign cases**, per provider and
for each anchored arm: Δ_arm = FPR(arm) − FPR(`off`), arm ∈ {`stats`, `rule`}, where a false positive is
`detection.correct = false` on a benign case (the agent reports a fault). Under the reduced control
protocol every benign case contributes exactly one static trial per arm per provider, so the contrast is
**paired by case** — **24 clusters, one pair each**. Δ = (b − c) / 24, where b = cases flagged under the
anchored arm but not under `off`, c = the reverse. **Four confirmatory contrasts:** {Anthropic, OpenAI}
× {`stats` − `off`, `rule` − `off`}.

- **CI method:** Newcombe's hybrid-score interval for a paired difference of proportions (Newcombe 1998,
  method 10), two-sided 95%, with the exact two-sided McNemar p-value on (b, c) reported beside it. It
  stays valid at the 0–2 discordant-pair counts expected here, where the percentile bootstrap is not
  (LIMITATIONS L30). No resampling.
- **Decision rule (proposed), per contrast:** **CONFIRMING** — the CI's lower bound > 0 (anchoring
  increased benign FPs); **REFUTING** the declared direction — the CI's upper bound < 0; otherwise
  **INCONCLUSIVE**. Per provider, the claim "anchoring increases benign false positives" is made if at
  least one of its two contrasts confirms with its McNemar p below the Holm-adjusted threshold over the
  four contrasts (family-wise α = 0.05); a single contrast's CI alone is reported, not generalized.
- **Power note:** with 24 pairs and no reverse discordance (c = 0), the lower bound first clears 0 at
  **b = 5** (Δ = 0.208, CI [0.028, 0.405]); with c = 1 it needs b ≥ 7. Simulated with independent
  per-case outcomes at an `off` FPR of 0.05 (H8's healthy-control `off` FPR: 1/40 = 0.025 pooled, i.e. 0 or 0.05 per provider): power ≈
  **0.27** at an anchored FPR of 0.20, **0.45** at 0.25, **0.61** at 0.30, **0.86** at 0.40. So this
  contrast detects only a LARGE anchoring effect; an INCONCLUSIVE result is expected for effects under
  ≈ 0.25 and is not evidence of no effect.
- **Descriptive (not tested):** the pooled benign FPR per arm × provider over the 24 cases with an
  **exact Clopper–Pearson** interval (clustered: one trial per case per arm × provider, so n = 24),
  reported beside the healthy-control FPR (20 cases) and the benign − healthy difference.
- **EXPLORATORY (with cluster counts):** per-type rates (6 types × **4 cases** each); the edit-form split
  — new key: **4 cases, one knob** (`training.grad_clip_norm`, non-binding: byte-identical to a clean run
  except one config line); changed value: 20 cases, 5 knobs.
- **Qualification facts (recorded before the run):** all six types qualified on development seeds; the
  learning-rate change is "**equivalent within the declared margin, with a small detectable decrease**"
  (−0.460 σ_ref, 90% CI [−0.907, −0.012] σ_ref). Visible band position of the cases actually built:
  **23 inside, 1 below (case_0144, dropout, −2.70σ), 0 above** (bs128 0/4/0, ep25 0/4/0 with one at
  +1.99σ, wd5e4 0/4/0, do01 1/3/0, lr005 0/4/0, clip1 0/4/0).
- **Comparators:** B2 and the form-only comparator `bform` on every benign case; B2+ ("config-diff with
  perfect knob semantics") as an upper bound — its fallback rate on the benign knobs and its benign FPR.

## Secondary (pre-registered, descriptive)

- Detection, identification, evidence F1 and recovery per operator × arm × agent × provider
  (case-clustered CIs); identification per operator with the `root_token_v2` matcher.
- **Evidence F1 under v2.2** (the code path is an accepted set; see Design). Disclosed limits, fixed
  before the run: partial spans below the 0.5 overlap and `line_range` citations of code stay
  uncredited. H8's evidence numbers are compared only as rescored under v2.2 (correction #7).
- ReAct − static evidence F1 per provider (no H8 comparison for Luna ReAct — see the exploratory arm).
- Submit compliance (missing / ignored fields) per provider, reported separately from diagnosis.
- Luna reasoning tokens per call; Haiku ReAct cache-read share; billed and uncached-equivalent cost.
- **Post-run second audit (~30 items):** stratified across lr, label-corruption, metric-inflation and
  shape-mismatch faults and the benign controls, same rubric and declared mapping; optionally a second
  annotator on a 20-item overlap (LIMITATIONS L33).

## EXPLORATORY — Luna ReAct with reasoning pass-back OFF (quantifies H8's defect only)

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

## Known gaps to close before running (tooling, not science)

- ~~The sweep planner does not yet schedule the benign controls.~~ **Closed** (2026-09-25):
  `--benign-seeds 70 … 93` schedules the 24 benign cases static-only under the reduced control protocol,
  with the type ↔ seed pairing taken from the case builder's own function (`benign_design`).
- **Analysis tooling still to build (before the Part 1 report, not before running; the method is fixed
  here):** the paired benign contrast (Newcombe method-10 interval, exact McNemar, Holm over the four
  contrasts) in `harness/sweep_stats.py` with tests against published worked examples; the generated
  report currently renders the benign FPR by edit form only.
- ~~B2+ report over the certified benign cases.~~ **Closed** (2026-09-25): nightly build-and-certify
  run 36136154151 (all jobs green) produced it; committed as `docs/audits/b2plus_report_20260925.md`.
  B2+ flags **24/24 benign cases** (benign FPR 1.00; fallback to a bare leaf name 20/24, an answer-key
  fault concept 4/24 — the learning-rate change named `lr_warmup`) and 0/20 healthy controls.
