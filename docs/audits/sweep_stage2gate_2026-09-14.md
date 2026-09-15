# Stage-2 gate — analysis report (2026-09-14)

> **SUPERSEDED by `sweep_stage2gate_2026-09-15.md`.** This report's recovery axis was VOID (the
> verify phase aborted off-canonical before the PR #6 thread-pin fix — every rerun exited 2). Kept
> as the record of what was reported before the fix; the 09-15 analysis is the live one. The
> numbers-provenance guard treats only the 09-15 analysis as current.

Sweep: `stage2gate` · plan `sweeps/stage2gate_plan.yaml` (252 cells, 0 MISSING) ·
agent progress 252 · verify progress 216 · manifest git_commit `4b4af43`.
Report generated read-only; **HYPOTHESES/FINDINGS/LIMITATIONS not edited** (pending review).

---

## 0. BLOCKER — the recovery axis of this gate is UNREADABLE (harness issue)

**First finding, before any analysis.** The verify phase took 1155 CPU-s over 216 reruns
(~5.3s each) versus Sweep 1's ~164s/rerun. That gap is not a speedup — **nothing retrained.**

Per-verify-cell breakdown (traced through `verify_repair.py`):

| what happened | cells | evidence |
|---|---|---|
| repair-validation **rejection**, no rerun (correct, 0 compute) | **78** | verdict `rejected`, `per_seed_hidden_metrics: []` |
| valid repair → **3 hidden-seed retrains attempted → all exited 2** | **138** | 138×3 = **414 subprocesses, every one exitcode 2**, both metrics `null` |
| tier-aware metric-tier shortcut (reported-metric, no retrain) | **0** | metric tier does **not** shortcut — it retrains too; its 156 subprocs also exited 2 |
| skipped as already-verified / cached | **0** | `verify_progress` empty at start |
| skipped as control (scored inline) | **36** | 252 agent − 36 control = 216 verify, matches exactly |

**Root cause.** The gate ran **outside the canonical container** (manifest: `in_container:
false`, `os: macOS-10.16`, `python: 3.9.12`, `cpu_model: i386`). `verify_repair.py` launches
`train.py` as a subprocess **without setting the thread-pinning env vars**, and `train.py`
calls `require_pinned_threads()` (train.py:390), which `sys.exit(2)`s when
`OMP/MKL/OPENBLAS/NUMEXPR/VECLIB_NUM_THREADS` are not all pinned to 1. On the unpinned macOS
shell every training subprocess aborted **before training**. The ~8.5 CPU-s per valid cell is
3× (Python + torch import → immediate exit 2), not three 15s training runs.

**Consequence — stated plainly:** **138 of 216 verify cells (64%) produced a substantive
recovery verdict (`not_recovered`) without the work that verdict implies.** Zero cells trained;
`recovered` was **unreachable** — a run that never trains has `metric_hidden_test_acc = null`,
which fails the tolerance check by construction. Verdict distribution: `not_recovered` 138,
`rejected` 78, **`recovered` 0**. The `rejected` verdicts are sound (decided at repair-spec
validation, pre-compute, platform-independent); the `not_recovered` verdicts are **artifacts of
the thread guard, not of repair quality** — e.g. `case_0022` was handed the *correct oracle
repair* `data.label_noise_fraction: 0.0` and scored `not_recovered`.

**The recovery / H3 axis of this gate cannot be read until this is resolved** (re-run verify
in-container, or set thread pins in the verify subprocess env). It is a harness defect, not a
result. **The detection / identification / evidence axes are unaffected** — see §1 (why).

---

## 1. What IS readable — and why the off-canonical run does not threaten it

The **agent phase is platform-independent**: it is Anthropic API calls scored by pure
comparison against hidden ground truth (detection/identification/evidence). No local training,
no float reductions — the macOS/py3.9 environment cannot perturb these axes. So G1/G2/G3
(all detection- or transcript-based; none use recovery) stand.

The off-canonical concern that applied to Sweep 1's L11 (retrained numbers drifting ~1e-3
across platforms vs each case's guard margin) **does not apply here in the same form**: the
verify phase did not produce off-canonical numbers — it produced **no numbers at all** (exit 2).
There is nothing to bound against a guard margin. The LIMITATIONS entry for this gate should
record *that* (verify produced zero training output off-canonical; recovery axis void), not an
L11-style perturbation bound. **Held for review rather than written**, because the harness fix
(re-run in-container) may moot it entirely.

