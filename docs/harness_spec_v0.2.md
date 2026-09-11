# TrainMD Harness Specification v0.2 (as-built)

**Status:** v0.2 supersedes v0.1. v0.1 described the *planned* harness; v0.2 describes the system
**as built and validated** through three operators (two silent, one crash) across the tabular
workload, with a real-model smoke test on each. It keeps v0.1's section numbering so the two can
be read side by side. Where v0.1 said "will," v0.2 says "does," and new subsystems (LLM agent,
provenance, validator, crash tier) are documented in their real form.

**Design priorities (unchanged from v0.1), in order:** (1) verification integrity, (2)
deterministic reproducibility, (3) cheap execution, (4) ease of adding operators. Every decision
that traded (1) or (2) for convenience was rejected — see DECISIONS.md for the running ledger.

---

## 1. Repository layout (as-built)

```
trainmd/
├── docs/                         problem_statement, lit_review, harness_spec,
│                                 DECISIONS, PROVENANCE, ARCHITECTURE, COMPARISON, walkthrough
├── workloads/tabular_adult/      data_prep.py, train.py, config.yaml, reference/stats.yaml
├── operators/
│   ├── base.py                   IncidentOperator protocol + frozen dataclasses
│   ├── silent/                   lr_warmup.py, label_corruption.py        (dynamics tier)
│   └── crash/                    shape_mismatch.py                        (execution tier)
├── harness/
│   ├── reference_run.py          10-seed reference protocol → stats.yaml
│   ├── build_case.py             tier-aware case builder + operator registry + idempotency guard
│   ├── validate_case.py          ~16 structural/consistency/well-formedness invariants
│   ├── scoring.py                four-axis scoring + cost-split + evidence matching
│   ├── run_agent.py              trial runner (crash-safe) + CLI
│   ├── provenance.py             trial-record schema + index sync
│   ├── pricing.py                per-model cost estimation
│   ├── tools/                    tool_context.py (gatekeeper), tools.py (the tools)
│   ├── llm/                      client.py (protocol + FakeLLMClient), anthropic_client.py
│   └── evaluator/                repair_spec.py, verify_repair.py, evaluate_checkpoint.py
├── agents/                       stub_agent.py, stub_degenerate.py, llm_agent.py
├── tests/                        one test file per module; ~240+ tests, fast + marked-slow
└── results/                      (gitignored) trial records, recovery results, index.jsonl
```

Operators live under a tier directory: `operators/silent/` (dynamics layer, completes-but-bad)
and `operators/crash/` (execution layer, fails-to-complete). The directory name `crash` is used
rather than `execution` to avoid collision with the `layer` field value (DECISIONS.md).

## 2. Execution model (as-built)

