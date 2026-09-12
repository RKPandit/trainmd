# TrainMD Harness Specification v0.3 (as-built)

**Status:** v0.3 supersedes v0.2, **frozen at the pre-sweep commit `75b6e2d`**. It describes the
system as built and validated through **four operators + a healthy control tier** across the
tabular workload, plus the two experiment agents (ReAct + static baseline), the pre-sweep
validation gates, schema-1.1 capture, and the sweep orchestrator. It keeps v0.2's section spine
and adds §16 (sweep orchestration) and §17 (validation gates). Where v0.2 said "three operators,"
v0.3 says "four + controls"; new subsystems are documented in their real form. No paid sweep has
run yet.

**Design priorities (unchanged), in order:** (1) verification integrity, (2) deterministic
reproducibility, (3) cheap execution, (4) ease of adding operators — plus a fifth that emerged:
(5) capture everything the analysis needs at trial/build time, because a paid sweep is
unrepeatable.

Every decision that traded (1) or (2) for convenience was rejected — see DECISIONS.md.

---

## 1. Repository layout (as-built)

```
trainmd/
├── docs/                         problem_statement, lit_review, harness_spec,
│                                 DECISIONS, PROVENANCE, ARCHITECTURE, COMPARISON, walkthrough
├── workloads/tabular_adult/      data_prep.py, train.py, config.yaml, reference/stats.yaml
├── operators/
│   ├── base.py                   IncidentOperator protocol + frozen dataclasses
│   ├── silent/                   lr_warmup, label_corruption, data_leakage  (dynamics tier)
│   ├── crash/                    shape_mismatch.py                          (execution tier)
│   └── control/                  healthy.py                                 (control tier)
├── workloads/tabular_adult/      … + datautil.py (nested-selection helper, copied into workspaces)
├── harness/
│   ├── reference_run.py          10-seed reference protocol → stats.yaml
│   ├── build_case.py             tier-aware builder + build_id + effect-size labels + registry
│   ├── validate_case.py          20 structural/consistency/well-formedness invariants (W1–W4, C1–C11, F1–F6)
│   ├── scoring.py                tier-aware four-axis scoring + cost-split + evidence matching
│   ├── run_agent.py              trial runner (crash-safe, trusted-agent guard) + CLI
│   ├── provenance.py             trial-record schema (v1.1) + index sync + supersession
│   ├── pricing.py                per-model cost estimation
│   ├── gate_known_answer.py      the known-answer gate (make gate-known-answer)
│   ├── audit_index.py            the impossible-combination audit (make audit-index)
│   ├── sweep.py                  the sweep orchestrator (plan / run / report)
│   ├── sweep_manifest.py         the compute-statement manifest
│   ├── tools/                    tool_context.py (gatekeeper), tools.py (the tools)
│   ├── llm/                      client.py (protocol + FakeLLMClient), anthropic_client.py
│   └── evaluator/                repair_spec.py, verify_repair.py, evaluate_checkpoint.py
├── agents/                       stub_agent, stub_degenerate, llm_agent, static_agent,
│                                 oracle_agent, degenerate_agent, always_broken_agent
├── tests/                        one+ test file per module; 460+ tests, fast + marked-slow
├── sweeps/                       (TRACKED) plan / manifest / progress files — pre-registration
├── docs/audits/                  (TRACKED) gate + audit + sweep tables
└── results/, cases/              (gitignored) trial records / built cases (answer-key material)
```

Operators live under a tier directory: `operators/silent/` (dynamics, completes-but-bad),
`operators/crash/` (execution, fails-to-complete), `operators/control/` (control, genuinely
healthy). The directory name `crash` avoids collision with the `layer` field value (DECISIONS.md).

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
- `oracle_repair()` — the known-good fix that restores the reference (a `{repair_type, patches}`
  dict; `None` for a control). Required; a registry test asserts it is admissible under the
  operator's own `admissible_repairs()` and is not the faulty value.

`layer` is `"dynamics"` (silent), `"execution"` (crash), or `"control"` (healthy). The four faults
are: **lr_warmup** (silent, easy, negative symptom), **label_corruption** (silent, subtle; nested
prefix flip sets from `datautil.py` make difficulty monotone in the noise fraction), **shape_mismatch**
(crash, binary recovery, log evidence), **data_leakage** (silent, flagship, POSITIVE symptom —
visible accuracy rises via an innocuously-keyed label-correlated feature that becomes pure noise at
hidden-test time). **control.healthy.v1** injects no fault (empty mutations/evidence, no repair,
`oracle_repair=None`). Each operator's symptom is verified empirically, and each strength must
fail/crash on ALL calibration seeds by ≥2σ margin, before its ladder is finalized (DECISIONS.md).

## 5. Case generation (as-built)

