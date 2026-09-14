# TrainMD — Findings

**What this document is.** The scientific narrative: what we have learned, the evidence
for it, how we interpret it, and what would change our minds. It grows one section per
sweep, and the **Standing findings** block at the top is *revised* as evidence accumulates
— strengthened, qualified, or refuted. This is the paper's Results + Discussion in draft.

**How it relates to the other running documents.** DECISIONS.md records *what* was decided
and why; RESEARCH_LOG.md records *how it felt to not know yet*; HYPOTHESES.md holds the
frozen pre-registration and its terse verdicts; `docs/audits/` holds the machine-generated
evidence. This document is the only place findings are *argued*. Every number here is
traceable to an audit file named in its section.

**Finding shape (used throughout):** Claim → Pre-registered prediction (if any) → Evidence
(table, numbers) → Interpretation → What would change our mind → Status.

**Status vocabulary:** `confirmed` (pre-registered criteria met) · `sharpened` (confirmed
with a more precise mechanism than predicted) · `refuted` (pre-registered criteria failed) ·
`unplanned` (not pre-registered; observed) · `pending replication` (one model/workload only).

---

## Standing findings (cross-sweep; revised as evidence accumulates)

| # | Finding | Evidence so far | Status |
|---|---|---|---|
| S1 | **Positive-symptom blindness.** Agents miss faults whose visible metrics look *good*, and a numeric reference band + decision rule restores detection. | Sweep 1: anchor-off gap 0.556, 95% CI [0.327, 0.774]; → 1.000 with the band+rule. **Confound: symptom direction ≡ operator identity (all positive = data_leakage); anchor = norm+rule, not norm alone.** | pilot support · confound-limited · pending factorial replication |
| S2 | ~~Detection follows symptom sign first, then magnitude.~~ **H2 (a fitted σ threshold) is REFUTED** — no threshold fitted, pooled curve non-monotone. Exploratory successor (post-hoc, to pre-register): symptom *sign* moderates magnitude→detection. | Sweep 1 H2 per-case table. | refuted (prediction) · exploratory successor · pending prospective test |
| S3 | **The reference band is a trade: it rescues true detection and induces false alarms on healthy runs.** | Sweep 1: anchor-on control FPR 0.222, 95% CI [0.0, 0.5] — 4/18 from just 2 unique healthy cases (not a population rate; the width argues for 20+ controls). | unplanned · under-powered · pending replication |
| S4 | **The ReAct−static gap is real but does not isolate tool use.** ReAct beats static +0.135 evidence F1 overall, 95% CI [0.075, 0.204], most on subtle noise; leakage sub-claim +0.006 (≤0 criterion **not** formally met). The arms also differ in calls, deliberation, tokens, and prompt text. | Sweep 1 H6 + cost table. | overall confirmed · sub-claim not formally confirmed · confounded (needs token-matched baseline) |
| S5 | **On the strict endpoint, this model names faults somewhat more reliably than it autonomously repairs them.** id − *strict* recovery is 0.10–0.24 (CI excludes 0) on 3/4 operators; *semantic* recovery nearly closes it, so most of the gap is submission-format compliance + strict admissibility. Pre-registered direction (recovery > id) refuted. | Sweep 1 H3 (strict primary + semantic). | refuted (predicted direction) · modest id>strict dissociation · pending replication |
| S6 | **Diagnostic outcomes are reproducible under nondeterminism; identification agreement drops on the hardest fault.** | Sweep 1 H4: mean agreement 0.82; leakage identification agreement 0.71 vs lr 0.96. | partially confirmed · pending replication |
| S7 | **Adult+MLP is robust to symmetric label noise**; label corruption is a *subtle* fault on tabular data. Even the operator's calibrated ladder (33/38/42% flips) degrades accuracy only ~1–2 pt. | Calibration sweeps (DECISIONS 2026-09-11, ladder 0.33/0.38/0.42). | unplanned · workload-specific |
| S8 | **A visible knob without a norm is not a signal.** A configuration value that names a fault, sitting in plain view in the prompt, does not trigger detection unless the agent also has a reference for what is normal — the missing baseline, not missing information, is what blinds it. | Sweep 1: `label_noise_fraction: 0.38` present, un-truncated, in 18/18 static anchor-off contexts and echoed in the response, yet static detected the fault 1/18 vs ReAct 11/18. | unplanned · pending replication |
| S9 | **~1 in 10 repairs is misplaced — an agent-compliance failure, counted only toward the semantic endpoint.** The model emits a well-formed repair as text in a sibling string field instead of the structured tool argument; this is a failure of the system under test, so it does *not* count toward strict autonomous success (it is recovered post-hoc for the semantic endpoint only). | Sweep 1: 31/324 (≈9.6%) folded; strict vs semantic recovery reported side by side. | unplanned · pending replication |
| S10 | **The workload constrains which positive-symptom mechanisms are possible: row memorization cannot inflate a metric here.** A validation metric can be inflated by memorized training rows only up to *train* accuracy; Adult/MLP's train–val gap is ~0.010, so the memorization ceiling (~0.863) sits only ~0.003 above the visible band edge (0.860) — no headroom for a laddered positive symptom. The viable second positive-symptom mechanism on this substrate is metric-side (biased computation), not data-side (overlap). | Step-0 (in-container, thread-pinned): overlap augmented val_acc ≤ 0.857 (below edge) for p∈{0.05,0.15,0.30}×seeds{0,1,2}; train_acc 0.862–0.864; biased-metric mechanism (a) clears the band on a plausible→implausible ladder (reported ≈0.88/0.94/0.98) with the checkpoint unchanged. | unplanned · workload-specific |
| S11 | **Adult contains duplicate records — 12 appear in both train and the hidden test by content hash — though the splits are index-disjoint.** A pre-existing dataset property, not an operator-induced leak; disjointness checks must therefore test *non-increase* of overlap, not absolute content-disjointness. | Step-0 row-hash intersection = 12 of ~30k; `data_prep` partitions one permutation (index-disjoint by construction). | unplanned · dataset property |

