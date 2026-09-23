# TrainMD — Current State (canonical)

**This is the single source of truth for the project's current state.** Updated at every gate.

> **Rule.** If this page and any other document disagree, this page is wrong OR the other document
> is stale — **fix whichever is stale in the same commit.** Machine-checkable facts in §a are
> verified against the repo by `scripts/check_current_state.py` in CI; that guard fails loudly on
> drift. Last updated: 2026-09-22 (Sweep 3 `h8_xprovider` complete — H8 confirmed where powered,
> H7 model-specific; next gate = Stage-4 plan).

---

## a. Instrument (machine-checkable)

The values below are checked against the repo by `scripts/check_current_state.py`. Do not hand-edit
them out of sync with the registry / code.

```yaml
operators_count: 7
operators:            # operator_id  (tier)
  - control.healthy.v1          # control
  - crash.shape_mismatch.v1     # execution
  - silent.data_leakage.v1      # dynamics
  - silent.data_leakage_neutral.v1  # dynamics (v3 Part 2 — neutral-key ablation; workload tabular_adult_neutral)
  - silent.label_corruption.v1  # dynamics
  - silent.lr_warmup.v1         # dynamics (bimodal-collapse; retired from the σ-ladder — L1/S12)
  - silent.metric_inflation.v1  # metric
case_count: 128                 # v3 Part 2 (H8 power): 108 faulty (6 ops × 3 strengths × 6 seeds 42–47) + 20 controls (seeds 50–69)
evidence_scorer_primary: evidence_v2.1
evidence_scorer_versions: [evidence_v1, evidence_v2, evidence_v2.1]
canonical_image_digest: sha256:0354db57c29a5092ace862a0d8716dfe3729d4f8b893fe3079c66d947daeb25d
reference_seeds: 30
latest_sweep: stage2gate
corrections_count: 6
```

- **Workloads:** 1 — `tabular_adult` (Adult / MLP). (Second workload deferred to the full study.)
- **Agents:** 2 — ReAct (tool-using; `react-1`) and static full-context (`static-1`); prompt version
  gets an anchor-arm suffix.
- **Anchor arms:** 3 — `off` / `numbers` / `rule` (legacy `on` → `rule`). *In flight:* STAGE3_PLAN
  Part 6 renames to `off` / `stats` / `rule` with de-evaluative wording.
- **Scorer:** `evidence_v2.1` (bipartite one-to-one matching) is primary; `evidence_v2` + `evidence_v1`
  retained beside it for audit (STAGE3_PLAN §0.4). **Provenance note:** Sweep-1 records were scored
  under **v1** until 2026-09-15 (the earlier "v2 primary" docs were a mislabel — the v1→v2 rescore was
  disclosed 2026-09-13 but never persisted); all records migrated to v2.1 primary in **correction #5**.
  A `check_scorer_versions.py` guard now asserts each report's declared scorer matches its records.
