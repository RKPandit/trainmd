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
| S1 | **Leakage-specific anchor-off blindness (the symptom-*direction* generalization is REFUTED).** `data_leakage` is missed anchor-off and a numeric baseline restores it — but a *second* positive-symptom mechanism (`metric_inflation`) is **not** harder than the subtle negative reference, so positive symptom direction is not what causes the blindness. | Stage-2 G1: `metric_inflation` off **0.250 [0.083, 0.417]** = `label_corruption` **0.250** (diff +0.001 [−0.281, +0.250]) ≫ `data_leakage` **0.042 [0.000, 0.125]**. Sweep-1 comparator was pooled (correction #4): lr_warmup **0.944** + label_corruption **0.333** → subtle gap ~25 pts, not 55. | **symptom-direction generalization REFUTED (Stage-2 G1)** · leakage-specific blindness retained · numeric-baseline effect → S13, now **model-specific** (Haiku; F14/S16) |
| S2 | ~~Detection follows symptom sign first, then magnitude.~~ **H2 (a fitted σ threshold) is REFUTED** — no threshold fitted, pooled curve non-monotone. Exploratory successor (post-hoc, to pre-register): symptom *sign* moderates magnitude→detection. | Sweep 1 H2 per-case table. | refuted (prediction) · exploratory successor · pending prospective test |
| S3 | **The reference band is a trade: it rescues true detection and induces false alarms on healthy runs.** | Sweep 1: anchor-on control FPR 0.222, 95% CI [0.0, 0.5] — 4/18 from just 2 unique healthy cases (not a population rate; the width argues for 20+ controls). | unplanned · under-powered · pending replication |
| S4 | **The ReAct−static gap is real but does not isolate tool use.** ReAct beats static +0.135 evidence F1 overall, 95% CI [0.075, 0.204], most on subtle noise; leakage sub-claim +0.006 (≤0 criterion **not** formally met). The arms also differ in calls, deliberation, tokens, and prompt text. | Sweep 1 H6 + cost table. | overall confirmed · sub-claim not formally confirmed · confounded (needs token-matched baseline) |
| S5 | **On the strict endpoint, this model names faults somewhat more reliably than it autonomously repairs them.** id − *strict* recovery is 0.10–0.24 (CI excludes 0) on 3/4 operators; *semantic* recovery nearly closes it, so most of the gap is submission-format compliance + strict admissibility. Pre-registered direction (recovery > id) refuted. **The gap is "naming vs correctly-formatted admissible submission," not "naming vs fixing" — recovery is degenerate on these operators (L19).** | Sweep 1 H3; Stage-2: `not_recovered` 0/138; degeneracy evidence = **B2's 30/30** (a no-diagnosis config reset). *(Corrected 2026-09-23: the DegenerateAgent's 18/18 was cited here, but it reads the oracle repair from hidden material, so it is true by construction.)* | refuted (predicted direction) · modest id>strict dissociation · **recovery axis degenerate (L19)** · pending replication |
| S6 | **Diagnostic outcomes are reproducible under nondeterminism; identification agreement drops on the hardest fault.** | Sweep 1 H4: mean agreement 0.82; leakage identification agreement 0.71 vs lr 0.96. | partially confirmed · pending replication |
| S7 | **Adult+MLP is robust to symmetric label noise**; label corruption is a *subtle* fault on tabular data. Even the operator's calibrated ladder (33/38/42% flips) degrades accuracy only ~1–2 pt. | Calibration sweeps (DECISIONS 2026-09-11, ladder 0.33/0.38/0.42). | unplanned · workload-specific |
| S8 | **A visible knob without a norm is not a signal.** A configuration value that names a fault, sitting in plain view in the prompt, does not trigger detection unless the agent also has a reference for what is normal — the missing baseline, not missing information, is what blinds it. | Sweep 1: `label_noise_fraction: 0.38` present, un-truncated, in 18/18 static anchor-off contexts and echoed in the response, yet static detected the fault 1/18 vs ReAct 11/18. | unplanned · pending replication |
| S9 | **~1 in 10 repairs is misplaced — an agent-compliance failure, counted only toward the semantic endpoint.** The model emits a well-formed repair as text in a sibling string field instead of the structured tool argument; this is a failure of the system under test, so it does *not* count toward strict autonomous success (it is recovered post-hoc for the semantic endpoint only). | Sweep 1: 31/324 (≈9.6%) folded; strict vs semantic recovery reported side by side. | unplanned · pending replication |
| S10 | **The workload constrains which positive-symptom mechanisms are possible: row memorization cannot inflate a metric here.** A validation metric can be inflated by memorized training rows only up to *train* accuracy; Adult/MLP's train–val gap is ~0.010, so the memorization ceiling (~0.863) sits only ~0.003 above the visible band edge (0.860) — no headroom for a laddered positive symptom. The viable second positive-symptom mechanism on this substrate is metric-side (biased computation), not data-side (overlap). | Step-0 (in-container, thread-pinned): overlap augmented val_acc ≤ 0.857 (below edge) for p∈{0.05,0.15,0.30}×seeds{0,1,2}; train_acc 0.862–0.864; biased-metric mechanism (a) clears the band on a plausible→implausible ladder (reported ≈0.88/0.94/0.98) with the checkpoint unchanged. | unplanned · workload-specific |
| S11 | **Adult contains duplicate records — 12 appear in both train and the hidden test by content hash — though the splits are index-disjoint.** A pre-existing dataset property, not an operator-induced leak; disjointness checks must therefore test *non-increase* of overlap, not absolute content-disjointness. | Step-0 row-hash intersection = 12 of ~30k; `data_prep` partitions one permutation (index-disjoint by construction). | unplanned · dataset property |
| S12 | **`lr_warmup`'s failure on Adult/MLP is BIMODAL, not graded** — a per-seed collapse to the majority-class baseline whose probability rises with the learning rate (and is microarch-sensitive), with no stable partial-degradation regime. The operator yields *detection* data, not σ-magnitude; the H2 σ-axis rests on `label_corruption`. Corrects the earlier "ladder saturation" (L1). | Calibration sweep (5 seeds, emulated amd64; `scripts/calibrate_lr_warmup.py`): collapse-to-0.756008 rate 0.10→0/5, 0.12/0.15→2/5, 0.20→4/5, **0.50 & 1.00→5/5**; at lr 0.30 one seed fell to 0.684 (below the majority baseline — anti-learned). | unplanned · workload-specific |
| S13 | **A numerical baseline restores detection — but this is MODEL-SPECIFIC (Haiku; small for Luna).** Supplying the healthy metric band flips *Haiku* from "looks fine → healthy" to detecting the fault, and the bare band (not the decision rule) does ~all of it. A second model (Luna) detects the silent fault off-anchor and gains only ~17 pts from the band. ~~The strongest-supported claim in the project.~~ | Stage-2 G2 (F10, Haiku): **numbers** arm closes **94–95%** of the off→rule gap on 3 operators; replicates S8/F8. **Sweep 3 (F14): off-anchor leakage detection Haiku 0.083 vs Luna 0.819 — band adds ~90 pts for Haiku, ~17 for Luna.** | **Haiku-specific** (Stage-2 G2) · **failed to replicate as a general effect on the 2nd model (F14)** · first ≥20-control FPR now measured (H8 controls) |
| S16 | **Reference-context dependence is model-specific.** The Sweep-1/gate headline that agents need a numeric reference baseline to detect silent faults holds for Haiku and largely does not for Luna. Model dependence is established; its cause (capability / hidden reasoning tokens / training) is not, at n=2. | Sweep 3 (F14): anchor-off descriptive-leakage detection **Haiku 0.083, Luna 0.819**; band adds ~90 pts (Haiku) vs ~17 pts (Luna). Two models, one workload, one mechanism family. | **model dependence ESTABLISHED · driver NOT identified (n=2, L28)** · pending a controlled cross-model design |
| S14 | **Detection tracks symptom *obviousness*, not symptom sign** (candidate replacement for the refuted S1 sign-claim). Detection falls monotonically with how visible the fault's symptom is: catastrophic crash → collapse → subtle silent → inverted (leakage). | Sweep-1 + gate anchor-off detection: shape crash **1.000**, lr collapse **0.944**, subtle silent (label 0.333 / metric 0.250) **0.25–0.33**, leakage **0.042–0.083**. | **EXPLORATORY · post-hoc · must be pre-registered before it is tested** |
| S15 | **On config-knob faults, a config-delta baseline (WITH clean-resolved-config + derived-key knowledge) matches the ref-anchored LLM on detection and recovery at better specificity; the agent's measured surviving value is identifying faults whose knob name ≠ the concept, and it is anchor-dependent.** NOT "the LLM adds nothing on detection/recovery" — that generalization is Sweep-3 / code-origin territory. | B2 (native 50-case): det **30/30**, FPR **0/20**, id **18/30**, ev 0.63, rec **30/30**. LLM ref-anchored (frozen, superseded set): det 1.00, id 0.96, rec 0.94, FPR 0.22. B2 id misses exactly `data_leakage` + `metric_inflation`; LLM off-anchor leakage id **0/30**. **Sweep 3 (F13): leakage identification often survives the tested key rename — equivalence unresolved in two anchored conditions, Luna's rule arm measurably lower, 0 refuting; this tests dependence on the two key names only, not mechanism understanding (code-pattern recognition / general leakage heuristics not ruled out).** | unplanned · per-operator DIRECTIONAL only (baselines native, LLM frozen-superseded — no cross-set gap CI) · **neutral-key test now DONE (H8/F13 — 4 of 6 cells meet the criterion as run; excluding floored Haiku-off, 3 of 5 answering cells confirm, 2 inconclusive)**; cross-set LLM−B2 gap CI still pending a matched-set run |

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

