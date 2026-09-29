# Stage 4 Part 3 — second workload (Fashion-MNIST CNN): DESIGN (APPROVED 2026-09-28, with the author's decisions below)

> **Author's decisions (2026-09-28):** (1) fault list approved; the two workloads' learning-rate faults are DIFFERENT
> mechanisms (workload 1: LR too high → collapse; workload 2: schedule misread → LR decays to ≈ 0 → stall) and are
> compared at the FAMILY level only, never as the same fault; (2) **218 cases**, with the neutral-key metric-inflation
> variant (closes L37 by design); (3) models **Haiku 4.5 + GPT-5.6 Luna (strict), static + ReAct (≈ $56)** — Sonnet
> deferred until Part 2's H11 / H12 results are in; (4) identification: the specs are shared EXACTLY for leakage,
> label corruption, metric inflation and crash; the LR-schedule fault is a SEPARATE operator with its OWN concept — the
> shared learning-rate concept is NOT widened (that would change workload-1 scoring after the freeze); at the Part 3
> re-freeze a test asserts every workload-1 operator spec is byte-identical.
>
> Drafted 2026-09-28. **Design only** — nothing here is built. It extends the prerequisites
> in #70 (data pin, clean CNN pipeline, two-AMD-runner byte-identity check: PASSED, CI run 36363133740). On approval
> the build follows the order in §7; a Part 3 pre-registration is written and locked before any agent trial.

## 1. Principles (carried from workload 1)

