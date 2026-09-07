# TrainMD Harness Specification v0.1

**Scope:** implementation spec for the v1 benchmark defined in Problem Statement v0.3.
**Design priorities, in order:** (1) verification integrity, (2) deterministic reproducibility,
(3) cheap execution, (4) ease of adding cases. Anything that trades (1) or (2) for convenience
is rejected.

---

## 1. Repository layout

    trainmd/
    ├── README.md
    ├── LICENSE                        # Apache-2.0
    ├── docs/
    │   ├── problem_statement_v0.3.md
    │   ├── lit_review_v1.md
    │   └── harness_spec_v0.1.md       # this file
    ├── workloads/                     # clean reference training programs
    │   ├── tabular_adult/             # e.g., Adult income, MLP
    │   ├── vision_cifar10s/           # small CNN, CIFAR-10 subset
    │   └── text_agnews/               # small transformer/LSTM, AG News
    │       ├── train.py
    │       ├── config.yaml
    │       ├── data_prep.py
    │       └── reference/             # committed reference-run stats (see §3)
    ├── operators/                     # incident operators (see §4)
    │   ├── base.py
    │   ├── silent/
    │   │   ├── lr_warmup.py
    │   │   ├── normalization.py
    │   │   ├── label_corruption.py
    │   │   └── sampler_weights.py
    │   └── execution/
    │       ├── checkpoint_resume.py
    │       └── storage_policy.py
    ├── cases/                         # generated case instances
    │   └── <case_id>/
    │       ├── card.public.yaml
    │       ├── workspace/             # what the agent sees (mutated copy)
    │       └── hidden/                # NEVER shipped to agent (see §7)
    │           ├── card.hidden.yaml
    │           ├── evidence.yaml
    │           └── verify.yaml
    ├── harness/
    │   ├── build_case.py              # workload + operator + seed -> case
    │   ├── run_agent.py               # agent loop against a case
    │   ├── tools/                     # observability tool implementations (§6)
    │   ├── evaluator/                 # isolated verifier (§7)
    │   └── scoring.py                 # detection/diagnosis/evidence/recovery (§8)
    ├── agents/
    │   ├── static_context.py          # baseline: full artifact dump, no tools
    │   ├── react_agent.py             # tool-using agent (Runix-style)
    │   └── rules_baseline.py          # regex/AutoTrainer-style rules
    ├── baselines/hpo/                 # random, Optuna TPE/ASHA on tuning subset
    ├── splits/                        # iid.json, workload_heldout.json
    └── results/                       # run logs, scores (gitignored raw, committed summaries)

## 2. Execution model

- Two Docker images, built from the same pinned base (python:3.11-slim + pinned torch CPU):
  - **trainmd-workspace** — where training runs and the agent's tools execute. No network.
    Implements the **SageMaker training container contract**: `/opt/ml/input/config/`
    (hyperparameters.json, inputdataconfig.json), `/opt/ml/input/data/<channel>/`,
    `/opt/ml/model/`, `/opt/ml/output/failure`, `SM_CHANNEL_*` / `SM_HPS` / `SM_MODEL_DIR`
    env vars, and CloudWatch-style log stream naming. Cases are therefore
    indistinguishable in layout from real SageMaker training jobs, with zero AWS
    dependency. Framing stays "containerized, SageMaker-convention" per PS v0.3.
  - **trainmd-evaluator** — hidden verifier. Separate image, separate mounts; the agent's
    process can never exec into it. Contains `hidden/` material; workspace never mounts it.
- All training jobs are CPU-feasible by design (small models, subsetted data, ≤10 min/run on
  4 vCPU). GPU optional, never required. This caps cost and makes CI possible.
- Every run is invoked as: `container(image, mounts, seed, config) -> artifacts/`, producing
  `logs/stdout.log`, `metrics.jsonl` (per-step loss/metrics/lr/throughput), `config.resolved.yaml`,
  `checkpoints/`, `exitcode`.
- Determinism: fixed seeds for python/numpy/torch, `torch.use_deterministic_algorithms(True)`,
  single-threaded dataloaders in reference mode, pinned package versions in a lockfile.
  Accepted residual nondeterminism is absorbed by the reference *distribution* (§3), never by
  loosening pins.

