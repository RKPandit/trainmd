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

### 4.0.5 Blind human audit (the one item that needs a person) — **COMPLETE 2026-09-25** (FINDINGS F16)
- Stratified sample ~60 trials (operator × provider × arm), blinded to score. An independent
  annotator judges: fault class named? localized? evidence sufficient? Compute agreement with
  the scorer; inspect every disagreement; report how corrections change H8/F14.
- If no annotator is available, an independent LLM judge with the same rubric, disclosed as
  weaker.
- **Tooling built 2026-09-23 (awaiting the annotator):** `make audit-sheet NAME=h8_xprovider` writes
  `audit/local/h8_xprovider/audit_sheet.xlsx` (60 shuffled rows, 15% healthy controls; ratings
  named / located / evidence / explained as Yes / Partial / No / N/A dropdowns) and the sealed
  `audit_key.csv` — both generated locally and NEVER committed (gitignored; the repo is public).
  `scripts/audit_agreement.py --sheet <returned.xlsx> --key <audit_key.csv>` reports agreement with
  the scorer (mapping declared in the script; DECISIONS 2026-09-23).
- **Result (2026-09-25):** identification 60/60 [0.940, 1.000], localization 51/51, evidence 48/51
  (50/51 counting Partial); no identification rate changes — H8 stands. One annotator, leakage-only
  sample (LIMITATIONS L33); A33 shows an evidence path the operator's evidence sets miss (reported,
  not acted on).

### 4.0.6 Cheap instrument fixes that Part 1's plan file needs anyway
- **Bare-stats anchor arm** (v3 Part 4, never built): mean/SD with no evaluative words. The
  current "numbers" arm says "healthy runs achieve…" and is not the treatment we claim.
  **Built 2026-09-23** as prompt v2 (`react-2` / `static-2`; DECISIONS): `stats` = mean, SD, n
  reference runs — no interval (a mean±2SD interval IS the decision threshold); `rule` = `stats` +
  "Values more than 2 SD from this mean, above OR below, are anomalous." Arm identity includes the
  prompt version, so v1 and v2 arms are never pooled.
- **B2+ (originally planned as a baseline):** B2 with a DECLARED key→concept mapping (one line per known knob),
  validated on held-out instances — a stronger, honest terminology baseline. **Built 2026-09-23,
  REFRAMED as an UPPER BOUND** ("config-diff with perfect knob semantics"): the map is the answer key
  for our own operators, so identification is perfect by construction; it is validated only on knobs
  NOT in the map — fallback rate + control false positives on the benign-control knobs and future
  operators (`scripts/b2plus_report.py`; DECISIONS).
- **Benign-configuration controls:** healthy runs with a legitimate non-default knob (e.g. a
  different but valid batch size). Tests whether anchored agents and config-diff baselines
  false-positive on legitimate change — the single best probe of "diagnosis vs flagging."
- Missing tool fields score as empty, not crash (Stage 3 mandate). **Built 2026-09-23**
  (DECISIONS; `tests/test_missing_tool_fields.py`) — previously documented as done but not built.
  A submit is always accepted (missing fields empty, extras ignored, same result for ReAct and
  static); `compliance` is recorded per trial and reported separately from diagnosis.

**Gate 4.0:** matcher fixed and re-scored with disclosure; statistics corrected; H8 released
and reproducible; human-audit agreement reported; the three cheap fixes built and certified.
Then and only then, paid runs.

---