- **Identification matcher:** `root_token_v2` (2026-09-22). A **shipped-but-unexploited vulnerability**
  (§f taxonomy, first instance) — an external reviewer showed v1 matched concept stems as free substrings,
  so it *would* score fault negations (`no_leakage`) and off-concept collisions (`memory_leak`) as correct;
  the audit of every scored-correct label in Sweeps 1–3 found **zero** such cases (0 of 1156), and a full
  re-score under v2 moves **0** labels (delta 0). So the rule was exploitable, was never exploited, and
  **no published identification number — nor the H8 verdict — moves**; the matcher hardening therefore
  did **not** tick `corrections_count` (no published number was ever wrong; the later bump to 6 is the
  unrelated zero-event interval fix, correction #6). v2 fixes it by principle: negation detection (token path only),
  whole-token/declared-inflection matching (never a free substring), and a per-operator
  `off_concept_vetoes()` list. See DECISIONS 2026-09-22; tests `test_identification_v2_hardening.py`;
  audit `scripts/audit_stage4_identification.py`.
  *Attribution note:* frozen sweeps are attributed by each record's sealed `accepted_classes`, never by
  today's `cases/` (case_id is not a stable operator key across rebuilds) — `operator_from_record`.
- **Canonical environment:** Linux/amd64 container **on NATIVE amd64** (`harness.platform_guard`:
  case/reference builds refuse under emulation — the agent-facing visible metric is per-case
  platform-sensitive up to ~2.8σ native-vs-emulated, L23; CPU stamped in each hidden card + manifest),
  thread-pinned; base `python:3.11-slim-bookworm`; image digest above (`docker/IMAGE_DIGEST`). Reference
  seeds `[200–229]` (**30**; adopted STAGE3_PLAN §5.2 2026-09-17, native amd64 EPYC,
  `tolerance_lower` **0.844655** = mean−2σ; prior 30-seed `[0–29]` band at `reference/stats.0-29seed.yaml`, 10-seed at `reference/stats.10seed.yaml`);
  hidden eval seeds `[100,101,102]`. **Seed-collision caveat:** reference `[0–29]` overlaps
  control/calibration seeds `{0,1,2}`, so control false-positive rate is biased **LOW by construction** —
  see LIMITATIONS L3. §5.1 (retain + label out-of-band controls; control FPR stratified by band position)
  **landed 2026-09-16**; §5.2 (reference → native EPYC `[200–229]`; controls → `[50–69]`) **adopted 2026-09-17** — circularity cured (§d).
- **Latest committed sweep:** `stage2gate` (252 cells; agent phase on host/API, verify phase canonical
  in-container). Agent-phase cost **~$11.71 estimated** (actual pending). Prior: `sweep1` (~$12.76 est).

## b. Claims and their status

Statistical-language rules (STAGE3_PLAN §"Statistical-language rules"): a failed pre-registered
prediction is **"failed to replicate"**; an effect is **"supported across N operators within one
model-workload setting"** (never "confirmed" in the paper); rationale text supports **"not
mentioned,"** never "not used"; every rate states its cluster count.

| Claim | Status |
|---|---|
| **A numerical reference baseline restores detection** (numbers arm closes ~94–95% of the off→rule gap on all 3 gate operators). | **Model-specific — supported for Haiku, FAILED TO REPLICATE as a general effect on the 2nd model.** Off-anchor leakage detection Haiku **0.083** vs Luna **0.819**; band adds ~90 pts (Haiku) / ~17 pts (Luna) — Sweep 3 / FINDINGS F14, S16. The Stage-2 "strongest-supported claim" framing is retired; the effect is Haiku-specific, its driver unidentified at n=2 (L28). |
| **Leakage identification survives renaming the two descriptive config keys (H8).** *(Reworded 2026-09-23 from "fault-mechanism, not config-key-name reading" — an overclaim: renaming two keys tests dependence on THOSE NAMES; code-pattern recognition and general leakage heuristics remain competing explanations.)* | **Often survives the tested renaming; equivalence unresolved in two anchored conditions; Luna's rule arm shows a measurable decrease** (Sweep 3, neutral-key ablation; PRIMARY = PAIRED strength×seed bootstrap): the pre-registered equivalence criterion (±0.15) is met in **4 of 6 provider-specific cells** — but **Haiku off is equivalent FAILURE** (identification ~6% in both variants: 0.056 / 0.069; the pre-registered floor clause says a floored off arm answers nothing), so identification survives the rename **at a working level in 3** (Haiku numbers/rule, Luna off); **0 refuting**; **2 inconclusive** (Luna numbers/rule; Luna rule Δ −0.115 [−0.197, −0.032], sub-0.30). **Not a mechanism claim.** Count is over provider-specific cells only — the pooled ×3 rows (all confirming) reuse the same trials and are a summary, never independent confirmations. Paired promoted to primary after seeing results, justified by the matched-pair design (point estimate unchanged; moves Haiku numbers inconclusive→confirming vs the unpaired 3/6). Disclosed in the report + DECISIONS 2026-09-22. FINDINGS F13; HYPOTHESES H8. |
| **Reference-context dependence is model-specific (H7).** | **Model dependence ESTABLISHED, driver NOT identified** (n=2 models; capability / hidden reasoning tokens / training all confounded — L28). Use "failed to replicate," not "refuted." FINDINGS S16/F14. |
| **Positive-symptom under-detection generalizes to a second mechanism.** | **Failed to replicate** (Stage-2 G1): `metric_inflation` anchor-off detection 0.250 [0.083,0.417] = `label_corruption` 0.250; diff +0.001 [−0.281,+0.250]. Symptom-direction≡blindness not supported (FINDINGS S1). |
| **The data-leakage condition is anchor-off-blind.** | **Observed** (data_leakage off-detection 0.042 [0.000,0.125]) but **cause not isolated** — leakage-specific vs representation/legibility unresolved; the representation ablation is a Stage-3 test (STAGE3_PLAN §3.4). |
| **Recovery discriminates diagnosis quality.** | **Does not, on current operators — degenerate** (L19): `not_recovered` 0/138. The evidence is **B2's 30/30 recovery** — a config-reset baseline with **no fault diagnosis**, reading only the agent-visible surface plus the committed clean reference config (never hidden material), recovers every case. (B2 is not "blind": it carries declared workload knowledge — the clean resolved config and which keys are derived.) *(Corrected 2026-09-23: the `DegenerateAgent`'s 18/18 was previously cited as the proof, but it reads the oracle repair from hidden verification material, so its recovery is true **by construction** and demonstrates nothing about a blind policy.)* Recovery reported for completeness only. |
| **Control false-positive rate.** | **First FPR measured on 20 unique controls (Sweep 3), still imprecise** × 2 providers — numbers **0.025 [0.000,0.075]**, off **0.025**, rule **0.100 [0.000,0.225]**. *Precision:* case-clustered 95% CI half-width ≈ **±0.04** (numbers/off) and **±0.11** (rule) at the observed rates; the numbers − rule contrast (−0.075 [−0.200, 0.000]) touches zero, so no arm difference is established. *(Corrected 2026-09-23: "first adequately-powered" withdrawn — 20 meets the L20 count threshold but this precision does not support "adequate"; and the claim that "the single out-of-band control drives the anchored FPs" contradicted the table — in the rule arm **3 of 4 FP trials are on IN-BAND controls**; across both anchored arms the out-of-band control accounts for 2 of 5 FPs.)* Zero-event strata carry a one-sided upper bound (correction #6). Supersedes the under-powered Sweep-1 (2 clusters) / Stage-2 (3 clusters, L20) rates. |
| **Tool use (ReAct) helps.** | **Supported but confounded** (FINDINGS S4): ReAct − static evidence F1 +0.135 [0.075,0.204] overall, but arms also differ in calls/deliberation/tokens/prompt; needs a token-matched baseline. |

## c. Known limitations (pointers to LIMITATIONS.md)

- **L1** lr_warmup degradation is bimodal, not graded (retired from the σ-ladder).
- **L2** One model, one workload (Haiku 4.5 / Adult-MLP) — everything is pending replication.
- **L3** The mean−2σ healthy band has a structural false-alarm floor (~2.3% one-sided under the fitted normal; normality CHECKED at n=30, not assumed — §0.5), and reference/control seeds overlap `{0,1,2}` (control FPR biased LOW). §5.1 (2026-09-16) landed the retain+label+stratify build-guard change; §5.2 still cures the seed circularity. Published control FPRs (Sweep-1 0.222; gate 0/12·6/12·2/12) were measured under the OLD rejecting guard on in-band-only controls — no number changes, interpretation narrows (L3(iii)).
- **L4** Identification depends on a principled root-token spec (versioned/hashed).
- **L5** Cloud-native / multi-stage faults are simulated or absent (Phase I).
- **L6** Cost figures are token-based estimates (console actuals pending).
- **L7** Confidence output is too sparse to gate on.
- **L8** Folded-repair recovery depends on a strict extractor.
- **L9** Symptom direction is perfectly confounded with operator identity (Sweep 1).
- **L10** The anchor confounds a numeric reference with an explicit decision rule.
- **L11** Sweep 1's training ran unpinned (reference itself canonical); numbers off-canonical.
- **L12** Small case count; the pre-registered matched-σ analysis was not run in-pipeline.
- **L13** Instructions are delivered as the initial user turn, not the provider system role.
- **L14** The workload's memorization ceiling limits which positive-symptom mechanisms it hosts.
- **L15** Adult contains duplicate records shared across splits (12 rows).
- **L16** The two positive-symptom operators are not matched on within-case detectability.
- **L17** Evidence scorer changed between sweeps (v1 → v2); Sweep-1 values are v1.
- **L18** The native-amd64 reference is byte-exact only within a microarchitecture.
- **L19** The recovery axis is degenerate on the three Stage-2 gate operators.
- **L20** Controls are under-powered: 3 unique healthy cases.
- **L21** The Stage-2 gate has split provenance (agent host / verify canonical in-container).
- **L22** Detection on the Stage-2 operators proceeds by config legibility, not metric reasoning.
- **L23** Per-case cross-platform drift affects BOTH metrics (native-vs-emulated up to ~2.8σ visible / ~2.1σ hidden, seed-dependent); native-vs-native is byte-exact (EPYC 9V45 ≡ 7763). L18 was mean-level, cross-microarch, native-only — it does not license native-vs-emulated or per-case claims. Artifacts must be built native amd64 (guard enforces); pre-guard artifacts (Sweeps 1–2, macOS) are internally consistent and stand.
- **L24** The metric tier's "the model is healthy" guarantee is partly SELECTED, not observed (the metric build guard discards out-of-band metric cases) — resolve before Sweep 3.

## d. What is next

**SWEEP 3 (`h8_xprovider`) COMPLETE (2026-09-22).** The H8 neutral-key ablation + cross-provider sweep
ran (agent phase 978/984 cells, $24.03, 6 unrun — all neutral×Luna×static; verify 834 reruns). Report:
`docs/audits/sweep_h8_xprovider_generated.md`. Results (all cited there):
- **H8 — identification often survives the tested key renaming; equivalence unresolved in two anchored
  conditions; Luna's rule arm shows a measurable decrease** (reworded 2026-09-23 from "fault-mechanism,
  not name-reading": renaming tests dependence on those two names only; code-pattern recognition and
  general leakage heuristics are not ruled out; Haiku off is equivalent failure at ~6%). PRIMARY analysis = PAIRED (strength×seed)
  bootstrap (point estimate identical to unpaired; promoted after seeing results, justified by the
  matched-pair design, unpaired retained alongside — disclosed). Neutral−descriptive identification
  equivalent within ±0.15 in **4 of 6 provider-specific cells** (Haiku off/numbers/rule, Luna off),
  **0 refuting**, **2 inconclusive** (Luna numbers/rule, modest sub-0.30 gap); pooled ×3 confirming is a
  summary of the same trials, not counted. Vs unpaired 3/6 — pairing moves Haiku numbers to confirming. FINDINGS F13.