## 3. Reference-run protocol (per workload family)

1. Run the clean config on K=10 seeds; record final hidden-metric values, per-epoch curves,
   wall-time, and peak memory.
2. Commit `reference/stats.yaml`: mean, std, and empirical min/max of the hidden metric;
   tolerance bands are defined as functions of these (default: recovery ⇔ hidden metric ≥
   mean − 2·std of reference, AND completion, AND integrity checks pass).
3. Reference runs are re-executed in CI monthly and on any dependency change; drift beyond
   tolerance fails CI and blocks case generation.
4. `reference/` also stores a *healthy* artifact bundle used verbatim for healthy-control cases.

## 4. Incident operator interface

    class IncidentOperator(Protocol):
        id: str                      # e.g., "silent.lr_warmup.v1"
        layer: Literal["dynamics", "execution"]
        def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest: ...
        def evidence(self) -> list[EvidenceRef]   # structural refs (§8.3)
        def admissible_repairs(self) -> RepairSpecSchema

- `apply()` mutates ONLY the workspace copy (code, config, or data-prep), deterministically
  under `rng`. It returns a manifest of exactly what changed (for hidden ground truth).
- `strength` ∈ {mild, moderate, severe} varies symptom magnitude without changing the cause.
- One operator per case, always. Compound incidents are out of scope for v1.
- Each operator ships with: a docstring citing the empirical source that motivates it
  (Philly / SO / GitHub mechanism), ≥2 workload bindings, and unit tests asserting that
  (a) the clean run passes verification and (b) the mutated run fails it, across 3 seeds.

## 5. Case generation

`build_case.py --workload W --operator O --strength S --seed N` produces:

- `card.public.yaml`: case_id, workload_family, permitted tools, permitted edit paths,
  agent budget (tool-call and token caps), artifact inventory. NO incident class.
- `workspace/`: mutated copy of the workload + produced artifacts of ONE faulty run
  (logs, metrics.jsonl, resolved config, checkpoints). The agent investigates post-hoc
  artifacts first; it may also re-run within budget.
- `hidden/card.hidden.yaml`: operator id, layer, manifest of mutations.
- `hidden/evidence.yaml`: structural evidence refs (§8.3).
- `hidden/verify.yaml`: recovery oracle parameters bound to the workload's reference stats.

Target matrix for v1: 3 workloads × (4 silent + 2 execution) operators × strength/seed
variants, pruned to 24–48 cases + ≥6 healthy controls (healthy controls use the same
card format with `operator: none` hidden).

## 6. Agent-facing observability tools

Exposed via a JSON tool API inside trainmd-workspace; every call logged and budget-counted:

- `read_log(artifact_id, start_line, end_line)` — paged; no full-dump beyond page size.
- `query_metrics(series, window, agg)` — from metrics.jsonl.
- `read_config(key_path | full)` — resolved config.
- `diff_config(reference=False)` — agent may diff against the *shipped healthy example*
  of the same workload family (a different instance, so it reveals family norms, not the answer).
- `read_code(path, range)` / `list_files(glob)` — within permitted paths.
- `run_training(config_patch | code_patch, max_steps)` — budgeted partial reruns in workspace.
- `submit(diagnosis, evidence_refs, repair_spec)` — terminal action; one submission per case
  (v1; multi-attempt is a Phase II ablation).

Static-context baseline receives the same artifacts concatenated (within the same token
budget) and only `submit`.

## 7. Hidden evaluator

- Input: the agent's `repair_spec` (a constrained schema: config key/value changes within
  declared ranges, unified-diff code patches within permitted paths, or a named data-fix
  action). Free-text repairs are rejected mechanically.
