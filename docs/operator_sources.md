# Operator Academic Sources

Maps each operator to the academic literature that motivated its design.

| Operator ID | Sources |
|-------------|---------|
| `silent.lr_warmup.v1` | Smith et al. "Don't Decay the Learning Rate, Increase the Batch Size" ICLR 2018; Goyal et al. "Accurate, Large Minibatch SGD" arXiv:1706.02677 |
| `silent.label_corruption.v1` | Natarajan et al. "Learning with Noisy Labels" NeurIPS 2013; Zhang et al. "Understanding Deep Learning Requires Rethinking Generalization" ICLR 2017 |
| `crash.shape_mismatch.v1` | — (standard engineering fault; no specific academic source) |
| `silent.data_leakage.v1` | Yang et al. "Rethinking Data Leakage" arXiv:2209.03345; Kapoor & Narayanan "Leakage and the Reproducibility Crisis in Machine-Learning-based Science" Patterns 2023; CMU arXiv:2403.16795 |
| `silent.metric_inflation.v1` | Roth et al. "Selective Prediction and Metric Inflation" arXiv:2604.04199; Kapoor & Narayanan "Leakage and the Reproducibility Crisis in Machine-Learning-based Science" Patterns 2023 (evaluation/measurement error as a distinct failure class). Metric tier (observability): the model is healthy; only the *reported* validation metric is computed on a non-representative subset. |