**Coverage.** 252/252 agent trials loaded, **0 exclusions** (0 `trusted`, 0 `card_superseded`,
0 failed). Faulty 216 (72 each × data_leakage / label_corruption / metric_inflation), control 36.
Model: `claude-haiku-4-5`. Evidence scored v2 (primary) with v1 alongside. Deviation note
(repeats 3→2, n=2 so repeat-agreement dropped) applies — CIs are wide by design.

CIs are **case-clustered** (cluster = case_id = operator×strength×seed; cluster bootstrap,
10 000 resamples, seed 20260914). Each (operator, arm) cell = 24 trials in 6 cases.

---

## 2. G1 — Does positive-symptom under-detection REPLICATE on a second mechanism?

**Verdict: REFUTED.**

Anchor-**off** detection (the intrinsic-blindness condition), point [95% cluster CI]:

| operator (off arm) | detection | 95% CI |
|---|---|---|
| data_leakage | **0.042** | [0.000, 0.125] |
| label_corruption (negative reference) | **0.250** | [0.083, 0.458] |
| metric_inflation (2nd positive mechanism) | **0.250** | [0.083, 0.417] |

Pre-registered confirm rule: CONFIRMED iff `metric_inflation` off CI-**upper** < `label_corruption`
off **point**. Here 0.417 **≮** 0.250 → **not confirmed**. The pre-reg's REFUTE clause fires
directly: `metric_inflation` detects **at** the negative-symptom operator.

Direct cluster-bootstrap contrasts (off arm):
- `metric_inflation − label_corruption` = **+0.001 [−0.281, +0.250]** — indistinguishable.
- `metric_inflation − data_leakage` = **+0.206 [+0.007, +0.393]** — metric_inflation detected **more**.
- `label_corruption − data_leakage` = **+0.208 [+0.000, +0.458]**.

**Interpretation.** The second positive-symptom mechanism carries **no detection penalty**
relative to the negative-symptom reference. `data_leakage` is the outlier — harder than *both*
other operators. So Sweep 1's positive-symptom under-detection appears **specific to the
data_leakage mechanism, not to symptom direction**. The "symptom-direction ≡ blindness"
reading that operator #6 was built to test is **not supported**.

---

## 3. G2 — Is a bare NORM sufficient, or is the RULE doing the work?

**Answer the data supports: baseline restoration — a bare norm suffices for *detection*; the
RULE's distinct contribution is *specificity* (fewer false alarms), not more detection.**

Detection by arm, and fraction of the off→rule gap closed by **numbers** alone:

| operator | off | numbers | rule | off→rule gap | closed by *numbers* |
|---|---|---|---|---|---|
| data_leakage | 0.042 | 0.917 | 0.958 | +0.917 | **95.5%** |
| label_corruption | 0.250 | 0.958 | 1.000 | +0.750 | **94.4%** |
| metric_inflation | 0.250 | 0.958 | 1.000 | +0.750 | **94.4%** |

The bare band (numbers) closes ~94–95% of the gap on every operator; the rule sentence adds
only ~4–5 pp of detection. The reference band is doing essentially all the detection work.

**But the RULE is not inert — it is a false-alarm regulator.** Control (healthy) false-positive
rate by arm:

| arm | control FP (predicted faulty on a healthy run) |
|---|---|
| off | **0/12 = 0.00** (agents default to "healthy" without a band) |
| numbers | **6/12 = 0.50** (a bare band makes agents over-flag healthy runs) |
| rule | **2/12 = 0.17** (the rule sentence tempers over-calling) |

So: **numbers restores detection but triples the healthy false-positive rate; the rule keeps most
of the detection gain while cutting FPs from 50% → 17%.** The mechanism is baseline restoration
for sensitivity, with the rule contributing calibrated specificity. (Agent effect, all arms:
ReAct > static by +0.06 to +0.14 per operator — consistent with detection being config-inspection-gated.)

---

## 4. G3 — Is metric_inflation detection explained by the within-case loss/accuracy inconsistency (L16)?

**Answer: NO. 0/72 metric_inflation trials cite the loss/accuracy inconsistency (strict
rationale scan, every arm). Detection is explained by direct CONFIG-KNOB inspection.**

