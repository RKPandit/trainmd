# Stage 3 — The Go/No-Go Plan (v3, scoped)

**Supersedes v2** (kept as `STAGE3_PLAN_v2_historical.md`; v1 likewise). v2 was correct about
*what* would make the finding defensible and wrong about *how much* to build first. This
version keeps every item whose outcome changes what a reviewer can conclude, and defers the
rest with explicit revival conditions.

**The test applied to every item:** *does a reviewer's conclusion depend on this, or does it
only change how comfortable we are?* Items failing that test are deferred, not deleted.

**Purpose (unchanged).** Decide cheaply whether *"ML debugging agents are strongly dependent
on normative reference context"* is a real property (-> full build, main-track) or an
artifact of one model, a self-descriptive config key, and cases constructed to lie outside a
band the prompt hands over (-> workshop/arXiv pilot, stop).

**Cost and time.** ~1 week, ~$25. (v2 was ~3-4 weeks, ~$100.)

**Carried forward from v2, unchanged and still binding:** the statistical-language rules
(failed-to-replicate vs refuted; not-mentioned vs not-used; cluster counts on every rate;
equivalence intervals for "no gap"); everything runs in the canonical container on native
amd64; no study-model paid trial before the pre-registration commit; every part ends with a
gate.

---

## Part 0 — Hygiene (DONE, except §5.1/§5.2 in flight)

§0.1 citations · §0.2 CURRENT_STATE + guard · §0.3 reproducible pipeline + release ·
§0.4 evidence scorer v2.1 · §0.5 30-seed reference — all landed.
In flight: §5.1 (retain + label out-of-band controls), §5.2 (disjoint seed sets), then
**Gate 0 closes and instrument work stops.**

---

## Part 1 — Non-LLM baselines (~1 session, free) — HIGHEST VALUE REMAINING

Without these the headline is dismissible in one sentence: *a one-line threshold rule would
match this*. Every faulty case is built to lie outside the band, and the numbers arm hands
the model the band. The LLM's value must appear in attribution, evidence, and repair — or
not at all, which is itself the finding.

- **B1 band detector** — flag if any monitored visible metric lies outside the supplied
  interval (exactly what the prompt gives the model).
- **B2 config-delta heuristic** — flag if any config key is non-default / newly present;
  name that key as the "diagnosis."
- **B3 union of B1+B2.** **B4 standardized-deviation score** (max |z|) with a swept
  threshold -> ROC.
- Report for each: detection, control false-positive rate, identification (B2 names a key),
  evidence (B1 cites the offending series), repair (B2 proposes "reset the key" — which on
  the current knob operators will RECOVER, quantifying L19).
- Run on every case in every sweep; appear in every report table as the floor.

**Gate 1:** baselines tabulated beside the LLM rows on the existing case set. If B1 ≈ LLM on
detection, that is written down now, not discovered by a reviewer.

---

## Part 2 — Representation ablation: the cheap test of the legibility confound (~1 session)

Currently every detection proceeds by reading a non-default config knob whose name often
describes the fault (`label_noise_fraction` nearly names it; `include_aux_feature` does not).
So the finding may be about *reading a suspicious name*, not about assessing health.

**The cheap decisive test:** build a **semantically neutral key** variant of `data_leakage`
with identical mechanics — same fault, same strengths, same seeds, key renamed to something
uninformative (e.g. `data.opt_c`). One operator change, no new machinery.

- If detection collapses on the neutral variant, the effect was substantially legibility.
- If it holds, legibility is not the mechanism, and the expensive code-origin operator is
  unnecessary.
- Either way it is answered for ~one session instead of four.

Pre-register both readings (Part 5). Keep the descriptive variant as the comparison arm.

**Gate 2:** neutral-key variant built, validated, known-answer gate 0 FAIL, W1 clean
(the new key must not name the fault or collide with an operator-id segment).

---

## Part 3 — Second provider (~1 session, ~$2 smoke) — non-study smoke only

One model is a curiosity; two providers is a property of current agents.

- One adapter (GPT-5-mini or Gemini 3.1 Flash-Lite): tool-call translation, usage, pricing,
  bounded retry, API-reported model string. Tests on fakes.
- **Smoke only on a non-study prompt and a throwaway case** — no study-model exposure before
  the pre-registration commit.
- Record the structured-output folding rate per provider (a secondary finding from Sweep 1).

**Gate 3:** adapter smoke-tested; prompt text byte-identical across providers (literal-slice).

---

## Part 4 — Anchor arms: bare statistics (~half session)

The v2 "numbers" arm said *"Healthy runs achieve … healthy range …"* — normative language,
not bare numbers.

- **off** (no reference) · **stats** (mean and SD / interval, NO evaluative words — no
  "healthy", no "achieve") · **rule** (stats + the explicit decision sentence).
- `rule` = `stats` + one sentence by construction; per-arm drift hashes; legacy `numbers`
  marked historical.