- **Same mechanisms, re-implemented from scratch.** Each fault is a new code path in the image pipeline, gated by a
  config key that its operator sets — exactly the workload-1 shape (the operator edits `config.yaml`; the workload's
  own code implements the path the key gates), so evidence (config keys + the operator's `CODE_PATH`) and repairs
  (config patches) work the same way. No code is shared with the tabular faults.
- **Same case design, same seeds:** 3 strengths × confirmatory seeds 42–47 per faulty operator; healthy controls
  50–69; benign controls 70–93 ∪ 110–157; reference 200–229; hidden-eval 100–102; development 0–29 for
  calibration only (`harness/seed_sets.py` — disjointness enforced).
- **Same tier contracts and calibration rule** (`operators/margins.py`): a positive-symptom rung must put the
  VISIBLE metric ≥ 2σ + 1e-3 above the band edge on EVERY seed; a silent rung must put the HIDDEN metric
  ≥ 2σ + 1e-3 below tolerance on every seed; checked at build time per case and in the calibration tests.
- **Workload-1 lesson built in:** the tabular lr fault turned out BIMODAL (each seed collapses or trains normally),
  so its strengths were collapse probabilities, not graded effects (LIMITATIONS L1 / S12). Every image fault must
  pass a **graded-effect check** on the development seeds (monotone mean effect across strengths, no seed at the
  clean level on a faulty rung) before its cases are built; a fault that fails is redesigned, or declared
  detection-only as the tabular lr fault was.

## 2. Faults — how each is re-implemented for images

| # | Operator (proposed id) | Mechanism (workload-1 counterpart) | Image implementation (gated code path) | Config keys set by the operator | Strength ladder (calibrated on dev seeds) | Symptom / tier |
|---|---|---|---|---|---|---|
| 1 | `silent.pixel_tag_leakage.v1` | label leakage (`data_leakage`) | A 4×4 corner patch whose brightness encodes the class label, stamped into TRAIN and visible-VALIDATION images; with probability p the patch shows a random class instead (noise). The hidden test split is never tagged, so a model that learns the shortcut is inflated on validation and degraded on clean test. | `data.corner_tag: true`, `data.corner_tag_noise: p` | lower p = stronger leak (as the tabular aux feature); e.g. p ≈ 0.4 / 0.25 / 0.1 → calibrate | visible ↑ above band; hidden ↓ below tolerance (silent) |
| 2 | `silent.pixel_tag_leakage_neutral.v1` | neutral-key leakage variant (`data_leakage_neutral`, H8) | Identical code path and values, but the keys AND the code identifiers carry no descriptive name (a separate `image_fmnist_neutral` workload family, as `tabular_adult_neutral`) | `data.opt_t: true`, `data.opt_t_level: p` | same p as #1 | as #1 |
| 3 | `silent.label_flip.v1` | label corruption (`label_corruption`) | A deterministic, nested fraction f of TRAINING labels flipped to their confusable partner class (T-shirt↔Shirt, Pullover↔Coat, Sneaker↔Ankle boot, Dress↔Trouser, Bag↔Sandal); nested-prefix index set so a larger f is a strict superset, identical across processes and hidden-eval seeds. Validation and test labels stay clean. | `data.flip_fraction: f` | f ≈ 0.2 / 0.35 / 0.5 → calibrate | visible ↓ and hidden ↓ (silent, negative symptom) |
| 4 | `silent.decay_unit.v1` | learning-rate fault (`lr_warmup`) — **re-designed to be graded, not bimodal** | The clean config decays the LR by `sched.decay_gamma` every `sched.decay_every` EPOCHS. The fault makes the schedule read that interval in optimizer STEPS (157 steps per epoch), so the LR collapses towards zero within the first epoch and training stalls — a smooth under-training, not a divergence coin flip. | `sched.decay_unit: steps` (new key; clean default is epochs), `sched.decay_gamma: γ` | γ closer to 1 = milder (e.g. 0.995 / 0.98 / 0.9 per step) → calibrate for graded effect | visible ↓ and hidden ↓ (silent, negative symptom) |
| 5 | `metric.confident_subset.v1` | metric inflation (`metric_inflation`) | The eval loop reports top-1 on the most-confident fraction q of validation images (max softmax probability), not on the full split. Model, optimisation and checkpoint are identical to the clean run; only the reported number moves; hidden evaluation is unaffected. | `eval.confident_fraction: q` | q ≈ 0.7 / 0.5 / 0.3 → calibrate to ≥ 4σ + 1e-3 above the mean | visible ↑ above band; hidden unchanged (metric tier) |
| 6 | `crash.channel_mismatch.v1` | shape mismatch (`shape_mismatch`) | `net.in_ch` disagrees with the grayscale data, so the first convolution raises at the first forward pass (a traceback naming the workload's own frames — the frozen evidence v2.3 crash-output and call-site sets apply unchanged). | `net.in_ch: c` | c = 2 / 3 / 4 (every rung crashes; the value is the strength, as the tabular input_dim) | crash (exit code ≠ 0) |

**Identification concepts (decided).** Leakage (#1, #2), label corruption (#3), metric inflation (#5, and its
neutral variant) and the crash (#6) declare EXACTLY the concept specs of their workload-1 counterparts. The LR-schedule
fault (#4) is a separate operator with its OWN concept (a learning-rate SCHEDULE / decay fault); the workload-1
learning-rate concept is left untouched, so no workload-1 score can move. The two LR faults are compared at the
learning-rate FAMILY level only. **Adding operators changes the frozen scorer fingerprint by construction** (`token_spec_sha256`, the
evidence spec): the matcher code does not change, but the freeze must be re-written deliberately with a DECISIONS
row BEFORE the Part 3 lock, the new specs reviewed like #68's, and a test added that every WORKLOAD-1 operator's spec
(tokens, vetoes, alternatives, accepted classes, evidence) is byte-identical to the frozen one.

**Decided — L37 closed by design:** `metric.confident_subset_neutral.v1` (keys `eval.opt_q`) is added: **7
operators / 126 faulty cases, 218 total.**

## 3. Controls

- **Healthy: 20** (seeds 50–69), the clean config.
- **Benign configuration changes: 72** (6 types × 12 seeds, the same block pairing as workload 1,
  `operators/control/benign.py::benign_design`), both edit FORMS kept so false positives stay separable by form:

  | Type | Form | Edit | Workload-1 counterpart |
  |---|---|---|---|
  | batch size | changed value | `optim.batch` 128 → 256 | bs128 |
  | epochs | changed value | `sched.epochs` 8 → 10 | ep25 |
  | weight decay | changed value | `optim.weight_decay` 5e-4 → 1e-3 | wd5e4 |
  | learning rate (normal range) | changed value — touches the lr-fault knob family | `optim.base_lr` 0.05 → 0.04 | lr005 |
  | dropout | NEW key | `net.dropout: 0.1` | do01 |
  | gradient clipping | NEW key (non-binding) | `optim.grad_clip: 1.0` | clip1 |

- **Qualification (as workload 1, STAGE4 4.0.6):** every benign type must stay inside the visible band AND above the
  hidden tolerance on all 12 of its seeds on AMD (`benign-qualify` CI task); a type that fails is replaced before any
  case is built.

## 4. Case counts

| | Recommended (neutral metric variant) | Minimal (mirror workload 1) |
|---|---|---|
| Faulty | 7 operators × 3 × 6 = **126** | 6 × 3 × 6 = **108** |
| Healthy | 20 | 20 |
| Benign | 72 | 72 |
| **Total** | **218** | **200** |

## 5. Reference-run plan

1. **Integration first** (build phase, before any reference number): the harness reads the visible-metric SERIES
   from the public card (`reference_visible_metric.series`) instead of the hard-coded `metric_visible_val_acc`
   (baselines' B1, tools, the band checks), so the image workload keeps its own name `val_top1`; the evaluator gains
   the image hidden metric (top-1 on the 5,000-image hidden split, `metric_hidden_test_acc`); the clean
   `reference/config.resolved.yaml` is committed for B2.
2. **30 reference seeds (200–229)** of the clean pipeline in the canonical container on a native **AMD EPYC** runner:
   ≈ 44 s per run → ≈ 22 min. Per run: final visible `val_top1` and hidden test top-1.
3. **Two independent AMD runners must agree byte-for-byte** (the existing `reference-repro` pattern, extended to
   this workload) before the band is adopted — the same bar #70 already passed for training itself.
4. **Committed `reference/stats.yaml`:** visible mean ± 2σ (the public band every case card carries), hidden mean
   and σ, tolerance_lower = mean_h − 2σ_h (recovery verification with the mean-of-3 rule on hidden-eval seeds
   100–102), min / max.
5. **Band sanity before calibration:** expected σ of a 5,000-image validation top-1 ≈ 0.003–0.006, so the
   positive-symptom bar (mean + 4σ + 1e-3) sits ≈ 0.015–0.03 above the mean — reachable by #1 and #5 at the
   proposed strengths; confirmed on development seeds before building.
6. Seed disjointness and the `reference-change-guard` (rebuild every case if the committed reference changes)
   extended to this workload.

## 6. Cost

**Build, reference, calibration, qualification, certify: CI time only ($0).** Agents, per model, with the Part 1
protocol (faulty × 3 arms × 2 repeats × {static, ReAct} + controls × 3 arms static = 924 static + 648 ReAct at 200
cases; ≈ +9% at 218), at measured costs per trial — Haiku from Part 1 (static 0.0135, ReAct 0.0390); GPT-5.6 Luna
medium strict from the Part 2 slice / pilot (0.0024 / 0.0041); Sonnet 5 off from the Part 2 slice / pilot
(0.0272 / 0.0477); Sonnet 5 xhigh static from the Part 2 slice (0.0442), its ReAct ASSUMED (off's × 0.0442 / 0.0272 =
0.0775, unmeasured):

| Models | Static + ReAct (200 cases) | × 1.2 contingency | Static only (× 1.2) |
|---|---|---|---|
| **Haiku 4.5 + GPT-5.6 Luna (strict)** | $42.62 | **≈ $51** | ≈ $18 |
| + Sonnet 5 thinking off | $98.66 | ≈ $118 | ≈ $48 |
| + Sonnet 5 off and xhigh | $189.73 | ≈ $228 | ≈ $97 |

(At 218 cases add ≈ 9%.) The image prompt is not expected to be longer than the tabular one (its `train.py` is
shorter; logs are similar), so the contingency covers context-length risk.

## 7. Build order (after approval; each step gated)

1. Merge #70 (data pin + pipeline + byte-identity check). 2. Harness integration (§5.1) with tests. 3. Reference run
on two AMD runners → adopt `stats.yaml`. 4. Fault code paths + operators, one at a time; each ships with the CLAUDE.md
proof (clean run passes verification AND the mutated run fails it, on 3 seeds) plus the graded-effect check.
5. Re-freeze the scorer for the new operators (DECISIONS; spec review). 6. Benign qualification on AMD. 7. Build and
certify all cases on AMD (validate-all, the FULL known-answer gate); `restore-cases`. 8. Part 3 pre-registration
(replication questions from Parts 1–2 on the new workload), locked. 9. Pilot / slice / run. **Part 3 stays the frozen
evaluation set: its cases and records are not released until its results are final** (LIMITATIONS L31).

## 8. Decisions (taken 2026-09-28 — see the header)

1. The fault list and mechanisms in §2 (in particular the decay-unit redesign of the lr fault, to avoid workload 1's
   bimodality).
2. Add the neutral-key metric_inflation variant (recommended; 218 cases) or mirror workload 1 exactly (200).
3. The model set and agents for Part 3 (cost table §6).
4. Whether the image operators share the workload-1 concept specs exactly (recommended, for comparable
   identification), with the lr concept widened to "learning-rate schedule".
