# Literature Review Addition v1.1 — Empirical Grounding for the Operator Taxonomy

**How to apply:** insert Section 14 below immediately before the existing "## Primary sources"
section of `lit_review_v1.md`, and append the "### Operator-realism sources" block to the end of
the existing "## Primary sources" section. This addition does not modify any existing content; it
supplements the review with the empirical grounding for TrainMD's fault operators (a concern
distinct from the benchmark-positioning analysis in §1–§13). Formatting matches the existing
numbered-section and sub-section style.

---

## 14. Empirical grounding for the operator taxonomy

The positioning analysis (§1–§13) answers "is TrainMD scooped, and how should it be framed?"
This section answers a different reviewer question: **"are the injected faults real, or
invented?"** TrainMD's credibility rests on its operators being controlled instances of faults
that practitioners actually encounter. The sources below establish that grounding. Consistent
with §5.4, these are used as *category-level realism evidence and hardness ordering* — not as
per-operator population-frequency weights.

### 14.1 The anchor taxonomy (Humbatova et al.)

Humbatova et al., "Taxonomy of Real Faults in Deep Learning Systems" (ICSE 2020, arXiv 1910.11015),
is the primary empirical anchor. It manually analyses 1,059 artefacts from GitHub commits/issues
across TensorFlow, Keras, and PyTorch plus Stack Overflow, enriched by structured interviews with
20 practitioners, and validated by a survey of a further 21 developers. Its validation survey
gives an ordinal hardness/prevalence ranking that TrainMD uses to weight the portfolio:

- **Training Data — 95% encountered; "Critical" severity (61%); "High" effort (78%).** The
  most-encountered and hardest-to-fix category. TrainMD's flagship silent operators
  (label_corruption, data_leakage, class_imbalance, tiny_subset) sit here.
- **Hyperparameters — 86%; mostly Minor/Medium.** The easy-baseline category (lr_warmup).
- **Preprocessing of Training Data — 86%.** Normalization-skew and tokenizer/truncation operators.
- **Model Type & Properties — 81%; Wrong Tensor Shape — 67%; Loss Function — 65%; Optimiser —
  57%; Activation Function — 43%.** Shape_mismatch (crash) and wrong_loss_coupling map here.

The survey confirms 13/15 categories were experienced by ≥50% of participants (average "yes" rate
66%), i.e. TrainMD's fault categories are broadly representative, not niche. **Verification note:**
frequencies are self-reported Likert responses from a 21-developer validation survey atop a
1,059-artefact taxonomy; cite as ordinal evidence of importance and hardness, never as a precise
per-operator probability (consistent with §5.4).

### 14.2 Production-practitioner evidence (CMU study)

Shankar, Garcia, Hellerstein & Parameswaran, "'We Have No Idea How Models will Behave in
Production until Production'" (CSCW 2024, arXiv 2403.16795), an interview study of ML engineers,
independently names three of TrainMD's operators as common, hard-to-diagnose production bugs:
**data leakage** ("assuming during training that there is access to data that does not exist at
serving time"), **label flipping** ("accidentally flipping labels in classification models"), and
**unset random seeds** in distributed training. The study's signature symptom — "a large
discrepancy between offline validation accuracy and production accuracy" — is precisely the
misleading-symptom property TrainMD's hidden-test-set recovery oracle is built to capture. This is
qualitative interview evidence; cite for realism and mechanism, not frequency.

### 14.3 Data-leakage pervasiveness and magnitude (flagship operator)

The flagship operator (data_leakage) is the best-evidenced in the portfolio:

- **Pervasiveness:** Yang et al., "Data Leakage in Notebooks: Static Detection and Better
  Processes" (ASE 2022, arXiv 2209.03345), find leakage "pervasive among over 100,000 analyzed
  public notebooks."
- **Scientific impact:** Kapoor & Narayanan, "Leakage and the reproducibility crisis in
  machine-learning-based science" (*Patterns* 4, 100804, 2023; earlier preprint arXiv 2207.07048),
  find leakage affects "at least 294 studies across 17 fields, leading to overoptimistic findings."
- **Magnitude:** Roth, "Which Leakage Types Matter? A Quantitative Landscape Across 2,047 Benchmark
  Datasets" (arXiv 2604.04199, 2026), quantifies selection/peeking leakage inflation (ΔAUC =
  +0.013–0.045; d_z = 0.27–0.93; +0.040 in 92% of datasets at k=10) and train/test-overlap
  memorization (d_z = 0.37 to 1.11 at 10% duplication, scaling with model capacity). A medical-
  imaging case saw validation AUC 0.75–0.99 collapse to a true-test AUC of 0.72.