---

## Sweep 1 (2026-09-12) — single model, single workload, two agents, anchor on/off

**Design (frozen at commit `75b6e2d`, pre-registered in HYPOTHESES.md).** 27 cases on the
tabular Adult/MLP workload — four operators (lr_warmup, label_corruption, data_leakage:
silent; shape_mismatch: crash) × 3 strengths × 2 seeds, plus 3 healthy controls — × 2 agents
(ReAct tool-using; static full-context) × 2 anchor conditions (reference band on/off) × 3
repeats = **324 trials**, claude-haiku-4-5 at temperature 1.0. Order randomized (seed 1234).

**Compute statement.** Agent phase: 324 trials, **$12.76 estimated** (ReAct $10.81, static
$1.95; actual console spend: *pending entry in `sweeps/sweep1_manifest.yaml`*), 0 failures,
~90 min wall. Verify phase: 286 recovery reruns × 3 hidden seeds, **46,966 CPU-s ≈ 13.0
core-hours**, CPU only. Hardware and lockfile hash: `sweeps/sweep1_manifest.yaml`.

**Gate before running.** Known-answer gate 189 checks / 0 FAIL on all 27 cases; audit-index
clean; validate-all 27/27; plan file git-clean and build_id-pinned.

**Evidence files.** `docs/audits/sweep_sweep1_20260913.md` (corrected report),
`docs/audits/sweep_sweep1_20260912.md` (original), `docs/audits/sweep1_diagnostics_20260912.md`.

### Post-hoc scoring corrections (disclosed; see HYPOTHESES.md Results and DECISIONS 2026-09-13)

