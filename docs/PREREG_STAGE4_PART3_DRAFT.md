# Stage 4 Part 3 — pre-registration (DRAFT for one-pass review — NOT LOCKED)

> Drafted 2026-09-29 at the author's request, after Part 2 was scored and recorded (H11 and H12 UNTESTABLE by the
> headroom rule, FINDINGS F24; LIMITATIONS L39, L40). Nothing here is locked. On approval it is appended to
> `docs/HYPOTHESES.md` and its verdict code (`harness/prereg_part3.py`) is written and tested on SYNTHETIC data
> before any Part 3 trial. **Open decisions for the review are marked ▶.**

## What changes from Parts 1–2, and why

- **Primary estimands pair detection with the SAME condition's false alarms (LIMITATIONS L39).** A detection-only
  estimand rewards a flag-everything policy: in Part 2, GPT-5.6 Luna at reasoning `none` detected 0.99 of faulty
  cases while flagging 84 of 92 controls in the off arm (J = +0.08). Every Part 3 confirmatory quantity is
  **Youden's J = detection rate on faulty cases − false-alarm rate on control cases**, per condition, per agent,
  per arm. Detection alone is reported beside J and gets its own replication verdicts.
- **Controls are run for BOTH agents** (▶ decision 1). Parts 1–2 ran controls with the static agent only, so ReAct
  has no false-alarm rate and no J. Part 3 runs the 104 controls under ReAct as well.
- **Workload: the image classifier** (`workloads/image_fmnist`, the certified 230 cases, CI `image-certify`).
  The two workloads share mechanisms at the family level. The LR faults are different mechanisms (design decision 1)
  and are compared at family level only.
- **The closed menu (LIMITATIONS L40) holds here too:** the image `train.py` carries every fault's gated code path.
  Results read as "diagnosis given a menu of gated paths". The exploratory Part 2 finding that ReAct detection
  depends on opening the code for some mechanisms (`docs/audits/stage4_part2_react_vs_static.md`) is re-examined
  descriptively.

## Carried-forward declarations

- **OpenAI tool schemas are strict in every cell**; Anthropic requests are streamed (DECISIONS 2026-09-27/28).
- **Scorer FROZEN**: identification root_token_v3, evidence v2.3, re-frozen 2026-09-29 for the image operators.
  Uniqueness is scoped per workload group, and the image identification specs were reviewed and closed
  2026-09-29. **Part 3's post-run blind human audit is the fresh validation of the image specs** (Part 1's
  protocol and sheet; items sampled across conditions, agents and operators).
- **End-to-end primary**: every trial counts; an empty or unparseable diagnosis is a miss on a faulty case and
  NOT a false alarm on a control. Validity is reported separately.
- **By mechanism**: pooled faulty estimates are the unweighted mean over mechanisms, so the two-variant
  mechanisms (leakage, metric inflation) are not counted twice. Mechanisms: leakage (pixel tag + neutral),
  label flip, decay unit, metric inflation (confident subset + neutral); the crash (channel mismatch) is
  excluded from every confirmatory quantity (detected from the exit code).
- **The pilot is excluded** from every analysis and never scored.
- **Anchor arms**: prompt v2 `off` / `stats` / `rule` (bare statistics / statistics + one decision sentence).

## Design (proposed)

- **Cases (230, certified on AMD EPYC):**
  - 126 faulty: 7 operators × 3 strengths × seeds 42–47.
  - 20 healthy controls: seeds 50–69.
  - 84 benign controls: 7 types × 12 seeds (70–93 ∪ 110–169).
- **Conditions (3):**
  - **Claude Haiku 4.5**: default settings, streamed.
  - **GPT-5.6 Luna, reasoning `medium`**: strict tools.
  - **GPT-5.6 Luna, reasoning `none`**: strict tools. Added by the author, 2026-09-29; cheap.
  - Sonnet stays deferred (design decision 3).