- **H7 — reference-context dependence is MODEL-SPECIFIC (failed to replicate as a general effect).**
  Off-anchor leakage detection Haiku 0.083 vs Luna 0.819; band adds ~90 pts (Haiku) / ~17 (Luna). The
  Stage-2 "strongest supported claim" is narrowed to Haiku; driver unidentified at n=2. F14/S16, L28.
- **Secondary (detection unchanged between variants): NOT met under anchoring** (neutral 6–9 pts
  lower; isolation evidence rules out an instrument cause → exploratory: key name affects detection
  *confidence* under anchoring, not identification). **Controls:** first ≥20-control FPR (0.025 /
  0.025 / 0.100). **Luna:** rule arm doesn't help; ~6% static evidence_refs crashes (80% retried, 6
  lost — L29). Verdict logic corrected mid-analysis to a CI equivalence test (was point-based;
  DECISIONS 2026-09-22, RESEARCH_LOG 35).

**NEXT GATE: write the Stage-4 plan** (cross-model / cross-workload design that can identify the
driver of the model difference — matched reasoning budget, ≥3 models, and/or a second workload;
close the L28/L29 gaps and a one-sided H8 equivalence pre-registration for replication). Not yet
written. Per the standing rule, no new instrument work starts until the Stage-4 plan lands.