These establish that leakage is common, consequential, and produces a *reproducible* val↑/test↓
signature — exactly the property that makes it TrainMD's discriminating flagship. **Verification
note:** the Roth (arXiv 2604.04199) and Kapoor & Narayanan figures should be confirmed against
primary PDFs before submission; the 2026 Roth preprint in particular is recent and unreviewed.
Use magnitude figures as existence-and-scale evidence; tune the operator's own leak strength to a
clean signature rather than citing these as target effect sizes.

### 14.4 Platform-interaction failures (Phase II justification)

Zhang et al., "An Empirical Study on Program Failures of Deep Learning Jobs" (ICSE 2020, the
Microsoft Philly study), found that ~48% of real deep-learning job failures occur in the
interaction with the platform (environment discrepancies, resource, permissions) rather than in
code logic. This is the empirical justification for TrainMD's Phase II real-cloud fault appendix
(IAM, quota, OOM on actual SageMaker) — and the reason those faults are *deferred* rather than
forced into the reproducible v1 core: they are environment-dependent and hard to make CPU-
reproducible. Cited in the problem statement §12.

### 14.5 Supporting operator-mechanism sources (secondary)

- **Seed variance** (for the deferred seed operator and to justify multi-seed recovery): Picard,
  "torch.manual_seed(3407) is all you need" (arXiv 2109.08203) — up to 1.82% CIFAR-10 test-
  accuracy spread from seed alone.
- **Loss/activation coupling and normalization** (mechanism references): DL bug-localization tools
  (e.g. Theia) enumerate "Labels/output-activation/Loss Mismatch" and "Input Data not Normalized"
  as recognised fault checks.
- **Class imbalance** (mechanism): the classical imbalance literature (Japkowicz & Stephen 2002;
  He & Garcia 2009; Krawczyk 2016) documents that aggregate accuracy masks minority-class collapse
  — the basis for scoring that operator against macro-F1, not accuracy.

### 14.6 How this grounding is used in the paper

Each operator carries its own citation in code (docstring), in DECISIONS.md, and in a running
`operator_sources.md` map that becomes the paper's operator table (operator → empirical source →
category/severity). The lit review provides the *aggregate* grounding ("our faults are drawn from
the empirical fault literature"); the operator table provides the *specific* grounding (each fault
traced to a source). This two-level structure — aggregate here, specific per-operator — is what
lets the paper claim realism defensibly and preempt the "you invented these faults" critique.

---

## Additions to "Primary sources"

Append this block to the end of the existing "## Primary sources" section.

### Operator-realism sources

- Humbatova, Jahangirova, Bavota, Riccio, Stocco, Tonella. "Taxonomy of Real Faults in Deep
  Learning Systems." ICSE 2020. arXiv 1910.11015. *(Anchor taxonomy; category frequency/severity.)*
- Shankar, Garcia, Hellerstein, Parameswaran. "'We Have No Idea How Models will Behave in
  Production until Production': How Engineers Operationalize Machine Learning." CSCW 2024.
  arXiv 2403.16795. *(Names leakage, label-flipping, seed bugs; misleading-symptom mechanism.)*
- Yang, Brower-Sinning, Lewis, Kästner. "Data Leakage in Notebooks: Static Detection and Better
  Processes." ASE 2022. arXiv 2209.03345. *(Leakage pervasiveness across 100k+ notebooks.)*
- Kapoor, Narayanan. "Leakage and the reproducibility crisis in machine-learning-based science."
  *Patterns* 4, 100804, 2023 (preprint arXiv 2207.07048). *(294 studies across 17 fields — VERIFY
  count against primary PDF.)*
- Roth. "Which Leakage Types Matter? A Quantitative Landscape Across 2,047 Benchmark Datasets."
  arXiv 2604.04199, 2026. *(Leakage magnitude — recent preprint, VERIFY against primary PDF.)*
- Zhang et al. "An Empirical Study on Program Failures of Deep Learning Jobs" (Microsoft Philly).
  ICSE 2020. *(48% platform-interaction failures — Phase II justification.)*
- Picard. "torch.manual_seed(3407) is all you need." arXiv 2109.08203. *(Seed variance — deferred
  seed operator.)*

**Verification checklist before submission (extends §13.4):** confirm arXiv IDs and reported
figures for the CMU study (2403.16795), Yang et al. (2209.03345), Kapoor & Narayanan (count: 294
vs 329 across preprint/published versions), and Roth (2604.04199) against primary PDFs. The Roth
2026 preprint and any 2026-range IDs are the highest priority to verify.
