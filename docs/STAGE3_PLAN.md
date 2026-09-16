# Stage 3 — The Go/No-Go Plan (v2)

**Supersedes v1** (kept as `STAGE3_PLAN_v1_historical.md`). Revised after two independent
external reviews (2026-09-15). v1's core was sound; both reviewers found holes that would let
a positive result be dismissed as "prompt compliance plus case construction." v2 fixes those
*before* any paid trial.

**Purpose (unchanged).** Decide cheaply whether *"ML debugging agents are strongly dependent
on normative reference context"* is a real, general property (-> full build, main-track) or an
artifact of one model, self-descriptive config keys, and cases constructed to lie outside a
band the prompt hands over (-> workshop/arXiv pilot, stop).

**Statistical-language rules (apply everywhere from now on):**
- A failed pre-registered prediction is reported as **"failed to replicate"** (gate status may
  say REFUTED); equivalence is never claimed without a pre-registered equivalence interval.
- Rationale text supports **"not mentioned,"** never **"not used."** Mechanism claims need a
  behavioral ablation.
- "Confirmed on N operators" is an internal label; the paper says **"supported across N
  operators within one model-workload setting."**
- Every primary contrast carries a case-clustered CI; every rate states its cluster count.

**Everything runs in the canonical container. No study-model paid trial before the
pre-registration commit. Every part ends with a gate.**

---

## Part 0 — Hygiene before science (~2 sessions, free) — BLOCKING

Nothing else starts until this lands. These are integrity issues a reviewer already found.

### 0.1 Citation audit (URGENT; human-verified)
- `docs/operator_sources.md` contains fabricated titles: 2604.04199 (actually Roth, *Which
  Leakage Types Matter?*), 2209.03345 (actually Yang et al., *Data Leakage in Notebooks*),
  2403.16795 (the CMU *operationalize ML* interview study, not a technical leakage paper).
- Action: every citation in `docs/` — title, authors, venue, year, arXiv ID, and the specific
  claim it is cited for — verified **by the author** against the primary page, in one pass,
  recorded in `docs/CITATIONS.md` with a "verified on <date>" column. Tooling may draft; a
  human checks. DECISIONS entry: citation errors found and the verification rule.

### 0.2 One canonical current-state document
- Create `docs/CURRENT_STATE.md`: what exists, what is claimed (with status), what is
  known-limited, what is next — one page, updated at each gate. It is the single source of
  truth; FINDINGS/HYPOTHESES/LIMITATIONS remain the detailed records and must not contradict it.
- Fix the known contradictions now: corrections count (4), the stale LR-mild recalibration
  advice, README (deleted workflow; "containerization next"), `build_all_cases.py`/CI
  "27 cases" -> registry-driven, spec "no paid sweep has run," problem statement "leakage
  deferred."
- Label `harness_spec_v0.1`, `HARDENING_PLAN`, `G1_GATE_PLAN`, and Stage 3 v1 as **historical
  planning documents** in their headers (purpose finished). Keep `problem_statement_v0.3` (scope/RQs)
  and `harness_spec_v0.3` (as-built architecture) **authoritative** — top pointer line + in-place
  status fix, not a historical header. (Corrected 2026-09-15: the earlier "problem_statement_v0.4"
  here was an error — v0.4 was drafted but never committed and does not exist; v0.3 remains the
  authoritative scope document. `harness_spec_v0.3` is the current as-built spec, not historical.)

### 0.3 Reproducible analysis pipeline
- `harness/sweep.py report` and `sweep_stats.py` must be **generic**: driven by the plan file
  and registry, no hardcoded operator list or case count, no Sweep-1 special-casing; the
  `on`->`rule` legacy mapping applied consistently in one place.
- Fix: `--build-missing` re-plan must preserve `--operators`.
- Compute the pre-registered CI on *fraction of gap closed by numbers* (bootstrap of the
  ratio, case-clustered).
- One command regenerates every table in `docs/audits/sweep_*.md` from records; CI runs it
  against a committed **frozen tabular export** and diffs.
