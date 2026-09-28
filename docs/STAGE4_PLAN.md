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

## Part 2 — Model dimension (~2 weeks) — model comparisons and within-model reasoning interventions (revised 2026-09-27)

**LOCKED 2026-09-28 — the binding text is `docs/HYPOTHESES.md` "Stage 4 Part 2 — PRE-REGISTRATION" (H11, H12;
Stage A / conditional Stage B; cap $100).** The notes below are its planning history.

**CURRENT DESIGN (author's decision 2026-09-27, after the pilot) — supersedes the 2026-09-24 design below where
they differ.**

*Conditions (7):* Haiku 4.5 (REUSED from Part 1) · Sonnet 5 thinking OFF · Sonnet 5 thinking ON (effort: see
item A below) · GPT-5.6 Luna medium (RE-RUN, strict) · GPT-5.6 Luna none · GPT-6 Luna medium · GPT-6 Sol
medium. **Opus 5.5 is DROPPED** (author's decision; consequence: the Sonnet 5 vs Opus 5.5 comparison goes; for
reference, Opus's pilot cost per static trial was 2.2× Sonnet 5 medium's). Every OpenAI cell sends strict tool
schemas.

*What the contrasts are, and are not (reviewer wording fix, binding on every Part 2 document):*
- **Model comparisons** — Haiku 4.5 vs Sonnet 5 (thinking off); GPT-6 Luna vs GPT-6 Sol; GPT-5.6 Luna vs
  GPT-6 Luna (both medium); Sonnet 5 (on) vs GPT-6 Sol (matched list price). Two models differ in training,
  size, tokenizer and data cutoff at once: a model comparison says WHICH MODEL does better on this benchmark,
  never that it "isolates capability". The phrase "isolates capability" is not used.
- **Within-model reasoning interventions** — Sonnet 5 thinking off vs on; GPT-5.6 Luna reasoning none vs
  medium. One request setting changes within one model (it also changes output length and cost, which are
  reported beside it).
- **ReAct vs static compares complete agent configurations** (tools, call budget, prompt, deliberation and
  tokens all differ), not "tool use" alone.

*Primary endpoints are END-TO-END (reviewer fix 3):* every trial counts; an empty or unparseable diagnosis
is a miss on a faulty case and never a false alarm on a control. **Validity is reported separately**, per
condition: the valid-submission rate and the completion status recorded per trial (record schema 1.3:
`tool_config`, per-call provider `completion`, per-trial `completion`). The valid-only view stays descriptive.

*Faulty cases are reported by distinct fault MECHANISM (reviewer fix 4):* pooled faulty-case estimates are
the unweighted mean over the five mechanisms (`harness.sweep_stats.MECHANISM`); the two leakage variants
(descriptive / neutral key names) are one mechanism and are shown separately only where the variant is the
contrast (H8-type), so leakage is never counted twice.

*Baselines on the same cases (reviewer fix 5):* the "what does the agent add?" table — B0/B1/B2/B3/BF vs every
agent row on detection, false alarms (healthy and benign separately), identification and cost — is built for
Part 1 (`docs/audits/agent_value_part1_200.md`, `scripts/agent_value_table.py`) and is regenerated for Part 2.
**B1 is FINAL-EPOCH (declared 2026-09-27 by the author, before the lock):** the reference band describes
the reference runs' FINAL accuracy, so the matching comparison is the run's final-epoch value. Until then B1
tested every epoch, flagging 16/20 healthy controls on the current build (final epoch: 1/20); the every-epoch
variant is reported in the table's appendix. Git trace: B1 was every-epoch from its first commit; the published
Stage-3 figure (1/20) was measured with it on the 9/17 build and does not reproduce from preserved series
(FINDINGS baseline table, footnote §).

*Scorer freeze (reviewer fix 6):* after the author's review of #68 (root_token_v3 / evidence_v2.3) the scorer
is FROZEN; Part 2 is scored with it from its first trial, and Part 2's post-run human audit is the fresh
validation of the frozen scorer — findings after lock go to LIMITATIONS, not a fix cycle, unless a result
would be wrong.

**Pilot results (2026-09-27; 91/91 cells, $1.98; check-reasoning and check-cache passed; NO scores —
`sweeps/stage4_part2_pilot_pilot_report.md`).** Strict mode removed the static parse failures (OpenAI static
10/10 parsed, 0 empty, every condition).
- *A — thinking volume (Anthropic; no thinking-token breakout is returned, so volume = output tokens minus
  visible output, calibrated on Sonnet 5's thinking-disabled calls at 0.58 output tokens per visible
  character, IQR 0.51–0.75 ⇒ roughly ±100 tokens per call):* Sonnet 5 medium static — thinking blocks in
  **8/10** trials, ≈ **215** estimated thinking tokens per call (median; mean ≈ 180); ReAct 3/3 trials, 8 of 14
  calls, ≈ 120 per call with a block. Sonnet 5 off: 0 blocks. Opus 5.5 medium static: 10/10, ≈ 120 median /
  240 mean. So Sonnet 5 medium DOES think in static, but briefly: output 531 vs 448 tokens per static trial
  (off). The within-model contrast at medium is a small intervention. **Proposal (volume only, decided before
  any score exists):** a 10-trial static thinking-volume probe of Sonnet 5 at **high** (its default) and
  **xhigh** (≈ $0.60 total, pilot-report only), then use the LOWEST of {high, xhigh} with thinking in ≥ 9/10
  trials AND median estimated thinking ≥ 4× medium's (≥ ≈ 900 tokens per call); if neither meets it, use
  xhigh and state the contrast's measured size. Medium is not kept as the "on" level unless the author
  prefers comparability with the price-matched GPT-6 Sol medium.
  **APPROVED (author, 2026-09-27) with the rule as written; same no-scores rule as the pilot.** Built:
  `sweeps/stage4_part2_probe_plan.yaml` — 20 static cells, Sonnet 5 at effort high and xhigh (`max_tokens`
  32,768 so the cap cannot truncate the volume being measured), on EXACTLY the 10 (case, arm, repeat) slots the
  pilot ran for Sonnet 5 medium (`plan --pilot-match-plan … --pilot-match-agent static`), so volumes compare on
  the same cases. The rule is applied mechanically by `scripts/thinking_volume.py` (tested:
  `tests/test_thinking_volume.py`); the chosen level is recorded here and in the pre-registration.
  **RESULT (2026-09-28): xhigh, by the pre-declared fallback** — thinking in 10/10 trials at both high and
  xhigh, but median estimated thinking 343 (high) and 734 (xhigh) tokens per call vs medium's 241 (1.4× and
  3.0×; the rule needed 4×). Measured H12 contrast (off vs xhigh): 0/10 vs 10/10 trials with thinking; ≈ 0 vs
  ≈ 734 thinking tokens per call; 448 vs 1,173 output tokens per static trial; $0.0270 vs $0.0343 per static
  trial. Probe cost $0.64 (`sweeps/stage4_part2_probe_thinking_volume.md`).
