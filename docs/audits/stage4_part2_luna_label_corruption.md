# GPT-5.6 Luna on label corruption, Part 1 vs Part 2 — and a cross-run H9 re-measurement · EXPLORATORY

> Read-only (author's request, 2026-09-30). Descriptive only; no verdict, estimand or rule changes. Stored trial
> records under the frozen scorer. Part 1 = GPT-5.6 Luna with NON-strict tools at the API's default effort (no
> effort sent). Part 2 = GPT-5.6 Luna `medium`, STRICT tools. Both are off arm, on the same 18 label-corruption
> cases (case_0055–0072).

## 1. Which figures are comparable

The quoted 0.833 (Part 1) is H9's rate **pooled over static + ReAct**. Part 2's 0.556 is **static only**
(Stage A). On the same protocol, static off arm:

| run | trials | detected | answered "none" | empty / unparseable | detection |
|---|---|---|---|---|---|
| Part 1 (non-strict, default effort) | 36 | 25 | 7 | 4 (L35 format failures) | **0.694** (valid only: 25/32 = 0.781) |
| Part 2 (strict, medium) | 36 | 20 | 16 | 0 | **0.556** |

Paired by case, Part 1 − Part 2 = **+0.139, 95% CI [−0.056, +0.333]** (18 cases; case bootstrap, 10,000
resamples, seed 20260930). This cannot be distinguished from 0.

## 2. The Part 2 misses — "noticed but dismissed"

All 16 Part 2 misses are parsed submissions answering "none" (class `none`). None is a format failure.

- **6 of 16 rationales name the label noise and explain it away as an intended setting**, e.g.:
  - "the configured label noise is consistently applied as part of th[e workload]";
  - "stable expected metrics under the explicitly configured 38% training-label noise";
  - "the configured label noise is an explicit workload setting rather than an u[nintended] …";
  - "plausible metrics for the explicitly configured 42% label-noise setting".
- **The other 10 reason through the MENU of other gated paths** (subset reporting, the auxiliary feature, input
  dimension) and never mention the noise key, e.g. "no configured subset reporting or auxiliary feature
  behavior". This is the closed-menu pattern of LIMITATIONS L40.
- **Part 1's misses:** 7 answered "none" (1 of the 11 misses names the noise key) and 4 had an empty diagnosis.
- **Detections:** all 20 of Part 2's cite the noise key, against 17 of Part 1's 25. Identification was correct in
  every detection in both runs.
- **Reasoning volume is similar:** median reasoning tokens per trial were 354 (Part 1) vs 326 (Part 2). Misses
  reason less than detections in both runs (medians 233 vs 398 in Part 1; 145 vs 444 in Part 2).

## 3. Do strict schemas change diagnostic behaviour, not just format?

**No evidence that they do.**
- Strict schemas remove the format failures (Part 1: 4/36 empty diagnoses here; L35).
- The only diagnostic difference on label corruption is a +0.139 gap whose interval includes 0.
- On every other mechanism, Part 2 Luna detected MORE than Part 1 Luna (table below): leakage 0.944 → 0.986,
  lr_warmup 0.861 → 0.972, metric inflation 0.778 → 1.000, crash 0.833 → 1.000.

The two runs also differ in more than the schema: Part 1 sent no effort (API default) while Part 2 sent `medium`,
and they ran on different dates. So no difference could be attributed to strict mode alone.

## 4. Cross-run H9 re-measurement — Haiku (Part 1) vs Luna medium (Part 2), off arm, same cases

Pooled over static + ReAct (H9's estimand; Part 2's ReAct = Stage B, 1 repeat):

| mechanism | Haiku P1 | Luna P1 | Luna medium P2 | Δ P2 Luna − P1 Haiku [95% CI] | H9 as run: Δ P1 Luna − P1 Haiku |
|---|---|---|---|---|---|
| data_leakage | 0.042 | 0.868 | 0.926 | +0.884 [+0.824, +0.940] | +0.826 [+0.771, +0.882] |
| label_corruption | 0.264 | 0.833 | 0.704 | **+0.440 [+0.306, +0.569]** | +0.569 [+0.444, +0.681] |
| lr_warmup | 0.792 | 0.875 | 0.963 | +0.171 [+0.042, +0.315] | +0.083 [−0.069, +0.250] |
| metric_inflation | 0.236 | 0.736 | 0.981 | **+0.745 [+0.639, +0.843]** | +0.500 [+0.403, +0.597] |
| shape_mismatch | 1.000 | 0.903 | 1.000 | +0.000 | −0.097 [−0.167, −0.028] |

Static only:

| mechanism | Haiku P1 | Luna P1 | Luna medium P2 | Δ P2 Luna − P1 Haiku [95% CI] |
|---|---|---|---|---|
| data_leakage | 0.000 | 0.944 | 0.986 | +0.986 [+0.958, +1.000] |
| label_corruption | 0.028 | 0.694 | 0.556 | +0.528 [+0.361, +0.694] |
| lr_warmup | 0.639 | 0.861 | 0.972 | +0.333 [+0.139, +0.556] |
| metric_inflation | 0.028 | 0.778 | 1.000 | +0.972 [+0.917, +1.000] |
| shape_mismatch | 1.000 | 0.833 | 1.000 | +0.000 |

J, static off arm (non-crash detection by mechanism − control false-alarm rate):
- Haiku P1: 0.130 (FA 4/92);
- Luna P1: 0.819 (FA 0/92);
- Luna medium P2: 0.878 (FA 0/92).

**Reading.** H9's two decision-carrying mechanisms keep large positive gaps when Part 2's strict Luna medium
replaces Part 1's Luna:
- label corruption shrinks, +0.569 → +0.440, but its lower bound stays well above 0;
- metric inflation grows, +0.500 → +0.745.

The model-dependence finding does not rest on Part 1's non-strict configuration. Caveat: this is a CROSS-RUN
comparison (different dates, no concurrent randomisation); the H9 column recomputes Part 1's published values
(F17) exactly.

## 5. Bearing on Part 3's H15

H15 (locked) re-tests H9 as a CONCURRENT comparison on the image workload: Luna medium (strict) vs Haiku, off arm,
J per mechanism, pooled over static and ReAct. That is the design this cross-run check cannot provide.

- **Direction.** The workload-1 re-measurement predicts H15's direction (Luna medium > Haiku) and suggests the J
  gaps will be large where Haiku has headroom.
- **Label corruption.** The strict-Luna figure is lower than Part 1's, and its misses are judgements that
  dismiss a visible key. Label flip is therefore the image mechanism most likely to shrink the gap.
- **Headroom.** It is read from Haiku alone, so none of this changes which mechanisms H15 tests.
- **Caveat.** Whether the "noticed but dismissed" behaviour recurs on the image workload is descriptive in Part 3
  (the code-opening / planted-key analyses), not a confirmatory quantity.