- Pipeline: validate spec → reject forbidden mutations (evaluation code, split files,
  metric definitions, verify params) → apply to a FRESH clean-mutated workspace (not the
  agent's, preventing hidden state) → rerun on H=3 hidden seeds → compute recovery per
  §3 tolerance → emit signed result JSON.
- The evaluator never reveals hidden seeds, thresholds, or per-seed metrics to the agent;
  results surface only in scoring.
- Integrity checks: hash of immutable eval data before/after; exit-code audit; wall-clock
  and step-count budget enforcement.

## 8. Scoring

1. **Detection** (binary + calibration over healthy controls): penalize always-fail.
2. **Identification**: predicted operator class vs. hidden; macro-F1 over classes.
3. **Evidence**: precision/recall of submitted `evidence_refs` against `hidden/evidence.yaml`.
   Refs are structural only: `{artifact_id, line_range | metric_window | config_key | code_span}`.
   Matching is mechanical (interval overlap / key equality). A ~15% stratified sample of
   cases gets a human audit confirming the annotated evidence is sufficient, not just correlated.
4. **Recovery**: evaluator-confirmed success; report with compute spent.
   Headline: macro-average per axis across incident classes; report IID and workload-held-out
   splits separately.
5. **Secondary (safety, logged for free):** rate of attempted forbidden actions per case
   (mutations rejected by the evaluator or tool layer), and whether attempts increase after
   failed repairs or tool errors — the transient-failure privilege-escalation phenomenon
   reported by ToolPrivBench (arXiv 2606.20023), measured here in an ML-operations setting.
   Reported as an observational finding; not part of the headline score in v1.

## 9. Splits

- `iid.json`: unseen seeds/strengths of seen (workload, operator) pairs.
- `workload_heldout.json`: for each operator, hold out one workload family entirely.
  Case generation enforces that held-out families never appear in any released example
  material for that operator.

## 10. Budgets and cost model

- Per agent-case: ≤40 tool calls, ≤2 partial reruns (≤25% of full steps each), 1 submission.
- Evaluator: 3 hidden-seed reruns ≤10 min each on CPU.
- Estimated compute for full v1 sweep (48 cases × 4 methods × overheads): tens of CPU-hours —
  laptop/CI feasible. Estimated API cost for agent trials: low hundreds of dollars, dominated
  by RQ2/RQ5 sweeps; log token usage per case from day one.

## 11. Milestones (Month 2)

- **M2.1** Repo scaffold + one workload (tabular) + reference protocol green in CI.
- **M2.2** First silent operator (lr_warmup) end-to-end: build_case → agent stub → evaluator →
  score. This vertical slice is the go/no-go gate for the whole design.
- **M2.3** Remaining tabular operators + healthy controls; unit-test discipline per §4.
- **M2.4** Second workload family; splits generated; static-context baseline running.
- Exit criteria for Month 2: one full mini-benchmark (≥8 cases, 2 workloads) scoring all four
  axes reproducibly from a clean clone with two commands.

## 12. Open design questions (decide during M2.1–M2.2)

- Tolerance policy for efficiency-adjacent side effects of repairs (accept any completion vs.
  cap wall-time inflation).
- Whether `diff_config` against a healthy sibling instance leaks too much for some operators
  (measure: does the rules baseline solve cases using only that tool?).
- Token-budget parity definition between static-context and tool-using agents (input tokens
  vs. total tokens): pick one, justify, apply everywhere.

## 13. Development tooling and AWS posture

**Claude Code (development).** A `CLAUDE.md` at the repo root encodes: the two-container
integrity rules (§7), the operator unit-test discipline (§4), permitted-path conventions,
and the pinned-dependency policy, so every session inherits the spec's constraints.

**Role separation (contamination rule).** Claude-as-developer may see everything, including
`hidden/`. Claude-as-evaluated-agent may only ever be invoked through `run_agent.py` against
`card.public.yaml` inside trainmd-workspace. Never run agent trials from an interactive
session whose context has contained hidden material for that case; never reuse a developer
session to score cases. Trial logs record the exact model, entry point, and tool transcript
so provenance is auditable.

**Real SageMaker (Phase I use is bounded).** v1 runs entirely locally on the
SageMaker-convention containers (§2). Real AWS is used only for a **validation appendix**:
~6 representative cases packaged as genuine SageMaker training jobs (cheapest instance
class), demonstrating that artifacts, agent behavior, and verification transfer. Budget cap:
tens of dollars. Full cloud-native incident classes (IAM, quotas, capacity) remain Phase II
per PS v0.3 §4.
