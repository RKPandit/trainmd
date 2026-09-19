# TrainMD — Limitations

Plain-language statement of what Sweep 1's results do and do not support, and where a Sweep-2
remedy is planned. The terse limitation IDs (L1–L8) are shared with `docs/FINDINGS.md`; the
per-hypothesis verdicts live in `docs/HYPOTHESES.md` Results and the evidence in `docs/audits/`.

## The corrections, stated plainly

All five post-hoc corrections removed harness-imposed penalties or fixed a measurement/aggregation
error; none inflated a score by changing ground truth. (The first three are the Sweep-1 scoring/
schema + folded-repair corrections; the fourth, 2026-09-15, disaggregated the pooled H1
negative-symptom comparator; the fifth, 2026-09-15, migrated Sweep-1 evidence from v1 — which the
docs had mislabeled as v2 — to **v2.1** (bipartite one-to-one) primary — see FINDINGS "Post-hoc
corrections" #4 and #5.) Originals are kept beside corrected values throughout.

## Disclosure rule

A correction applied after results exist is (1) fixed by the fault's *meaning*, never by copying
observed model outputs into ground truth; (2) disclosed in `HYPOTHESES.md`, the sweep report
header, and `DECISIONS.md`; (3) reported with the original numbers kept alongside the corrected
ones; (4) applied only to free axes (re-scoring) or via the standard evaluator (re-verification);
and (5) recorded with a per-record audit trail so each score is reproducible.

## Limitations

**L1 — `lr_warmup`'s degradation is BIMODAL, not a graded ladder** *(rewritten 2026-09-14 — the
earlier "ladder saturation" framing was a misdiagnosis).* On Adult/MLP a too-high learning rate does
not degrade the model *gradually*: at lr ≤0.07 it trains normally (~0.84); from ~0.08 up each seed
either COLLAPSES to the majority-class baseline (exactly 0.756008, ~44σ below tolerance) or trains
~0.83 — a coin flip near the LR-stability boundary whose collapse PROBABILITY rises with lr
(0.10→0/5, 0.12/0.15→2/5, 0.20→4/5, 0.50 & 1.00→5/5; at 0.30 one seed fell *below* baseline, 0.684)
and which is also microarch-sensitive (the same (lr, seed) can flip AMD↔Intel — the source of the
original `[mild-1]/[mild-2]` flakes and the four cases identical at 0.756008). Measured:
`scripts/calibrate_lr_warmup.py`. There is NO lr producing a stable partial degradation, so `lr_warmup`
**cannot** provide graded σ-rungs on this workload — recalibration to a stable ~2σ mild is impossible
(reported under the stop-and-report clause). *Resolution:* `lr_warmup` is reframed as a bimodal-collapse
operator (strengths = increasing collapse probability; a valid case is a run that actually collapsed)
and **retired from the H2 σ-ladder**; **`label_corruption` carries the σ-axis** (stably graded:
~0.825/0.818/0.800 mild/moderate/severe, tight per-seed spread; S7). A second stably-graded operator
(train-subset-fraction or excessive weight_decay) is a Sweep-2 candidate. DECISIONS 2026-09-14;
FINDINGS (per-lr collapse table); RESEARCH_LOG.

**L2 — One model, one workload.** Every number is Claude Haiku 4.5 on the Adult dataset with an MLP.
The standing findings are marked *pending replication* until a second provider's model and a second
workload run the same cases. *Sweep-2 remedy:* add a second model (for H5) and a second workload.

**L3 — The healthy-reference band has a structural false-alarm floor, and control seeds sit inside the
reference set.** Two distinct issues:

*(i) Band floor — MEASURED, not assumed (updated §0.5).* The recovery/health band is the one-sided
lower bound `tolerance_lower = mean − 2σ`. Under a fitted normal ~2.3% of genuinely healthy runs fall
below it by construction. The earlier "~5% by construction" phrasing (two-sided ±2σ) has been replaced
with the measured statement: at the adopted **30-seed** reference, normality was **checked** —
Shapiro–Wilk W=0.9585, p=0.2835 (n=30, low power to reject, so a non-rejection is weak evidence) — and
BOTH candidate bands are recorded: normal `mean−2σ = 0.843719` and the empirical 2.5th percentile
`= 0.844825` (they differ 1.11e-3; the distribution is mildly platykurtic). **We adopt `mean−2σ`, not
the empirical percentile** (DECISIONS 2026-09-15): at n=30 the empirical 2.5th percentile is an order
statistic set by one or two tail observations (high sampling variance), and it would pin metric-tier
`case_0032` (`silent.metric_inflation.v1` — NOT a control; see the 2026-09-16 documentation-error
correction in DECISIONS) at +8.1e-5 headroom — an order of magnitude below the measured cross-microarch
reproducibility bound (~4e-4, L18), i.e. a validity margin smaller than known platform noise. Under
`mean−2σ` that case clears by +0.00118. Empirically 0/30 reference seeds fell below the band. The
band that cures positive-symptom blindness (H1/F1) still induces false positives at the band edge (~22%
of anchor-on control trials); a 3σ band remains a Sweep-2 pre-registration candidate.

*(ii) Control-band circularity — bias direction LOW (new §0.5).* The reference band is estimated from
seeds `[0–29]`, which **overlap the control-case seeds `{0,1,2}` and the calibration/dev seeds
`{0,1,2}`**. So the healthy controls are judged against a band their own runs helped estimate — the
control false-positive rate is therefore biased **LOW by construction** (a control cannot easily fall
outside a band it helped define). This matters: control FPR is half of G2's headline. *Fix (sequenced,
forced order):* **§0.5 (30-seed band, done) → §5.1 (retain + label out-of-band controls) → §5.2
(disjoint seeds: reference → `[200–229]`, controls rebuilt on confirmatory seeds) → Gate 0.** §5.1 must
land before §5.2, else the `build_case.py` control guard silently rejects the out-of-band controls that
make the measurement honest.

*(iii) §5.1 landed (2026-09-16): the control build guard no longer rejects on band position.* A control
is now valid iff its run COMPLETED with a finite hidden metric and a checkpoint; its band position (both
visible and hidden) is recorded and control FPR is **stratified** (in_band / out_of_band, per arm, each
with cluster count and case-clustered CI) — a pooled control FPR is never reported alone. Stratification
keys on the **VISIBLE** band position by mechanism (a false positive is triggered by the metric the agent
reads and compares to its band); the hidden band position is reported alongside as a case-quality label.
**Any PUBLISHED control FPR was measured under the OLD rejecting guard on in-band-only controls** —
Sweep-1's anchor-on 0.222 and the gate's off 0/12 · numbers 6/12 · rule 2/12. No published number changes
(this is a build-guard change, not a re-score); its INTERPRETATION narrows — those rates are conditional
on in-band controls, so they under-state out-of-band false positives. Classified a **documentation/
interpretation update, not a correction** (`corrections_count` stays 5; DECISIONS 2026-09-16). §5.2 still
moves the reference off `[0–29]` to break the circularity that biases even the stratified rate LOW.