Three Sweep-1 corrections were applied, disclosed, with originals kept beside corrected values
in every table. The first two were **scoring/schema artifacts, not model behaviour**; the third
(#3) is **model-side output folding, not a harness bug** — we recover a well-formed repair the
model misplaced. All three *removed* a harness-imposed penalty on the model; none changed ground
truth to raise a score. Found by the read-only diagnostics and corrected by principle — never by
copying observed outputs into ground truth.

1. **Identification** was scored by exact membership in enumerated class sets; the model
   wrote correct free-form labels (`excessive_learning_rate`, `excessive_label_noise`,
   `auxiliary_feature_leakage`) that scored 0. Replaced by **root-token matching** defined from
   each fault's *concept* (lr: `learning_rate|lr`; label: `label` + `nois|corrupt|flip|…`;
   leakage: `leak`; shape: `shape|dimension|dim`), with a uniqueness guard (a two-fault or
   cross-fault label fails). 190 of 324 identification results flipped wrong→correct; 0
   regressions. Judgment call logged: leakage labels naming only the *mechanism*
   (`aux_feature_enabled`) without the *concept* (`leak`) are genuine misses — identification
   scores the fault class; the evidence axis credits the mechanism. Touches **H3, H4 only.**
2. **Shape recovery** was 0.347 because 29 trials submitted `input_dim: null` — "remove the
   injected override" — which the schema could not express. That is the *more faithful* repair
   (the clean config has no such key). `null` now means *unset* for keys an operator declares
   absent-when-clean, verified oracle-equivalent for all three such keys. 29/29 re-verified
   recovered → **0.347 → 0.750**; 18 genuine no-repair failures stand. Touches the shape
   recovery axis only.
3. **Folded repair recovery (`parser_fix_v1`) — MODEL-SIDE output folding, not a harness parser
   bug.** Some submissions emitted the repair as text (`<parameter name="repair_spec">{…}`, the
   text-tool idiom) *inside* the `rationale` string instead of the structured `repair_spec` field;
   the harness recorded the structured tool_use input faithfully. We now recover a single
   well-formed `{repair_type, patches}` object the model misplaced (strict: no key scraping,
   ambiguous → not recovered) and flag it, live and historically. This raises recovery on every
   faulty operator that had folded repairs. See **F9** for the folding rate as a finding in itself.

**Unchanged by any correction:** detection and evidence — therefore H1, H2, H6, and the controls
finding stand exactly as pre-registered. Recovery moves (Corrections 2–3), sharpening H3.

**The corrected recovery ordering is the designed difficulty gradient.** Final recovery —
shape_mismatch **0.944**, lr_warmup **0.903**, label_corruption **0.583**, data_leakage **0.431**
— ranks the operators exactly as the benchmark intended them to be hard: a mechanical crash with a
single correct value is the most repairable, an inverted-symptom leak the least. That gradient was
invisible in the raw table (shape 0.35, silent ops ≈0.39–0.51), *flattened by three harness
artifacts* — narrow class sets, an unexpressible unset, and folded repairs. Removing them let the
intended structure show through.

### F1 — Positive-symptom blindness (H1) · pilot support (confound disclosed)

**Claim.** Agents diagnose faults whose observable symptoms are *bad* far more reliably than
faults whose symptoms are *good*; without a baseline for "normal," a positive symptom reads
as success.
**Pre-registered prediction.** Anchor-off leakage detection ≥30 points below matched
negative-symptom detection; anchor-on gap ≤10.
**Evidence** (`sweep_sweep1_20260913.md`, Primary contrasts). Anchor **off**, pooled and
case-clustered: gap (negative − positive) **0.556, 95% CI [0.327, 0.774]** (pos 0.083 / 6 cases,
neg 0.639 / 12 cases). Nearest-σ matched mean paired gap **0.528**. Anchor **on**: **1.000 /
1.000** (gap 0).
**Interpretation.** The pooled contrast is large and in the predicted direction: a model that
located the leaking feature (Sweep-0 transcript, RESEARCH_LOG 16) still judged a 0.90-accuracy run
healthy with no reference for what 0.90 *means* here, and one healthy-band line flips it.
**Stage-0 caveats (external review, 2026-09-13) — why this is pilot, not a clean confirm.**
(a) **Symptom direction is perfectly confounded with operator identity** — every positive-symptom
case is data_leakage, every negative case is lr_warmup/label_corruption — so the gap may reflect
symptom direction *or* leakage being intrinsically harder; only a second positive-symptom operator
separates them (the matched-σ pairing narrows σ but not this confound). (b) The pre-registered
**"matched σ-distance" comparison was not performed** by the pipeline (it pools); the nearest-σ
pairing is a supplement (see L12). (c) The anchor manipulation **confounds a numeric reference with
an explicit decision rule** — Sweep 1 shows **norm + rule** restores detection, not that a norm
alone does (see L10; three-arm design in open questions).
**What would change our mind.** A second positive-symptom operator (breaking the confound); a
three-arm none/numbers-only/numbers+rule anchor; a second model/workload.
**Status.** **Pilot support** — pre-registered pooled contrast large and in the predicted
direction, pending factorial replication. (Was "confirmed"; downgraded on external review for the
operator-identity confound and the un-run matched analysis.)

