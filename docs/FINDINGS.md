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

Two Sweep-1 numbers were **scoring/schema artifacts, not model behaviour**, found by the
read-only diagnostics and corrected by principle — never by copying observed outputs into
ground truth. Original numbers are kept alongside corrected ones in every table.

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

**Unchanged by either correction:** detection, evidence, and non-shape recovery — therefore
H1, H2, H6, and the controls finding stand exactly as pre-registered.

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

### F5 — Naming vs repairing (H3) · refuted (direction reversed)

**Claim (as pre-registered).** Recovery exceeds identification — agents fix faults without
naming them.
**Evidence** (H3 block, corrected). Identification vs recovery: lr_warmup **0.94 / 0.83**;
label_corruption **0.64 / 0.51**; shape_mismatch **0.99 / 0.75**; data_leakage **0.44 /
0.39**. Identification ≥ recovery on every operator. Original (artifact) numbers: 0.00 /
0.83, 0.00 / 0.51, 0.35 / 0.35, 0.01 / 0.39.
**Interpretation.** The "fixes it but can't name it" pattern seen in single trials was
produced by two scoring artifacts (a schema example anchoring the label; then enumerated
class sets too narrow for free-form labels). With principled matching the dissociation
reverses: this model *names* the fault class more reliably than it produces an *admissible,
verified* repair — repair fails on strict ranges, unexpressible fixes (now fixed), and
outright no-repair submissions (18 on shape). The pre-registration explicitly listed this
refutation as a possible outcome and it is reported as such.
**Status.** Refuted. Direction reversed; reported with original numbers alongside.

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