- The claim is then stated at the level the data supports: *numerical context* (if stats
  works) vs *normative reference context* (if only rule works).

---

## Part 5 — Pre-registration (commit BEFORE any study trial)

- **H7 (headline):** reference context restores detection — estimated **per named model and
  per operator**, plus a pooled hierarchical (case-clustered) estimate. Confirming: stats −
  off ≥ +0.40 with CI excluding 0 for each model **and** on the neutral-key variant.
  Refuting: gap < +0.15 on the neutral-key variant (legibility was the mechanism), or a
  model with no gap. **Equivalence interval** pre-declared for "no gap" (|Δ| < 0.10).
- **H8 (mechanism, cheap form):** the neutral-key variant isolates legibility. Detection on
  neutral vs descriptive keys, same mechanics. (The stronger telemetry-first protocol is
  deferred — see below.)
- **Baselines B1–B4 in every table.** LLM value = (identification, evidence, repair) beyond
  B3, with CIs.
- **Recovery is reported as a compliance measure**, not repair competence, until a
  wide-admissible operator exists (L19). DegenerateAgent's 18/18 stands as the evidence.
- **Cell equation written out** before budgeting; controls in the static protocol × arms × 1
  repeat; ReAct on a pre-specified subset. Cost cap and repeats declared. Deviations
  appended, never edited.

---

## Part 6 — Run and decide (~$25)

- **Primary protocol:** static agent across the matrix — 2 models × 3 arms × operators
  {data_leakage (descriptive + neutral), label_corruption, metric_inflation} × strengths ×
  2 confirmatory seeds × 2 repeats + ≥ 20 controls.
- **ReAct:** pre-specified subset (one seed, one repeat, all arms) for the tool-use contrast.
- Verify in-container; baselines on every case; report regenerated by the one command.

**Decision table (pre-registered):**

| H7 per-model (both) | Neutral-key holds | Verdict |
|---|---|---|
| yes | yes | **GO** — full build (2nd workload, more operators, frontier tier, and *then* the deferred items below); main-track target |
| yes | no | Partial — the effect is substantially config legibility; workshop with that as the honest headline |
| yes | ambiguous | Revive the code-origin operator (Deferred A) to settle it, then re-decide |
| no | — | **NO-GO** — model-specific; workshop/arXiv pilot on the benchmark + audited findings |

---

## Deferred, with explicit revival conditions

These were in v2. Each is real work with real value; none changes a reviewer's conclusion
*at this stage*. Revive only on its stated condition.

| Item | Why deferred | Revive when |
|---|---|---|
| **A. Code-patch harness + config-silent code-origin operator** (file-edit mutations, `code_patch` repair, sandbox with resource limits/network isolation/AST denylist, attribution logic) | ~3-4 sessions of machinery to enable ONE operator; the neutral-key variant (Part 2) tests the same confound for ~1 session | The neutral-key result is **ambiguous**, or a code-repair experiment is actually planned (not merely possible) |
| **B. Two-stage telemetry-first protocol** (staged tool allowlist, two-part submission) | The strongest mechanism test, but heavy; a code-withheld ablation arm gets most of it | H7 confirms and a main-track submission needs a behavioral (not rationale-based) mechanism claim |
| **C. Sub-band case category** (fault present, symptom inside the band, detection-only) | New validity tier + guard + validator branches, to add H2 rungs | H2' becomes a headline claim rather than an exploratory one |
| **D. Frontier-model slice** (Sonnet/Opus) | ~$60-120; answers capability-vs-context, which is a second-paper question | GO verdict reached; run it as part of the full build |
| **E. Wide-admissible-repair operator** (makes recovery discriminate, closes L19) | Recovery is not carrying the headline; reporting it as a compliance measure is honest and free | Recovery becomes a claimed contribution |
| **F. Token-matched iterative no-tools baseline** | Isolates tool use from deliberation; H7 is about context, not tools | The ReAct-vs-static contrast becomes a headline claim |
| **G. Human realism / evidence-sufficiency audit** | Full-study item | Main-track submission |
| **H. Second workload** | Answers cross-modality transfer, which only matters once the finding is solid on one | GO verdict reached |
| **I. CI parallelization** (`pytest -n auto`) | Comfort, not conclusions — though the ~1h nightly is a real tax | It blocks iteration during the full build |

---

## Sequencing
Gate 0 (§5.1, §5.2) → Part 1 → Part 2 → Part 3 → Part 4 → Part 5 (commit) → Part 6 → decide.
The paper skeleton is drafted in parallel from frozen instrument sections; results wait for
Part 6.

## The standing rule for the rest of this project
Before building anything, ask: **does a reviewer's conclusion depend on this?** If the honest
answer is "it makes me more comfortable," it goes in the deferred table with a revival
condition. Instrument work stops at Gate 0 and resumes only when an item's condition fires.