**Pass-2 mechanism addendum (2026-09-13; diagnostics2 §1).** The mechanism is not a failure to
investigate. Of the 32 anchor-off leakage trials that returned `detected=false`, **0 never looked**
— every one read `train.py`, and **35 of 36** named the auxiliary feature; only **2–3** used the word
*leakage*, and the dominant move was to declare the run healthy (dismissal language in **13/18**
ReAct and **17/18** static; "accuracy good/high" in ~half). So F1 is **looked-but-didn't-recognize,
with rationalization**: the agent sees the leaking feature and, because the outcome looks good,
reframes it as normal rather than a fault. Verbatim (≤40 words each):
> (ReAct, case_0004) "The training run completed successfully with exit code 0. Metrics: training loss and validation accuracy show normal, healthy training dynamics. Configuration: all hyperparameters are reasonable. Logs: no errors or warnings."
> (ReAct, case_0013) "Configuration analysis: learning rate 0.01 (reasonable for Adam on tabular data), batch size 256 (reasonable), optimizer Adam with weight_decay 0.0001 (standard). No incident found."
> (ReAct, case_0014) "Learning rate 0.01 (reasonable for Adam), batch size 256 (reasonable), MLP hidden dims [64, 32], no dropout, ReLU activation. The run looks healthy."

### F2 — A σ detection threshold (H2) · REFUTED (prediction not met); new exploratory hypothesis

**Pre-registered prediction.** A **single monotone detection-vs-σ curve with a fitted 50% threshold
and interval.**
**Outcome — REFUTED.** No threshold was fitted, and the pooled detection-vs-σ curve is
**non-monotone**. The pre-registered prediction is not met. (This was previously labelled
"sharpened," which presented a failed prediction as a success; corrected on external review.)
**Evidence** (diagnostics §3; H2 block), reported primarily against **visible signed σ** (what the
agent observes; hidden σ is benchmark harm, separate). Negative symptoms, anchor-off:
label_corruption at σ_hidden ≈ 11–18 detects 0.33–0.50; lr_warmup at σ ≈ 24 detects 0.67; at σ ≈ 44
detects 1.00. Positive symptoms, anchor-off: leakage detects 0.00–0.33 at σ_hidden = 6, 21, 23, 56,
64 — no trend. Anchor-on: 1.00 everywhere (ceiling; σ invisible). Table retained.
**New EXPLORATORY hypothesis (post-hoc, not confirmatory).** *Symptom **sign** moderates the
magnitude→detection relationship* — within negative-symptom faults detection rises with σ;
positive-symptom faults floor regardless. To be **pre-registered and tested prospectively** in a
later sweep, not claimed from this data.
**Caveat (see L1).** lr_warmup's three strengths share σ = 44.6, so the negative-symptom curve has
one point between σ ≈ 18 and σ ≈ 44 — too sparse to fit a threshold even post-hoc.
**Status.** **Refuted** (pre-registered prediction). The moderation idea is exploratory, pending a
prospective pre-registration with a denser σ ladder (Sweep 2).

### F3 — The reference band is a trade (unplanned) · unplanned