- **Agents: static and ReAct**, both on every case.
- **Per condition and agent** (Part 1's protocol, plus the controls for ReAct):
  - faulty × 3 arms × 2 repeats = 756 trials;
  - controls × 3 arms × 1 repeat = 312 trials.
  - That is 1,068 per condition × agent, 2,136 per condition, **6,408 trials** in total.
- **Projected cost** (measured $/trial: Haiku from Part 1, static 0.0135 and ReAct 0.0390; Luna from Part 2
  strict, static 0.00215 and ReAct 0.00316, used for both Luna conditions):

  | condition | static (1,068) | ReAct (1,068) | total |
  |---|---|---|---|
  | Haiku 4.5 | $14.44 | $41.68 | $56.12 |
  | Luna medium | $2.30 | $3.37 | $5.67 |
  | Luna none | $2.30 | $3.37 | $5.67 |
  | **all** | | | **$67.46 → × 1.2 contingency ≈ $81** |

  Without ReAct controls (▶ decision 1): ≈ $53 → × 1.2 ≈ $64. The image prompt is expected to be no longer than the
  tabular one (8 epochs of metrics, a shorter `train.py`).
- **Cost cap ▶ decision 2:** proposed $90 for the run, projected from a slice as in Part 2. The rest runs only if
  the slice projection fits; otherwise the author decides before further spend.
- **Pre-run gates:**
  - `validate-all` green on the 230 image cases;
  - the scorer freeze unchanged;
  - a pilot (never scored) on each condition × agent;
  - `check-cache` / `check-reasoning` on ReAct cells.

## Primary quantity

For a condition c, agent a and arm r:

- DET(c, a, r) = the unweighted mean over the 4 non-crash mechanisms of the detection rate on that mechanism's
  faulty trials.
- FA(c, a, r) = the false-alarm rate over the 104 control cases (a trial with `detected: true`). Healthy and
  benign are pooled for J, and each is also reported separately.
- **J(c, a, r) = DET − FA.**

Per-mechanism J_m = detection on mechanism m − FA (the same FA for every mechanism).

**Headroom (Part 1/2 rule, applied to J):**
- A mechanism carries a decision only if the reference condition's J_m has a 95% upper bound below 0.85, read
  from the reference condition's data only.
- The reference condition is the one a hypothesis expects to be LOWER: Luna `none` for H13, Haiku for H14.
- At least 2 eligible mechanisms are required; otherwise the hypothesis is UNTESTABLE.
- Because J subtracts false alarms, it has more room below its ceiling than detection alone (▶ decision 3: keep
  the 0.85 threshold on J, or tie it to detection as before).

**Bootstrap (all confirmatory tests):**
- 10,000 paired case-level resamples, stratified by mechanism for faulty cases and by control type for controls,
  with one seeded generator per hypothesis.
- Two-sided p with ties counted half: p = min(1, 2·min(L + T/2, U + T/2)/B), as in Part 2.
- 95% percentile interval.
- **Holm across the confirmatory family** below (the J-based tests; α = 0.05). The detection-based replications
  form their own Holm family (▶ decision 4).

## Confirmatory

### H13 — Without reasoning, GPT-5.6 Luna's J is LOWER, driven by false alarms on controls (replication of Part 2's exploratory finding)

- **Estimand:** ΔJ = J(Luna medium) − J(Luna none), **static agent, `off` arm**, over the eligible mechanisms.
- **Decomposition:** ΔJ = ΔDET + ΔFA, with ΔDET = DET(medium) − DET(none) and ΔFA = FA(none) − FA(medium).
- **Declared direction:** ΔJ > 0.
- **"Driven by false alarms"** holds iff ΔFA's 95% interval lies above 0 AND ΔFÂ ≥ ½·ΔĴ.
- **CONFIRMING:** Holm-rejected, ΔĴ > 0, and "driven by false alarms" holds.
- **CONFIRMING (J only, not FA-driven):** rejected with ΔĴ > 0, but the false-alarm clause fails. Reported as
  such: the J gap replicates and its source does not.
- **REFUTING:** rejected with ΔĴ < 0, or not rejected with the ΔJ interval inside ±0.15 ("shown small").
- **INCONCLUSIVE:** everything else.
- The ReAct `off` contrast and the `stats` / `rule` contrasts are reported descriptively beside it (▶ decision 5:
  make the ReAct `off` contrast a second confirmatory test in the family instead).

### H14 — Model dependence (H9-style replication on the image workload): Luna medium's J exceeds Haiku's

- **Estimand:** per eligible mechanism m, Δ_m = J_m(Luna medium, `off`) − J_m(Haiku, `off`), pooled over the two
  agents (possible now that ReAct has controls) and over strengths and repeats.
- **Decision rule:** H9's intersection–union.
  - **CONFIRMING** iff Δ_m's 95% lower bound > 0 on every decision-carrying mechanism.
  - **REFUTING** iff every Δ_m upper bound < 0.20.
  - **INCONCLUSIVE** otherwise.
- **Also reported as a verdict:** H14-DET, the same rule on detection (H9's original estimand), in the detection
  family.
- **Descriptive:** Luna none vs Haiku.

### H15 — Bare statistics close most of the off→rule gap, per model (H10-style replication)

- **Estimand:** per condition, f_J = (J(`stats`) − J(`off`)) / (J(`rule`) − J(`off`)) over the eligible
  mechanisms, pooled over agents. A mechanism is eligible if the condition's own J rule − off gap is ≥ 0.30.
  A condition with no eligible mechanism is UNTESTABLE.
- **Decision:** H10's rule. Bootstrap p for f = 0.5; Holm over the tested conditions.
  - **CONFIRMING:** rejected and f̂ > 0.5.
  - **REFUTING:** rejected and f̂ < 0.5.
  - **INCONCLUSIVE:** otherwise.
- **Also reported as a verdict:** H15-DET, the same rule on detection, in the detection family.
- **Stated in advance:** Luna medium may be UNTESTABLE on detection (as in Part 1), but less likely on J.

## Descriptive only — no verdicts

- **Per condition × agent × arm table:** DET, FA (healthy and benign separately), J, identification (the new image
  specs), evidence F1, recovery (strict and semantic), and validity.
- **Benign false alarms by FORM** ("changed" vs "added"), and on the schedule no-op specifically: does flagging the
  schedule keys differ from finding the unit bug?
- **The closed menu:** ReAct detection conditional on opening `train.py` / the config (as in the Part 2
  exploratory audit), and dormant-path flagging on controls.
- **Cross-workload, family-level comparison** with Parts 1–2: same mechanism family, same condition, and
  explicitly not the same fault.
- **Baselines B0–B3 / BF** on the image cases, where they apply.

## Before lock (remaining)

1. ▶ Decisions 1–5 above.
2. `harness/prereg_part3.py` plus synthetic tests: confirm, refute (both kinds), inconclusive, untestable, the
   FA-driven clause, Holm edges, and document ↔ code agreement.
3. Generate and commit the plans (static + ReAct; the ReAct controls if decision 1 is yes); a slice; a projection.
4. Restore path for the image bundle (`restore-cases` for the 230 image cases alongside workload 1's 200).
