# Stage 4 Part 2 — pre-registration (DRAFT; NOT locked — being assembled)

> Started 2026-09-27 to carry forward declarations decided before Part 2 is designed in full. The Part 2
> design lives in `docs/STAGE4_PLAN.md` (Part 2); this draft will be completed from its "Declared in the
> Part 2 pre-registration" paragraphs, reviewed by the author, and — on approval — appended to
> `docs/HYPOTHESES.md` before any Part 2 trial, as Part 1 was.

## Carried-forward declarations

- **OpenAI tool schemas are strict in every Part 2 cell** (`strict: true`; schemas strict-compatible) —
  decided 2026-09-27 (`docs/STAGE4_PLAN.md`, Part 2 DECISION).
- **Part 1's GPT-5.6 Luna numbers are affected by non-strict schemas (LIMITATIONS L35).** In Part 1 the
  OpenAI tools were sent without strict mode; Luna's submit arguments degenerated in a measurable share of
  trials (runaway whitespace to truncation; garbled keys that swallowed evidence and repair), so its
  end-to-end detection, identification, evidence F1 and recovery under-state its diagnoses
  (`docs/audits/stage4_part1_followup.md`). Therefore **GPT-5.6 Luna medium is RE-RUN in Part 2** under
  strict schemas, and **no Part 2 estimate or contrast uses, reuses or pools Part 1 Luna trials.**
  (Haiku 4.5 reuse from Part 1 is unaffected.)

- **The pilot is excluded from every analysis and is never scored.** The Part 2 pilot
  (`sweeps/stage4_part2_pilot_plan.yaml`: 10 static + 3 ReAct cells per new condition, seed 20260927) runs
  with scoring switched off (`run_trial(score=False)`); its only output is `pilot-report` — cost, token
  volume including thinking / reasoning tokens, reasoning presence past the first tool call, and
  structured-output / strict-mode compliance. No detection, identification, evidence or recovery value is
  computed or shown, so the pilot cannot inform any threshold of this pre-registration. Its trials carry
  `conditions.pilot = true`; the analysis loaders drop them, and `report` / `run_verify` refuse a pilot sweep.

## Dependency — this pre-registration is NOT locked until

1. the **second human audit** (Part 1 post-run audit, `audit/local/stage4_part1/`) has returned, and
2. the **metric_inflation matcher decision** (LIMITATIONS L36) has been made from the operator's mechanism
   and, if changed, applied with a disclosed rescore —

so that Part 2 is scored with the FINAL matcher from its first trial.

## To be completed

Hypotheses, estimands, decision rules, multiplicity and power — from `docs/STAGE4_PLAN.md` Part 2, after
the pilot.
