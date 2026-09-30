# Stage 4 Part 3 — pre-registration (DRAFT r2 — SUPERSEDED: approved 2026-09-29 with design C, a $120 cap, H15 pooled as H9, and H17 added; locked in `docs/HYPOTHESES.md`, "Stage 4 Part 3 — PRE-REGISTRATION")

> r2, 2026-09-29, revised with the author's inputs after the Part 2 follow-ups (ReAct controls; four conditions;
> ReAct arms off + stats; a small J-based confirmatory set; motivations cited). Nothing is locked. On approval
> it is appended to `docs/HYPOTHESES.md` and `harness/prereg_part3.py` is written and tested on SYNTHETIC data
> before any Part 3 trial. **Open decisions are marked ▶.**

## Why Part 3 looks like this

**Part 3 is the FIRST CONFIRMATORY TEST of findings that were exploratory in Part 2.** Every confirmatory test
below cites the Part 2 result that motivates it. Those results were found AFTER Part 2's verdicts, in
investigations labelled exploratory (`docs/audits/stage4_part2_control_false_alarms.md`,
`stage4_part2_react_vs_static.md`, `stage4_part2_followups.md`). They were not tested there, and Part 3 does not
re-use any Part 2 trial.

- **Primary quantity: Youden's J (LIMITATIONS L39).** A detection-only estimand rewards a flag-everything policy.
  Part 2's Luna `none` detected 0.99 of faulty cases while flagging 84/92 controls in the static off arm.
  J = detection on faulty cases − false-alarm rate on controls, per condition, agent and arm.
- **ReAct cells include controls** (healthy + benign), so J is computable under investigation. Part 2's Stage B
  had no controls, so its ReAct false alarms were never measured.
- **Workload:** the image classifier (`workloads/image_fmnist`; the 230 cases certified on AMD, CI
  `image-certify`). Its LR fault is a different mechanism from workload 1's and is compared at family level only.
- **The closed menu (L40):** the image `train.py` also carries every fault's gated code path. Results read as
  "diagnosis given a menu of gated paths".

## Carried-forward declarations

- **Protocol settings:** strict OpenAI tool schemas and streamed Anthropic requests. The pilot is never scored.
  Prompt v2 anchor arms.
- **Scorer FROZEN:** root_token_v3 / evidence v2.3, re-frozen 2026-09-29 with workload-scoped uniqueness; the image
  specs were reviewed and closed 2026-09-29. **The Part 3 post-run blind human audit is the fresh validation of the
  image identification specs.**
- **End-to-end primary:** an empty or unparseable diagnosis is a miss on a faulty case and NOT a false alarm on a
  control. Validity and compliance (no-submit, truncation) are reported per condition × agent. L35's
  strict-mode whitespace truncation is expected at ≈ 0.2%.
- **By mechanism:** faulty estimates are the unweighted mean over the 4 non-crash mechanisms:
  - leakage: pixel tag + neutral;
  - label flip;
  - decay unit;
  - metric inflation: confident subset + neutral.

  The crash is excluded from every confirmatory quantity. The **silent faults** in H14 are leakage and metric
  inflation (both variants each), the two whose ReAct detection fell in Part 2.
- **Sonnet 5 "thinking off"** is `thinking: disabled` at the model's default effort (as in Part 2; L38).

## Design (proposed)

- **Cases (230):**
  - 126 faulty: 7 operators × 3 strengths × seeds 42–47.
  - 20 healthy controls: 50–69.
  - 84 benign controls: 7 types × 12 seeds (70–93 ∪ 110–169).
- **Conditions (4), each static AND ReAct:**
  - Claude Haiku 4.5;
  - Claude Sonnet 5, thinking off;
  - GPT-5.6 Luna, reasoning `medium` (strict);
  - GPT-5.6 Luna, reasoning `none` (strict).
- **Static**, Part 1's protocol: faulty × arms off / stats / rule × 2 repeats (756), plus controls × 3 arms × 1
  repeat (312). That is 1,068 per condition.
- **ReAct** (▶ decision 1, the recommended option C): arms **off + stats**, faulty × 1 repeat (252) and controls ×
  1 repeat (208). That is 460 per condition. `rule` is dropped for ReAct to fit the budget, since no ReAct
  confirmatory test uses it.