- Records release plan: a sanitized `results_release/` export (submissions, tool traces,
  transcripts, scores, verdicts, case metadata, scorer versions) committed at each sweep, with
  a script that rebuilds every reported number from it. Decide now what is sanitized (nothing
  hidden-side; no API keys) and document it.

### 0.4 Evidence scorer v2.1 — one-to-one matching
- Precision and recall via **bipartite matching** (each submitted ref matches at most one GT
  ref and vice-versa; best-match by IoU). Duplicated correct refs and shotgun submissions
  spanning every alternative set are penalized.
- Adversarial tests: duplicate-correct-ref, shotgun-over-all-sets, and the existing
  broad-span cases. Re-score stored trials under v2.1, report v2->v2.1 delta, disclose.

### 0.5 Reference distribution — DONE (adopted 2026-09-15)
- Regenerated the reference from **30 seeds** on native amd64 in CI (never emulated), two-runner
  **byte-exact** (both AMD EPYC 7763). Reported BOTH bands: normal `mean−2σ = 0.843719` and empirical
  2.5th percentile `= 0.844825`. **Tolerance uses `mean−2σ`** (not empirical) — DECISIONS 2026-09-15,
  reasons: (a) the empirical percentile is a high-variance order statistic at n=30; (b) it pins control
  `case_0032` at +8.1e-5, below the ~4e-4 cross-microarch noise floor (L18). Normality **checked**
  (Shapiro p=0.28, n=30, low-power caveat), not assumed; the "5% by construction" language is replaced
  with the measured statement (LIMITATIONS L3). Cases rebuilt (all 33 pass their tier guard under the
  new band; two controls tight). Sweeps 1/2 marked **frozen** (10-seed-era historical artifacts, not
  regenerated). Prior band preserved at `reference/stats.10seed.yaml`.
- **Seed-collision (reported, not resolved here):** reference `[0–29]` overlaps control/calibration
  seeds `{0,1,2}` → control FPR biased **LOW**. Forced next order: **§0.5 → §5.1 → §5.2 → Gate 0.**

**Gate 0:** citations verified; CURRENT_STATE committed and consistent; `report` regenerates
the Stage-2 tables byte-identically from records; v2.1 tests green; 30-seed reference adopted.

---

## Part 1 — Non-LLM baselines (~1 session, free) — CRITICAL

The numbers arm tells the model where the band is, and every faulty case is built to lie
outside it. A one-line rule would match the LLM. The LLM's value must show in attribution,
evidence, and repair — not binary detection.

- **B1 band detector:** flag if any monitored visible metric lies outside the supplied
  interval (exactly what the prompt gives the model).
- **B2 config-delta heuristic:** flag if any config key is non-default / newly present
  relative to the clean workload config; name that key as the "diagnosis."
- **B3 union of B1+B2.** **B4 standardized-deviation score** (max |z| over series) with a
  swept threshold -> ROC.