---

**Stage 3 v2 (`STAGE3_PLAN.md`) — Part 0: Hygiene before science (BLOCKING).** Nothing else starts
until Part 0 lands. Done so far: citation audit (§0.1 — `CITATIONS.md`), canonical CURRENT_STATE
(§0.2 — this page), reproducible analysis pipeline + records release (§0.3 — plan-driven report,
committed `results_release/`, CI byte-match + guards), evidence scorer v2.1 (§0.4), and the **30-seed
reference distribution (§0.5 — ADOPTED:** `tolerance_lower` 0.843719 = mean−2σ; empirical band recorded
but not adopted; normality checked; Sweeps 1/2 frozen as 10-seed-era historical artifacts).

**GATE 0 CLOSED (2026-09-18).** All closure conditions from the on-hold entry are met: (1) the known-answer gate's **`--full` mode (with `verify_repair`) is GREEN on main** (CI run 35299999490); (2) **`--full` is documented (DECISIONS) and wired into CI** — unconditionally in `build-validate`, and conditionally (on a committed-reference / data-pin change) in `reference-change-guard`; (3) the **structural ≥2σ+1e-3 margin rule** for positive-symptom rungs landed (`operators/margins.py`, enforced in BOTH operator build guards AND the calibration tests), with `data_leakage` mild recalibrated **p 0.35→0.28** (native largest-p-that-clears) and all six positive-symptom rungs clearing both halves natively; (4) the native **`[200–229]` band is validated end-to-end on main** — the PR #10 merge adopted the band onto main (main had still been on `[0–29]`), and `reference-change-guard` correctly detected the reference change, **rebuilt ALL cases against the committed reference, and ran the FULL gate GREEN**. Merged: PR #10 → main `5edfedc`. **Next: STAGE3_PLAN v3 Part 2 — neutral-key variant.** Per v3's standing rule, INSTRUMENT WORK STOPS here and resumes only when a deferred item's revival condition fires.

