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

**L11 — Sweep 1 executed on non-canonical macOS.** The canonical reference environment is Linux/CI
(cross-platform training divergence is ~seed-scale, so tolerance bands are only strictly valid on
the platform that produced them). The paid Sweep-1 run was executed on macOS, which the manifest
records; Sweep 1 is **not** relabelled as canonical. *Remedy:* run the canonical sweep in the Linux
container (Stage 1).

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