## Part 1 — Fault-type generality (~1 week, ~$50) — the decision point
As v1: all six operators, both providers, now with the bare-stats arm, B2+, and benign
controls. Pre-register H9 (model dependence generalizes beyond leakage) and H10 (band benefit
tracks symptom type per model). Gate 1 decides whether Part 2 runs at full scope.
**Declared in the Part 1 pre-registration — anchor arms are NEW treatments:** Part 1 runs prompt v2
(`off` / `stats` / `rule`). Only the `off` arm is comparable across H8 and Stage 4 (no reference line
in either version; the fixed template text is byte-identical). `stats` and `rule` are new treatments:
v2 `rule` keeps v1's ±2σ decision boundary but not its wording, and v2 `stats` has no v1 counterpart
(v1 `numbers` carried evaluative words and the interval). No v2 stats/rule result is compared with,
or pooled with, an H8 numbers/rule result; analysis keys arms by (arm, prompt version) so this is
enforced structurally (`harness/anchors.py`; `tests/test_analysis_generic.py`).
**Declared in the Part 1 pre-registration — prompt caching (cost optimization, no expected effect
on outputs):** Anthropic ReAct cells run with prompt caching (one top-level `cache_control`, 5-minute
TTL); static cells and OpenAI cells are unchanged (OpenAI caches automatically). It is transport-only:
the prompt text is byte-identical with caching on or off (`tests/test_prompt_caching.py`), so no
effect on model outputs is expected or tested for. Per-trial cost is reported BOTH as billed and as
the uncached-equivalent, so Part 1 compares with Sweeps 1–3. **Pre-run slice gate:** run the agents phase on a small
slice first (`run --phase agents --max-trials N`, including ≥ 5 Anthropic ReAct cells), then
`python -m harness.sweep check-cache --name <part1>` must report `passed` — at least one Haiku ReAct
trial with `cache_read_tokens > 0` — before the full run. (The agents phase also stops by itself if 5
multi-call Anthropic ReAct trials all miss the cache.) Measured on H8: Haiku ReAct resent
84% of its input as history; caching would have cut that cell from $18.85 to ≈ $8.70 (DECISIONS
2026-09-23).
**Declared in the Part 1 pre-registration — the workload source changed:** both `train.py` files now
contain an inert `training.grad_clip_norm` path (absent = no clipping; needed for the new-key benign
control — DECISIONS 2026-09-23). The clean path is numerically unchanged (A/B-proven), but agents that
read `train.py` see four extra lines (a one-line comment and the clipping path), so even the `off` arm is
comparable with H8 only approximately.
**Declared in the Part 1 pre-registration — benign-configuration controls (24 cases, case_0129–0152):**
the POOLED benign false-positive rate over all 24 benign cases is **confirmatory** (clustered by case:
24 clusters). Per-type rates (6 types × **4 cases** each) and the edit-form split — new key: **4 cases,
one knob** (`training.grad_clip_norm`); changed value: 20 cases, 5 knobs — are **EXPLORATORY** and
reported with those cluster counts. The learning-rate change (0.01 → 0.005) is "**equivalent within the
declared margin, with a small detectable decrease**" in hidden accuracy (−0.460 σ_ref, 90% CI
[−0.907, −0.012] σ_ref; `docs/audits/benign_qualification.md`). What agents will SEE is the visible band
position of the cases actually built (not the development-seed shares): **23 inside, 1 below
(case_0144, dropout, −2.70σ), 0 above** — per type: bs128 0/4/0, ep25 0/4/0 (one at +1.99σ), wd5e4
0/4/0, do01 1/3/0, lr005 0/4/0, clip1 0/4/0 (below/inside/above; from the build-and-certify case-margin
table, run 35947111127).
**Declared in the Part 1 pre-registration — Luna ReAct is NOT comparable with H8's:** H8's Luna ReAct ran
with Luna's reasoning discarded between tool calls (LIMITATIONS L32; fixed — reasoning items are now
replayed). Part 1 Luna ReAct therefore runs a different (corrected) protocol; no Part 1 Luna ReAct result
is compared with or pooled with H8's. Luna static and all Haiku cells are unaffected. **Pre-run slice
gate, extended:** besides `check-cache`, `python -m harness.sweep check-reasoning --name <part1>` must
report `passed` on the slice (Luna ReAct produces reasoning items: prior items must be replayed on every
later call, and reasoning must recur after the first tool call); the agents phase also stops by itself
if any trial drops them.
**Post-run second audit (Part 1):** after the Part 1 run, a second blind audit of ~30 items stratified
across the operators the first audit did not cover — lr, label-corruption, metric-inflation and
shape-mismatch faults, plus the benign-configuration controls — with the same rubric, tooling and
declared mapping; optionally a second annotator on a 20-item overlap to measure human–human
agreement (LIMITATIONS L33).
**Release archive — decided at paper time (no longer a Part 1 prerequisite; DECISIONS 2026-09-23):**
the archive platform (Zenodo / GitHub Releases / Hugging Face) is chosen at submission, once the venue's
anonymity and hosting rules are known. Enforced now: new sweep releases (Stage 4 onward) are exported
LOCALLY and NOT committed (`.gitignore` ignores `results_release/*` except the three committed releases —
sweep1, stage2gate, h8_xprovider — which stay); verify one locally with `make verify-release NAME=<sweep>`
(the same `rebuild_tables` byte-match CI runs); CI (`scripts/check_release_files.py`) fails if any other
release directory is committed or any file under `results_release/` exceeds 10 MB.

## Part 2 — Model dimension (~2 weeks) — contrasts that isolate ONE factor each (revised 2026-09-24)
Planning only; no runs. Every model fact below was verified 2026-09-24 against the providers'
OFFICIAL docs (platform.claude.com/docs; developers.openai.com/api/docs), not third-party sites; the
OpenAI figures were re-read from the raw pages because a summarizer misread the pricing table.