**Six** post-hoc corrections have been applied, disclosed, with originals kept beside corrected
values in every table — five to Sweep-1 records (#1–#5, below) and a sixth (#6, 2026-09-23) to the
interval renderer across every released sweep. The first two were **scoring/schema artifacts, not model behaviour**; the third
(#3) is **model-side output folding, not a harness bug** — we recover a well-formed repair the
model misplaced; the fourth (#4, added 2026-09-15) is an **analysis-aggregation correction** —
a pooled comparator that averaged two unlike operators; the fifth (#5, 2026-09-15) is an
**evidence-scorer migration** — Sweep-1 records carried v1 while the docs said v2; they are migrated
to **v2.1** (bipartite one-to-one) primary (details below). The first three *removed* a harness-imposed
penalty on the model; none changed ground truth to raise a score. Found by the read-only
diagnostics and corrected by principle — never by copying observed outputs into ground truth.

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

4. **H1 negative-symptom comparator was POOLED across unlike operators (2026-09-15, Stage-2
   re-analysis).** Sweep 1 reported the anchor-off negative-symptom comparator as **0.639**,
   pooling lr_warmup and label_corruption over 12 cases. Per-operator re-analysis of the *stored*
   Sweep-1 trials (`scripts` re-run, no re-scoring, no new trials) splits it: **lr_warmup 0.944
   [0.833, 1.000]** (34/36, 6 cases) and **label_corruption 0.333 [0.194, 0.444]** (12/36, 6
   cases). lr_warmup's faults collapse to the majority baseline (~44σ — unmissable), so pooling it
   with the *subtle* negative fault inflated the comparator. Against the subtle negative-symptom
   operator alone the H1 anchor-off gap is **~25 points (0.083 vs 0.333)**, not 55. The Stage-2
   gate independently measured label_corruption anchor-off detection at **0.250**, consistent with
   0.333. This changes an *interpretation* (the comparator baseline), not any trial's score. Touches
   **H1/S1/F1** — see F1's correction below and the status revision.

5. **Evidence-scorer migration: Sweep-1 records were V1, not V2; migrated to V2.1 primary (2026-09-15).**
   The union bug an external reviewer flagged (v2 credits each submitted ref against the UNION, so
   duplicates/shotgun over-score) is fixed by **v2.1 bipartite one-to-one matching**. Making v2.1 the
   record primary surfaced that **Sweep-1 `scores.evidence` had never left v1** — the v1→v2 rescore was
   *disclosed* on 2026-09-13 (DECISIONS) but never persisted, so §0.3's "v2 primary" claim was a
   **provenance mislabel** (a wrong statement about which instrument produced a number — the more
   serious half). Decomposition of the change (v1 stored → v2.1), NOT what the first framing said:
   - **(a) v1→v2 span-strictness** (already disclosed 2026-09-13, L17): dominates — `shape_mismatch`
     mean **0.807 → 0.607** (over-broad traceback line/code spans fail v2's IoU≥0.5 + 3× width).
   - **(b) v2→v2.1 bipartite fix**: the union bug actually bit **`lr_warmup`, not `shape_mismatch`** —
     **5 sweep-1 lr_warmup trials**, ~**−0.13** each (duplicate/overlapping refs); stage2gate and all
     config-key operators **unchanged** (v1=v2=v2.1).

   | sweep | operator | trial | v2 | v2.1 | Δ |
   |---|---|---|---|---|---|
   | sweep1 | lr_warmup | case_0023 | 0.706 | 0.571 | −0.134 |
   | sweep1 | lr_warmup | case_0026 | 0.800 | 0.667 | −0.133 |
   | sweep1 | lr_warmup | case_0026 (×3) | 0.632–0.706 | 0.500–0.571 | ≈−0.13 |

   **H6 (ReAct − static evidence F1) recomputed under v2.1: 0.135 → 0.1343**, CI [0.070, 0.206];
   **pre-registered ≥ +0.10 criterion still holds** (point ≥ 0.10; CI-lower still dips below 0.10 —
   unchanged from the original verdict), because shape_mismatch drops for both agents ~equally so the
   *difference* barely moves. Retained: `evidence_v2` + `evidence_v1` beside `evidence` (v2.1) on every
   record. My first framing ("v2.1 fixed shape_mismatch") was **wrong** and is corrected here.

6. **Zero-event intervals rendered a false-precision `[0, 0]` (2026-09-23; third external review,
   STAGE4 4.0.2).** The case-clustered bootstrap percentile CI returns `[0, 0]` for any stratum with
   **zero** observed events, because every resample also contains zero — which reports *zero
   uncertainty from zero observations*. That is a wrong interval, not a style choice, and it sat in
   reports presented as externally verifiable. **Method:** in every table a zero-event **rate** now
   carries the **exact two-sided 95% Clopper–Pearson interval over the number of UNIQUE CASES**,
   `[0, 1 − 0.025^(1/n_cases)]` — the same cluster unit as the case-clustered bootstrap it replaces
   (trials within a case are correlated; bounding over trials would itself overstate precision), and
   two-sided so it is comparable with the intervals beside it. The one-sided form appears only in
   prose, labelled as a ceiling: twenty clean control cases still leave a **one-sided 95% ceiling of
   0.139** (~14%). Rendered `0.000 [0, U]†` with a legend; `harness/sweep_stats.zero_event_upper`, locked by
   `tests/test_zero_event_interval.py`. **No point estimate moves** — only intervals, all of which
   were wrong in the direction of **overstating precision**. Affected rows (before → after):

   | sweep | row | n_fp / n_trials | before | after |
   |---|---|---|---|---|
   | sweep1 | control FPR, off (pooled) | 0/18 trials over **3** cases | `[0.000, 0.000]` | `[0, 0.708]` |
   | stage2gate | control FPR, off (pooled) | 0/12 trials over **3** cases | `[0.000, 0.000]` | `[0, 0.708]` |
   | h8_xprovider | every zero-event control-FPR row (20 rows: pooled + in/out-of-band strata, per arm × provider) | 0 events over 1–20 cases | `[0.000, 0.000]` | `[0, 0.975]` (1 case) … `[0, 0.168]` (20 cases) |

   The three generated reports were regenerated, `rebuild_tables` byte-matches the **regenerated**
   (not the old) reports from the committed releases, and the frozen-artifact note on each records
   the correction. Scope: *rates* only — differences (e.g. numbers − rule) are not binomial rates and
   are unchanged. Rows with **1–2 events** keep their bootstrap CI but are now flagged **‡** —
   the percentile bootstrap understates uncertainty at that count (1 of 19 cases: bootstrap upper
   0.158 vs exact Clopper–Pearson 0.260), the same false-precision class as `[0, 0]`, recorded as
   LIMITATIONS L30 and not fixed here (STAGE4 plans exact CP on case-level counts for every row
   before the paper). Non-zero tiny-n strata (e.g. 1/1, 1/2) are additionally
   flagged in the narrative as single-control artifacts.

**Unchanged by corrections #1–#4:** detection trial scores — therefore H2 and the controls finding
stand as pre-registered. Recovery moves (Corrections 2–3), sharpening H3. **H1's headline is revised**
by the analysis-aggregation correction #4 + Stage-2 G1 (below). **Correction #5 moves evidence and
H6** (evidence scorer v1→v2.1; H6 0.135→0.134, verdict held) — see above. **Correction #6 moves no
point estimate and no verdict** — only the upper edge of zero-event rate intervals.

**Shipped-but-unexploited vulnerability (2026-09-22) — identification matcher hardened `root_token_v1`→
`root_token_v2`** (a fifth change-taxonomy category, CURRENT_STATE §f; NOT a numbered correction — no
published number was ever wrong). An external reviewer showed the v1 rule matched concept stems as free
substrings, so it *would* credit fault negations (`no_leakage`) and off-concept collisions (`memory_leak`)
as correct identifications. The audit — attributing each frozen-sweep record's operator from its OWN sealed
`accepted_classes`, never today's `cases/` — found **zero** such labels among every scored-correct
identification in Sweeps 1–3 (0 of 1156), and a full re-score under the hardened rule flips **0** labels in
either direction. So the rule was exploitable but was never exploited: **no published identification number,
and no H8 verdict, moves**, and the matcher hardening therefore did **not** tick the corrections count (a
moved-number counter must not tick when nothing moved; the count's later move to six is correction #6,
an unrelated interval fix). The exploitable rule is still closed by principle (negation detection,
whole-token/inflection matching, per-operator off-concept vetoes). DECISIONS 2026-09-22;
`tests/test_identification_v2_hardening.py`; `scripts/audit_stage4_identification.py`.

**Latent-bug fixes (2026-09-15; NOT corrections — no published number was wrong).** Two defects in
the analysis code were repaired while making the report pipeline plan-driven (STAGE3_PLAN §0.3), each
caught *before* it reached a committed number, so the corrections count stays **four**: (i) the H2
`detection_rate_anchor_on` filter matched "on" *after* the on→rule normalization (always empty) — but
the committed `sweep_sweep1_20260913.md` shows `anchor_on: 1.0`, so the bug postdates it and never
published; (ii) `recovery_endpoints` iterated a hardcoded 4-operator list that predated
`metric_inflation`, which would have dropped its recovery row from a generated stage2gate report (none
was ever committed; the hand analysis had it right). Both are fixed by the generic pipeline. See
DECISIONS 2026-09-15 (the correction-vs-latent-bug-fix distinction).

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

**Stage-2 correction + refutation (2026-09-15; `sweep_stage2gate_2026-09-15.md`, and correction #4
above).** Two things resolved together. (i) The negative comparator that made the pooled gap 0.556
was **inflated by pooling** lr_warmup (0.944, a ~44σ collapse — unmissable) with the subtle
label_corruption (0.333). Against the subtle fault alone the anchor-off gap is **~25 points (0.083
vs 0.333)**, not 55. (ii) The pre-registered confound-breaker — a **second positive-symptom
operator** — was built (`metric_inflation`) and tested at the gate: it detected anchor-off at
**0.250 [0.083, 0.417]**, indistinguishable from the negative reference label_corruption **0.250
[0.083, 0.458]** (`metric_inflation − label_corruption` +0.001 [−0.281, +0.250]), and far above
data_leakage **0.042**. So **the symptom-direction generalization is REFUTED (Stage-2 G1):** a
positive symptom is not intrinsically harder to detect; data_leakage's blindness is
**leakage-specific**, not a property of positive symptom direction. What survives is the *anchor*
half of the claim (a numeric baseline restores detection — now F10) and an exploratory
obviousness gradient (F11), not the symptom-sign claim.
**Status (revised).** Symptom-direction blindness: **REFUTED as a generalization** (Stage-2 G1);
the pooled-comparator "pilot support" is withdrawn. Retained, narrower: (a) data_leakage is
anchor-off-blind and leakage-specific; (b) a numeric baseline restores detection (F10). S1 revised
accordingly.

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
**Interpretation.** Part of this cost is *structural*: the one-sided `mean−2σ` health band places
~2.3% of healthy runs below it under the fitted normal (updated §0.5 — normality CHECKED at the 30-seed
band, Shapiro p=0.28, n=30, low power; the earlier "~5%" was the two-sided ±2σ figure). Part is the
model over-reading an edge. The band's benefit
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

**Stage-2 addendum (2026-09-15) — read the id−strict contrast correctly.** On the Stage-2 gate
operators, recovery is **degenerate** (`not_recovered` 0/138; a no-diagnosis config-reset baseline,
B2, recovers 30/30 — L19; the DegenerateAgent's 18/18, cited here previously, is true by construction
because it reads the oracle repair from hidden material — corrected 2026-09-23), so **id − strict recovery there is "naming vs a correctly-formatted admissible submission,"
NOT "naming vs fixing"** — strict recovery cannot fail for a wrong-but-admissible repair because
the admissible space is a single oracle-equivalent point. The Sweep-1 id > strict dissociation
above is therefore best read the same way (submission-format compliance + admissibility, which
semantic recovery nearly closes), not as "names but cannot fix." This reframing is the honest
description across both sweeps; genuine "names vs fixes" evidence needs a wide-admissible operator
(L19 remedy).

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

## Stage-2 gate (2026-09-15) — new findings and addenda

**Design.** 3 operators (`data_leakage`, `label_corruption`, `metric_inflation`) × 3 strengths ×
2 seeds × 3 anchor arms (off / numbers / rule) × 2 agents × 2 repeats + 3 controls = 252 cells,
claude-haiku-4-5. Built to break Sweep 1's symptom↔operator confound (L9) with a **second
positive-symptom operator** and to separate a numeric norm from a decision rule with a **three-arm
anchor** (L10). Agent phase on host (API calls); verify phase canonical in-container. Evidence:
`docs/audits/sweep_stage2gate_2026-09-15.md`. G1/G3 verdicts also in HYPOTHESES.md (Results).

### F10 — A numerical baseline restores detection (G2) · confirmed on three operators

**Claim.** Supplying the healthy metric band is what flips agents from "the run looks fine → healthy"
to detecting the fault; the **bare band** does the work, not the decision-rule sentence.
**Evidence** (Stage-2 G2, case-clustered). Fraction of the anchor-off→rule detection gap closed by
the **numbers** arm alone: data_leakage **95.5%** (off 0.042 → numbers 0.917 → rule 0.958),
label_corruption **94.4%** (0.250 → 0.958 → 1.000), metric_inflation **94.4%** (0.250 → 0.958 →
1.000). The rule sentence adds only 4–5 pp of detection.

| operator | off | numbers | rule | gap closed by *numbers* |
|---|---|---|---|---|
| data_leakage | 0.042 | 0.917 | 0.958 | 95.5% |
| label_corruption | 0.250 | 0.958 | 1.000 | 94.4% |
| metric_inflation | 0.250 | 0.958 | 1.000 | 94.4% |

**Control-specificity caveat (suggestive, NOT established).** A bare band may over-flag healthy
runs: control false-positive rate off **0.000**, numbers **0.500 [0.000, 0.750]**, rule **0.167
[0.000, 0.500]**; numbers−rule **+0.336 [0.000, 0.750]** — but over only **3 control clusters**, so
the CIs do not exclude "no effect." "Numbers over-flags, the rule reins it in" is a hint, not a
result (L20; needs ≥20 controls).
**Interpretation.** This is the mechanism of Sweep-1 S8/F8 ("a visible knob without a norm is not a
signal") replicated on three operators and separated into its numeric-vs-rule components: the
**missing baseline**, not missing information or an explicit instruction, is what blinds the agent.
**What would change our mind.** A second model/workload where the band does not move detection; or a
control-powered sweep showing the numbers arm's specificity cost is negligible (making the rule
sentence redundant) or large (making it necessary).
**Status.** **confirmed on three operators (Stage-2 G2)** · replicates S8 · the strongest-supported
claim in the project · control-specificity cost pending ≥20 controls.

### F11 — Detection tracks symptom obviousness, not symptom sign (post-hoc) · exploratory

**Claim (candidate replacement for the refuted symptom-*sign* framing).** Anchor-off detection
falls monotonically with how *obvious* a fault's symptom is — a catastrophic crash is caught
almost always, a majority-class collapse nearly always, a subtle silent degradation ~a quarter to
a third of the time, and an inverted (looks-*better*) leakage almost never.
**Evidence** (Sweep-1 + Stage-2 anchor-off detection, stored trials):

| symptom class | operator | anchor-off detection |
|---|---|---|
| crash (execution) | shape_mismatch | 1.000 [1.000, 1.000] |
| collapse to baseline | lr_warmup | 0.944 [0.833, 1.000] |
| subtle silent | label_corruption | 0.333 / gate 0.250 |
| subtle silent | metric_inflation | 0.250 [0.083, 0.417] |
| inverted (looks better) | data_leakage | 0.083 / gate 0.042 |

**Interpretation.** This ordering is what the refuted symptom-*direction* claim (S1/F1) was really
picking up: not that positive symptoms are special, but that *less obvious* symptoms are missed more
— and an inverted symptom is the least obvious of all. It reframes S1's survivor as a monotone
obviousness gradient rather than a sign dichotomy.
**What would change our mind — and the discipline.** It is **post-hoc and exploratory**: assembled
from data already seen, across two sweeps with different designs, small per-cell n. It **must be
pre-registered with an a-priori obviousness ordering and tested prospectively** before it is a
finding; quoted now only as the candidate framing that replaces the refuted claim.
**Status.** **EXPLORATORY · post-hoc · pre-register before testing.**

### Limitations exposed by Sweep 1

- **L1 — lr_warmup ladder saturation.** Mild (lr=0.1) already collapses the model to the
  majority baseline; all three strengths share σ = 44.6. The operator contributes one
  effect-size point, leaving an H2 gap between σ ≈ 18 and 44. *Fix:* recalibrate mild toward
  the tolerance edge (Sweep 2).
- **L2 — Single model, single workload.** Every finding is Haiku 4.5 on Adult/MLP. S1–S6 are
  `pending replication` until a second provider and a second workload run the same cases.
- **L3 — The mean−2σ band's structural false-positive floor** (~2.3% one-sided under the fitted
  normal; normality CHECKED at n=30, §0.5) **and reference/control seed overlap** (control FPR biased
  LOW). A 3σ band is a pre-registration candidate; seed-disjointness is sequenced §5.1→§5.2.
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

## Part 1 — Non-LLM baselines (2026-09-17) — free floor contestants

### F12 — On config-knob faults, the agent's measured value is identifying faults whose knob name does not name the concept, and it is anchor-dependent

**Integrity caveat (foregrounded).** The baselines are measured on the NATIVE 50-case set
(config axes are platform-independent; per-operator verdicts deterministic, ×6 for the 30
faulty). The LLM numbers are from the FROZEN Sweep-1/Stage-2 records on the now-SUPERSEDED
case set + band. These are **per-operator DIRECTIONAL comparisons only — NOT a cross-set gap
with a case-clustered CI.** A real LLM−B2 gap CI needs the LLM re-run on the identical native
cases; the generalization is resolved by **Sweep 3** (matched set) and the **code-origin
operator**, not here.

**B2's knowledge, stated (not hidden in "trivial").** B2 diffs the run's RESOLVED config
against a committed CLEAN RESOLVED reference (`reference/config.resolved.yaml`) and knows which
keys are DERIVED (`model.input_dim` is a function of the data schema, so a leakage-added column
bumps it as a *consequence*). That is WORKLOAD-SPECIFIC knowledge a generic config-diff lacks;
it is defensible — a real remediation tool learns which keys are derived — but it is knowledge,
so every B2 number below is a "config-delta baseline WITH the clean resolved config + derived-key
set," not a naive differ. (`harness/baselines.py`; DECISIONS 2026-09-17.)

**Evidence (re-measured; native 50-case set; `harness.baselines` through `score_diagnosis` +
`verify_repair`).**

| baseline | detection (faulty) | control-FPR | identification | evidence F1 | recovery |
|---|---|---|---|---|---|
| **B0** exitcode | 6/30 (crash only) | 0/20 [0, 0.168]† | — | — | — |
| **B1** band | 24/30 = 0.80 | 1/20 = 0.05 | — | 0.43 | — |
| **B2** config-delta [^b2] | **30/30 = 1.00** | **0/20 [0, 0.168]†** | **18/30 = 0.60** ‡ | 0.63 | **30/30 = 1.00** |
| **B3** union (B1∪B2) | **30/30 = 1.00** | 1/20 = 0.05 | 18/30 = 0.60 ‡ | 0.63 | 30/30 = 1.00 |

[^b2]: B2 uses the clean RESOLVED config + the derived-key set (`model.input_dim`) — workload-specific
knowledge, disclosed above; not a naive config-diff.

† Zero-event rate: exact two-sided 95% Clopper–Pearson interval over the 20 unique control cases, not a
demonstrated zero (correction #6, 2026-09-23; previously written `0/20 = 0.00`). ‡ **Terminology, not localization** — see below: B2
localizes the injected knob on every case; its class string is that key's leaf name, so this column
scores whether the key's *name* contains the concept token.

LLM (FROZEN, prior superseded set; case-clustered CI within the frozen data):
off-anchor det 0.46 [0.31,0.61] / id 0.41 [0.26,0.57] / rec 0.37 [0.24,0.52], FPR 0/30 — 30 trials over only **3** unique control cases, so a one-sided 95% ceiling of 0.632 ·
stats (numbers) arm det 0.94 [0.90,0.99] / id 0.83 [0.74,0.92] / rec 0.85 [0.74,0.94], FPR 6/12=0.50 ·
ref-anchored det 1.00 / id 0.96 [0.92,0.99] / rec 0.94 [0.88,0.98], FPR 4/18=0.22.

Per-operator (B2): **lr, label, shape** identified AND recovered; **data_leakage,
metric_inflation** recovered but NOT identified (`aux_feature_strength` / `eval_subset_fraction`
do not contain the fault concept). LLM off-anchor per-operator: shape id 17/18, lr 18/18,
label 14/30, metric 4/12, **leakage 0/30**.

**Localization vs terminology (2026-09-23, STAGE4 4.0.3).** B2's two "NOT identified" operators are
**localized correctly** — its repair patches exactly the injected knob, which is why it recovers
them (30/30 on the native 50-case set; on the neutral-key cases its submitted repair likewise targets
the injected `opt_c` / `opt_c_level` — `scripts/baseline_report.py`). What it lacks is
**terminology**: its output convention emits the changed key's leaf name as the fault class, so it
cannot produce "leakage" for `aux_feature_strength` (or `opt_c`). Its identification miss on those
operators is therefore **partly built into the convention**, not a capability finding, and the two
must be reported apart: **localization 30/30; terminology 18/30** (0/6 on each of `data_leakage` and
`metric_inflation`).

**Interpretation (measured, not generalized).** On THIS workload's five operators, a
config-delta baseline with knowledge of the clean resolved config and of derived keys **matches
the ref-anchored LLM on detection (30/30 vs 1.00) and on recovery (30/30 vs 0.94), at an
observed-lower FPR (0/20 over 20 cases — one-sided 95% ceiling 0.139 — vs 4/18 = 0.22 over 3 cases — suggestive only: the intervals
overlap at these n; "better specificity" withdrawn 2026-09-23).** We do NOT claim "the LLM adds nothing on detection or recovery":
that generalization is what Sweep 3 and the code-origin operator would test and is not
established here — and recovery in particular is a DEGENERATE axis on these operators (L19: any
admissible repair reconstructs the clean run), so the recovery match is expected, not evidence
of cleverness. The honest headline: **on config-knob faults, the agent's measured value is
IDENTIFICATION of faults whose knob name does not name the concept** — `data_leakage` (knob
`aux_feature`, concept `leak`) and `metric_inflation` (knob `eval_subset_fraction`, concept
`bias`/`inflation`) — where B2 scores 0/6 each and the anchored LLM 0.83–0.96. That gap is a
**terminology** gap (above): B2 localizes these faults but its convention cannot name them, and the
LLM's ability to produce the word "leakage" is **not by itself evidence of understanding**. **And that
value is ANCHOR-DEPENDENT:** off-anchor the LLM's `data_leakage` identification collapses to 0/30.
Part 2's neutral-key test (H8, F13) then showed the identification does **not** depend on the two
descriptive key names — but it cannot decide fault-understanding: code-pattern recognition and
general leakage heuristics remain competing explanations *(the earlier "exactly what the neutral-key
test decides" overstated the test; corrected 2026-09-23)*.

**Correction folded in (RESEARCH_LOG 32).** An earlier correctly-run table read B2/B3 detection
as 24/30 and concluded "the LLM's detection edge is the crash tier." That was an instrument
artifact — `_IGNORE_KEYS` masking `model.input_dim` under a source-vs-resolved diff — not a
benchmark property; with resolved-vs-resolved B2/B3 detect 30/30 and the crash-edge reading is
**WITHDRAWN**. The number was real; the conclusion was the artifact.

**What would change our mind.** (a) A neutral-key operator variant on which the anchored LLM's
identification holds while B2's (config-name match) misses → identification is
fault-understanding, not legibility. (b) Sweep-3 matched-set LLM trials letting a real LLM−B2
gap CI be computed. (c) A code-origin operator (fault in code, no config knob) on which B2 is
structurally blind but the LLM is not → the agent's value extends beyond config-knob faults.

**Status:** unplanned · baselines native 50-case vs LLM frozen superseded set (per-operator
directional only, no cross-set gap CI) · generalization pending Sweep 3.

---

## Sweep 3 (2026-09-22) — neutral-key ablation, cross-provider

### F13 — Leakage identification often survives the tested key rename (H8) · equivalence unresolved in two anchored conditions; Luna's rule arm shows a measurable decrease; not a mechanism claim

The decisive test of S15/F12's surviving headline. `silent.data_leakage_neutral.v1` renames the two
config keys (`include_aux_feature`/`aux_feature_strength` → `opt_c`/`opt_c_level`) with the fault
mechanism held byte-identical (same derivation `datautil._derived_column`, identical hidden faulty
values at every strength/seed). H8 asks whether the anchored LLM's leakage identification is
fault-understanding or key-name reading. Pre-registered **two-sided equivalence** on Δ = neutral −
descriptive identification, case-clustered 95% CI: confirming iff the whole CI ⊂ ±0.15; refuting iff
Δ < −0.30 with the CI excluding 0; else inconclusive.

**Result — PRIMARY analysis is the PAIRED (strength×seed) bootstrap** (n_trials 978 deduped, both
providers, per-arm × provider — source `docs/audits/sweep_h8_xprovider_generated.md`). The neutral and
descriptive variants are the SAME fault built at matched (strength, seed), so the pre-registered design
pairs them; the primary CI resamples matched (strength, seed) PAIRS together (18 pairs/facet). The
**point estimate is identical** to the unpaired contrast — only the CI differs. *Disclosure: promoting
the paired bootstrap to primary is an analysis change made after seeing results (it moves the Haiku
numbers arm from inconclusive to confirming); it is justified by the matched-pair design, not the
outcome, and the unpaired contrast is retained alongside it in the report.* **Counting rule:** the tally
is over the **6 provider-specific cells only** (2 providers × 3 arms); the `pooled` rows reuse the same
trials, so they are a cross-provider **summary**, NOT independent confirmations, and are never added to
the count. Under the paired primary: **4 of 6 provider-specific cells confirming** (Haiku off/numbers/rule,
Luna off), **2 inconclusive** (Luna numbers, Luna rule), **0 refuting** — pooled ×3 all confirming
(summary). (Unpaired: **3 of 6** provider-specific confirming — Haiku off/rule, Luna off — and 3
inconclusive; the only difference is Haiku numbers.) **Identification often survives the tested renaming;
equivalence is unresolved in two anchored conditions (Luna numbers, Luna rule); Luna's rule arm shows a
measurable decrease.** The neutral rename does not collapse identification toward the config-name-blind
B2 floor — but see the next paragraph for what that does and does not establish.

**What this test can and cannot show (2026-09-23 framing correction — the earlier "mechanism, not
name-reading" headline overstated it).**
- **It tests dependence on THOSE TWO NAMES, not "mechanism."** Renaming `include_aux_feature` /
  `aux_feature_strength` → `opt_c` / `opt_c_level` removes one lexical cue. Surviving that removal shows
  identification does not *require those two key names*; it does not show the agent reasons about the
  fault mechanism. **Code-pattern recognition** (the derivation `datautil._derived_column` is byte-identical
  in both variants and visible in the workspace) and **general leakage heuristics** (a suspiciously
  near-perfect validation metric reads as "leakage" regardless of any name) **remain competing
  explanations** that this design does not separate.
- **One of the four "confirming" cells is equivalent FAILURE.** Haiku's off arm meets the equivalence
  criterion (Δ −0.014 [−0.083, +0.056]) because identification is **~6% in both variants** (neutral
  0.056, descriptive 0.069). Equivalence at a failing level supports **no** understanding claim — it says
  only that removing the names cannot lower a rate that is already near zero. The pre-registered verdict
  count, stated both ways: **4 of 6** provider-specific cells meet the equivalence criterion as run; by the pre-registration's own floor clause Haiku-off does not answer H8, so **3 of 5 answering cells confirm** (Haiku numbers, Haiku rule, Luna off) and **2 are inconclusive** (Luna numbers, Luna rule). (Identification in the three: Haiku numbers
  0.889/0.847, Haiku rule 0.861/0.861, Luna off 0.800/0.806.)

**Direction of the (paired) inconclusives matters (recorded, not smoothed over):**
- **Haiku numbers** Δ **+0.042** [−0.056, +0.139] (paired): now **confirming** — the paired CI no longer
  crosses +0.15; the sign is the NON-THREATENING direction (cannot rule out neutral being *better*).
  (Unpaired [−0.083, +0.167] was inconclusive on the upper side only.)
- **Luna numbers** Δ −0.072 [−0.172, +0.013] (paired): CI reaches the threatening side but includes 0.
- **Luna rule** Δ −0.115 [**−0.197, −0.032**] (paired), CI **excluding 0**: a **real but modest**
  neutral-below-descriptive gap on Luna's rule arm — statistically non-zero yet **far short of the
  −0.30 refutation bound**. Consistent with a small config-legibility contribution to Luna's
  *anchored* identification, not a collapse.

**Instrument check (pre-registered secondary):** detection + semantic recovery track closely between
variants (e.g. Luna-off detection 0.819 vs 0.814; Haiku-rule detection 0.986 vs 0.986) — no
variant-driven divergence, so the identification contrast is not an instrument artifact.

**Method note (lesson, not a retrofit):** the ±0.15 test was applied symmetrically as pre-registered.
Because only neutral ≪ descriptive threatens the mechanism claim, a **one-sided** confirming bound
(`lo > −0.15`, upper side free) is the correct pre-registration for the next sweep — it would not
flag the non-threatening Haiku-numbers excursion. We did **not** switch it post-hoc (that is the move
pre-registration exists to prevent); logged for replication.

**Status:** pre-registered (HYPOTHESES H8) · **4 of 6** provider-specific cells meet the equivalence criterion as run; by the pre-registration's own floor clause Haiku-off does not answer H8, so **3 of 5 answering cells confirm** (Haiku numbers, Haiku rule, Luna off) and **2 are inconclusive** (Luna numbers, Luna rule); 0
refuting · Luna's rule arm shows a measurable (sub-refutation) decrease · updates S15 narrowly:
identification on `data_leakage` does not depend on the two descriptive key names; it is **not** shown to
be mechanism understanding (code-pattern recognition and general leakage heuristics are not ruled out).

### F14 — Reference-context dependence is model-specific (H7 failed to replicate as a general effect) · headline

The Sweep-1 / Stage-2 headline **F10/S13 — "agents need a numeric reference baseline to detect the
silent fault"** — held for Haiku and **largely does NOT hold for the second model.** With a second
provider added (H7 measured per model), anchor-off descriptive-leakage detection is:

| model | off-anchor detection | numbers | rule | reference band adds |
|---|---|---|---|---|
| Anthropic Haiku | **0.083** | 0.972 | 0.986 | **~90 points** |
| OpenAI Luna | **0.819** | 0.986 | 0.986 | **~17 points** |

(Source `sweep_h8_xprovider_generated.md`, detection by operator × arm, `silent.data_leakage.v1`,
anthropic vs openai facets.) Luna detects the silent leakage off-anchor at **0.82** — it does not
need the reference band. The reference-context effect is real for Haiku and marginal for Luna.
Stated as **"failed to replicate,"** never "refuted" (n = 2 models, STAGE3 statistical-language
rule).

**Status:** **model dependence ESTABLISHED** (two models, one workload, one mechanism family) · **its
CAUSE is NOT** — capability, hidden reasoning tokens (Luna reasons by default; Haiku has no such
budget — L27, and a new limitation this sweep), or training differences are all uncontrolled at
n = 2 · supersedes the "strongest supported claim" framing of S13/F10.

### F15 — Luna structured-output compliance: evidence_refs omissions alongside folding (secondary) · unplanned

Two Luna transport/robustness properties, reported descriptively (not diagnosis-quality axes):
(a) the pre-registered per-provider structured-output **folding** rate; and (b) a **harness-crash**
class new to the cross-provider run — ~**6% of first-attempt Luna static trials** called `submit()`
without the required `evidence_refs` (≈31 of ~492 Luna trials; `sweeps/h8_xprovider_progress.jsonl`).
**~80% recovered on the built-in retry** (25/31 completed on the second attempt); **6 cells were
lost**, all **neutral × Luna × static** (the crash fix — `submit()` returning a tool error instead of
raising — applies only from the next sweep; DECISIONS/LIMITATIONS). A large per-provider compliance
gap is a **caveat on cross-provider score comparison**, not a finding about either model's diagnosis.

**Status:** unplanned · Luna-specific · the crash class is fixed forward-only · pending replication.

---

## How to update this document

After each sweep's diagnostics close: (1) add a **Sweep N** section in the shape above;
(2) revise the **Standing findings** table — change a status only with the evidence line that
justifies it; (3) move any answered open question into a finding; (4) add the corresponding
RESEARCH_LOG entry the same day. Never edit a prior sweep's section except to add a
"superseded by Sweep N" note.
