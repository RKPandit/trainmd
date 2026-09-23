# Stage 4 — Validate, then Identify the Driver (v2)

**Supersedes v1** (kept as `STAGE4_PLAN_v1_historical.md`). v1 went straight to expansion. A
third external review (2026-09-22) made the case that the instrument's *scoring* has not
earned the trust its *construction* has — and that scaling an unvalidated scorer multiplies
invalid rows. v2 inserts a bounded validation stage in front and re-orders the rest. No new
harness subsystems are added.

**The paper's framing (from the review, adopted):** *when reference context improves or
distorts ML-agent diagnosis* — a question that accommodates heterogeneous and negative
results and does not require every model to fail like Haiku.

**Where Stage 3 left us.** Reference-context dependence is model-specific (Haiku 0.08 vs Luna
0.82 detection off-anchor). H8: identification usually survives renaming the config keys —
equivalence established in 1 of 4 provider-specific anchored cells, unresolved in 3, refuted
in 0. Both are real; neither is yet valid enough to publish as stated, for the reasons in 4.0.

**The test for every item (unchanged):** does a reviewer's conclusion depend on this?

**Solo-project budget:** validation ~3–4 sessions plus one friend's afternoon; then the
expansion as before. Roughly 8–10 weeks to a submission-ready study. Target: NeurIPS Datasets
& Benchmarks or COLM.

---

## Stage 4.0 — Validation (BLOCKING; ~3–4 sessions, ~$0)

### 4.0.1 Identification matcher audit (first — it can change results)
- The root-token rule accepts `no_leakage` and `memory_leak` as correct for data_leakage
  (substring `leak`). Audit ALL scored-correct identification labels in Sweeps 1–3 for
  negations and off-concept matches; report the count and the rate change if they are
  scored as wrong.
- Fix the rule by principle: negation detection (`no_`, `not_`, `absent`, `without`) → wrong;
  concept-bearing tokens must match as whole tokens or declared stems, not arbitrary
  substrings; an explicit per-operator EXCLUSION list for known off-concept collisions
  (memory_leak). Re-score, preserve originals, disclose as correction #6 if any published
  number moves.
- Adversarial tests: the reviewer's three labels plus a panel of ~20 negations/off-concept
  strings per operator must FAIL; the oracle and known synonyms must PASS.

### 4.0.2 Statistical corrections
- H8 bootstrap must resample the matched (strength, seed) PAIRS together, not case_ids
  independently. Recompute; report sensitivity to shared seeds across strengths.
- Boundary-aware intervals: zero-event rates get a Clopper–Pearson (or Wilson) upper bound,
  never [0, 0]. State that 0/20 permits ~14% one-sided.
- Control narrative corrected to the table (rule-arm FPs are 3/4 in-band). Replace "first
  adequately-powered" with a stated precision: what half-width 20 controls give at the
  observed rate.
- H8 tally: 3 confirming provider-specific cells, not 4 (pooled rows reuse observations);
  Haiku off-arm equivalence is equivalent FAILURE at ~6% and supports nothing.
- **Before the paper (its own disclosed change):** move the control-FP table to exact
  Clopper–Pearson on case-level counts for EVERY row — one method throughout. Correction #6 fixed
  only zero-event rows; the percentile bootstrap still understates uncertainty at 1–2 events
  (1 of 19 cases: bootstrap upper 0.158 vs exact 0.260 — LIMITATIONS L30; rows flagged ‡).

### 4.0.3 Framing corrections (docs)
- H8 conclusion becomes: "identification often survives the tested renaming; equivalence is
  unresolved in three anchored conditions; GPT's rule arm shows a measurable decrease."
  Remove "mechanism, not name-reading" — renaming tests dependence on those names, and
  code-pattern recognition remains a competing explanation.
- DegenerateAgent reads the oracle repair from hidden material; its 18/18 was by
  construction, not a blind policy. B2's 30/30 is the relevant evidence for L19. Correct it.
- B2's identification failure is partly built into its output convention (it emits a key
  name). Report localization separately from terminology; add B2+ (below).
- Cite and position AutoTrainer (ICSE 2021) and RFT-FaultBench/RFT-FM as predecessors.

### 4.0.4 Release the H8 records
- `export_release --sweep h8_xprovider` with the retry accounting; `rebuild_tables` must
  reproduce the report from the release. Report performance both among valid submissions and
  end-to-end under the fixed retry policy; separate model-malformed output from infrastructure.

### 4.0.5 Blind human audit (the one item that needs a person)
- Stratified sample ~60 trials (operator × provider × arm), blinded to score. An independent
  annotator judges: fault class named? localized? evidence sufficient? Compute agreement with
  the scorer; inspect every disagreement; report how corrections change H8/F14.
- If no annotator is available, an independent LLM judge with the same rubric, disclosed as
  weaker.

### 4.0.6 Cheap instrument fixes that Part 1's plan file needs anyway
- **Bare-stats anchor arm** (v3 Part 4, never built): mean/SD with no evaluative words. The
  current "numbers" arm says "healthy runs achieve…" and is not the treatment we claim.
- **B2+ baseline:** B2 with a DECLARED key→concept mapping (one line per known knob),
  validated on held-out instances — a stronger, honest terminology baseline.
- **Benign-configuration controls:** healthy runs with a legitimate non-default knob (e.g. a
  different but valid batch size). Tests whether anchored agents and config-diff baselines
  false-positive on legitimate change — the single best probe of "diagnosis vs flagging."
- Missing tool fields score as empty, not crash (Stage 3 mandate).

**Gate 4.0:** matcher fixed and re-scored with disclosure; statistics corrected; H8 released
and reproducible; human-audit agreement reported; the three cheap fixes built and certified.
Then and only then, paid runs.

---

## Part 1 — Fault-type generality (~1 week, ~$50) — the decision point
As v1: all six operators, both providers, now with the bare-stats arm, B2+, and benign
controls. Pre-register H9 (model dependence generalizes beyond leakage) and H10 (band benefit
tracks symptom type per model). Gate 1 decides whether Part 2 runs at full scope.

## Part 2 — Model dimension (~2 weeks, ~$100–200)
As v1, unchanged in substance: Sonnet 5, GPT-5.6 Terra, **Luna with reasoning.effort=none**
(the cleanest confound test; the review independently endorses distinguishing capability
from reasoning budget), optional open-weight. Static agent as primary protocol. Per-model +
hierarchical estimates.

## Part 3 — Second workload, frozen as the evaluation set (~2 weeks)
As v1, with one change from the review: the second workload doubles as the **fresh frozen
evaluation set** — built after the scorer and protocol stop changing, never used for
development. Synthetic tabular (closes the prior-knowledge objection). Gate 3: does the
pattern replicate on data no model has seen?

## Then: write.

---

## Deferred (unchanged), with the review's additions noted
Code-origin operator; two-stage telemetry protocol; **within-band faults** (the sub-band
tier — a real probe, but a new validity category; revive if the benign-control result makes
"diagnosis vs flagging" the headline); **mismatched-reference arm**; wider repair space
(recovery is not a claimed contribution); third workload; human realism audit beyond 4.0.5.

## Standing rules
Validate before scaling. Pre-register every paid part. "Failed to replicate," never
"refuted," at n < 4 models. Strict readings encoded in tests. The public plan carries only
run-time fields. Instrument work only when a gate requires it.
