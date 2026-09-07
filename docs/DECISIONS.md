# Design Decisions Log

Per CLAUDE.md: every design decision that deviates from the spec gets a line
here (date, decision, reason). The spec is then updated, not silently bypassed.

| Date | Decision | Rationale | Spec ref |
|------|----------|-----------|----------|
| 2026-09-07 | Docker deferred to M2.2; SageMaker path/env-var conventions (SM_CHANNEL_*, SM_HPS, SM_MODEL_DIR) kept in M2.1 training scripts as CLI-arg fallbacks | M2.1 scope is repo scaffold + reference protocol. Training scripts accept SageMaker env vars but fall back to CLI args for local execution, avoiding Docker complexity while maintaining interface compatibility. The full container contract (spec §2) will be enforced in M2.2. | §2, §11 M2.1 |
| 2026-09-07 | Two-metric visible/hidden split: `metric_visible_val_acc` (agent-visible), `metric_hidden_test_acc` (hidden, recovery oracle) | The recovery oracle (spec §3, §7) must use a held-out test metric that agents never optimize against. Validation accuracy is the agent-visible metric for diagnosis; test accuracy determines recovery success. Tolerance bands (`mean − 2·std`) are computed on the hidden test metric only. | §3, §7 |
| 2026-09-07 | Hidden metric computed only by evaluator on saved checkpoints; workspace never sees test data; data split config separated from training config | `train.py` never loads test data or computes `metric_hidden_test_acc`. The evaluator (`harness/evaluator/evaluate_checkpoint.py`) is the sole code path for the hidden metric. Data-prep config (`data_split.yaml`) is separate from the training config so `config.resolved.yaml` never mentions holdout fractions or split metadata. Hidden data lives in `.hidden_data/` (sibling to `.data/`), not a subdirectory, so a single volume mount of `.data/` cannot leak test files. | §7 |