- *B — GPT-5.6 Luna none, ReAct (1 truncation → empty diagnosis):* runaway WHITESPACE — after 428 valid
  characters of the submit arguments the model emitted " \r" (space, carriage return) 4,037 times until the
  8,192-token cap. The run starts right after a numeric value inside the second evidence item's `detail`
  object, outside any string. JSON allows unlimited whitespace between tokens, so strict decoding permits it;
  it is the Part 1 failure (L35) with different characters. Reported only; no change.
- *C — reasoning tokens:* the report read the wrong field (turn level, not the call's `usage`), so it printed
  0 everywhere. Fixed; OpenAI's reported reasoning tokens now show (e.g. GPT-5.6 Luna medium static 1,974,
  GPT-6 Luna medium static 3,441; Luna none 0 — reported and genuinely zero), and a provider that reports none
  (Anthropic) prints "not reported", never 0.

**Cost re-estimated from the pilot** (per condition: 780 static trials = 108 faulty × 3 arms × 2 repeats + 44
controls × 3 arms; the pilot's measured $ per trial, which includes thinking/reasoning output):

| Condition | $ / static trial (pilot) | $ / ReAct trial (pilot, n = 3) | 780 static | 780 ReAct |
|---|---|---|---|---|
| Haiku 4.5 (REUSED from Part 1) | — | — | 0 | 0 |
| Sonnet 5, thinking off | 0.0270 | 0.0477 | 21.08 | 37.21 |
| Sonnet 5, thinking on (medium) | 0.0279 | 0.0291 → **0.0477** † | 21.72 | 37.21 † |
| GPT-5.6 Luna medium (re-run, strict) | 0.0023 | 0.0041 | 1.76 | 3.20 |
| GPT-5.6 Luna none | 0.0021 | 0.0054 | 1.64 | 4.21 |
| GPT-6 Luna medium | 0.0012 | 0.0023 | 0.90 | 1.79 |
| GPT-6 Sol medium | 0.0207 | 0.0309 | 16.15 | 24.10 |
| **Total (new conditions)** | | | **≈ $63** | **≈ $108** † |

† Sonnet 5 on ReAct: the 3-trial pilot figure (0.0291) is below thinking-off's, so the off figure is used as
the floor (pilot-literal ReAct total ≈ $93). *If the "on" level moves to high/xhigh (item A):* every
+1,000 output tokens per static trial adds $0.010 per trial, i.e. + $7.80 per 780 static trials.
Static-primary Part 2 ≈ **$63** (was ≈ $175 with Opus 5.5 and assumed multipliers); with ReAct ≈ $171.

---

*Design history (2026-09-24), kept for the record; superseded above where they differ:*

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
`check-cache` must for caching. Re-estimate the budget from the pilot before committing. **Pilot as built
(2026-09-27):** `sweeps/stage4_part2_pilot_plan.yaml` — 10 static + 3 ReAct cells per new condition (Sonnet 5
off; Sonnet 5 medium and Opus 5.5 medium with `max_tokens` 16,384; GPT-5.6 Luna medium and none, GPT-6 Luna
medium, GPT-6 Sol medium — every OpenAI cell with strict tool schemas), 91 cells, ≈ $3.75 at the table's
assumed multipliers (the plan header's machine estimate is Haiku-prior-based and understates it). **Pilot rule
(author's):** it reports ONLY cost, token volume incl. thinking, reasoning presence past the first tool call and
strict-mode compliance (`python -m harness.sweep pilot-report`); no score is computed or shown, and pilot
trials are excluded from every analysis. **Lock dependency:** the Part 2 pre-registration is not locked until
the second human audit returns and the metric_inflation matcher decision (L36) is made, so Part 2 is scored
with the final matcher from the start.

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
Sol, GPT-5.6 Luna none; Haiku 4.5 and GPT-5.6 Luna medium reused from Part 1): **≈ $173** — *superseded
2026-09-27: GPT-5.6 Luna medium is now RE-RUN under strict schemas (decision below), ≈ $175*; ReAct for the
same conditions ≈ $387. The Anthropic thinking-on figures rest on ASSUMED output multipliers (medium
2.5× H8's visible output; off 1×) — the pilot replaces them.

**DECISION for Part 2 (approved by the author 2026-09-27) — strict function schemas on every OpenAI
cell, and GPT-5.6 Luna is RE-RUN in Part 2, not reused from Part 1.** Part 1 sent the Responses-API tools
WITHOUT `strict: true` (0 of 6 tools; `harness/llm/openai_client.py::to_responses_tools`), so Luna's
function-call arguments were unconstrained and degenerated in a measurable share of trials
(`docs/audits/stage4_part1_followup.md`: 118 of 1,296 faulty Luna trials with an empty diagnosis — 90
runaway-whitespace truncations, every one salvageable — and 234 valid submissions whose garbled key swallowed
evidence / repair; LIMITATIONS L35). **Decided:** every OpenAI cell in Part 2 sends `strict: true`, with the
tool schemas made strict-compatible (`additionalProperties: false`, every property required, optional fields
nullable) and a unit test on the request shape. Because strict mode changes the condition, **GPT-5.6 Luna
medium is RE-RUN in Part 2** under the same schema as every other OpenAI cell; its Part 1 results are not
reused or pooled with Part 2 (a Part 1 vs Part 2 Luna contrast would confound the model with the tool schema).
Cost: + ≈ $2.01 static / + ≈ $3.19 ReAct (table above), so the static-primary total above rises to ≈ $175.
Haiku reuse is unaffected (0 empty diagnoses on Haiku static; Anthropic tool calls showed none of these
patterns). **Declared in the Part 2 pre-registration** (`docs/PREREG_STAGE4_PART2_DRAFT.md`): Part 1's Luna
numbers were produced under non-strict schemas and are affected by argument degeneration (L35) — end-to-end
detection, identification, evidence and recovery under-state Luna — so no Part 2 contrast uses Part 1 Luna.

## Part 3 — REQUIRED second workload: a small image classifier (DESIGN ONLY, 2026-09-27; author's decision)

**Why.** Every Part 1–2 result is one workload (tabular Adult MLP). A second workload with a different data
modality, pipeline and config layout — faults RE-IMPLEMENTED from scratch, not ported — tests whether the
pattern belongs to the agents or to our first pipeline. It is required, not optional.

**Workload `image_small` (proposal).** A compact CNN (2 conv blocks + 1 linear layer, ≈ 50k parameters), plain
PyTorch — **no new dependency** (IDX/NumPy files read with `numpy`; no torchvision; torch 2.2.2 / numpy 1.26.4
pins unchanged), deterministic CPU kernels, single-threaded loader in reference mode, ≈ 1 min per run on
4 vCPU (well inside the ≤ 10 min rule). Split: train / visible validation / hidden test, fixed by a committed
split file, dataset files vendored with sha256 in the lockstep data target (never fetched at run time).

**Dataset options** (to confirm: licence, size and a timing run before building):

**DATASET DECIDED (author, 2026-09-27): Fashion-MNIST.** Reason (recorded): it is familiar to models, like
Adult, so the PIPELINE changes while prior familiarity stays roughly constant — the second workload then tests
the pipeline, not a familiarity shift. Before any case is built: (1) the data are pinned with sha256 checksums
exactly as Adult's are (`workloads/*/reference/data_manifest.yaml` + the data target; never fetched at run time),
and (2) CNN training is verified BYTE-IDENTICAL across two separate AMD runners (same commit, same image; metrics
and model weights hashed). Only then are operators calibrated and cases built.

| Dataset | Size / shape | Licence | ≈ accuracy, compact CNN, ~1 min CPU | For | Against |
|---|---|---|---|---|---|
| **Fashion-MNIST** (recommended) | 70k, 28×28 grey, 10 classes | MIT | ≈ 0.88–0.90 on a 20k-train subset | small, fast, not saturated, stable run-to-run | widely known (prior-knowledge objection, as Adult) |
| KMNIST (Kuzushiji) | 70k, 28×28 grey, 10 classes | CC BY-SA 4.0 | ≈ 0.90–0.93 | less familiar to models | share-alike terms to check for redistribution |
| CIFAR-10 (subset) | 60k, 32×32 RGB, 10 classes | no explicit licence (research use) | ≈ 0.55–0.65 | colour, harder, noisier | 1 min only on a subset; higher run-to-run spread widens bands |
| sklearn digits | 1.8k, 8×8 grey | BSD | ≈ 0.97 in seconds | trivial to vendor | too small: validation noise swamps mild faults |

**Different pipeline and config layout (by design):** config sections `data / augment / net / optim / sched /
eval` with DIFFERENT key names from workload 1 (e.g. `optim.base_lr`, `sched.warmup_epochs`, `net.in_ch`), a
per-epoch `eval` loop that logs `val_top1` (not `metric_visible_val_acc`), separate `augment` stage, image
normalisation stats in config. The SageMaker training contract (/opt/ml layout, SM_* env vars, log names) is kept.

**Faults — RE-IMPLEMENTED from scratch** (one per mechanism of workload 1, so results are reported by mechanism
across workloads; 3 strengths × 6 seeds each, calibrated like workload 1: clean passes verification and the
mutated run fails it on 3 seeds before merge):
1. **Leakage — label-encoding pixel patch:** a small corner patch whose intensity encodes the label, stamped
   into train and visible-validation images but not the hidden test set (visible metric inflated, hidden
   metric not).
2. **Label corruption:** class-pair label flips in the training labels at fraction p.
3. **Learning-rate schedule fault:** a warmup/step-unit error (epochs read as steps) that spikes the effective
   learning rate early (collapse / slow recovery).
4. **Metric inflation:** the eval loop reports accuracy on a confidence-filtered subset of the validation set.
5. **Crash — shape mismatch:** `net.in_ch` (or the flatten size) disagrees with the data (1 vs 3 channels) →
   crash at the first forward pass.
*(Optional sixth, image-specific, only if calibration allows: train/eval normalisation mismatch — a silent
degradation with no workload-1 analogue, reported separately, never pooled with the five.)*

**Controls:** 20 healthy (seeds) + benign configuration controls in the SAME two forms as workload 1
(changed-value and new-key), 6 types × 12 seeds — e.g. batch size, dropout, epochs, learning rate within the
normal range, weight decay, a random-crop augmentation toggle (new key). ≈ **182 cases** (90 faulty + 20 + 72).

**Cost (agents only; data, calibration and builds are free CPU).** Per model: 816 static trials (90 faulty × 3
arms × 2 repeats + 92 controls × 3 arms) + 540 ReAct (90 faulty × 3 arms × 2 repeats), at Part 1's measured
cost per trial (Haiku static 0.0135 / ReAct 0.0390; GPT-5.6 Luna 0.0029 / 0.0042) and the Part 2 pilot's for
Sonnet 5 (off 0.0270 / 0.0477; on 0.0279 / 0.0477), ×1.2 contingency for a longer training script:

| Models | static | ReAct | total | with ×1.2 |
|---|---|---|---|---|
| **Haiku 4.5 + GPT-5.6 Luna** | 13.38 | 23.33 | **$36.71** | **≈ $44** |
| + Sonnet 5 thinking off | + 22.03 | + 25.76 | $84.50 | ≈ $101 |
| + Sonnet 5 off and on | + 44.80 | + 51.52 | $133.03 | ≈ $160 |

**Gate and freeze.** Built after the scorer and protocol are frozen, used for nothing else, and — as before —
the frozen evaluation set: never released until its results are final (LIMITATIONS L31). Design only: no
code, no cases, no runs until the author approves this section.

*Superseded Part 3 text (2026-09-24), kept for the record:*
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