*(iv) §5.2 ADOPTED (2026-09-17): reference `[0–29]` → native EPYC `[200–229]` (tol 0.844655), controls rebuilt on disjoint seeds `[50–69]`; circularity cured. The 20-control band-position distribution was MEASURED (native, run 35179221087): **visible 0/20 below-band, hidden 1/20 below-band (case_0033); 5% visible / 10% hidden out-of-band.** So the old guard would have rejected ≈1/20 = **5%** of these healthy runs — the in-band selection bias is **mild and real**, not the ~25% first (wrongly) imagined and not zero. The low-side count is boundary-sensitive across microarchs (case_0033's margin −0.001223 sits within the ~5e-3 cross-microarch per-seed noise, L18/L23), so on another native runner it can be 0/20.)*

**L4 — Identification depends on a principled token spec.** Fault naming is scored by root-token
matching whose version and content hash are recorded on every trial. The spec is defined from each
fault's meaning, but any future change to it requires re-scoring the affected trials with disclosure
(it is not frozen ground truth). No Sweep-2 remedy needed; this is a maintenance rule.

**L5 — Cloud-native and multi-stage faults are simulated or absent.** Phase I covers single-job
training incidents; the crash tier is represented by one binary-recovery operator (shape mismatch).
Distributed, data-pipeline, and infrastructure faults are out of scope until Phase II.

**L6 — Cost figures are token-based estimates.** The reported $12.76 is derived from per-trial token
counts times list price, not the provider's console-billed total. The manifest's `actual_spend_usd`
is filled from the console at sweep end; until then cost comparisons are estimates (accurate for
*ratios*, e.g. the 5.5× ReAct:static multiple, which are unaffected by an overall price factor).

**L7 — Confidence is too sparse to act on.** Only 52 of 324 trials supplied a confidence value, almost
all in the top bin, and confidence does not separate the control false positives from true detections
(the one FP with a value scored 0.65, above the lowest true-detection confidence of 0.42; three of
the four FPs gave no confidence at all). No confidence threshold can gate the control false positives
today. *Sweep-2 remedy:* make confidence a required submit field so calibration (ECE) and false-
positive gating can be tested properly.

**L8 — Folded-repair recovery depends on a strict extractor.** Correction #3 recovers a misplaced
repair only when exactly one complete `{repair_type, patches}` JSON object is embedded in the
submission (no partial reconstruction, no key scraping; ambiguous or unparseable cases are flagged,
not recovered), and the recovered repair then goes through normal validation. The folding rate and
the structured-vs-recovered channel split are reported every sweep; a change to the extractor
requires re-reporting both. The live agent path applies the same recovery and flags it
(`submission_parse_warning`), so future sweeps self-heal.

**L9 — Symptom direction is perfectly confounded with operator identity.** In Sweep 1 every
positive-symptom case is `data_leakage` and every negative-symptom case is `lr_warmup` or
`label_corruption`. So the 0.556 anchor-off detection gap (H1) may reflect symptom direction *or*
leakage being intrinsically harder to diagnose — the design cannot separate them. Only a **second
positive-symptom operator** (Sweep-2 remedy) can. The supplementary nearest-σ matched contrast
narrows the σ difference but does **not** touch this confound.

**L10 — The anchor manipulation confounds a numeric reference with an explicit decision rule.** The
anchor-on prompt gives the agent both a reference band *and* the instruction that values outside it
are anomalous. Sweep 1 therefore shows that a **norm plus a decision rule** restores detection, not
that a norm alone does. *Sweep-2 remedy:* a three-arm design — none / numbers-only / numbers+rule.
*Implemented (Stage 2):* the three-arm anchor (`off` / `numbers` / `rule`) is now selectable on both
agents, with `rule` a strict superset of `numbers` (one appended sentence). Legacy Sweep-1 "on" maps
to "rule" in analysis (never rewritten). Sweep-2 will run all three arms; the prediction shape is in
HYPOTHESES.md (numbers-only closing the gap ⇒ baseline restoration; only rule ⇒ instruction
following). DECISIONS 2026-09-13.

**L11 — Sweep 1's training ran with unpinned threading (the reference itself was canonical).**
*Corrected 2026-09-13:* an earlier version of this limitation said Sweep 1 used a "non-canonical
macOS reference." **That is false.** With every BLAS/OpenMP thread pool pinned to 1, the native
linux/amd64 reference is **byte-identical to the macOS reference** Sweep 1 used *(refined by L18: byte-exact only WITHIN a microarch; ≤~1e-3 across the fleet)* (tolerance_lower
0.843535) — there is no platform difference in the reference. The real, narrower caveat: Sweep 1's
**training runs** (each case build, and the recovery reruns) executed with **unpinned** threading, so
they sampled a run-to-run-nondeterministic process; the reference band they were scored against was
correct.
*What this does NOT affect:* detection, identification, and evidence (they don't depend on the
training float noise), the reference band, and any faulty-case verdict (see below). It only adds
noise to which side of a *tight* boundary a borderline healthy run landed on.
*Quantified residual doubt (not hand-waved).* CI measured the unpinned run-to-run spread at up to
**~0.0037** on per-seed hidden accuracy. Against each Sweep-1 case's faulty-vs-tolerance margin:
- **Faulty cases cleared by ≥ 0.0095** — far outside the ~0.0037 noise band, so threading **could
  not** have flipped any faulty case's tier guard. Faulty verdicts stand.
- The **two tight controls** in the fresh canonical build sit at **+0.00196** and **+0.00137** above
  tolerance — **inside** the ~0.0037 spread. So a control's healthy-clears-tolerance guard *was*
  within the threading noise band; a borderline healthy run could have been sampled either side.
This is the honest bound: **control guards were within the threading noise; faulty guards were not.**
It is also the empirical basis for **≥ 20 unique controls in Sweep 2** — three controls at these
tight margins cannot distinguish signal from threading jitter (and the control FPR CI was already
[0, 0.5], L7/S3). *Remedy:* thread pinning is now enforced (train.py guard) and Sweep 2 runs in the
canonical container; add 20+ unique controls.

**L12 — Small case count and an un-run matched analysis.** The 324 trials come from only **27 unique
cases** (6 per faulty operator, 3 controls; 12 trials/case), and trials within a case are not
independent. Every primary contrast therefore reports a **case-level bootstrap 95% CI** (10,000
resamples), and those intervals are wide — the control FPR interval is [0.0, 0.5] over 3 control
cases. The pre-registered "at matched σ-distance" comparison for H1 was **not** performed by the
metrics pipeline (it pools); a supplementary nearest-σ pairing is reported instead. *Sweep-2
remedy:* more cases per cell and a factorial design.

**L13 — Instructions are delivered as the initial user-role message, not the provider system role.**
What the docs call the instruction/framing prompt is sent as the first `user` turn; the harness does
not use the provider `system` field. The name was corrected (not the mechanism) so Sweep 1's
instrument is preserved unchanged. *Sweep-3 candidate:* switch to the provider system field — a
deliberate instrument change to make between studies, **never** mid-study.

**L14 — The workload's memorization ceiling limits which positive-symptom mechanisms it can host.** On
Adult/MLP the train–val gap is only ~0.010, so the highest reported accuracy any *data-side*
memorization trick (e.g. copying training rows into validation) can reach is train accuracy (~0.863) —
a mere ~0.003 above the visible band edge (0.860). A positive-symptom fault built on row overlap /
memorization therefore has no laddered headroom on this workload; Step-0 confirmed it empirically
(augmented val_acc ≤ 0.857 for every strength/seed). The second positive-symptom operator (#6) is
instead a *metric-side* biased computation, which is model-independent and clears the band by design. A
workload that overfits (e.g. the planned vision workload) could host a memorization-based positive
symptom; Adult/MLP cannot. *No remedy needed — a constraint on operator design, recorded so the
mechanism choice is auditable* (FINDINGS S10; DECISIONS 2026-09-13; RESEARCH_LOG 27).

**L15 — Adult contains duplicate records shared across splits.** 12 rows appear in both the training set
and the hidden test by content hash (of ~30k), although the splits are disjoint by *index* (`data_prep`
partitions a single permutation). This is a property of the raw dataset, not a leak introduced by any
operator, and is negligible in magnitude. Consequence: any operator or validator disjointness check is
written as "does not INCREASE train↔test overlap" (plus index-disjointness), never absolute
content-disjointness — which would false-positive on these pre-existing duplicates (FINDINGS S11;
DECISIONS 2026-09-13).

**L16 — The two positive-symptom operators are NOT matched on within-case detectability.**
`silent.metric_inflation.v1` reports an inflated *accuracy* computed on a confidence-selected subset,
but `val_loss` is still computed on the full validation split — so an epoch row shows a normal loss
(~0.30) beside an inflated accuracy (~0.88–0.98), an internal inconsistency an agent can detect with
**no external baseline**. `silent.data_leakage.v1` has no such contradiction: the model genuinely
learned the leaked feature, so its loss and accuracy agree, and detecting it requires either a
reference band or reading the code. This is kept deliberately (a subset-accuracy bug plausibly would
not touch the loss — it is the realistic form; see DECISIONS 2026-09-13), but it is a **confound for
any metric_inflation-vs-data_leakage detection comparison**: a difference in anchor-off detection
between the two could reflect the within-case loss/accuracy signal rather than symptom magnitude or
direction. *Sweep-2 remedy (diagnostics):* tag rationales/transcripts that cite the loss/accuracy
mismatch, reported per operator × anchor, so consistency-checking detection is distinguishable from
positive-symptom-magnitude detection. *Sweep-3 candidate:* a matched variant that computes the loss
on the same subset, removing the internal contradiction (HYPOTHESES.md).

**L17 — Evidence numbers changed scorer between sweeps (v1 → v2); Sweep-1 values were v1.** Sweep 1's
evidence F1 (F4/H6, S4) was computed under **evidence_v1**, which credited any span overlap and treated
omitted bounds as 0/∞. From Sweep 2 the primary scorer is **evidence_v2** (IoU ≥ 0.5 + a 3× width cap
for line/code spans, required explicit bounds, alternative sufficient sets, and a *measured*
containment window for metric_window). This is a **disclosed measurement change, not a finding**: on
Sweep-1 data v2 lowers `shape_mismatch` evidence F1 **0.807 → 0.607** (over-broad traceback line/code
spans no longer credited on partial overlap), nudges `lr_warmup` +0.009, and leaves
`data_leakage`/`label_corruption`/`control` unchanged. The metric_window containment rule changed the
match status of **zero** Sweep-1 refs (the anomaly spans the whole run, so every in-run localization —
sharp or lazy — stays credited). v1 values are preserved beside v2 (`evidence_v1`); both are reported.
DECISIONS 2026-09-13; `harness/rescore.py::rescore_evidence_v2`.

*Addendum (2026-09-15, correction #5): the v1→v2 rescore above was **disclosed but never persisted** —
Sweep-1 `scores.evidence` stayed **v1** until 2026-09-15, so the "v2 primary from Sweep 2" statement was
a provenance **mislabel**. Correction #5 migrates all records to **evidence_v2.1** (bipartite one-to-one)
primary: v1→v2 span-strictness lands (shape_mismatch 0.807→0.607, as above) PLUS the v2→v2.1 union-bug fix
(which bit `lr_warmup`, 5 sweep-1 trials ~−0.13, not shape_mismatch). H6 0.135→0.1343, ≥+0.10 verdict held.
A `scripts/check_scorer_versions.py` guard now asserts each report's scorer matches its records so a
which-instrument mislabel cannot recur.*

**L18 — The native-amd64 reference is byte-exact only WITHIN a microarchitecture.** With the data
pinned to committed hashes (identical bytes on every runner — verified by CI fingerprints), native
training still differs across amd64 microarchitectures because float REDUCTION ORDER differs (AVX-512
vs AVX2 FMA). Measured cross-microarch spread on the reference: visible mean **4.28e-4 (0.28σ)**,
hidden mean **9.73e-4 (0.47σ)**, hidden σ-estimate ~1e-3, and `tolerance_lower` **2.99e-3** (the last
exceeds the tightest case-guard margin, +1.37e-3). *(These deltas were measured under the 10-seed
reference era; the 30-seed adoption (§0.5) does not change them — cross-microarch divergence is a
property of the float reduction, not the seed count. The current tightest case-guard margin under the
30-seed band is metric-tier `case_0032` at +1.19e-3, still above the ~4e-4 reproducibility floor and the
reason the empirical band was rejected — see L3.)* *Revised guarantee (replacing "byte-identical
across runners"):* **byte-exact within a microarchitecture; across heterogeneous native amd64 the
means reproduce within ~1e-3 (≤0.5σ) and σ-estimates within ~3e-3, with data pinned.** This is
scientifically harmless — the spread is well inside seed noise (≤0.5σ) and far below every faulty
guard margin — and it does not touch case validation, because C4/C9/C11 re-derive from the COMMITTED
`stats.yaml` (a fixed file), never a fresh run. The CI reference-diff is therefore tolerance-based
(means ≤2e-3, `tolerance_lower` ≤6e-3 + an exact derivation check; DECISIONS 2026-09-14), and a
`reference-change-guard` rebuilds all cases against a changed committed reference. *Fix direction if
byte-exactness across the fleet ever matters:* pin CI to a fixed-CPU runner, or impose a deterministic
reduction order (e.g. a fixed BLAS kernel / higher-precision accumulation). Stage 1b's "byte-identical
across two independent runners" was an over-reading — two agreeing runners are not the fleet (see the
RESEARCH_LOG standing lesson).

*SCOPE CORRECTION (2026-09-16, cross-reference L23).* Everything L18 characterizes is **mean-level,
cross-microarch, NATIVE-vs-native** equivalence, and all of it is true — indeed a 2026-09-16 CI run on
two DIFFERENT EPYC microarchs (9V45 vs 7763) was **byte-identical across all 1900 metric fields**
(max Δ 0.000e+00), tightening "~4e-4 cross-microarch" to byte-exact for that pair. **What L18 does NOT
license:** (a) any **native-vs-EMULATED** claim — L18 never measured emulation, and it turns out
native-EPYC vs emulated-Rosetta diverges up to ~2.8σ (visible) / ~2.1σ (hidden) per seed (L23); and
(b) any **per-case** robustness claim — L18's figures are on the *mean* (0.28σ), whereas per-case
(the operative quantity for detection) is up to ~2.8σ. The "~4e-4 reproducibility floor" phrase above
therefore means *cross-microarch native*, not "the platform floor in general". See L23.

**L19 — The recovery axis is DEGENERATE on the three Stage-2 gate operators.** `not_recovered
= 0/138`: every admissible structured repair recovered, because each operator's admissible-repair
space is effectively a single oracle-equivalent point (unset the leak key / reset
`label_noise_fraction` / unset `eval_subset_fraction`) — any admissible repair reconstructs the
clean run and clears tolerance. Proof (harness probe, free, no LLM; `docs/audits/sweep_stage2gate_2026-09-15.md`
§0.1): the trusted `DegenerateAgent` — detect=True, **wrong class, no evidence**, blind admissible
repair — scores **18/18 = 1.000** strict recovery across all three operators. So on these operators
**strict recovery measures submission-format compliance + admissibility, not repair correctness**,
and cannot discriminate diagnosis quality (this generalizes the 2026-09-07 lr_warmup note in
DECISIONS). *Sweep-2 remedy:* operators with a genuinely **wide** admissible-repair space, where a
*wrong-but-admissible* value fails to recover (a continuous knob with a broad admissible band whose
sub-range alone restores health, or a multi-key repair where a plausible-but-wrong key leaves the
fault). Until then recovery is reported for completeness but is not a discrimination axis.

**L20 — Controls are under-powered: 3 unique healthy cases.** The gate has 3 control cases (one per
control-seed); per anchor arm that is 12 trials from 3 clusters, so the case-clustered control
false-positive CIs are enormous — off **[0.000, 0.000]**, numbers 0.500 **[0.000, 0.750]**, rule
0.167 **[0.000, 0.500]**, numbers−rule +0.336 **[0.000, 0.750]**. No control-arm contrast is
decidable and the control FPR is not a population rate. This extends L12/S3's under-powering from
Sweep 1. *Remedy:* **≥20 unique control cases per workload** before any false-positive claim
(detection specificity, false-intervention rate, or an anchor-arm FP contrast) is stated as
established rather than suggestive. *(§5.1, 2026-09-16: control FPR is now stratified by band position
and out-of-band controls are retained rather than discarded — L3(iii). That removes the LOW selection
bias but does NOT cure under-power: with 3 controls the strata are even smaller, so the ≥20 requirement
is unchanged and is the binding constraint on any control claim.)* *(§5.2 adopted 2026-09-17: measured on 20 native controls — visible 0/20 below-band, hidden 1/20 below-band; 5%/10% out-of-band. **Residual caveat:** these 20 are seed replicas of ONE configuration (seeds 50–69), so 0–2/20 out-of-band says the band is well calibrated FOR THIS CONFIGURATION — NOT specificity against benign configuration VARIANTS, a full-study item.)*

**L21 — The Stage-2 gate has SPLIT PROVENANCE across its two phases.** The agent phase ran on the
host (macOS-10.16 / py3.9, `in_container: false`) — acceptable because it is Anthropic API calls,
which are platform-independent and involve no local training. The verify/recovery phase ran in the
canonical container (Linux/amd64, threads pinned, `in_container: true`, image `trainmd:canonical`
`sha256:0354db57…`) after the verify thread-pin fix (DECISIONS 2026-09-15). Both are recorded
separately in `sweeps/stage2gate_manifest.yaml` (`agent_phase` / `verify_phase.provenance`). The
two phases having different provenance is intentional and disclosed; a reader must not assume a
single environment produced the whole gate.

**L22 — Detection on the Stage-2 operators proceeds by CONFIG LEGIBILITY, not metric reasoning.**
Each gate operator injects a single non-default config key, and G3 showed detection reasons from
that key (0/72 use the loss/accuracy inconsistency; every `metric_inflation` detection cites
`eval_subset_fraction`). So the gate's detection axis substantially measures "spot the anomalous
config knob given a reference band," not "reason about the metrics." This is **equal across all
three operators**, so it does not bias the G1 cross-operator contrast, but it limits what the gate
says about metric-*based* diagnosis. *Sweep-2 remedy:* include at least one operator whose fault is
**not** a single legible config key (a code-path or data-distribution fault), and pre-register the
config-legibility factor before leaning on cross-operator detection contrasts.

**L23 — Per-case cross-platform drift affects BOTH metrics and is an order of magnitude larger than
the mean-level equivalence L18 characterized.** Three regimes, measured (2026-09-16):

- **Native-vs-native (cross-microarch): robust.** Two CI runners, AMD EPYC 9V45 and EPYC 7763,
  produced **byte-identical** visible AND hidden metrics across all 1900 fields (max Δ 0.000e+00) —
  tighter even than L18's ~4e-4 (EPYC-vs-Xeon). This is the regime L18 measured.
- **Native-vs-emulated: BOTH metrics fragile.** Native EPYC vs emulated Rosetta (Apple-Silicon Docker),
  30 clean reference seeds: **visible** mean |Δ| 1.5e-3 (0.81σ), **max 5.16e-3 (2.80σ)**, 3/30 over 2σ;
  **hidden** mean |Δ| 2.3e-3 (1.08σ), **max 4.57e-3 (2.14σ)**, 6/30 over 2σ. Deterministic within a
  platform (two emulated runs byte-identical); the divergence is native-vs-emulated float, seed-dependent
  and chaotic (curves identical for ~8 epochs then diverge). The repo's own `RESEARCH_LOG:269` had already
  recorded a single **hidden** seed moving 0.0053 (2.6σ) macOS-vs-Linux — hidden is NOT robust across
  platforms. *(Earlier in this investigation "hidden is robust ~4e-4" was asserted; that was L18's
  cross-microarch figure over-generalized from seed 0's coincidentally tiny delta — CORRECTED here: both
  metrics are per-case platform-sensitive across native-vs-emulated.)*
- **Mean-level vs per-case.** L18's equivalence is on the MEAN (visible 0.28σ). **Detection is per-case**
  — the agent compares ONE case's visible metric to the band — so the operative figure is the per-case
  one (up to ~2.8σ), an order of magnitude larger.

*Consequence + fix.* A case built on one platform against a band computed on another is compared against
the wrong yardstick (the agent-facing visible metric may not match its band). So **every case and
reference artifact must be generated on native amd64** — now ENFORCED by the `harness.platform_guard`
canonical-platform guard (`build_case`, `reference_run` refuse under emulation; the CPU is stamped into
each hidden card / sweep manifest). *Not retroactive:* artifacts generated before the guard carry this
caveat. **Sweeps 1–2 and the Stage-2 gate ran on macOS x86_64 (metric AND band both macOS — L21, L124/
this entry), so they are INTERNALLY CONSISTENT and stand as run**; the hazard is a FUTURE mix of a native
band with a non-native case, which the guard now prevents. Evidence table: the full 30-seed
native-vs-emulated per-seed deltas (both metrics) are in `docs/audits/` / this investigation's record.

**L24 — The metric tier's "the model is healthy" guarantee is partly SELECTED, not observed.** The
`build_case` metric-tier guard rejects a `silent.metric_inflation.v1` case unless the true hidden
accuracy lands INSIDE the band (`tolerance_lower ≤ hidden ≤ mean+2σ`). A genuine metric-inflation run
whose model drifts out-of-band through ordinary seed noise is therefore silently DISCARDED — the same
class of selection bias §5.1 removed from the CONTROL guard, in the other direction (it flatters the
"model untouched" claim rather than specificity). It affects an operator that is in the Stage-2 gate and
slated for Sweep 3. *Not fixed here* (§5.1 scope was controls). *Fix, sequenced BEFORE Sweep 3 builds
more metric cases (STAGE3_PLAN):* retain out-of-band metric cases and record their band position (as
§5.1 did for controls), so the metric tier's model-health property is measured rather than selected.
The 6 metric cases sit in_band on hidden — RE-DERIVED from the native §5.2 candidate build (case_0025–0030, run 35179221087, against the 200–229 band, tol 0.844655, hidden σ 0.001796): their true hidden accuracy is **0.85σ–1.26σ ABOVE the mean** (σ from mean −1.26…−0.85), well within ±2σ, while their VISIBLE metric is inflated **+12σ to +57σ** by the fault (as designed). (Band value finalised at adoption — cross-microarch ±2e-4.)


**L25 — Recovery uses a MEAN-of-hidden-seeds rule (disclosed definition change, 2026-09-17); the
baseline recovery match is a degenerate-axis result.** `recovered` iff the MEAN of the 3
hidden-seed accuracies ≥ `tolerance_lower` (was: every seed individually), every seed having run
(exit 0), plus — metric tier — the MEAN visible metric in-band. Rationale: "all 3 seeds ≥
mean−2σ" fails a genuinely correct repair ~7% of the time BY CONSTRUCTION (1 − 0.977³, one seed
past a one-sided 2σ band); this bit exactly once under the tighter native band (hidden_eval
seed 101 clean = 0.844317, 2.19σ below the mean, < tol 0.844655) and failed 18 oracle-round-trip
tests. The mean has σ/√3 spread, so it fails only when the model is genuinely degraded
(`compute_recovery_verdict` + `tests/test_recovery_rule.py`; frozen-sweep delta = 0). **Rejected
alternatives:** re-selecting hidden_eval seeds (test-set selection bias, the class §5.1/§5.2
removed) and decoupling the recovery tolerance from the detection band (one band, not two).
**Caveat on the baseline recovery numbers:** B2 recovers 30/30 — but recovery is DEGENERATE on
these operators (L19: any admissible repair reconstructs the clean run), so a config-reset
matching the oracle is expected, not evidence of repair intelligence. B2's control-FPR is 0/20
(no config delta on a clean control), so on specificity B2 dominates the band detector B1 (1/20,
the case_0039 two-sided-band false positive) — the 0-FPR floor is B2, not B1.

**L26 — The second provider (GPT-5.6 Luna) has NO dated snapshot to pin; the alias IS the
snapshot.** Anthropic model ids are dated (e.g. `claude-haiku-4-5-20251001`), so a trial's model
is reproducible from the id alone. OpenAI publishes only the floating alias `gpt-5.6-luna` (no
`gpt-5.6-luna-YYYY-MM-DD` exists, verified 2026-09-19), so the alias can be silently repointed to a
newer build. Consequence: for the Luna arm, model provenance rests on the **API-reported model
string captured per trial** (`LLMResponse.raw["model"]` → `llm_transcript[*].api_model` in every
record; the adapter already records it) rather than on the requested id. This is an asymmetry with
the Anthropic arm — a Luna result is reproducible only against whatever build the alias pointed to
at run time. Mitigations: (i) the per-trial `api_model` is the ground-truth provenance and is
audited; (ii) re-pin to a dated snapshot the moment OpenAI publishes one (docs/DECISIONS.md
2026-09-19). Any drift in the aggregate `api_model` across a sweep is a provenance-split flag.