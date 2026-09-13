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
| S1 | **Positive-symptom blindness.** Agents miss faults whose visible metrics look *good*, and a one-line healthy-reference band cures it. | Sweep 1: leakage detection 0.086 → 1.000 with the band; negative-symptom faults 0.639 → 1.000. | confirmed · pending replication (Haiku, tabular) |
| S2 | **Detection follows symptom *sign* first, then magnitude.** Within negative-symptom faults detection is monotone in σ; positive-symptom faults floor regardless of σ (to σ=64). | Sweep 1 H2 per-case table. | sharpened · pending replication |
| S3 | **The reference band is a trade: it rescues true detection and induces false alarms on healthy runs.** | Sweep 1: control FPR 0 → 0.22 with the band; all 4 FPs anchor-on at band-edge values. | unplanned · pending replication |
| S4 | **Tool-mediated investigation helps where investigation matters, not where seeing everything suffices.** ReAct beats static by +0.32 evidence F1 on subtle label noise and ≈0 on leakage, at ~5.5× the cost. | Sweep 1 H6 + cost table. | confirmed (incl. sub-claim) · pending replication |
| S5 | **This model names faults at least as reliably as it repairs them.** Identification ≥ recovery on every operator once scoring artifacts are removed; the earlier "fixes-but-can't-name" pattern was an artifact. | Sweep 1 H3 (corrected). | refuted (as predicted direction) · pending replication |
| S6 | **Diagnostic outcomes are reproducible under nondeterminism; identification agreement drops on the hardest fault.** | Sweep 1 H4: mean agreement 0.82; leakage identification agreement 0.71 vs lr 0.96. | partially confirmed · pending replication |
| S7 | **Adult+MLP is robust to symmetric label noise** (≤25% flips < 1 pt degradation); label corruption is a *subtle* fault on tabular data. | Calibration sweeps (DECISIONS 2026-09-12). | unplanned · workload-specific |
| S8 | **A visible knob without a norm is not a signal.** A configuration value that names a fault, sitting in plain view in the prompt, does not trigger detection unless the agent also has a reference for what is normal — the missing baseline, not missing information, is what blinds it. | Sweep 1: `label_noise_fraction: 0.38` present, un-truncated, in 18/18 static anchor-off contexts and echoed in the response, yet static detected the fault 1/18 vs ReAct 11/18. | unplanned · pending replication |
| S9 | **Tool-use output is unreliable enough to need recovery: ~1 in 10 repairs is misplaced.** The model sometimes emits the repair as text inside a sibling string field instead of the structured tool argument; a harness that scores only the structured field silently undercounts capability. | Sweep 1: 31/324 (≈9.6%) repair submissions folded and recovered (`parser_fix_v1`); 0 ambiguous. | unplanned · pending replication |

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

### F1 — Positive-symptom blindness (H1) · confirmed

**Claim.** Agents diagnose faults whose observable symptoms are *bad* far more reliably than
faults whose symptoms are *good*; without a baseline for "normal," a positive symptom reads
as success.
**Pre-registered prediction.** Anchor-off leakage detection ≥30 points below matched
negative-symptom detection; anchor-on gap ≤10.
**Evidence** (`sweep_sweep1_20260913.md`, H1 block; scores table). Anchor **off**: leakage
detection **0.086** vs negative-symptom **0.639** — a 55-point gap. Static agent: **0/18**
leakage detections; ReAct: 3/18. Anchor **on**: **1.000 / 1.000** — gap 0. All 36
anchor-on leakage trials detected.
**Interpretation.** A frontier model located the leaking feature and derived its label
dependence (Sweep-0 transcript, RESEARCH_LOG 16) yet, with validation accuracy at 0.90 and no
reference for what 0.90 *means* on this workload, judged the run healthy. One line — "healthy
runs achieve ≈0.857 (0.854–0.860)" — turns the same evidence into a diagnosis. Finding, cause,
and intervention in one table.
**What would change our mind.** A second model detecting leakage anchor-off at parity with
negative-symptom faults (H5, Sweep 2); or the effect vanishing on a workload where the model
has strong priors about the achievable accuracy.
**Status.** Confirmed by pre-registered criteria. Pending replication across models/workloads.

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

### F2 — Detection is gated by symptom sign, then scaled by magnitude (H2) · sharpened

**Claim.** Two mechanisms, not one. *Within* negative-symptom faults, anchor-off detection is
monotone in effect size; positive-symptom faults floor regardless of effect size.
**Pre-registered prediction.** A single monotone detection-vs-σ curve with a threshold.
**Evidence** (diagnostics §3; H2 block). Negative symptoms, anchor-off: label_corruption at
σ_hidden ≈ 11–18 detects 0.33–0.50; lr_warmup at σ ≈ 24 detects 0.67; at σ ≈ 44 detects
1.00. Positive symptoms, anchor-off: leakage detects 0.00–0.33 at σ_hidden = 6, 21, 23, **56,
64** — no trend. Anchor-on: 1.00 everywhere (ceiling; σ invisible).
**Interpretation.** The prediction was right about the threshold and wrong that it was the
whole story: a larger leak makes the metrics look *better*, so magnitude cannot rescue a
fault whose sign is wrong. This unifies F1 and F2 into one law — sign gate, then threshold.
**Caveat (see L1).** lr_warmup's three strengths all collapse to the majority-class baseline
(identical σ = 44.6), so the negative-symptom curve has one point between σ ≈ 18 and σ ≈ 44.
**Status.** Sharpened. The threshold's location needs a denser σ ladder (Sweep 2).

