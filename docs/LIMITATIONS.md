# TrainMD — Limitations

Plain-language statement of what Sweep 1's results do and do not support, and where a Sweep-2
remedy is planned. The terse limitation IDs (L1–L8) are shared with `docs/FINDINGS.md`; the
per-hypothesis verdicts live in `docs/HYPOTHESES.md` Results and the evidence in `docs/audits/`.

## The corrections, stated plainly

All three post-hoc corrections removed harness-imposed penalties on the model; none inflated a
score by changing ground truth. Originals are kept beside corrected values throughout.

## Disclosure rule

A correction applied after results exist is (1) fixed by the fault's *meaning*, never by copying
observed model outputs into ground truth; (2) disclosed in `HYPOTHESES.md`, the sweep report
header, and `DECISIONS.md`; (3) reported with the original numbers kept alongside the corrected
ones; (4) applied only to free axes (re-scoring) or via the standard evaluator (re-verification);
and (5) recorded with a per-record audit trail so each score is reproducible.

## Limitations

**L1 — The learning-rate ladder is saturated.** All three strengths of `lr_warmup` already collapse
the model to the majority-class baseline, so they share one effect size (σ ≈ 44.6). The operator
contributes a single point to the detection-vs-σ curve, leaving a gap between σ ≈ 18 and 44.
*Sweep-2 remedy:* recalibrate the mild strength toward the tolerance edge so the ladder spans the
threshold region.

**L2 — One model, one workload.** Every number is Claude Haiku 4.5 on the Adult dataset with an MLP.
The standing findings are marked *pending replication* until a second provider's model and a second
workload run the same cases. *Sweep-2 remedy:* add a second model (for H5) and a second workload.

**L3 — The healthy-reference band has a structural false-alarm floor.** A mean ± 2σ band leaves about
5% of genuinely healthy runs outside it by construction, and the band that cures positive-symptom
blindness (H1/F1) induces those false positives at the band edge (~22% of anchor-on control trials).
*Sweep-2 remedy:* a 3σ band is a pre-registration candidate — expected to keep the detection gain
while cutting the structural false positives.

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
linux/amd64 reference is **byte-identical to the macOS reference** Sweep 1 used (tolerance_lower
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