**Claim.** The intervention that cures positive-symptom blindness induces false alarms on
healthy runs whose metrics sit at the band edge.
**Evidence** (Primary contrasts; controls block). Anchor-on control detection FPR **0.222, 95% CI
[0.000, 0.500]** — but this is **4/18 trials from only 2 unique healthy cases (case_0005,
case_0006)**, bootstrapped over the **3** control cases. It is **not a population false-positive
rate**; the CI runs from 0 to 0.5, and that width is precisely the argument for **20+ controls in
Sweep 2**. Anchor-off control FPR was 0/18. Rationales cite band-edge values (one healthy run
genuinely above 0.8599; one misread 0.8546 as "below the floor 0.8538").
**Interpretation.** Part of this cost is *structural*: a mean±2σ band places ~5% of healthy
runs outside it by construction. Part is the model over-reading an edge. The band's benefit
(F1) is bought with a measurable false-alarm cost — which is the honest way to present the
intervention.
**What would change our mind / next.** A 3σ band (pre-registration candidate for Sweep 2)
should cut structural FPs without losing true detections, whose σ-distances are ≥ 6.
**Status.** Unplanned; pending replication.

### F4 — The ReAct−static gap (H6) · overall confirmed; sub-claim not formally confirmed; confounded

**Claim.** The ReAct agent out-scores the static full-context baseline on evidence — most on
subtle faults, near-zero on leakage — at ~5.5× the cost.
**Pre-registered prediction.** ReAct ≥ +0.10 evidence F1 overall; ReAct − static ≤ 0 on
leakage while > 0 on negative-symptom faults.
**Evidence** (Primary contrasts; H6 block). Overall ReAct − static evidence F1 **0.135, 95% CI
[0.075, 0.204]** (24 cases) — the point meets ≥0.10 but the CI lower bound dips below it, so the
overall criterion is met at the point estimate, not robustly. Per operator: label_corruption
**+0.32**, lr_warmup **+0.17**, shape **+0.04**, data_leakage **+0.006**, control 0. Cost: ReAct
$10.81 / static $1.95 (**5.5×**).
**Sub-claim.** Leakage required ReAct − static ≤ 0; observed **+0.006 — practically zero but
formally NOT confirmed** against a ≤0 criterion.
**Interpretation + confound (external review).** Where the symptom is subtle, stepwise querying
finds evidence a one-shot read skims past; where the answer is in code (leakage), seeing everything
at once is as good. But **ReAct vs static does not isolate tool use**: the arms also differ in call
count, deliberation, context ordering, token budget, and prompt text — the ReAct prompt names
learning rate / batch size / optimizer, which may itself advantage lr_warmup. A **token-matched
deliberative baseline** is needed to attribute the gap to tools.
**Status.** Overall confirmed at the point estimate (CI dips below 0.10); leakage sub-claim not
formally confirmed (+0.006 vs ≤0); mechanism confounded pending a token-matched baseline.
**Scorer note (Stage 2).** These evidence F1 numbers are **evidence_v1**. From Sweep 2 the primary
scorer is **evidence_v2** (IoU + width penalty + required bounds + alternative sets; LIMITATIONS L17,
DECISIONS 2026-09-13). On Sweep-1 data v2 materially changes only `shape_mismatch` (mean evidence F1
0.807→0.607, from over-broad traceback spans) and nudges `lr_warmup` (+0.009); the silent-operator
means are unchanged. v1 is preserved beside v2; the per-arm H6 gap will be recomputed under v2 in the
Sweep-2 report — this Sweep-1 verdict is reported under v1 as originally run.

### F5 — Naming vs repairing (H3) · refuted (predicted direction); modest id>strict dissociation

**Claim (as pre-registered).** Recovery exceeds identification — agents fix faults without
naming them.
**Endpoints.** The primary endpoint is **STRICT recovery** (a valid *structured* repair submitted
and verified — autonomous success). **SEMANTIC recovery** (strict + repairs recovered post-hoc from
folded output) is secondary. The earlier verdict ("no dissociation") was read off the *semantic*
endpoint; recomputed here against **strict** as primary, with case-clustered CIs:

| operator | identification | strict recovery | semantic recovery | id − strict (95% CI) | id − semantic (95% CI) |
|---|---|---|---|---|---|
| shape_mismatch | 0.986 | 0.750 | 0.944 | **0.236 [0.208, 0.250]** | 0.042 [0.014, 0.069] |
| lr_warmup | 0.931 | 0.833 | 0.903 | **0.097 [0.056, 0.139]** | 0.028 [0.000, 0.056] |
| label_corruption | 0.639 | 0.514 | 0.583 | **0.125 [0.056, 0.194]** | 0.056 [0.014, 0.111] |
| data_leakage | 0.431 | 0.389 | 0.431 | 0.042 [−0.056, 0.139] | 0.000 [−0.056, 0.069] |