### F3 — The reference band is a trade (unplanned) · unplanned

**Claim.** The intervention that cures positive-symptom blindness induces false alarms on
healthy runs whose metrics sit at the band edge.
**Evidence** (diagnostics §6; controls block). Control false-positive rate: anchor-off
**0/18**, anchor-on **4/18** (0.222); overall FPR 0.111, false-intervention rate 0.111 (the
same 4 trials — a "repair" on a healthy run). Rationales cite band-edge values (one healthy
run genuinely above 0.8599; one misread 0.8546 as "below the floor 0.8538").
**Interpretation.** Part of this cost is *structural*: a mean±2σ band places ~5% of healthy
runs outside it by construction. Part is the model over-reading an edge. The band's benefit
(F1) is bought with a measurable false-alarm cost — which is the honest way to present the
intervention.
**What would change our mind / next.** A 3σ band (pre-registration candidate for Sweep 2)
should cut structural FPs without losing true detections, whose σ-distances are ≥ 6.
**Status.** Unplanned; pending replication.

### F4 — Tools help where investigation matters (H6) · confirmed, incl. sub-claim

**Claim.** The ReAct agent out-scores the static full-context baseline on evidence — most on
subtle faults, not at all on leakage — at ~5.5× the cost.
**Pre-registered prediction.** ReAct ≥ +0.10 evidence F1 overall; ReAct − static ≤ 0 on
leakage while > 0 on negative-symptom faults.
**Evidence** (H6 block; cost table). ReAct − static evidence F1: label_corruption **+0.32**,
lr_warmup **+0.17**, shape **+0.04**, data_leakage **+0.006**, control 0. Cost: ReAct
$10.81 / static $1.95 (**5.5×** dollars, 7–8× input tokens; ~$0.06–0.08 vs ~$0.012 per
trial). Anchor-off detection also separates the agents: label_corruption ReAct 0.61 vs static
0.06 — investigation is what finds a subtle fault without a baseline.
**Interpretation.** Where the symptom is subtle (a <1-pt accuracy drop), stepwise querying
of metrics finds evidence a one-shot read skims past. Where the answer is in the code
(leakage), seeing everything at once is as good — and the static agent avoids the distractor
paths the tool loop wandered down. The cost-quality map, not "tools help," is the result.
**Status.** Confirmed by pre-registered criteria, including the leakage sub-claim.

### F5 — Naming vs repairing (H3) · refuted (no meaningful dissociation)

**Claim (as pre-registered).** Recovery exceeds identification — agents fix faults without
naming them.
**Evidence** (H3 block, FINAL corrected — after all three corrections). Identification vs
recovery, and the gap (id − rec): shape_mismatch **0.986 / 0.944** (0.042); lr_warmup
**0.944 / 0.903** (0.041); label_corruption **0.639 / 0.583** (0.056); data_leakage **0.437 /
0.431** (0.006). Identification is marginally ≥ recovery on every operator, but **every gap is
≤ 0.06.** Original (artifact) numbers were 0.00 / 0.83, 0.00 / 0.51, 0.35 / 0.35, 0.01 / 0.39.
**Interpretation.** The pre-registered direction (recovery > identification — "fixes it but
can't name it") is **refuted**: it was an artifact of a schema example anchoring the label plus
class sets too narrow for free-form labels. But the data does **not** support a reversed
dissociation either — a 1-to-6-point edge is within the noise of these per-operator rates
(≤72 trials each). The honest reading is **near-parity**: once the three harness penalties are
removed, this model *names* a fault about as reliably as it produces an *admissible, verified*
repair. There is no doing/understanding gap at this scale in either direction. (Where recovery
still trails at all, it is strict admissible ranges and the residual no-repair/inadmissible
submissions, not an inability to name the fault.)
**Status.** Refuted (pre-registered direction). No meaningful dissociation; reported with
original numbers alongside.

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
ReAct anchor-off on the same six cases detected **11/18**. `label_noise_fraction` (0.15–0.42
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

**Interpretation.** A benchmark that scores only the structured field would undercount repair
capability by ~10% here, and unevenly across operators. The recovery + `submission_parse_warning`
now runs in the live agent path, so future sweeps self-heal and report the folding rate.

**What would change our mind.** A different model/prompt with a near-zero folding rate would make
this Haiku/prompt-specific rather than a general tool-use caution.

**Status.** `unplanned` · pending replication.

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

### Open questions carried to Sweep 2 (candidates for pre-registration)

1. Does S1 hold for a second provider's cheap model — and does a *more capable* model
   rationalize positive-symptom faults more or less (H5)?
2. Does a 3σ band retain F1's detection gain while removing the structural FPs of F3?
3. With a recalibrated lr ladder, where exactly is the negative-symptom detection threshold?
4. Does S4's cost-quality map hold when the static agent's context exceeds one window
   (a larger workload)?
5. Does label corruption remain "subtle" on a noise-sensitive workload (vision)?

---

## How to update this document

After each sweep's diagnostics close: (1) add a **Sweep N** section in the shape above;
(2) revise the **Standing findings** table — change a status only with the evidence line that
justifies it; (3) move any answered open question into a finding; (4) add the corresponding
RESEARCH_LOG entry the same day. Never edit a prior sweep's section except to add a
"superseded by Sweep N" note.