- **Total: 6,112 trials.**
- **Cost** (measured $/trial: Haiku from Part 1; Sonnet off and both Luna conditions from Part 2's full run):

  | option (ReAct design) | ReAct / condition | total trials | projected | × 1.2 |
  |---|---|---|---|---|
  | **C — off + stats, faulty ×1, controls ×1 (recommended)** | 460 | 6,112 | **$90.87** | **$109.04** |
  | B — off + stats, faulty ×2, controls ×1 | 712 | 7,120 | $114.20 | $137.05 |
  | A — off + stats + rule, faulty ×2, controls ×1 | 1,068 | 8,544 | $147.17 | $176.60 |

  Option C by condition (static + ReAct): Haiku $32.39, Sonnet off $50.99, Luna medium $4.26, Luna none $3.23.
  **Only C fits under ≈ $120 with contingency** (B fits only without it). The confirmatory tests are clustered by
  case, so a second ReAct repeat adds little power.
- **Cap ▶ decision 2:** $120. A slice runs first. The rest runs only if the slice's projection fits; otherwise the
  author decides before further spend. Image prompts may cost differently from the tabular ones that the costs
  were measured on, and the slice measures this.
- **Pre-run gates:**
  - `validate-all` green on the 230 image cases;
  - the scorer freeze unchanged;
  - a never-scored pilot on each condition × agent;
  - `check-cache` / `check-reasoning` on ReAct cells.

## Quantities and shared rules

- **DET(c, a, r)** = the unweighted mean over mechanisms of the detection rate.
- **FA(c, a, r)** = the share of control trials with `detected: true`, over all 104 controls (healthy and benign
  pooled; each also reported alone).
- **J = DET − FA**; per mechanism, J_m = det_m − FA. For H14, **J_silent** uses the silent mechanisms only.
- **Bootstrap:**
  - 10,000 paired, case-level resamples, stratified by mechanism (faulty cases) and control type (controls), with
    one seeded generator per test;
  - two-sided p with ties counted half: p = min(1, 2·min(L + T/2, U + T/2)/B);
  - 95% percentile intervals.
- **Headroom rules** read only the data of the condition or arm the test expects to be LOWER, so they cannot
  select on the effect. A test without enough eligible units is UNTESTABLE and leaves the family.
- **ONE Holm family** over every testable confirmatory test below (family-wise α = 0.05). H15's
  intersection–union test enters Holm with its IU p-value, the largest of its per-mechanism p. Each test's
  verdict:
  - **CONFIRMING:** Holm-rejected in the declared direction, with its clause (if any) met;
  - **REFUTING:** rejected opposite to it, or not rejected with the interval inside ±0.15 ("shown small");
  - **INCONCLUSIVE:** otherwise.

## Confirmatory set (5 tests; J-based)

### H13a — Without reasoning, Luna's J is lower in the STATIC protocol, via false alarms

- *Motivation (Part 2 exploratory):* static off arm, J = +0.08 for Luna `none` vs +0.90 for Luna `medium`. `none`
  flagged 18/20 healthy and 66/72 benign controls, naming dormant gated code paths.
  - `medium` flagged 0/92.
  - The strict adapter was shown not to introduce it.
  - Part 1's non-strict Luna flagged 0/92.
- *Estimand:* ΔJ = J(Luna medium) − J(Luna none), static, off arm. ΔJ = ΔDET + ΔFA, with ΔFA = FA(none) −
  FA(medium).
- *Declared direction:* ΔJ > 0.
- *Clause "via false alarms":* ΔFA's 95% interval lies above 0 and ΔFÂ ≥ ½·ΔĴ. If rejected with ΔĴ > 0 but the
  clause fails, the verdict is reported as **CONFIRMING (J only)**.
- *Headroom:* a mechanism is eligible if J_m(Luna none)'s upper bound is < 0.85; ≥ 2 eligible mechanisms are
  required.

### H13b — Without reasoning, Luna's J is lower in the ReAct protocol, via misses

- *Motivation (Part 2 exploratory):* ReAct off arm, silent-fault detection 0.19 for Luna `none` vs 0.85 for
  `medium`, though `none` opened `train.py` in 89/90 trials. `none` answered "none" on 32/36 leakage and 12/18
  metric-inflation cases, the opposite of its static behaviour. Part 2 ReAct had no controls, so FA was unmeasured.
- *Estimand:* ΔJ as in H13a, ReAct, off arm, all 4 mechanisms.
- *Declared direction:* ΔJ > 0.
- *Clause "via misses":* ΔDET = DET(medium) − DET(none) has its 95% interval above 0 and ΔDET̂ ≥ ½·ΔĴ. If rejected
  with ΔĴ > 0 but the clause fails, the verdict is **CONFIRMING (J only)**.
- *Headroom:* as in H13a, on ReAct data.

### H14 — Under investigation, bare statistics raise J on the silent faults (ReAct `stats` vs `off`), per condition with headroom

- *Motivation (Part 2 exploratory):*
  - ReAct off-arm silent detection fell well below static: Sonnet off leakage 0.61 and metric inflation 0.39,
    against static ≥ 0.95.
  - **Every** ReAct "none" answer had read the config with the planted key in it: Sonnet off 25/25, xhigh 18/18.
  - 11/25 Sonnet-off misses justified the inflated accuracy as typical for the dataset, a judgement the
    reference statistics could correct. (No stats arm existed for ReAct in Part 2.)
- *Estimand:* per condition, ΔJ_silent = J_silent(ReAct, `stats`) − J_silent(ReAct, `off`).
- *Declared direction:* ΔJ_silent > 0.
- *Headroom:* a condition is tested only if its ReAct off-arm J_silent has a 95% upper bound < 0.85, read from the
  off arm only.
  - Expected to be tested: **Sonnet off and Haiku**.
  - Luna medium (0.85 detection in Part 2) is expected not to be.
  - Luna none is excluded by design: its ReAct misses are the reasoning effect that H13b tests, not a missing
    reference.
- Each tested condition is one test in the Holm family.

### H15 — Model dependence replicates on J (H9 on the image workload): Luna medium > Haiku, off arm

- *Motivation:* Part 1's H9 was CONFIRMING on detection. Label corruption Luna − Haiku was +0.569 and metric
  inflation +0.500 (FINDINGS F17). Part 2 showed detection alone can be inflated, so the replication is on J.
- *Estimand:* per eligible mechanism m, Δ_m = J_m(Luna medium, off) − J_m(Haiku, off), pooled over static and ReAct
  (▶ decision 3: pool, or static only as in Part 1's protocol), strengths and repeats.
- *Rule:* H9's intersection–union.
  - **CONFIRMING** iff every eligible Δ_m has its lower bound > 0.
  - **REFUTING** iff every Δ_m has its upper bound < 0.20.
  - **INCONCLUSIVE** otherwise.
- *Headroom:* J_m(Haiku)'s upper bound < 0.85; ≥ 2 mechanisms.

### H16 — Bare statistics close most of the off→rule gap, on J (H10 replication), per model, static

- *Motivation:* Part 1's H10 was CONFIRMING for Haiku (f = 0.909 [0.869, 0.947], detection) and UNTESTABLE for Luna
  (no gap). On J, false alarms under `rule` can shrink the gap and change f.
- *Estimand:* per model (Haiku; Luna medium), f_J = (J(stats) − J(off)) / (J(rule) − J(off)), static only (ReAct has
  no `rule` arm). It is computed over the model's mechanisms with a J rule − off gap ≥ 0.30.
- *Decision:* H10's rule, with bootstrap p for f = 0.5.
  - **CONFIRMING:** f̂ > 0.5.
  - **REFUTING:** f̂ < 0.5.
- A model with no eligible mechanism is UNTESTABLE.

## Descriptive only — no verdicts

- **Code opening (L40):** ReAct rates of opening `train.py` / the config, detection conditional on opening the
  training script, and whether the planted key was visible via `read_config` in "none" answers.
- **Compliance:** ended without submit (Part 2: Luna medium ReAct 5/108); strict-mode whitespace truncation (L35);
  Sonnet repair omission (Part 2: static thinking-off 40/639 correct diagnoses without a repair).
- **Detection-only versions** of H13–H16, beside the J verdicts.
- **Per condition × agent × arm:** identification (the new image specs), evidence F1, and recovery (strict and
  semantic).
- **Benign false alarms by form** (changed vs added), and the schedule no-op.
- **Controls under ReAct vs static.**
- **Cross-workload, family-level** comparison with Parts 1–2.
- **Baselines B0–B3 / BF** on the image cases, where they apply.

## Before lock (remaining)

1. ▶ Decisions 1–3.
2. `harness/prereg_part3.py` plus synthetic tests covering:
   - confirm, refute (both kinds), inconclusive, untestable;
   - the two clauses;
   - Holm with an IU p-value;
   - document ↔ code agreement.
3. Plans (static; ReAct with controls), a slice, and a projection against the cap.
4. A restore path for the image bundle, beside workload 1's.