**Interpretation.** The pre-registered direction (recovery > identification) is **refuted** on both
endpoints — it was an artifact of a schema example anchoring the label plus narrow class sets. On
the **primary (strict) endpoint** the dissociation runs the *other* way: identification exceeds
strict recovery on 3 of 4 operators with a case-clustered CI excluding 0 (shape 0.24, lr 0.10,
label 0.13). But **semantic recovery nearly closes it** (id − semantic ≈ 0–0.06), so most of the
strict shortfall is **submission-format compliance** (the 9.6% folding, F9) plus strict admissible
ranges — not an inability to name the fault. Original (artifact) numbers were 0.00/0.83, 0.00/0.51,
0.35/0.35, 0.01/0.39.
**Status set from the primary (strict) endpoint:** pre-registered direction **refuted**; a **modest
id > strict-recovery dissociation** (largely a compliance/admissibility effect, not diagnostic).
Both endpoints reported.

### F6 — Reproducibility under nondeterminism (H4) · partially confirmed

**Claim.** Repeat-to-repeat agreement is high on easy cells and lower on hard ones.
**Evidence** (H4 block, diagnostics §4). Mean agreement **0.82** (corrected; 0.70 original).
Per operator (detect / identify): lr_warmup 0.92 / 0.96; label_corruption 0.83 / 1.00;
data_leakage 0.88 / **0.71**; shape 1.00 / 0.96 (0.21 before the unset fix); control 0.75.
**Interpretation.** Detection is reproducible everywhere. Identification agreement drops
0.25 on the hardest fault: the same model on the same leakage case sometimes names the
concept ("leakage") and sometimes only the mechanism ("aux feature enabled") — which the
principled rule scores differently. That is real variability in *how the model explains
itself*, not noise in the harness. Scores are stable; cost varies ±30% (RESEARCH_LOG 9).
**Status.** Partially confirmed (identification axis meets the ≥0.2 gap on the hardest
operator; detection agreement is uniform).

### F7 — Cost of diagnosis (secondary) · reported

ReAct ≈ $0.06–0.08/trial, flat across operators; static ≈ $0.012. Hard cases do not cost
more per trial than easy ones at this scale — investigation *length* is bounded by the turn
budget, not by difficulty. Two of 324 ReAct trials hit `max_turns` without submitting
(both on unrelated cells; no pattern).

### F8 — A visible knob without a norm is not a signal (H1/H2 mechanism) · unplanned

**Claim.** A configuration value that *names* the fault, sitting in plain view in the prompt, does
not by itself trigger detection. What is missing is not information but a **norm** — a reference
for what the value should be.
**Evidence** (diagnostics2 §2). Static anchor-off on label_corruption detected the fault **1/18**;
ReAct anchor-off on the same six cases detected **11/18**. `label_noise_fraction` (0.33–0.42
depending on strength) was present in **all 18** static contexts, **un-truncated**, about **2% of
the way into the prompt** (in `config.yaml`), and the response text even **echoed** it. So the knob
was seen and named, not lost to context length or ordering.
**Interpretation.** This is F1's law applied to a config value rather than a metric: without a
baseline for "normal," a positive- or unknown-valence observation reads as unremarkable. The
one-shot static agent, committing in a single pass with no reference band, does not treat `0.38` as
anomalous; ReAct's iterative querying more often surfaces the deviation. The fix for F1 (a healthy
reference band) is predicted to help here too — a Sweep-2 check.
**What would change our mind.** A model that flags an out-of-distribution knob value anchor-off,
without a norm, would make this a capability gap rather than a norm gap.
**Status.** `unplanned` · pending replication.

### F9 — Repair submissions are frequently mis-channeled (secondary) · unplanned