| metric_inflation, by arm | cites loss/acc inconsistency | cites config knob `eval_subset_fraction` |
|---|---|---|
| off | **0/24** | 6/24 (= exactly the 6 detected; the 18 misses submitted "healthy", empty rationale) |
| numbers | **0/24** | 20/24 |
| rule | **0/24** | 20/24 |

Every detected metric_inflation trial reasons from the config knob (e.g. *"eval_subset_fraction
0.92 causes reported accuracy on the top-92% most-confident predictions, inflating the metric
without changing the model"*). The within-case loss/accuracy mismatch (L16) plays **no** role.

**Implication for G1:** G1's replication is **not** confounded by consistency-checking (the
pre-reg's stated worry) — that worry is empirically absent. **However, a different confound is
present:** the operator's knob is **legible in `config.yaml`**, so metric_inflation "detection"
is substantially a *config-reading* task, not symptom-direction reasoning. This applies **equally
to all three operators** (all inject a config knob), so it does not differentially bias the G1
cross-operator contrast — but it means the whole gate measures "spot the config anomaly given a
band" more than "symptom-direction blindness." Worth pre-registering as a first-class factor for
Sweep 2 (e.g. an operator whose fault is *not* a single legible config key).

---

## 5. Exploratory (not a pre-registered claim) — magnitude boundary

metric_inflation ladder: mild q=0.92 (~0.88 visible) → severe q=0.50 (~0.98 visible).

| strength | off-arm detection | all-arms detection |
|---|---|---|
| mild (~0.88) | 0.500 (4/8) | 0.792 |
| moderate (~0.94) | 0.125 (1/8) | 0.708 |
| severe (~0.98) | 0.125 (1/8) | 0.708 |

Detection **falls** with implausibility (mild > moderate ≈ severe) — the **opposite** of the
exploratory "detection rises with implausibility" hypothesis. **Not interpretable:** n = 8
trials / 2 cases per strength (off arm), and per §4 detection here is config-knob-inspection
incidence, not perception of the inflated *magnitude* (agents flag the knob 0.92 vs 0.50, not
the visible 0.88 vs 0.98). No magnitude boundary can be read from this gate.

---

## 6. Evidence scorer v1 vs v2

**Identical on every trial: mean F1 delta (v2 − v1) = 0.000 for all three operators.**

| operator | evidence F1 v2 | evidence F1 v1 | Δ |
|---|---|---|---|
| data_leakage | 0.477 | 0.477 | 0.000 |
| label_corruption | 0.555 | 0.555 | 0.000 |
| metric_inflation | 0.544 | 0.544 | 0.000 |
| all faulty (n=216) | 0.525 | 0.525 | 0.000 |

The v2 machinery (IoU + width penalty + required bounds + alternative sufficient sets) is
**inert on this gate's submissions** — agents cite the config key (matched identically by both
scorers) and rarely submit the metric_window ranges where v2 diverges from v1. This is disclosure,
not a defect; it means v2-vs-v1 cannot be compared on Stage-2 data and the comparison must wait
for submissions that exercise metric_window bounds.

Identification (context), point estimates: data_leakage 0.486, label_corruption 0.708,
metric_inflation 0.667 (off-arm identification 0.00 / 0.17 / 0.21 respectively — tracks detection).

---

## 7. Summary of verdicts

| gate | verdict | one line |
|---|---|---|
| **G1** | **REFUTED** | 2nd positive mechanism detects = negative reference (off: 0.250 vs 0.250; diff +0.001 [−0.281,+0.250]); leakage-specific, not symptom-direction. |
| **G2** | baseline restoration (+ rule = specificity) | numbers closes ~94–95% of the detection gap; rule adds little detection but cuts control FP 50%→17%. |
| **G3** | inconsistency NOT used | 0/72 cite loss/acc mismatch; detection is config-knob inspection → a config-legibility confound (equal across operators). |
| Exploratory | no magnitude boundary readable | detection falls with implausibility, but n=8/2-cases and knob-driven. |
| Evidence v2 | inert here | v2 == v1 on every trial; comparison deferred. |
| **Recovery / H3** | **VOID (harness bug)** | verify ran off-canonical; all 414 retrains exited 2; 0 recovered; re-run in-container before reading. |
