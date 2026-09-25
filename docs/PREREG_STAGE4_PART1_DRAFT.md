# Stage 4 Part 1 — pre-registration (DRAFT for the author's review; NOT yet locked)

> Finalized 2026-09-25 from the "Declared in the Part 1 pre-registration" paragraphs of
> `docs/STAGE4_PLAN.md` Part 1, the v1 plan's H9/H10 wording, and H8's template. **Not a
> pre-registration until the author approves it**; on approval it is appended to `docs/HYPOTHESES.md`
> ("do not edit above this line"), dated on commit, before any Part 1 trial. Every threshold below is a
> PROPOSAL marked for review; items marked **[DECIDE]** need an explicit decision before locking.

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
- **Cells:** 108 × 3 × 2 × 2 × 2 = **2,592 faulty** + 44 × 3 × 2 = **264 control** = **2,856**.
- **Protocol changes vs H8, all declared:** prompt caching on Anthropic ReAct cells (transport-only;
  billed and uncached-equivalent cost both reported); reasoning preserved across tool calls on both
  providers (H8's Luna ReAct discarded it — LIMITATIONS L32 — so **Part 1 Luna ReAct is not comparable
  with H8's**; Luna static and all Haiku cells are unaffected); a submit is always accepted, with
  compliance recorded separately (missing fields scored empty).
- **Cost estimate:** from H8's measured per-trial costs (Haiku static ≈ $0.014, Haiku ReAct with caching
  ≈ $0.040 [H8 simulation], Luna static ≈ $0.003, Luna ReAct ≈ $0.004 before the reasoning replay, which
  adds replayed reasoning to Luna's input): ≈ **$41**; cap **$60** (`--max-cost-usd`), with the agents
  phase's cost cap, circuit breaker, cache check and reasoning check active.

## Pre-run gates (all must pass before the full run)

1. Sweep preconditions: `validate-all` green on the 152 cases.
2. A slice (`run --phase agents --max-trials N`, ≥ 5 Anthropic ReAct and ≥ 5 Luna ReAct multi-call
   trials): `python -m harness.sweep check-cache --name <part1>` → `passed`, and
   `python -m harness.sweep check-reasoning --name <part1>` → `passed` (prior Luna reasoning replayed on
   every later call and recurring after the first tool call). The agents phase also stops by itself if
   either check fails mid-run.

## H9 — Model dependence generalizes beyond leakage (CONFIRMATORY)

**Hypothesis.** The off-anchor detection gap between the two models found on leakage in H8 (Luna 0.82
vs Haiku 0.08 — FINDINGS F14) is a property of silent-fault diagnosis, not of leakage.

**Estimand.** For each silent operator, Δ_op = detection(Luna, `off`) − detection(Haiku, `off`),
pooled over agents, strengths and repeats; case-clustered 95% CI (case-level bootstrap, 10k resamples;
exact Clopper–Pearson for any 0- or 100%-rate cell). **Operators in scope:** lr_warmup,
label_corruption, metric_inflation, data_leakage_neutral (and data_leakage, as the within-Part-1
replication of F14). **Excluded:** shape_mismatch — a crash, detected from the exit code by both
models (stated in advance; it cannot carry a model gap).

- **CONFIRMING (proposed):** Δ_op > 0 with the CI excluding 0 on **every** non-leakage silent operator
  in scope → model dependence is a property of diagnosis; proceed to Part 2 at full scope.
- **REFUTING (proposed):** the CI includes 0 on **every** non-leakage silent operator while leakage's
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

## Benign-configuration controls

- **CONFIRMATORY estimand:** the POOLED benign false-positive rate over all **24 benign cases**
  (clustered by case: 24 clusters), per arm and model, with exact Clopper–Pearson intervals, reported
  beside the healthy-control FPR (20 cases) and their difference (case-clustered). This is an
  estimate with an interval, not a threshold test **[DECIDE: add a threshold, e.g. "benign FPR exceeds
  healthy FPR by ≥ 0.15 with CI excluding 0 ⇒ agents flag legitimate change"?]**.
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
- **Evidence F1 caveat [DECIDE before locking]:** the blind audit (F16) found a valid evidence path —
  config key → consuming `train.py` code → the label-derived `_derived_column` — that the leakage
  operator's evidence set does not admit; 49% of H8 leakage submissions cite it. Either (a) keep the
  evidence scorer as is and pre-declare evidence F1 on leakage as a lower bound for agents that cite
  code, or (b) add the code path as an alternative evidence set BEFORE the run (a scorer change with its
  own DECISIONS row and a disclosed rescore of H8's evidence numbers).
- ReAct − static evidence F1 per provider (no H8 comparison for Luna ReAct).
- Submit compliance (missing / ignored fields) per provider, reported separately from diagnosis.
- Luna reasoning tokens per call; Haiku ReAct cache-read share; billed and uncached-equivalent cost.
- **Post-run second audit (~30 items):** stratified across lr, label-corruption, metric-inflation and
  shape-mismatch faults and the benign controls, same rubric and declared mapping; optionally a second
  annotator on a 20-item overlap (LIMITATIONS L33).

## Known gaps to close before running (tooling, not science)

- **The sweep planner does not yet schedule the benign controls** — it enumerates only
  `control.healthy.v1` on the control seeds; benign operators (seeds 70–93) must be added to the plan
  (static-only, reduced control protocol) with a test, before `plan` is run.
- B2+ report over the certified benign cases: produced by the nightly build-and-certify now running
  (run 36136154151); to be committed as the B2+ baseline artifact.
