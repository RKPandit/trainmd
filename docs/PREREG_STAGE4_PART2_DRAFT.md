# Stage 4 Part 2 — pre-registration (DRAFT; NOT locked — being assembled)

> Started 2026-09-27 to carry forward declarations decided before Part 2 is designed in full. The Part 2
> design lives in `docs/STAGE4_PLAN.md` (Part 2); this draft will be completed from its "Declared in the
> Part 2 pre-registration" paragraphs, reviewed by the author, and — on approval — appended to
> `docs/HYPOTHESES.md` before any Part 2 trial, as Part 1 was.

## Carried-forward declarations

- **OpenAI tool schemas are strict in every Part 2 cell** (`strict: true`; schemas strict-compatible) —
  decided 2026-09-27 (`docs/STAGE4_PLAN.md`, Part 2 DECISION).
- **Part 1's GPT-5.6 Luna numbers are affected by argument degeneration (LIMITATIONS L35) — an OBSERVED
  basis, not a missing flag:** recomputed per trial from the transcripts, 90 Part 1 OpenAI submit calls were
  unparseable, every one ending at the output cap (76 static, 14 ReAct), against 0 for Haiku; the tools sent
  were the canonical open schema (code at the recorded commit; Part 1 records predate the per-trial
  `tool_config` block). Luna's submit arguments degenerated in a measurable share of
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

- **Conditions (7; author's decision 2026-09-27, after the pilot):** Haiku 4.5 (reused from Part 1), Sonnet 5
  thinking off, Sonnet 5 thinking on (effort fixed from thinking VOLUME only — `docs/STAGE4_PLAN.md` Part 2,
  item A), GPT-5.6 Luna medium (re-run, strict), GPT-5.6 Luna none, GPT-6 Luna medium, GPT-6 Sol medium.
  Opus 5.5 is dropped.
- **Wording.** Contrasts are **model comparisons** (Haiku 4.5 vs Sonnet 5 off; GPT-6 Luna vs Sol; GPT-5.6 vs
  GPT-6 Luna; Sonnet 5 on vs GPT-6 Sol at matched list price) or **within-model reasoning interventions**
  (Sonnet 5 off vs on; GPT-5.6 Luna none vs medium). No result is described as isolating capability. ReAct vs
  static compares complete agent configurations.
- **Primary endpoints are end-to-end;** validity is reported separately. Every trial counts: an empty or
  unparseable diagnosis is a miss on a faulty case and never a false alarm on a control. Per condition, the
  valid-submission rate and the recorded completion status (record schema 1.3: `tool_config`, per-call
  provider `completion`, per-trial `completion`) are reported beside the primary numbers; the valid-only view
  is descriptive.
- **Faulty cases are reported by distinct fault mechanism.** Pooled faulty-case estimates are the unweighted
  mean over the five mechanisms (`harness.sweep_stats.MECHANISM`); the two leakage variants are one mechanism.
- **Baselines on the same cases.** The "what does the agent add?" table (B0/B1/B2/B3/BF vs every agent row:
  detection, false alarms — healthy and benign separately — identification, cost) is reported for Part 2 as
  for Part 1 (`scripts/agent_value_table.py`). Whether B1 is declared on the final epoch (see STAGE4_PLAN,
  "Open before lock") is decided before lock.
- **Scorer frozen before the first trial;** Part 2's post-run human audit is the fresh validation of the
  frozen scorer (findings go to LIMITATIONS unless a result would be wrong).

## Dependency — this pre-registration is NOT locked until

1. the **second human audit** (Part 1 post-run audit, `audit/local/stage4_part1/`) has returned, and
2. the **metric_inflation matcher decision** (LIMITATIONS L36) has been made from the operator's mechanism
   and, if changed, applied with a disclosed rescore,
3. the author has reviewed #68 (root_token_v3 / evidence_v2.3) and the scorer is **frozen**, and
4. the Sonnet 5 "on" effort level is fixed by the thinking-volume rule (STAGE4_PLAN Part 2, item A) —

so that Part 2 is scored with the FINAL, frozen scorer from its first trial.

## To be completed

Hypotheses, estimands, decision rules, multiplicity and power — from `docs/STAGE4_PLAN.md` Part 2, after
the pilot.
