# Operator Academic Sources

Maps each operator to the academic literature that motivated its design. Bibliographic metadata,
the exact claim supported by each source, and the required author sign-off are tracked in
[`CITATIONS.md`](CITATIONS.md). A source motivates an operator category or mechanism; it does not
by itself validate the exact implementation or effect size used by TrainMD.

| Operator ID | Sources |
|-------------|---------|
| `silent.lr_warmup.v1` | Smith et al., "Don't Decay the Learning Rate, Increase the Batch Size" (ICLR 2018; arXiv:1711.00489), for the learning-rate/batch-size relationship; Goyal et al., "Accurate, Large Minibatch SGD: Training ImageNet in 1 Hour" (2017 technical report; arXiv:1706.02677), for linear learning-rate scaling and gradual warmup. These support mechanism realism, not TrainMD's exact LR ladder. |
| `silent.label_corruption.v1` | Natarajan et al., "Learning with Noisy Labels" (NeurIPS 2013), for class-conditional random label flips; Zhang et al., "Understanding deep learning requires rethinking generalization" (ICLR 2017; arXiv:1611.03530), for the ability of overparameterized networks to fit randomized labels. |
| `crash.shape_mismatch.v1` | — (standard engineering fault; no specific academic source) |
| `silent.data_leakage.v1` | Yang, Brower-Sinning, Lewis & Kästner, "Data Leakage in Notebooks: Static Detection and Better Processes" (ASE 2022; arXiv:2209.03345), for leakage pervasiveness and process/static-analysis evidence; Kapoor & Narayanan, "Leakage and the reproducibility crisis in machine-learning-based science" (*Patterns*, 2023; arXiv:2207.07048), for cross-field scientific impact; Shankar, Garcia, Hellerstein & Parameswaran, "'We Have No Idea How Models will Behave in Production until Production': How Engineers Operationalize Machine Learning" (CSCW 2024; arXiv:2403.16795), for qualitative practitioner evidence about training/serving leakage and offline/production discrepancy. The Shankar study is an interview study, **not** a technical leakage-detection paper. |
| `silent.metric_inflation.v1` | Simon Roth, "Which Leakage Types Matter? A Quantitative Landscape Across 2,047 Benchmark Datasets" (2026 preprint; arXiv:2604.04199), for quantitative evidence that selection/peeking and duplication can inflate evaluation; Kapoor & Narayanan (above), for leakage as a measurement-integrity threat. These motivate the metric/observability category, not the exact confidence-subset implementation. In TrainMD the model is healthy; only the *reported* validation accuracy is computed on a non-representative subset. |
