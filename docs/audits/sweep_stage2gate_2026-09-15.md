# Stage-2 gate — full report incl. recovery (2026-09-15)

Sweep: `stage2gate` · plan `sweeps/stage2gate_plan.yaml` (252 cells, 0 MISSING) ·
agent progress 252 · verify progress 216 (canonical re-run). Supersedes the
2026-09-14 report, whose recovery axis was VOID (verify aborted off-canonical);
recovery is now readable after the PR #6 thread-pin fix. Detection verdicts
(G1/G2/G3) are unchanged. Report generated read-only; **HYPOTHESES/FINDINGS not edited.**

## Provenance — the two phases differ (recorded in the manifest)

| phase | environment | what it is |
|---|---|---|
| **agent** | host (Darwin), `in_container: false` | Anthropic API calls — **platform-independent** |
| **verify** | **canonical container** (Linux/amd64, threads pinned), `in_container: true`, image `trainmd:canonical` `sha256:0354db57…` | real thread-pinned hidden-seed retrains |

The verify phase was re-run in-container on 2026-09-15 after PR #6. The manifest
`verify_phase` counts were corrected to the **canonical run only** (216 reruns,
1.991 core-hours, 7219.6 s wall); an earlier off-canonical attempt (every rerun  <!-- src: manifest -->
aborted exit 2 → 138 false `not_recovered`) is excluded (it had double-counted the
manifest to 432 reruns).

CIs are **case-clustered** (cluster = case_id = operator×strength×seed; cluster
bootstrap, 10 000 resamples, seed 20260914). Deviation note applies (repeats 3→2 →
wider CIs; within-cell repeat-agreement not computed at n=2). Model `claude-haiku-4-5`.

---

## 0. Recovery is now real — verify integrity check

| check | result |
|---|---|
| verdict distribution (216 faulty cells) | **recovered 138 · rejected 78 · `not_recovered` 0 · `verify_error` 0** |
| **`verify_error` count** | **0** ✓ (the PR #6 fix eliminated the thread-pin aborts) |
| trained cells (recovered) | 138 → **414/414 seed-runs exitcode 0, 414/414 non-null hidden metrics** |
| per-trained-cell compute | ~51.9 CPU-s (three real ~17 s hidden-seed retrains, in-container) |  <!-- src: manifest -->
| zero-compute cells | 78 → **all `rejected` at repair-validation, all `cpu_sec = 0`** (no rerun; correct) |
| folded repairs (`parser_fix_v1`) | **16** submissions (13 recovered, 3 rejected) → semantic channel reported |

Every trained cell that submitted a valid, admissible structured repair **recovered**
(`not_recovered` is empty): for these operators the admissible-repair space is narrow
enough that any admissible repair restores health, so the recovery question collapses
to *"did the agent submit an admissible structured repair at all."* The 78 rejections
are cells with no admissible repair submitted.

---

## 0.1 LIMITATION — the recovery axis is DEGENERATE on these three operators

**Stated plainly, not as a footnote.** `not_recovered = 0/138`: **every** admissible structured
repair recovered. On these operators the admissible-repair space is effectively a single
oracle-equivalent point (unset the leak key / reset `label_noise_fraction` / unset
`eval_subset_fraction`), so a run that applies *any* admissible repair is the clean run and
clears tolerance. **Strict recovery here therefore measures SUBMISSION-FORMAT COMPLIANCE +
admissibility, not repair correctness.**

**Concrete proof (harness probe, free, no LLM).** The trusted `DegenerateAgent` — detects the
fault, names the **WRONG** class, cites **NO** evidence, and blindly submits the admissible
(oracle) value — was run through the sanctioned `score_recovery` path over all 18 gate cases:

| operator | degenerate strict recovery |
|---|---|
| data_leakage | 6/6 = **1.000** |
| label_corruption | 6/6 = **1.000** |
| metric_inflation | 6/6 = **1.000** |
| **all** | **18/18 = 1.000** |

*(host arm64; recovery of an oracle repair is environment-robust — the probe is a binary
does-it-recover, restored to ~0.85 vs tolerance 0.8435.)*  <!-- src: reference-stats -->

An agent that does **zero diagnostic work** — wrong class, no evidence — scores **perfect**
recovery. So the recovery axis on these operators **cannot discriminate diagnosis quality**;
the strict-recovery numbers in §1 should be read as a floor set by submission mechanics, and
the real diagnostic signal lives in detection / identification / evidence. This generalizes
the 2026-09-07 DECISIONS note (recovery degeneracy shown for lr_warmup) to all three Stage-2
operators.

**Sweep-2 remedy.** Recovery becomes discriminating only with operators whose admissible-repair
space is genuinely **wide**, so that a *wrong-but-admissible* value **fails** to recover (e.g. a
continuous knob with a broad admissible band where only a sub-range restores health, or a
multi-key repair where a plausible-but-incorrect key choice leaves the fault). Until then,
recovery is reported for completeness but is **not** a discrimination axis, and this belongs in
LIMITATIONS with that remedy.

---

## 1. Recovery — strict (primary) vs semantic (secondary), case-clustered

**Strict** = structured `repair_spec` verified `recovered` (autonomous-success headline).
**Semantic** = strict + folded repairs recovered via `parser_fix_v1`. Both established.

| operator | n | cases | strict recovery | semantic recovery | identification | id − strict (95% CI) |
|---|---|---|---|---|---|---|
| data_leakage | 72 | 6 | **0.528** [0.403, 0.639] | 0.528 [0.389, 0.639] | 0.486 [0.361, 0.597] | **−0.041** [−0.069, −0.014] |  <!-- src: analysis-bootstrap -->
| label_corruption | 72 | 6 | **0.597** [0.556, 0.639] | 0.667 [0.667, 0.667] | 0.708 [0.681, 0.736] | **+0.111** [+0.056, +0.167] |  <!-- src: analysis-bootstrap -->
| metric_inflation | 72 | 6 | **0.611** [0.583, 0.667] | 0.722 [0.681, 0.778] | 0.667 [0.597, 0.750] | **+0.056** [+0.014, +0.111] |  <!-- src: analysis-bootstrap -->

- **id − strict is "naming vs correctly-formatted admissible submission," NOT "naming vs
  fixing."** Because every admissible structured repair recovers on these operators (§0, and
  the degeneracy limitation below), strict recovery here measures whether the agent emitted an
  *admissible repair in the structured `repair_spec` field* — **not whether the repair was
  correct.** So for the config-knob operators (label_corruption, metric_inflation) id > strict
  means agents name the fault more often than they submit a correctly-formatted admissible
  repair (a tool-use-compliance gap, not a diagnosis gap — folding closes most of it, so
  semantic ≈ id); for **data_leakage the sign flips** (−0.041) — agents emit an admissible  <!-- src: analysis-bootstrap -->
  repair more often than they correctly *name* the fault. Neither contrast speaks to repair
  correctness on these operators.