- Report for each: detection, false-positive rate on controls, identification (B2 names a
  key), evidence (B1 cites the offending series), and repair (B2 can propose "reset the
  key" — which, on the current knob operators, will RECOVER, exposing L19 quantitatively).
- These run on every case in every sweep and appear in every report table as the floor.

**Gate 1:** baselines implemented, run on the Stage-2 case set, tabulated beside the LLM
rows. If B1 ~= LLM on detection (expected), that fact is written down now.

---

## Part 2 — Harness: file-edit mutations + hardened `code_patch` (~3 sessions)

Unchanged in intent from v1 (see v1 Part 1) with these corrections:

### 2.1 Security is a boundary, not a denylist
Keep the AST denylist as defense in depth; the guarantee is the sandbox:
- Verification workspace in an isolated temp dir: **no hidden data, no evaluator code, no
  case dir** reachable; canonical path resolution and symlink rejection on all inputs.
- Subprocess runs with a **scrubbed environment** (no credentials; only the thread pins and
  minimal PATH), non-root, **network verified off** (a test asserts a socket attempt fails),
  and **resource limits**: CPU-time, wall-time, memory, process count, file-size
  (`ulimit`/`prlimit`/cgroup as available in the container).
- Test each: path escape rejected; env contains no key; network attempt fails; a
  fork-bomb/large-file patch is killed and scored as a repair failure.

### 2.2 Outcome attribution (fixes PR #6's survivorship bias)
- **Agent-caused failures are repair failures.** A patched `train.py` that crashes, times
  out, exceeds limits, or produces an invalid/missing checkpoint -> `not_recovered` with the
  cause recorded (`repair_failure_reason`).
- **`verify_error` is reserved for infrastructure failures outside the agent's control**,
  attributed by a pre-flight: the evaluator trains the *clean* file in the same sandbox
  first; if that fails, the environment is at fault (`verify_error`); if it succeeds and the
  patched run fails, the patch is at fault (`not_recovered`).
- Test both branches. Regenerate any affected verdicts.

### 2.3 Everything else as v1 Part 1.1-1.4
File-edit `MutationRecord`; C6 for file edits; W1 for injected code; `code_patch` schema
(one edit; allowed files; exact-once match; size cap; AST parse); oracle = exact revert;
`code_span` + measured `metric_window` evidence; prompt bump (react-2/static-2) with drift
hashes; no new tools.

**Gate 2:** known-answer gate green on a planted file-edit case; sandbox tests green;
attribution tests green; CI full suite green.

---

## Part 3 — The config-silent code-origin operator + representation ablation (~2 sessions)

### 3.1 Naming and criteria
It is a **config-silent, code-origin** fault (not "metric-only" — the static agent sees the
code). Criteria as v1 Part 2.1, plus: injected code must be plausible engineering with no
announcing comment; config.yaml and config.resolved.yaml byte-identical to clean.

### 3.2 Candidate selection — frozen engineering criteria only
Prototype in Step 0 (dev seeds only, 5.2), rank by criteria **without ever looking at agent
performance**: (1) gradient-accumulation bug (`zero_grad` gated on `step % k`) — first
choice; (2) tiny hard-coded clip norm; (3) feature zeroing (likely lacks a visible symptom);
(4) hard-coded LR decay — weakest (the logged `lr` series announces it). STOP if none
qualifies; report.

### 3.3 Strength ladder spanning the band (revives H2 honestly)
Rungs at approximately: **below band, near boundary, moderately outside, far outside.** This
requires a new case category: **sub-band faulty** — mutation present, symptom inside the
healthy band, **detection-only** (recovery undefined; excluded from recovery denominators;
flagged in the card). Build guard and validator gain the category. Pre-register the
detection-vs-standardized-deviation curve (H2') on this ladder.

### 3.4 Representation ablation (isolates semantic legibility)
For ONE existing knob operator (data_leakage), build three variants with identical mechanics:
(a) descriptive key (as now); (b) **semantically neutral key** (e.g. `data.opt_c`); (c) the
same fault injected as a **code edit** with no key. Same strengths, same seeds. This is the
direct test of "self-descriptive keys are detected more readily," and it is what lets "the
data-leakage condition" become a claim about representation rather than about leakage.
(Semantic legibility is *not* equal across current operators; L22 is corrected to say so.)

**Gate 3:** one config-silent operator + the leakage representation triplet built, validated,
known-answer green; Step-0 tables committed; ladder categories validated.

---

## Part 4 — Two-stage telemetry-first protocol (~1-2 sessions)

Mechanism claims need behavior, not rationales.
- **Stage A (telemetry):** tools limited to `read_config`, `read_log`, `query_metrics`,
  `list_files` — **no `read_code`**. Agent must commit `{detected, suspected_series}`.
- **Stage B (diagnosis):** `read_code` unlocked; agent submits the full diagnosis + repair.
- Implemented as a staged tool allowlist in `ToolContext` + a two-part submission; both
  agents; recorded per stage; prompt versioned. The Stage-A commitment is the H8 outcome;
  Stage B is scored as today.
- Cheaper fallback if staging proves heavy: a **code-withheld ablation arm** (no `read_code`
  at all) alongside the normal arm. Prefer staging.
- G3 behavioral ablation for metric_inflation: a variant where val_loss is computed on the
  same subset (removing the internal inconsistency) — detection compared to the original.

**Gate 4:** staged protocol tests green (Stage A cannot read code; Stage B can); a stub agent
round-trips both stages; report shows per-stage outcomes.

---

## Part 5 — Controls and seeds (~1 session, CPU)

### 5.1 Unfiltered controls — **DONE 2026-09-16** (guard + stratification; ≥20 controls still pending §5.2)
- **Retain every completed unmodified run.** Do not reject controls that fall outside the
  band; label them and **stratify** reporting (in-band / out-of-band). The
  control build guard changed from "reject below tolerance" to "record band position."
  *Landed:* `build_case`/`validate_case` record `band_position ∈ {in_band,below_band,above_band}`
  for both metrics (hidden-side only — WALL: never on the public card); control FPR is stratified
  (overall + in_band + out_of_band, per arm, case-clustered CI), keyed on the **VISIBLE** band
  position by mechanism (a false positive is triggered by the metric the agent reads), hidden
  reported alongside as a case-quality label. Frozen sweeps byte-identical (graceful fallback).
- >= 20 unmodified controls on confirmatory seeds. State plainly that these are seed replicas
  of one configuration (seed diversity, not configuration diversity); benign configuration
  variants are a full-study item. *(Still pending — arrives with §5.2's confirmatory-seed rebuild.)*
- **Two follow-ups surfaced during §5.1, sequenced BEFORE Sweep 3 (the study run, Part 9):**
  1. **Native-only artifact generation.** Case/reference builds must run on native amd64 — the
     agent-facing visible metric is per-case platform-sensitive (up to ~2.8σ native-vs-emulated;
     LIMITATIONS L23). ENFORCED by `harness.platform_guard` (build guards refuse under emulation;
     CPU stamped in the hidden card + manifest). §5.2's confirmatory rebuild MUST run native (CI).
  2. **Metric-tier in-band selection bias** (LIMITATIONS L24): the metric guard discards a
     metric-inflation case whose model drifts out-of-band via seed noise — the §5.1 bias in the
     other tier. Retain + label out-of-band metric cases (as §5.1 did for controls) before Sweep 3
     builds more metric cases. Reported, not yet fixed.

### 5.2 Three disjoint seed sets (declared in DECISIONS, enforced by validator)
- **Reference seeds** (band estimation, 30 — currently `[0–29]`; **moves to `[200–229]`** to break the
  §0.5 seed collision). **Development seeds** (operator qualification, Step 0, calibration).
  **Confirmatory seeds** (faulty cases + controls used in sweeps). No overlap; a validator check fails
  on any reuse.
- **Forced order (§0.5 ruling):** §5.1 (retain + label out-of-band controls) MUST land BEFORE §5.2
  moves the reference off `[0–29]` — else the `build_case.py` control guard silently rejects the
  out-of-band controls. Sequence: **§0.5 (done) → §5.1 → §5.2 → Gate 0.**

**Gate 5:** >= 20 controls validated with band-position labels; seed-set disjointness enforced.

---

## Part 6 — Anchor arms (~half session)

- **off:** no reference. **stats:** bare calibration statistics — mean and SD (and the
  interval) with **no evaluative language** (no "healthy," no "range," no "achieve").
  **rule:** stats + explicit decision sentence. `rule` = `stats` + one sentence, by
  construction; per-arm drift hashes; legacy `numbers` -> historical.
- The claim is stated at whichever level the data supports: "numerical context" (if stats
  works) vs "normative reference context" (if only labeled/rule works). Pre-register both
  readings.

---

## Part 7 — Second provider adapter (~1 session) — non-study smoke only

- One adapter (GPT-5-mini or Gemini 3.1 Flash-Lite): tool-call translation, usage, pricing,
  retry, API model string. Tests on fakes.
- **Smoke test only on a non-study prompt and a non-study case** (a throwaway synthetic case
  not in any sweep) — no study-model exposure before pre-registration. Record the folding
  rate per provider as a secondary.

---

## Part 8 — Pre-registration (commit BEFORE any study trial)

- **H7 (headline):** reference context restores detection — estimated **per named model and
  per operator**, plus a pooled hierarchical (mixed-effects, case-clustered) estimate.
  Confirming: stats - off >= +0.40 with CI excluding 0 for each model, *and* on the
  config-silent operator, *and* on the code-edit leakage variant. Refuting: gap < +0.15 on
  the config-silent or code-edit variants (representation was the mechanism), or a model with
  no gap. **Equivalence interval** pre-declared for "no gap" (e.g. |delta| < 0.10).
- **H8 (mechanism, behavioral):** Stage-A (telemetry-only) detection is raised by the
  reference arm; the config-withheld/code-withheld comparison isolates metrics vs legibility.
  No rationale-based inference.
- **H2' (detection vs standardized deviation):** monotone curve across the spanning ladder;
  pre-registered fit and threshold with CI. Obviousness operationalized *only* by
  pre-declared variables (|z| of visible metric; crash yes/no; key legibility class; artifact
  count) — never assigned post hoc.
- **Model-tier heterogeneity** (was H5): descriptive, per model; not a causal capability
  test. Frontier slice deferred to 3b.
- **Recovery discrimination — validity check, not a hypothesis:** DegenerateAgent must fail
  on the code operator (harness validity). *Research question:* recovery conditional on
  correct detection+identification, evaluated against a **pre-specified panel of plausible
  admissible wrong repairs**.
- **Baselines B1-B4 reported in every table.** LLM value = (identification, evidence, repair)
  beyond B3, with CIs.
- **Cell equation written out** before budgeting, with the control cross-product bounded:
  controls run in the static protocol x 3 arms x 1 repeat only; ReAct on a pre-specified
  subset. Cost cap and repeats declared. Deviations appended, never edited.

---

## Part 9 — Run and decide (~$40-60)

- **Primary protocol:** static (standardized) agent across the full matrix — 2 models x 3
  arms x operators {data_leakage triplet, config-silent, label_corruption, metric_inflation
  (+ ablation variant)} x spanning ladder x 2 confirmatory seeds x 2 repeats + >= 20 controls.
- **ReAct:** pre-specified subset (one seed, one repeat, all arms) for the tool-use contrast.
- Two-stage protocol on the config-silent operator and the leakage triplet.
- Verify in-container; baselines on every case; report regenerated by the one command.

**Decision table (pre-registered):**

| H7 per-model (both) | H8 behavioral | H7 on code-edit & config-silent | Verdict |
|---|---|---|---|
| yes | yes | yes | **GO** — full build (2nd workload, ~8 operators, ~100 cases, frontier tier, token-matched baseline, human realism audit); main-track target |
| yes | yes | no | Partial — effect depends on representation; workshop with the representation finding as the honest headline |
| yes | no | — | Partial — context helps config-reading, not health assessment; workshop |
| no | — | — | **NO-GO** — model-specific; workshop/arXiv pilot on the benchmark + audited findings |

---

## Sequencing
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 (commit) -> 9. Parts 5-7 can overlap with 2-4. The
paper skeleton is drafted in parallel from frozen instrument sections; results wait for Part 9.

## Deferred to the full study (explicitly)
Second workload; frontier tier; token-matched iterative no-tools baseline; human realism and
evidence-sufficiency audit; benign configuration-variant controls; required confidence output
(cheap — may be added at Part 8 if trivial).

## Risks
- Step 0 finds no clean code fault -> add a fifth candidate; else defer H8 to the second
  workload and say so.
- Staging is heavier than expected -> code-withheld ablation arm as the fallback.
- Baselines match the LLM on everything -> that is the finding; the paper's contribution is
  then the instrument plus the negative result about agentic detection — publishable, and far
  better learned now.