**Part 1 stays on its models** — `claude-haiku-4-5-20251001` and `gpt-5.6-luna` — so operator generality
is not confounded with a model change. Lifecycle check: `gpt-5.6-luna` is NOT deprecated (OpenAI's
deprecations page lists it only as a recommended REPLACEMENT for older models). `claude-haiku-4-5-20251001`
is Active with retirement "not sooner than October 15, 2026" and ≥ 60 days' notice — so Part 1 is not
at risk, but Part 2 must not rely on re-running Haiku after that date without re-checking.

**Design (author's decisions, 2026-09-24)** — each contrast isolates ONE factor; Fable 5.1 and GPT-6
Astra deferred. Anthropic models run at ONE explicit effort, **medium**, throughout (defaults differ:
Sonnet 5 high, Opus 5.5 medium, so defaults would mix capability with effort).
1. **Sonnet 5 with thinking OFF is REQUIRED — it is the pivot:** Haiku 4.5 (no thinking) vs Sonnet 5
   (off) isolates capability WITHOUT reasoning; Sonnet 5 off vs on (medium) isolates reasoning within
   one model; Sonnet 5 vs Opus 5.5 (both medium) isolates capability WITH reasoning.
2. Capability within OpenAI: GPT-6 Luna → GPT-6 Sol (both medium).
3. Generation within tier: GPT-5.6 Luna vs GPT-6 Luna (both medium).
4. Matched-price cross-provider pair: **Sonnet 5 medium vs GPT-6 Sol medium** ($2 / $10 each).
   *Limitation (stated in the pre-registration):* the providers' effort scales do not correspond —
   "medium" is each provider's own label, not a matched reasoning budget.
5. Reasoning within OpenAI: GPT-5.6 Luna none vs medium (medium = Part 1's setting).

**Verified model facts**

| Model | API ID | Pinned snapshot? | $/MTok in · 5m cache write · cache read · out | Knowledge cutoff | Reasoning control | Temperature |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | yes (dated) | 1 · 1.25 · 0.10 · 5 | reliable Feb 2025 (training Jul 2025) | extended thinking only (budget_tokens); effort NOT supported | settable |
| Claude Sonnet 5 | `claude-sonnet-5` | yes ("every Claude model ID is a pinned snapshot, including the dateless IDs") | 2 · 2.50 · 0.20 · 10 | Jan 2026 | adaptive thinking ON by default, can be disabled; effort low…max, default **high** | non-default → HTTP 400 (4.7+) |
| Claude Opus 5.5 | `claude-opus-5-5` | yes | 4 · 5 · 0.20 (0.05×) · 20 | Jun 2026 | adaptive thinking ALWAYS on (disabling → 400); effort low…max, default **medium** | non-default → HTTP 400 |
| GPT-5.6 Luna | `gpt-5.6-luna` | alias only (no dated snapshot) | 0.20 · 0.25 · 0.02 · 1.20 | Feb 16, 2026 | reasoning.effort none…max, default medium | not documented |
| GPT-6 Luna | `gpt-6-luna` | alias only | 0.10 · 0.125 · 0.01 · 0.50 | May 18, 2026 | reasoning.effort none…max, default medium | not documented |
| GPT-6 Sol | `gpt-6-sol` | alias only | 2.00 · 2.50 · 0.20 · 10.00 | Apr 20, 2026 | reasoning.effort none…max, default medium | not documented |

OpenAI prices are short-context (≤ 272K input tokens; above that 2× input/cache and 1.5× output).
Reasoning/thinking tokens are billed as OUTPUT on both providers. Claude 4.7+ models (Sonnet 5, Opus
5.5) use a newer tokenizer (~30% more tokens for the same text than Haiku 4.5's), so token counts are
not comparable across the Anthropic ladder — compare cost in dollars. Minimum cacheable prompt: Haiku
4.5 4,096 tokens, Sonnet 5 1,024, Opus 5.5 512. No GPT-6 model or GPT-5.6 Luna has a dated snapshot:
the alias is the snapshot (the LIMITATIONS L26 caveat extends to them). *Consistency check:* GPT-5.6
Luna's $1.20 output rate is confirmed by H8's bill ($1.63 billed vs $1.454 estimated + ≤ $0.18
unpriced writes; at $0.75 it could not exceed ≈ $1.39).

**Adapter work — IMPLEMENTED with tests before Part 1** (reasoning-preservation PR; DECISIONS
2026-09-24; the pinned `anthropic` 0.125.0 SDK already accepts `output_config` / `thinking` — no
dependency or image-digest change):
1. **Temperature** sent only to models that accept it (Sonnet 5 / Opus 5.5 would return 400);
   "model default (not settable)" recorded in the model block.
2. **Effort** from the cell (`output_config.effort`), validated per model (Haiku 4.5 has none), constant
   within a trial, recorded in conditions + model block.
3. **Thinking blocks passed back unchanged** (with signatures) — and the SAME class of bug on OpenAI:
   H8's Luna ReAct ran with reasoning items discarded between tool calls (LIMITATIONS L32); both paths
   now replay the provider-native turn verbatim (OpenAI stateless, encrypted reasoning).
4. **Thinking-token accounting:** thinking/reasoning is billed inside output tokens (already correct);
   per call the transcript records `reasoning_blocks`, `replayed_reasoning_blocks`, `reasoning_tokens`;
   per-cell `max_tokens` (it caps thinking + text) with truncations reported per condition.
5. **Price table / metadata:** Opus 5.5, GPT-6 Luna, GPT-6 Sol added (history archive regenerated);
   GPT-6 knowledge cutoffs. Thinking settings per cell (`thinking: disabled` for the Sonnet 5 pivot;
   Opus 5.5 rejects it — validated).

**Pilot first (~$3), with two live gates:** ~10 static + a few ReAct trials per Anthropic condition to
measure real thinking volume (replaces the assumed multipliers below) and to assert, live, that
**thinking is still present on turns AFTER the first tool call** — `python -m harness.sweep
check-reasoning --name <pilot>` must report `passed` (prior thinking replayed on every later call AND
reasoning recurring after the first tool call; the agents phase also stops by itself on a drop), as
`check-cache` must for caching. Re-estimate the budget from the pilot before committing.

**Cost estimate** (per condition, 780 static trials = 108 faulty cases × 3 arms × 2 repeats + 44
controls × 3 arms × 1; ReAct shown for comparison). Built from H8's MEASURED per-trial token profiles
(Anthropic static 9,172 in / 903 out; ReAct 76,167 in / 2,217 out over 10 calls; OpenAI static 6,978 in
(1,132 cached) / 911 out; ReAct 26,639 in (18,220 cached) / 1,350 out), Anthropic ReAct prompt caching
(84% of input read as history, the rest written at 1.25×), OpenAI measured caching with uncached input
priced at the write rate (upper bound), and the +30% tokenizer factor for Sonnet 5 / Opus 5.5.
**Assumed, to be replaced by a pilot:** thinking output multipliers vs H8's visible output — low 1.5×,
medium 2.5×, high 4× — and Luna `none` = 0.5× H8's medium output.

| Condition | $ / static trial | $ / ReAct trial | 780 static | 780 ReAct |
|---|---|---|---|---|
| Haiku 4.5, no thinking (reuse Part 1) | 0.0137 | 0.0327 | 10.68 | 25.52 |
| **Sonnet 5, thinking OFF (pivot)** | 0.0356 | 0.0851 | 27.76 | 66.35 |
| Sonnet 5, thinking on, effort medium | 0.0532 | 0.1283 | 41.50 | 100.06 |
| Opus 5.5, effort medium | 0.1064 | 0.2399 | 83.00 | 187.15 |
| GPT-5.6 Luna, medium (reuse Part 1) | 0.0026 | 0.0041 | 2.01 | 3.19 |
| GPT-5.6 Luna, none | 0.0020 | 0.0033 | 1.58 | 2.56 |
| GPT-6 Luna, medium | 0.0012 | 0.0019 | 0.93 | 1.49 |
| GPT-6 Sol, medium | 0.0240 | 0.0382 | 18.68 | 29.79 |

Static-primary Part 2, new conditions only (Sonnet 5 off + medium, Opus 5.5 medium, GPT-6 Luna, GPT-6
Sol, GPT-5.6 Luna none; Haiku 4.5 and GPT-5.6 Luna medium reused from Part 1): **≈ $173**; ReAct for the
same conditions ≈ $387. The Anthropic thinking-on figures rest on ASSUMED output multipliers (medium
2.5× H8's visible output; off 1×) — the pilot replaces them.

## Part 3 — Second workload, frozen as the evaluation set (~2 weeks)
As v1, with one change from the review: the second workload doubles as the **fresh frozen
evaluation set** — built after the scorer and protocol stop changing, never used for
development. **Never released until its results are final:** a release of scored records discloses
per-case ground truth and burns the cases (LIMITATIONS L31), so the frozen set's records, cases and
hidden-derived fields stay unreleased until its results are final. Synthetic tabular (closes the prior-knowledge objection). Gate 3: does the
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