`build_case.py` turns (workload, operator, strength, seed) into a case:
1. **Idempotency guard:** refuses to rebuild an existing (workload, operator, strength, seed)
   tuple unless `--force`, which rebuilds in place reusing the case ID. A tuple maps to exactly
   one opaque case ID (`case_0001`); never silently duplicates.
2. Copies allowlisted workload files into `workspace/`, symlinks visible data.
3. Runs the operator, then runs training once.
4. **Tier-aware build guard:** silent must complete (exitcode 0, finite, below tolerance); crash
   must fail (non-zero exitcode, no checkpoint); control must complete and CLEAR tolerance
   (inverted). An operator may add a `build_guard_checks()` hook (data_leakage uses it to insist
   the visible metric is above the mean+2σ upper band — the misleading symptom is real).
5. Writes the public card (opaque ID, workload family, permitted tools, budget, the healthy-run
   **reference band** for the visible metric, and a content-derived **`case_build_id`** — no
   incident info) and the hidden files: `card.hidden.yaml` (operator, workload identity, mutations,
   accepted_classes, **the effect-size labels**: faulty_visible_value, visible/hidden σ-distance,
   symptom_direction ∈ {negative, positive, within_band, crash, none}), `evidence.yaml`,
   `verify.yaml` (tolerance, hidden seeds, admissible repairs, **oracle_repair**; `faulty_value`
   null for crash).

**Build IDs / supersession:** `case_build_id` = SHA-256 over the canonical hidden content +
workload source hashes (train.py, config.yaml, datautil.py), written into both cards. Content-
derived, not a UUID: a no-op rebuild yields the same id; a material change yields a new one.
Trials record it; a rebuilt case marks prior trials superseded (validator C10, audit R9).

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

**Tier-aware:** on a **control**, correct `detected` is false (flagging a healthy run is a
detection false positive); evidence F1 = 1.0 iff no refs were submitted else 0.0; recovery is
replaced by **`no_unnecessary_repair`** (correct iff no patches; a submitted repair sets
`false_intervention`). `aggregate_scores` computes `recovery_rate` over non-control trials only,
adds `detection_false_positive_rate_on_controls` + `false_intervention_rate`, and **excludes
`trusted` records** (printing the count). `confidence`/`rationale` are stored raw but unscored.

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

`harness/provenance.py` defines the versioned trial record (**schema 1.1**: environment incl. git
commit + dirty flag + `case_build_id`, model, usage, submission, tool + LLM transcripts, scores,
budget, plus the **pre-sweep capture blocks**: `prompt` {text, sha256, `prompt_version` — drift-
guarded}, `conditions` {sweep_name, agent_type, anchor, repeat_index}, `termination_reason` — an
eight-value enum separating the model's choice from the harness stopping it — `symptom_direction`,
and per-transcript `api_model`/`latency_sec`; the submission adds optional `confidence`/`rationale`).
These are captured now because they are unrecoverable after a paid sweep. The index gains required
condition columns (termination_reason, agent_type, anchor, repeat_index, symptom_direction). It keeps
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
The ReAct loop treats a `max_tokens` cut-off as a continuation (capped), and takes an `anchor`
flag (`off` omits the reference-band line — the H1/H6 sweep factor; `prompt_version` records it).

**The static baseline (H6 control):** `agents/static_agent.py` assembles the whole run into one
prompt and makes ONE call — the control condition for tool-mediated investigation. It shares the
prompt text, submit schema, reference band, and healthy-runs guidance VERBATIM with the ReAct agent
(literal slices of one template) and differs only in investigation mode; it reads through the
sealed tool layer, tags assembly reads `context_assembly`, and HARD-FAILS rather than diagnose on
a budget-truncated view. **Probe agents:** `oracle_agent`/`degenerate_agent` are TRUSTED (read
`hidden/` directly) — `run_trial` refuses them without `allow_trusted`, and aggregation excludes
their `trusted:true` records; `always_broken_agent` (untrusted, tool layer only) is the
"diff-the-config" floor caught by the controls. Stub agents remain the zero-cost pipeline smoke.

## 13. Case validator (as-built) — new subsystem

`harness/validate_case.py` runs **20 invariants** on any case (or all), replacing manual review at
scale. **WALL** (W1 no hidden token in the workspace incl. control/healthy; W2 public card free of
incident info; W3 hidden seeds disjoint; **W4 the FORMATTED hidden values appear nowhere agent-
visible**, reported by file+offset). **CONSISTENCY** (C1–C3 identity/registry; C4 tolerance from
stats; C5 faulty-value below tolerance — tier-aware, inverted for control; C6 deep mutation check;
C7 index matches record; C8 recovery files linked; **C9 public reference band == stats**; **C10
(INFO) superseded trials**; **C11 effect-size labels agree with stats**). **WELL-FORMEDNESS** (F1
required files; F2 hidden-card fields — control may have empty mutations; F3 verify fields incl.
oracle_repair; F4 accepted_classes; F5 checkpoint matches tier; **F6 control shape**). Every check
ships a **planted-violation test** that injects the fault and asserts the check catches+names it —
no planted test, no check. The known-answer gate and audit-index (§17) sit above this.

