# CLAUDE.md — TrainMD project rules

## What this project is
TrainMD is a research benchmark: controlled, injected incidents in small PyTorch training
jobs, with hidden verified grading of agent diagnoses and repairs. The benchmark is the
product; agents are contestants. Authoritative docs, in priority order:
1. docs/problem_statement_v0.3.md  (scope, claims, RQs — do not exceed this scope)
2. docs/harness_spec_v0.1.md       (architecture, interfaces, milestones)
3. docs/lit_review_v1.md           (positioning; claims-to-avoid list)

## Non-negotiable integrity rules
- `cases/*/hidden/` is NEVER mounted, copied, read, or referenced by anything in the
  agent-facing workspace path. The evaluator container is the only reader.
- Never run an evaluated-agent trial from an interactive session that has seen hidden
  material for that case. Agent trials go through harness/run_agent.py only.
- Evaluation data, split files, metric definitions, and verify params are immutable at
  trial time; the evaluator hashes them before and after every run.
- Every operator ships with unit tests proving: clean run passes verification AND mutated
  run fails it, on 3 seeds, before the operator is merged.

## Engineering conventions
- Determinism: seed python/numpy/torch; torch.use_deterministic_algorithms(True);
  single-threaded dataloaders in reference mode; all deps pinned in the lockfile.
  Never loosen pins to fix drift — investigate.
- CPU-only by default; any run must complete in ≤10 min on 4 vCPU.
- Workspace containers implement the SageMaker training contract (/opt/ml layout,
  SM_* env vars, CloudWatch-style log names). No real AWS calls in Phase I code.
- Small PRs, one milestone item per branch. Conventional commits.
- Every design decision that deviates from the spec gets a line in docs/DECISIONS.md
  (date, decision, reason). The spec is then updated, not silently bypassed.

## Current milestone
M2.1: repo scaffold + tabular workload + reference-run protocol green in CI.
Definition of done: `make reference WORKLOAD=tabular_adult` produces reference/stats.yaml
from 10 seeded runs, and CI re-verifies it from a clean clone.

## Working style for Claude Code sessions
- Read the relevant spec section before implementing; quote the section number in the PR.
- Prefer boring, testable code over clever code; this repo's credibility is its product.
- If a spec requirement seems wrong or ambiguous, STOP and surface it — do not improvise
  benchmark-integrity behavior.