**Claim.** The model reaches a correct repair but does not always place it in the structured
tool argument — it sometimes serializes it as text (`<parameter name="repair_spec">{…}`) inside
the `rationale` string. This is a **tool-use output-format reliability** effect, not a harness
parsing defect: the API delivered, and the harness stored, exactly what the model produced.

**Evidence.** Of 324 Sweep-1 submissions: 199 placed the repair in the structured field, 94
carried no repair (correct on healthy/undetected trials), and **31 (≈9.6%) folded the repair
into the rationale**; all 31 were cleanly recoverable (a single complete `{repair_type, patches}`
object), 0 ambiguous, 0 unparseable. By operator: shape_mismatch 14, label_corruption 8,
lr_warmup 6, data_leakage 3 — i.e. it is not specific to the crash tier. Recovering them (strict
extraction, then the normal verify path) raised recovery on all four operators (see the
"structured vs recovered" table in `docs/audits/sweep_sweep1_*.md`).

**Interpretation.** Two things are true at once, and the report keeps them apart. (1) It is an
**agent-compliance failure of the system under test**: the model produced the right fix but failed
to put it in the structured field, so it does **not** count toward *strict* autonomous success —
strict recovery is the headline. (2) It is also a *measurement* caution: a benchmark that scored
only the structured field would understate diagnostic *capability*, which is why the *semantic*
endpoint (strict + folded-recovered) is reported alongside strict, never in place of it. The two
endpoints bracket the truth: strict = "did the agent autonomously succeed end-to-end," semantic =
"did the agent know the fix." The live path recovers + flags (`submission_parse_warning`) so future
sweeps self-heal and report the rate.

**What would change our mind.** A different model/prompt with a near-zero folding rate would make
this Haiku/prompt-specific rather than a general tool-use caution.

**Status.** `unplanned` · pending replication. (Reframed on external review from "harness
undercount" to a compliance failure counted only toward the semantic endpoint.)

### Limitations exposed by Sweep 1

- **L1 — lr_warmup ladder saturation.** Mild (lr=0.1) already collapses the model to the
  majority baseline; all three strengths share σ = 44.6. The operator contributes one
  effect-size point, leaving an H2 gap between σ ≈ 18 and 44. *Fix:* recalibrate mild toward
  the tolerance edge (Sweep 2).
- **L2 — Single model, single workload.** Every finding is Haiku 4.5 on Adult/MLP. S1–S6 are
  `pending replication` until a second provider and a second workload run the same cases.
- **L3 — The 2σ band's structural false-positive floor** (~5% of healthy runs by
  construction). A 3σ band is the pre-registration candidate.
- **L4 — Identification depends on a principled token spec** whose version and hash are
  recorded per trial; a future change to the spec requires re-scoring with disclosure.
- **L5 — Cloud-native faults are simulated or absent** (Phase II); the crash tier is
  represented by one binary-recovery operator.
- **L6 — Cost figures are estimates** until the console-billed amount is entered in the
  manifest.
- **L7 — Confidence is too sparse to act on.** Only **52 of 324** trials supplied a confidence
  value, almost all in the top bin, and it does **not** separate the control false positives from
  true detections (max FP confidence 0.65 ≥ min true-detection 0.42; 3 of the 4 FPs gave no
  confidence at all). A confidence threshold cannot gate the control FPs today. *Sweep-2 candidate:*
  make confidence a required submit field so calibration/ECE and FP-gating can be tested.
- **L8 — Folded-repair recovery depends on a strict extractor.** Correction #3 recovers a repair
  only when exactly one complete `{repair_type, patches}` object is embedded (no key scraping;
  ambiguous → not recovered), then runs it through the normal validation. The recovery rate and the
  structured-vs-recovered channel split are reported per sweep; a change to the extractor requires
  re-reporting both. The live path self-heals and flags (`submission_parse_warning`).
- **L9 — Symptom direction is perfectly confounded with operator identity (H1).** Every
  positive-symptom case is data_leakage; every negative-symptom case is lr_warmup/label_corruption.
  The H1 gap cannot be separated from "leakage is intrinsically harder" until a **second
  positive-symptom operator** exists. *Sweep-2 remedy:* add one.
