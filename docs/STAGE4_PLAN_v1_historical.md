# Stage 4 — Identifying the Driver

**Where Stage 3 left us.** The H8 sweep (984 cells, two providers) found that reference-context
dependence is **model-specific**: Haiku detects leakage at 0.08 off-anchor, Luna at 0.82; the
band adds ~90 points for one and ~17 for the other. H8 confirmed neither model reads the config
key name. The finding is real, and it is under-determined: with **n = 2 models, one mechanism
family, one workload**, the driver cannot be identified (L28), and the claim cannot be
distinguished from a leakage-specific or Adult-specific artifact.

**The question Stage 4 answers:** *what predicts a model's dependence on reference context,
and does that dependence hold across fault types and data?*

**The test applied to every item (unchanged):** does a reviewer's conclusion depend on this?

**Target venue:** NeurIPS Datasets & Benchmarks track or COLM. Not MLSys (wrong contribution
type), not a one-month deadline (the design below needs six to eight weeks).

---

## Part 1 — Fault-type generality (~1 week, ~$50) — RUN FIRST, IT IS THE DECISION POINT

Rerun the current design on **all six operators**, both current providers. Cases exist and are
certified; this is a plan-file change, not a build.

- Design: 5 faulty operators (leakage descriptive + neutral, label_corruption, lr_warmup,
  shape_mismatch, metric_inflation) × 3 strengths × 6 seeds × 3 arms × 2 agents × 2 providers
  × 2 repeats, plus 20 controls in the static protocol.
- Faulty cases: 108 (up from 36). Cells ≈ 2,600 + controls. Estimate from measured per-trial
  costs: Haiku ~$0.06, Luna ~$0.004 → roughly **$45–60**.
- Baselines B0–B4 on every case.

**Pre-register before running** — the decision rule for the whole stage:
- **H9 (model dependence generalizes):** the off-anchor detection gap between providers is
  present on every silent operator (not only leakage), per-operator case-clustered CIs
  excluding zero.
  - CONFIRMING → model dependence is a property of diagnosis, not of leakage → proceed to
    Part 2.
  - REFUTING (the gap exists only on leakage) → the finding is *leakage-specific* model
    dependence; the paper's claim narrows to that; Part 2 is reduced to leakage only.
- **H10 (the reference band's benefit tracks symptom type per model):** pre-register the
  expected pattern (largest on positive-symptom faults, smallest on crashes) and test it per
  provider.
- Recovery reported as a compliance measure (L19 stands); the code-origin operator that would
  make it discriminate stays deferred.

**Gate 1:** report per-operator × provider × arm table; H9 verdict; go/no-go for Part 2.

---

## Part 2 — Model dimension: from n=2 to a pattern (~2 weeks, ~$100–200)

Only after Gate 1. Choose models to **span the candidate drivers**, so the design can separate
them rather than merely add points:

| model | why | isolates |
|---|---|---|
| Claude Sonnet 5 | same provider as Haiku, more capable | capability within a lab |
| GPT-5.6 Terra | same provider as Luna, more capable | capability within the other lab |
| Luna with `reasoning.effort = none` | same model, reasoning off | **reasoning tokens** — the cleanest confound test we can run |
| one small open-weight model (if budget) | different training regime | lab/recipe |

The `reasoning=none` arm is the most important row. Luna reasons by default; Haiku does not.
If Luna-without-reasoning collapses toward Haiku's off-anchor detection, reasoning tokens are
the driver and the paper's claim becomes mechanistic. If it does not, capability or training is.
This is one API parameter, no new adapter, and it directly targets L28.

- Design: same six operators, three arms, **static agent as the primary protocol** across all
  models (H7 is about context, not tools); ReAct on a pre-specified subset.
- Pre-register per-model estimates plus a hierarchical pooled estimate (the reviewers'
  request), with the driver hypotheses stated: capability, reasoning, provider.
- Cost: frontier models are ~25× Haiku; run them at 1 repeat on moderate strength first
  (~$40 each), full design only if the cheap slice justifies it.

**Gate 2:** per-model off-anchor detection with CIs; the reasoning-off result; a stated
driver or a stated inability to separate them.

---

## Part 3 — Second workload (~2 weeks, CPU + ~$50)

Only after Gate 2. Answers the last reviewer attack: *Adult is a toy, and Luna may simply know
its achievable accuracy.*

- Pick a workload where prior knowledge is unlikely: a **synthetic tabular** task with a
  generated ground truth (no public leaderboard to remember), or a small text task with a
  recent dataset. Synthetic is cheaper, deterministic, and closes the prior-knowledge
  objection cleanly; say so as the reason.
- Port the operators that are workload-agnostic (leakage, label corruption, lr, metric
  inflation, controls); reference distribution at 30 seeds; certify.
- Rerun Part 1's design on it for the two cheap providers.

**Gate 3:** does the model-dependence pattern replicate on a workload no model has seen?

---

## Then: write

The paper's claim after Parts 1–3: *Diagnostic agents' reliance on reference context varies
enormously by model — [driver, if identified] — and this holds across N fault types and two
workloads; the variation is not explained by config-name reading (H8) or by threshold
comparison (baselines).* With the certified instrument, pre-registered hypotheses, and
released records as the methodological contribution.

Draft the instrument sections now (they are frozen). Results sections after each gate.

---

## Deferred (unchanged from v3, plus)
Code-origin operator (revive if recovery becomes a claimed contribution); two-stage
telemetry protocol; sub-band tier; token-matched no-tools baseline; human realism audit.
**New:** a third workload (vision) — only if Part 3 replicates and a modality claim is wanted.

## Standing rules
Pre-register every part before its paid run. Report H7-style results as "failed to
replicate," never "refuted," until n ≥ 4 models. Strict readings encoded in tests. Instrument
work only when a gate's result requires it. Fix the crash-class (missing tool fields score as
empty, not crash) before Part 1's run — it is the one instrument change Stage 3 mandated.