Training runs as a subprocess of `train.py`, which follows the SageMaker training-container
contract (`/opt/ml/...` paths, `SM_*` env-var fallbacks) so a case resembles a real cloud job
with no cloud dependency. Determinism is enforced: seeded python/numpy/torch,
`torch.use_deterministic_algorithms(True)`, single-thread dataloaders, pinned dependencies via
`uv.lock`. Operators that introduce their own randomness (e.g. label_corruption's flip set) derive
a **process-stable** seed via `hashlib` — never Python's per-process-salted `hash()` — so the
injected fault is identical across the separate subprocesses the evaluator spawns (DECISIONS.md).

Runs are CPU-feasible by design. The ≤10-minute target holds for the tabular workload and governs
CI; for heavier future workloads (vision, text), overnight CPU generation is accepted, with the
recovery oracle's 3-seed rerun as the dominant multiplier.

Each run produces, under `run_output/`: `metrics.jsonl` (per-epoch train/val, visible only),
`logs/stdout.log`, `config.resolved.yaml` (with any config-flag mutation nested consistently with
where the operator sets it), `checkpoints/` (silent tier only — a crash produces none), and
`exitcode`.

## 3. Reference-run protocol (as-built)

`reference_run.py` runs the clean workload on 10 seeds, trains (visible metrics only), then calls
the evaluator to compute each run's **hidden** test score, and writes mean/std/min/max and the
tolerance band (default `mean − 2·std`) to `reference/stats.yaml`. The canonical environment is
Linux/CI (macOS produces slightly different floats — cross-platform training divergence is the
same order as seed-to-seed std, so the reference and any verification must share a platform;
DECISIONS.md). `scripts/verify_reference.py` re-checks reproduction in CI.

## 4. Incident operator interface (as-built)

`operators/base.py` defines the `IncidentOperator` protocol and frozen dataclasses
(`MutationRecord`, `Manifest`, `EvidenceRef`, `RepairSpecSchema`). Every operator implements:
- `apply(workspace, rng, strength)` — mutates the workspace copy (one config-flag mutation),
  returns a `Manifest` recording exactly what changed (ground truth).
- `evidence()` — the **minimal sufficient** evidence set: root-cause config key + observable
  symptom (metric window for silent faults, log `line_range` for crash tracebacks). Not every
  artifact in the causal chain (DECISIONS.md).
- `admissible_repairs()` — a `RepairSpecSchema` naming legal keys and value ranges; excludes the
  faulty value and any "change nothing" repair, and excludes unrelated keys (so a wrong-fault
  guess is rejected).
- `accepted_classes()` — a `frozenset` of legitimate class names, defined **by principle** (the
  fault's core concept), not by expanding to match observed model outputs.

`layer` is `"dynamics"` (silent) or `"execution"` (crash). Each operator's symptom is verified
empirically before its evidence set is finalized (the "measure, don't assume" rule).

## 5. Case generation (as-built)

`build_case.py` turns (workload, operator, strength, seed) into a case:
1. **Idempotency guard:** refuses to rebuild an existing (workload, operator, strength, seed)
   tuple unless `--force`, which rebuilds in place reusing the case ID. A tuple maps to exactly
   one opaque case ID (`case_0001`); never silently duplicates.
2. Copies allowlisted workload files into `workspace/`, symlinks visible data.
3. Runs the operator, then runs training once.
4. **Tier-aware build guard:** silent operators must complete (exitcode 0, finite, below
   tolerance); crash operators must fail (non-zero exitcode, no valid checkpoint). A case failing
   its tier's guard is rejected.
5. Writes the public card (opaque ID, workload family, permitted tools, budget — no incident
   info) and the hidden files: `card.hidden.yaml` (true operator, workload identity, mutations,
   accepted_classes), `evidence.yaml`, `verify.yaml` (tolerance, hidden seeds, admissible repairs;
   `faulty_value` is null for crash cases).

## 6. Agent-facing observability tools (as-built)

`harness/tools/tool_context.py` is the gatekeeper for one agent on one case: it counts every tool
call against the budget, confines all file access via `resolve()` + `is_relative_to(workspace_root)`
(one structural check subsuming `..`, absolute paths, symlink escape — no fragile string
blocklists, so `hidden/` is physically unreachable), logs a full transcript, and stores the final
submission. `harness/tools/tools.py` implements: `read_log`, `query_metrics`, `read_config`,
`read_code`, `list_files`, `submit`. `diff_config`/`run_training` are deferred (return
"not available"). Every file access routes through the gatekeeper.

## 7. Hidden evaluator (as-built)

`harness/evaluator/` is the sealed grader for recovery:
- `repair_spec.py` — strict parse/validate of a proposed repair: rejects unknown keys,
  out-of-range values, non-numeric values, booleans, and non-finite values, each with a
  machine-readable reason code (also feeding the safety metric).
- `verify_repair.py` — the recovery oracle. Takes workload identity from the **hidden card only**
  (allowlist-checked, so a tampered public card cannot redirect what runs); builds a **fresh**
  workspace from trusted source + the hidden mutation manifest (never the agent's workspace);
  applies the fix; reruns training on the hidden seeds; declares **recovered** only if every seed
  completes and clears tolerance (for crash cases: completes AND clears tolerance). Hashes trusted
  inputs before/after; writes result to `results/<case>/recovery_<trial_run_id>.yaml` (linked to
  the trial, idempotent on re-verify — never into `hidden/`).
- `evaluate_checkpoint.py` — the single code path allowed to read the hidden test set.

## 8. Scoring (as-built)

`harness/scoring.py` grades four axes plus a secondary safety count, matched mechanically:
- **Detection** (binary; healthy controls prevent "always broken" gaming).
- **Identification** (predicted class vs the hidden `accepted_classes` set, normalized for
  case/separators — no LLM judge).
- **Evidence** (precision/recall/F1: `config_key` matched at fault granularity with config
  artifact normalization; `metric_window` by series + interval overlap; `line_range`/`code_span`
  by line overlap).
- **Recovery** (via the evaluator).

**Cost split (a load-bearing design choice):** `score_diagnosis()` runs the three free, instant
axes + safety inline the moment an agent trial returns; `score_recovery` / `score_recovery_standalone`
runs the expensive recovery axis (which retrains) as a separate, restartable step and merges the
verdict back into the trial record and the index. `aggregate_scores` macro-averages across trials.

## 9. Splits (as-built + planned)

IID split (unseen seeds/strengths of seen operator×workload pairs) is available now. The
workload-held-out split (hold out one workload per operator) requires ≥2 workloads and is enabled
once the vision workload lands. Case generation enforces that held-out families never appear in
released example material for that operator.

## 10. Budgets and cost model (as-built, measured)

Per agent-case budget: bounded tool calls (default cap), bounded partial reruns, one submission.
Measured per-trial cost on the cheapest current model is ~$0.03–0.07 (crash cases cheapest; silent
faults with more investigation costliest); token use varies ±~30% run-to-run under temperature-1.0
nondeterminism, while four-axis *scores* are stable across runs. Every trial records exact token
counts and an `is_estimate`-flagged cost via `pricing.py`. The recovery oracle's 3-seed rerun is
the dominant compute cost at scale; keep the seed count modest and batch verifications separately
from the fast paid agent trials.

## 11. Provenance and the trial runner (as-built) — expands v0.1 §11

`harness/provenance.py` defines the versioned trial record (environment incl. git commit +
dirty flag, model, usage, submission, tool + LLM transcripts, scores, budget) and keeps
`results/index.jsonl` — one line per trial — synced with the record on every (re)score.
`harness/run_agent.py` orchestrates a trial crash-safely: it writes a partial record to disk
*before* the agent runs, runs the agent inside `try/finally`, and in `finally` scores the free
diagnosis axes, finalizes the record ("completed"/"crashed"), overwrites the partial, and updates
the index — then re-raises any crash. This guarantees a paid trial's tokens are never lost. The
CLI selects a stub agent by name or an LLM agent via `--model`.

## 12. The LLM agent (as-built) — new subsystem

`harness/llm/client.py` defines the provider-agnostic `LLMClient` protocol and `FakeLLMClient`
(scripted responses — lets the full agent loop be tested at zero cost). `agents/llm_agent.py` is a
ReAct loop: it builds a system prompt (task + exact tool signatures + submit schema documenting all
evidence kinds: `config_key`, `metric_window`, `line_range`, `code_span`), then iterates
send→tool-calls→execute→append until `submit` or a turn/token cap. Token usage is captured into the
record **immediately after each model call**, so a crash preserves already-paid tokens.
`harness/llm/anthropic_client.py` implements the protocol via the Anthropic SDK with bounded retry
(≤2 retries on transient errors, none on auth/400), reading the key from the environment only.
Stub agents (`stub_agent`, `stub_degenerate`) exercise the whole pipeline for free and prove
scoring discriminates diagnosis quality from blind recovery.

## 13. Case validator (as-built) — new subsystem

`harness/validate_case.py` runs ~16 invariants on any case (or all), replacing manual review at
scale: **WALL** (no hidden token in the visible workspace; public card free of incident info;
hidden seeds disjoint from reference seeds), **CONSISTENCY** (case-id/workload agreement; unique
registry tuple; tolerance recomputed from reference within epsilon; faulty-value below tolerance —
tier-aware, null-tolerant for crash; deep mutation check; **index matches trial record**;
**recovery files linked to trials**), and **WELL-FORMEDNESS** (required files — tier-aware for the
checkpoint; hidden-card and verify.yaml required fields incl. non-empty accepted_classes). Manual
line-by-line audit of generated output remains the practice while operators are new — it has
repeatedly caught issues neither the invariants nor the tests did.

## 14. Development posture and AWS (as-built) — from v0.1 §13

Built with `uv` (locked deps, `uv run`), a `CLAUDE.md` encoding integrity rules for coding
sessions, and the developer/evaluated-agent separation (an evaluated agent is only ever invoked
through `run_agent.py` against the public card; developer sessions may see everything). Real AWS is
Phase II only — a small real-SageMaker validation appendix demonstrating transfer of the
SageMaker-convention cases to genuine cloud faults (IAM, quota, OOM), never the reproducible v1
core.

## 15. What changed from v0.1 (summary)

- Crash tier added (execution layer, tier-aware build guard, null faulty_value, log-based
  evidence, tier-aware validator checks).
- LLM agent + model clients + provenance + validator built and documented (v0.1 had these as
  plans or absent).
- Scoring cost-split, evidence-matching normalization, and principled accepted-class sets
  formalized.
- Idempotency guard and index/recovery consistency added (found necessary via line-by-line audit).
- Cost model replaced with measured figures.
- Splits, workloads, and cloud faults reconciled with the staged v1/Phase-II scope in
  problem_statement v0.4.