*(superseded 2026-09-18 — Gate 0 CLOSED, see above)* **GATE 0 ON HOLD (re-opened 2026-09-17).** Adopting the tighter native `[200–229]` band broke the recovery axis (18 CI failures on PR #10; the 350/0 FAST gate ran without `verify_repair`). Gate 0 does NOT close until: (1) the recovery MEAN-rule lands and the 18 recovery/oracle-round-trip tests are green in CI, (2) the known-answer gate's `--full` mode (with `verify_repair`) is green, and (3) the `--full` requirement is documented + wired into CI (the CI YAML step follows when the token has `workflow` scope). Progress: B2 re-measured (detection/recovery 30/30) ✓; recovery mean-rule + `compute_recovery_verdict` landed ✓ (CI-pending). *(The closure text below is SUPERSEDED.)*

*(superseded 2026-09-17)* GATE 0 CLOSED. §0.5→§5.1→§5.2 landed: reference moved to native EPYC `[200–229]` (tol 0.844655), the four seed sets are disjoint (W3b), and the 50-case set (30 faulty + 20 controls, seeds 50–69) validates 50/50 with a native known-answer gate of **350 checks, 0 FAIL**. The 20-control band-position distribution was measured (visible **0/20** below-band, hidden **1/20** below-band — case_0033; **5% visible / 10% hidden** out-of-band; low-side boundary-sensitive across microarchs), correcting an earlier invented “25%”: the old-guard selection bias is **mild and real** (≈1/20 = 5% would have been rejected), not severe. **Next: STAGE3_PLAN v3 Part 1 — non-LLM baselines (free).** Per v3's standing rule, INSTRUMENT WORK STOPS here and resumes only when a deferred item's revival condition fires.

*(historical, superseded)* Forced next sequence (§0.5 ruling): the 30-seed band still overlaps
control/calibration seeds `{0,1,2}`, biasing control FPR **LOW by construction**. The fix is ordered
and must land in this order before Gate 0 closes: **§0.5 (done) → §5.1 (DONE 2026-09-16: retain + label
out-of-band controls; control build guard records band position instead of rejecting; control FPR
stratified in_band/out_of_band, keyed on the visible band by mechanism) → §5.2 (disjoint seeds:
reference → `[200–229]`, controls rebuilt on confirmatory seeds — MUST run native amd64) → Gate 0.**
§5.1 landed before §5.2, so the build guard no longer silently rejects the out-of-band controls that
make the measurement honest. **Two §5.1 follow-ups sequenced before Sweep 3 (Part 9):** (1) native-only
artifact generation — now enforced by `harness.platform_guard` (L23); (2) the metric-tier in-band
selection bias — retain + label out-of-band metric cases as §5.1 did for controls (L24, reported not
yet fixed). **Remediation note:** the three controls were rebuilt under EMULATION during §5.1 (a local
Apple-Silicon working tree; `cases/` is gitignored, nothing committed) — they must be rebuilt on native
amd64 (CI) before use; the canonical item-5 band table was computed from the native CI reference.

**Gate 0:** citations verified; CURRENT_STATE committed and consistent; `report` regenerates the
Stage-2 tables byte-identically from records; v2.1 tests green; **native EPYC `[200–229]` reference adopted and validated end-to-end on main by `reference-change-guard`; Gate 0 CLOSED (2026-09-18) on the full-mode `verify_repair` gate**; §5.1/§5.2
seed-disjointness landed.

**CI lanes (2026-09-18/19):** split by cost. **FAST** (every push, ~2–3 min): fast tests
(`-m "not slow_integration"`) + the cheap static guards (frozen-report byte-match,
reference-change detect) — no case build, no training. **FULL** (pull_request to `main` +
nightly): the FAST lane plus **`build-validate`** (build-all + validate-all + the FULL
`verify_repair` gate + margin/baseline/calibration), the slow/training tests, and the
two-runner reference-repro. Training tests are auto-marked `slow_integration` at collection
(`tests/conftest.py`). Case-build (train-heavy) is what made push slow, so it moved to the
full lane (a case-build break surfaces at PR time, not on push). The merge guarantee is
preserved by branch protection — `test-suite-slow` + `build-validate` (FULL gate on a PR)
are REQUIRED checks (DECISIONS 2026-09-18/19). `pytest -n auto` on the slow lane is deferred
(needs `pytest-xdist` added to the pinned image).

## e. Document map (by role)

**AUTHORITATIVE** (current; this page supersedes their *status* text only):
- `CURRENT_STATE.md` — this page: current state, claim statuses, next gate.
- `problem_statement_v0.3.md` — scope, claims, RQs (CLAUDE.md authority #1; do not exceed).
- `harness_spec_v0.3.md` — as-built architecture / interfaces.
- `CLAUDE.md` — project rules and authority ordering.
- `STAGE3_PLAN.md` — the current plan (v2).

**DETAILED RECORD** (append-only; never reinterpreted — earlier entries superseded by later ones and
by this page, not edited):
- `DECISIONS.md`, `RESEARCH_LOG.md`, `HYPOTHESES.md`, `FINDINGS.md`, `LIMITATIONS.md`, `CITATIONS.md`.
- `docs/audits/` — append-only evidence trail (gate certifications + sweep reports; committed, never
  gitignored). Per sweep: `sweep_<name>_generated.md` (machine-authored, the ONLY place a number is
  authored — regenerated by `make report`, byte-matched in CI) and `sweep_<name>_..._analysis.md`
  (the human narrative, which may not invent a number — checked by `check_analysis_numbers.py`).
- `results_release/<sweep>/` — sanitized, committed records release (allowlist + scan + trusted
  exclusion; STAGE3_PLAN §0.3). `rebuild_tables.py` reproduces each generated report from it alone
  (no `cases/`, `results/`, or registry) — the external-verification path.

**NEEDS UPDATE** (stale content, purpose intact): `TrainMD_Codebase_Walkthrough.md` (last synced
`0965f3a`; v4 sync scheduled).

**HISTORICAL** (purpose finished; superseded where it conflicts here): `harness_spec_v0.1.md`,
`HARDENING_PLAN.md`, `G1_GATE_PLAN.md`. *(Stage 3 v1 also belongs here but `STAGE3_PLAN_v1_historical.md`
was never committed.)*

**Referenced but non-existent** (drafted, never committed — do not cite as sources):
`problem_statement_v0.4`, `harness_spec_v0.2`, `STAGE3_PLAN_v1_historical.md`.

## f. Change-classification taxonomy (look it up; do not reconstruct)

Five categories for a change to a committed fact, so the next classification is a lookup:

- **Correction** — a PUBLISHED number was measurably wrong. Bumps `corrections_count`; the
  corrected value becomes primary, the prior retained for audit. *e.g.* correction #5 (evidence
  v1→v2.1); correction #6 (2026-09-23, zero-event intervals: every rate with 0 observed events had
  rendered a false-precision `[0, 0]`, replaced by a one-sided 95% Clopper–Pearson upper bound — an
  interval is a published number, so this counts even though no point estimate moved); the 6 tracked
  in `corrections_count`.
