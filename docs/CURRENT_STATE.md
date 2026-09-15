# TrainMD — Current State (canonical)

**This is the single source of truth for the project's current state.** Updated at every gate.

> **Rule.** If this page and any other document disagree, this page is wrong OR the other document
> is stale — **fix whichever is stale in the same commit.** Machine-checkable facts in §a are
> verified against the repo by `scripts/check_current_state.py` in CI; that guard fails loudly on
> drift. Last updated: 2026-09-15 (Stage-3 v2, Part 0 / §0.2).

---

## a. Instrument (machine-checkable)

The values below are checked against the repo by `scripts/check_current_state.py`. Do not hand-edit
them out of sync with the registry / code.

```yaml
operators_count: 6
operators:            # operator_id  (tier)
  - control.healthy.v1          # control
  - crash.shape_mismatch.v1     # execution
  - silent.data_leakage.v1      # dynamics
  - silent.label_corruption.v1  # dynamics
  - silent.lr_warmup.v1         # dynamics (bimodal-collapse; retired from the σ-ladder — L1/S12)
  - silent.metric_inflation.v1  # metric
case_count: 33                  # cases/registry.hidden.yaml (6 × 5 faulty ops + 3 controls)
evidence_scorer_primary: evidence_v2.1
evidence_scorer_versions: [evidence_v1, evidence_v2, evidence_v2.1]
canonical_image_digest: sha256:0354db57c29a5092ace862a0d8716dfe3729d4f8b893fe3079c66d947daeb25d
reference_seeds: 10
latest_sweep: stage2gate
corrections_count: 5
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
- **Canonical environment:** Linux/amd64 container, thread-pinned; base `python:3.11-slim-bookworm`;
  image digest above (`docker/IMAGE_DIGEST`). Reference seeds `[0–9]` (**10**; *in flight:* raised to
  **30** in STAGE3_PLAN §0.5); hidden eval seeds `[100,101,102]`.
- **Latest committed sweep:** `stage2gate` (252 cells; agent phase on host/API, verify phase canonical
  in-container). Agent-phase cost **~$11.71 estimated** (actual pending). Prior: `sweep1` (~$12.76 est).

## b. Claims and their status

Statistical-language rules (STAGE3_PLAN §"Statistical-language rules"): a failed pre-registered
prediction is **"failed to replicate"**; an effect is **"supported across N operators within one
model-workload setting"** (never "confirmed" in the paper); rationale text supports **"not
mentioned,"** never "not used"; every rate states its cluster count.

| Claim | Status |
|---|---|
| **A numerical reference baseline restores detection** (numbers arm closes ~94–95% of the off→rule gap on all 3 gate operators). | **Supported** across 3 operators within one model-workload setting (Stage-2 G2 / FINDINGS S13, F10). Strongest-supported claim. Control-specificity cost only *suggestive* (3 control clusters — L20). |
| **Positive-symptom under-detection generalizes to a second mechanism.** | **Failed to replicate** (Stage-2 G1): `metric_inflation` anchor-off detection 0.250 [0.083,0.417] = `label_corruption` 0.250; diff +0.001 [−0.281,+0.250]. Symptom-direction≡blindness not supported (FINDINGS S1). |
| **The data-leakage condition is anchor-off-blind.** | **Observed** (data_leakage off-detection 0.042 [0.000,0.125]) but **cause not isolated** — leakage-specific vs representation/legibility unresolved; the representation ablation is a Stage-3 test (STAGE3_PLAN §3.4). |
| **Recovery discriminates diagnosis quality.** | **Does not, on current operators — degenerate** (L19): `not_recovered` 0/138; DegenerateAgent scores 18/18 strict recovery. Recovery reported for completeness only. |
| **Control false-positive rate.** | **Under-powered** (L20): 3 unique control cases; arm CIs span up to [0.000,0.750]. No control claim is established. |
| **Tool use (ReAct) helps.** | **Supported but confounded** (FINDINGS S4): ReAct − static evidence F1 +0.135 [0.075,0.204] overall, but arms also differ in calls/deliberation/tokens/prompt; needs a token-matched baseline. |

## c. Known limitations (pointers to LIMITATIONS.md)

- **L1** lr_warmup degradation is bimodal, not graded (retired from the σ-ladder).
- **L2** One model, one workload (Haiku 4.5 / Adult-MLP) — everything is pending replication.
- **L3** The ±2σ healthy band has a structural false-alarm floor (~5% under normality).
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

## d. What is next

**Stage 3 v2 (`STAGE3_PLAN.md`) — Part 0: Hygiene before science (BLOCKING).** Nothing else starts
until Part 0 lands. Done so far: citation audit (§0.1 — `CITATIONS.md`), canonical CURRENT_STATE
(§0.2 — this page), reproducible analysis pipeline + records release (§0.3 — plan-driven report,
committed `results_release/`, CI byte-match + guards). Remaining: evidence scorer v2.1 (§0.4), a
30-seed reference distribution (§0.5).

**Gate 0:** citations verified; CURRENT_STATE committed and consistent; `report` regenerates the
Stage-2 tables byte-identically from records; v2.1 tests green; 30-seed reference adopted.

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
