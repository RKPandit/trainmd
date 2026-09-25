# Stage 4 Part 1 — pre-registration (DRAFT for the author's review; NOT yet locked)

> Finalized 2026-09-25 from the "Declared in the Part 1 pre-registration" paragraphs of
> `docs/STAGE4_PLAN.md` Part 1, the v1 plan's H9/H10 wording, and H8's template; revised the same day
> with the author's decisions (benign contrast, evidence scorer v2.2, H9 scope, planner, exploratory
> arm), and again after the author's final review (H9 headroom rule and small-gap refutation, H10
> replaced, benign contrast two-sided, multiplicity per hypothesis, analysis built before the run).
> **Not a pre-registration until the author approves it**; on approval it is appended to
> `docs/HYPOTHESES.md` ("do not edit above this line"), dated on commit, before any Part 1 trial.
> Thresholds approved by the author 2026-09-25 (0.85, 0.20, 0.30, 0.5); no **[DECIDE]** items remain.

## Design (fixed before running)

- **Models (unchanged from H8, so operator generality is not confounded with a model change):**
  `claude-haiku-4-5-20251001` (a dated snapshot; no thinking; temperature 1.0) and `gpt-5.6-luna`
  (effort fixed at medium; the model is an ALIAS, not a pinned snapshot — no dated Luna id exists, so
  provenance rests on the API-reported model string recorded per call; LIMITATIONS L26).
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

## Analysis fixed in code BEFORE the run

Every confirmatory verdict below is computed mechanically by `harness/prereg_part1.py` (thresholds are
module constants that match this document) and rendered in the generated report's "Pre-registered
verdicts" section. It is tested on synthetic data before any Part 1 trial — for each hypothesis a
dataset that must CONFIRM, one that must REFUTE, and the named edge cases (lr_warmup at Haiku's ceiling
→ "no headroom — untestable"; fewer than two decision-carrying operators → INCONCLUSIVE; a Δ interval
that merely includes 0 → INCONCLUSIVE; a near-0.5 f → INCONCLUSIVE; an unadjusted p < 0.05 that fails
Holm → INCONCLUSIVE) — and the paired interval is checked against Newcombe's published Table III
(`tests/test_prereg_part1.py`).

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

## H10 — Bare statistics close most of the off→rule detection gap, per model (CONFIRMATORY)

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

## Benign-configuration controls — does anchoring change benign false positives? (CONFIRMATORY, two-sided)

**Hypothesis (two-sided; both mechanisms stated).** Showing the agent a reference band changes how
often it flags a legitimate, benign configuration change as a fault, relative to no reference (`off`).
Two mechanisms pull in opposite directions: an **in-band reference may REASSURE** (the visible metric is
inside the healthy range, so the agent is less likely to call a benign change a fault — fewer false
positives); and the `rule` arm's **"anomalous" sentence may PRIME flagging** — in H8, 3 of the rule
arm's 4 control false positives were on IN-BAND controls (FINDINGS; HYPOTHESES H8 results), which the
reassurance account does not predict. The claim is therefore **two-sided: increase or decrease**.

**Estimand (paired arm contrast; no level threshold).** On the **24 benign cases**, per provider and
for each anchored arm: Δ_arm = FPR(arm) − FPR(`off`), arm ∈ {`stats`, `rule`}, where a false positive is
`detection.correct = false` on a benign case (the agent reports a fault). Under the reduced control
protocol every benign case contributes exactly one static trial per arm per provider, so the contrast is
**paired by case** — **24 clusters, one pair each**. Δ = (b − c) / 24, where b = cases flagged under the
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
- **Power note:** with 24 pairs and no reverse discordance (c = 0), a lone effect must clear α/4 =
  0.0125: **b ≥ 8** (p = 0.0078); at the last Holm step (α) b ≥ 6 suffices. With c = 1 it needs b ≥ 11
  at α/4. Simulated with independent per-case outcomes at an `off` FPR of 0.05 (H8's healthy-control
  `off` FPR: 1/40 = 0.025 pooled, i.e. 0 or 0.05 per provider), power for a lone contrast at α/4 is ≈
  **0.11** at an anchored FPR of 0.25, **0.22** at 0.30, **0.53** at 0.40 and **0.80** at 0.50 (at α:
  0.31 / 0.47 / 0.78 / 0.94). **A DECREASE is detectable only if the `off` FPR is itself high** (e.g.
  off 0.30 → anchored 0.05: power 0.22 at α/4); from an `off` FPR near 0.05 there is no room to fall.
  This contrast detects only LARGE effects; INCONCLUSIVE is the expected outcome for smaller ones and
  is not evidence of no effect.
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
- ~~Analysis tooling.~~ **Closed** (2026-09-25): H9 (with the headroom rule), H10 and the benign
  contrast output their verdicts mechanically (`harness/prereg_part1.py`; see "Analysis fixed in code
  BEFORE the run").
- ~~B2+ report over the certified benign cases.~~ **Closed** (2026-09-25): nightly build-and-certify
  run 36136154151 (all jobs green) produced it; committed as `docs/audits/b2plus_report_20260925.md`.
  B2+ flags **24/24 benign cases** (benign FPR 1.00; fallback to a bare leaf name 20/24, an answer-key
  fault concept 4/24 — the learning-rate change named `lr_warmup`) and 0/20 healthy controls.