- **Latent-bug fix** — a defect caught BEFORE it published. No `corrections_count` change
  (nothing wrong was ever released). *e.g.* the §0.3 scorer/analysis fixes.
- **Documentation error** — prose that was NEVER true as written. No number changes;
  `corrections_count` unchanged. *e.g.* `case_0031/0032` mislabelled “control” (they are
  `silent.metric_inflation.v1`) — DECISIONS 2026-09-16; and the 2026-09-23 framing corrections
  (STAGE4 4.0.2/4.0.3): the H8 “mechanism, not name-reading” headline, the control narrative that
  contradicted its own table, “first adequately-powered FPR”, the `DegenerateAgent` 18/18 read as a
  blind-repair result, and B2's identification miss read as pure capability — all overclaims, none a
  moved number.
- **Stale snapshot** — prose that was TRUE when written but the world moved under it. Not an
  error; update in place. *e.g.* `case_count` 33 (correct pre-§5.2, now 50); the retrospective's
  test count (grew every PR).
- **Shipped-but-unexploited vulnerability** — an exploitable RULE (not a wrong number) that
  reached published results, was then AUDITED across every stored label it could have mis-scored,
  found to have fired **zero** times, and hardened. No `corrections_count` change — no published
  number was ever wrong — but distinct from a latent-bug fix because the defect *did* ship; the
  disclosure carries the audit that proves zero impact. *First instance (2026-09-22):* the
  identification matcher `root_token_v1`→`root_token_v2` — v1 matched concept stems as free
  substrings and would have scored fault negations (`no_leakage`) and off-concept collisions
  (`memory_leak`) as correct; audit of all 1156 scored-correct identifications in Sweeps 1–3 found
  0 such labels, re-score delta 0. DECISIONS 2026-09-22; `scripts/audit_stage4_identification.py`.