- **L10 — The anchor confounds a numeric reference with an explicit decision rule.** The anchor-on
  prompt supplies both a band *and* the rule "values outside this range are anomalous," so Sweep 1
  shows **norm + rule** restores detection, not that a norm alone does. *Sweep-2 remedy:* the
  three-arm design (none / numbers-only / numbers+rule).
- **L11 — Sweep 1's training ran with unpinned threading (its reference was canonical).**
  *Corrected 2026-09-13:* the reference was **not** platform-specific — with threads pinned, native
  linux/amd64 is byte-identical to Sweep 1's macOS reference *(refined 2026-09-14: byte-exact only WITHIN a microarch; means reproduce ≤~1e-3 across heterogeneous amd64 — LIMITATIONS L18)*. The real caveat is narrower: Sweep 1's
  training runs (case builds, recovery reruns) used unpinned BLAS threading (run-to-run spread up to
  ~0.0037 on per-seed hidden acc). This **cannot** have flipped any faulty guard (faulty margins
  ≥ 0.0095) but is **within** the two tight control margins (+0.00196, +0.00137) — so control guards
  sat inside the threading noise, faulty guards did not. Detection/identification/evidence are
  unaffected. Full statement + Sweep-2 basis (≥20 controls) in `docs/LIMITATIONS.md` L11. *Remedy:*
  pinning is now enforced (`train.py` guard); Sweep 2 runs canonical.
- **L12 — Only 27 unique cases; the pre-registered matched-σ analysis was not run in-pipeline.**
  324 trials come from 27 cases (6/faulty operator, 3 controls), so primary contrasts use
  case-clustered bootstrap CIs and those intervals are wide (control FPR [0, 0.5]). The pooled H1
  contrast substitutes for the pre-registered "matched σ-distance" comparison; a supplementary
  nearest-σ pairing is reported but does not resolve the L9 confound. *Sweep-2 remedy:* more cases
  per cell and a factorial symptom×operator design.
- **L13 — Instructions are delivered as the initial user-role message, not the provider system
  role.** The harness sends what the docs call the "instruction/framing prompt" as the first
  `user` turn; it does not use the API `system` field. Sweep 1's instrument is preserved as-is
  (renamed for accuracy, not switched mid-study). *Sweep-3 candidate:* switch to the provider
  system field — never mid-study.

### Open questions carried to Sweep 2 (candidates for pre-registration)

1. Does S1 hold for a second provider's cheap model — and does a *more capable* model
   rationalize positive-symptom faults more or less (H5)?
2. Does a 3σ band retain F1's detection gain while removing the structural FPs of F3?
3. With a recalibrated lr ladder, where exactly is the negative-symptom detection threshold?
4. Does S4's cost-quality map hold when the static agent's context exceeds one window
   (a larger workload)?
5. Does label corruption remain "subtle" on a noise-sensitive workload (vision)?
6. **Add a second positive-symptom operator** to break the symptom↔operator confound (L9), so the
   H1 gap can be attributed to symptom direction rather than to leakage-specific difficulty.
7. **Three-arm anchor design (none / numbers-only / numbers+rule)** to separate a numeric norm from
   an explicit decision rule (L10) — does a norm alone restore detection?
8. **Token-matched deliberative baseline** for H6, so the ReAct−static gap can be attributed to
   tool use rather than to call count / deliberation / tokens / prompt wording.
9. **Metric-inflation within-case signal (L16):** tag rationales/transcripts that flag
   `metric_inflation` via the loss/accuracy inconsistency, per operator × anchor, so
   consistency-checking detection is distinguished from positive-symptom-*magnitude* detection
   before H1 leans on the second positive-symptom operator (diagnostics plan in HYPOTHESES.md; a
   loss-on-same-subset matched variant is a Sweep-3 candidate).

---

## How to update this document

After each sweep's diagnostics close: (1) add a **Sweep N** section in the shape above;
(2) revise the **Standing findings** table — change a status only with the evidence line that
justifies it; (3) move any answered open question into a finding; (4) add the corresponding
RESEARCH_LOG entry the same day. Never edit a prior sweep's section except to add a
"superseded by Sweep N" note.