- **Folding matters here.** For label_corruption and metric_inflation, semantic > strict
  (+0.07–0.11), closing most of the id−strict gap — i.e. much of the "recovery shortfall"  <!-- src: analysis-bootstrap -->
  is repairs folded into a text field, a tool-use-compliance failure, not a repair failure.
  (Folded breakdown of the 16: metric_inflation 8 recovered, label_corruption 5 recovered + 2
  rejected, data_leakage 1 rejected — so data_leakage had **0 folded-*recovered*** and its
  strict = semantic.)

Strict recovery by arm (tracks detection — you cannot repair what you do not detect):

| operator | off | numbers | rule |
|---|---|---|---|
| data_leakage | 0.000 | 0.667 | 0.917 |
| label_corruption | 0.000 | 0.917 | 0.875 |
| metric_inflation | 0.208 | 0.792 | 0.833 |  <!-- src: analysis-bootstrap -->

---

## 2. Comparison to Sweep 1 — and the off-canonical caveat

Sweep 1's recovery numbers were produced **off-canonical** (macOS, `ru_maxrss_platform:
darwin`, unpinned BLAS — the `require_pinned_threads` guard did not yet exist at Sweep 1's
commit; L11 records the ~0.0037 nondeterministic spread). **Stage-2's are canonical  <!-- src: reference-stats/L11 -->
in-container.** metric_inflation is new in Stage-2 (no Sweep 1 baseline).

**Pooled per operator (strict):**

| operator | Sweep 1 (off-canonical) | Stage-2 (canonical) | Δ |
|---|---|---|---|
| data_leakage | 0.389 | 0.528 | +0.139 |  <!-- src: sweep1-generated -->
| label_corruption | 0.514 | 0.597 | +0.083 |  <!-- src: sweep1-generated -->
| metric_inflation | — | 0.611 | (new) |

**The pooled Δ is a design artifact, not an environment effect.** Sweep 1 used 2 anchor
arms (off/on, 50% off-weight); Stage-2 uses 3 (off/numbers/rule, 33% off-weight), and
off-arm recovery is ~0 — so Stage-2's lower off-weight inflates its pooled rate. Isolating
that by matching arms (**Stage-2 off+rule only vs Sweep 1 off+on**, since legacy on→rule):

| operator (strict, arm-matched) | Sweep 1 (off+on) | Stage-2 (off+rule) | Δ |
|---|---|---|---|
| data_leakage | 0.389 | 0.458 | +0.069 |  <!-- src: sweep1-generated -->
| label_corruption | 0.514 | 0.438 | −0.076 |  <!-- src: sweep1-generated -->
| metric_inflation | — | 0.521 | (new) |  <!-- src: sweep1-generated -->

Arm-matched, the differences shrink to **within sampling noise** (CI widths ~±0.15 at  <!-- src: analysis-bootstrap -->
n=48/6 cases) and flip sign between operators. **Conclusion:** moving verify from
off-canonical (unpinned macOS) to canonical (pinned container) did **not** systematically
shift recovery verdicts — as expected, since the oracle-class repairs restore accuracy to
~0.85, far above tolerance 0.8435, and the L11 off-canonical spread (~0.0037) is well  <!-- src: reference-stats/L11 -->
inside that margin. The environment fix restores *correctness of the axis* (no more false
`not_recovered` from aborts), not a change in the recovery *rate*.

---

## 3. Detection gate verdicts (unchanged — agent phase, platform-independent)

### G1 — REFUTED
Anchor-off detection: metric_inflation **0.250** [0.083, 0.417] vs label_corruption **0.250**
[0.083, 0.458] vs data_leakage **0.042** [0.000, 0.125]. Confirm rule (mi off CI-upper 0.417
< lc point 0.250) fails; the pre-reg REFUTE clause fires — the 2nd positive mechanism detects
**at** the negative reference. Contrasts (off): mi − lc **+0.001** [−0.281, +0.250]; mi − dl  <!-- src: analysis-bootstrap -->
**+0.206** [+0.007, +0.393]; lc − dl **+0.208** [+0.000, +0.458]. data_leakage is the outlier;  <!-- src: analysis-bootstrap -->
Sweep 1's under-detection is **leakage-specific, not symptom-direction**.

### G2 — baseline restoration for detection; rule = specificity (suggestive, not established)
Numbers closes **~94–95%** of the off→rule detection gap on all three operators (rule adds
~4–5 pp). Control (healthy) false-positive rate by arm, **case-clustered 95% CIs over the
3 unique control cases** (this is the whole control set — 12 trials/arm from 3 cases):

| arm | control FP | 95% CI (3 control cases) |
|---|---|---|
| off | 0/12 = 0.000 | [0.000, 0.000] |
| numbers | 6/12 = 0.500 | **[0.000, 0.750]** |
| rule | 2/12 = 0.167 | [0.000, 0.500] |

numbers − rule FP difference = **+0.333 [0.000, +0.750]** (3 shared control cases). **The
CIs are enormous** — the numbers arm's interval spans 0.00–0.75 and the numbers−rule
difference's lower bound touches 0. So *"a bare band triples over-flagging on controls, the
rule reins it in"* is **suggestive, not established** at n=3 control cases; the point
estimates hint at it but the intervals do not exclude "no effect." **This width is the
empirical argument for ≥20 unique control cases in Sweep 2** — with 3, the control FPR is not
a population rate and no control-arm contrast is decidable.

### G3 — the inconsistency is NOT used
**0/72** metric_inflation trials cite the loss/accuracy inconsistency (L16) in any arm. Every
detection reasons from the **config knob** `eval_subset_fraction`. G1 is therefore **not**
confounded by consistency-checking — but a **config-legibility** confound is present (equal
across all three operators, so it does not bias the G1 contrast; flag for Sweep 2).

### Exploratory (not pre-registered) — no magnitude boundary
metric_inflation off-arm detection *falls* with implausibility (mild 0.500 > moderate 0.125 ≈
severe 0.125) — opposite the hypothesis — but n=8/2-cases and knob-driven; not interpretable.

### Evidence v2 vs v1 — inert here
Mean F1 delta (v2 − v1) = **0.000** for all operators (data_leakage 0.477, label_corruption  <!-- src: analysis-bootstrap -->
0.555, metric_inflation 0.544). Agents cite the config key (matched identically by both scorers)  <!-- src: analysis-bootstrap -->
and rarely submit metric_window bounds where v2 diverges; v2-vs-v1 comparison deferred.

---

## 4. Summary

| axis | verdict |
|---|---|
| **Recovery** | **readable but DEGENERATE on these operators** (§0.1): `not_recovered = 0/138`, degenerate agent scores 18/18 strict recovery → the axis measures submission-format compliance + admissibility, NOT repair correctness; not a discrimination axis until Sweep-2 wide-admissible operators. Mechanics: 0 `verify_error`, real in-container retrains; strict 0.53/0.60/0.61 (dl/lc/mi). Canonical vs off-canonical does not shift the rate (arm-matched Δ within noise). |  <!-- src: analysis-bootstrap -->
| **Control FPR** | 3 unique control cases → CIs enormous (numbers 0.500 [0.000,0.750]); "numbers over-flags" is suggestive-not-established; argues for ≥20 controls in Sweep 2. |
| **G1** | **REFUTED** — 2nd positive mechanism detects = negative reference; leakage-specific. |
| **G2** | numbers restores detection (~94–95% of gap); rule adds specificity (control FP 50%→17%). |
| **G3** | inconsistency unused (0/72); detection is config-knob inspection (config-legibility confound). |
| Exploratory | no magnitude boundary readable (n=8, knob-driven). |
| Evidence v2 | inert on this gate (v2 == v1); deferred. |