## 14. Development posture and AWS (as-built) — from v0.1 §13

Built with `uv` (locked deps, `uv run`), a `CLAUDE.md` encoding integrity rules for coding
sessions, and the developer/evaluated-agent separation (an evaluated agent is only ever invoked
through `run_agent.py` against the public card; developer sessions may see everything). Real AWS is
Phase II only — a small real-SageMaker validation appendix demonstrating transfer of the
SageMaker-convention cases to genuine cloud faults (IAM, quota, OOM), never the reproducible v1
core.

## 15. What changed from v0.2 (summary)

- **data_leakage** (flagship positive-symptom fault) + `datautil.py` nested-selection helper;
  **control tier** (`control.healthy.v1`) with tier-aware scoring (`no_unnecessary_repair`, false
  intervention, control FPR) and inverted build/validator guards.
- **`oracle_repair()`** required on every operator; **content-derived `case_build_id`** +
  superseded-trial detection; validator grew to 20 checks (**W4**, **C9–C11**, **F4–F6**).
- Two **experiment agents**: the ReAct agent gained a `max_tokens` continuation and an `anchor`
  flag; the **static full-context baseline** (H6 control) was added, sharing prompt text verbatim.
- **Trusted probe agents** (oracle/degenerate) + the `run_trial` guard + aggregate exclusion; the
  untrusted `always_broken` baseline.
- **Schema 1.1** pre-sweep capture (prompt block, conditions, termination_reason enum,
  api_model/latency, confidence/rationale, symptom_direction + σ-distances) + required index columns.
- The two **validation gates** (§17) and the **sweep orchestrator** (§16) — the pre-registration,
  cost-cap, resume, and reporting layer.
- Calibration discipline formalized: a strength is valid only if it fails/crashes on ALL
  calibration seeds by ≥2σ margin.

## 16. Sweep orchestration (as-built) — new subsystem

`harness/sweep.py` turns `HYPOTHESES.md`'s design into an auditable run. **`plan`** enumerates the
design (operators × strengths × seeds + controls) × (agent × anchor × repeat) into a **committed**
`sweeps/<name>_plan.yaml` (seeded cell order; conservative max-observed cost fallback with a
measured-vs-fallback split; MISSING → nonzero; `--build-missing` generates absent cases). The
committed plan is the executable pre-registration. **`run --phase agents`** is the paid phase: it
REFUSES unless the known-answer gate is green, audit-index has no FAIL, validate-all is green,
every planned case's `case_build_id` matches the plan, the plan is git-clean, and the API key is
set; it is resumable (a crash costs one trial), stops before a hard **`--max-cost-usd`**, and stops
on a **circuit breaker** (`--max-consecutive-failures`) if a systemic failure appears. Diagnosis is
scored inline; recovery is not run. **`run --phase verify`** is the free CPU phase afterwards
(recovery reruns on non-control submitted trials, recording CPU-core-hours / wall / peak memory).
**`report`** aggregates per (operator, agent, anchor) and computes the H1–H6 metrics + control
rates → `docs/audits/sweep_<name>_<date>.md`. `harness/sweep_manifest.py` writes the tracked
compute-statement manifest (hardware captured once + per-phase totals; `actual_spend_usd` entered
manually). Agent/trial/cost are injectable, so the orchestration is tested on stubs at zero cost.

## 17. Validation gates (as-built) — new subsystem

The pre-sweep safety net: free checks that catch bug *classes* before a paid sweep grades against
a broken ground truth. **`harness/gate_known_answer.py`** (`make gate-known-answer`) runs an oracle
(evidence+class from the OPERATOR, repair from the verify FILE, so it can't mirror a corrupted
file), a degenerate, and an always-broken agent over every case and asserts what MUST hold — the
oracle exactly correct, the degenerate strictly out-scored on identification+evidence, the controls
catching the always-broken agent. Any oracle deviation means ground truth is wrong for that case;
the table names it. **`harness/audit_index.py`** (`make audit-index`) flags impossible score
combinations (recovered-not-detected, no-submission-yet-scored, control-patch-no-intervention,
cost≠tokens×price, …) as FAIL and reporting conditions (superseded trials, out-of-range confidence)
as INFO; `assert_clean_for_aggregation` refuses to aggregate over a FAIL-dirty index. Both write
dated tables to `docs/audits/`, exit nonzero only on FAIL, and every check has a planted-violation
test. First run: known-answer 189 checks 0 FAIL, audit 0 FAIL.
