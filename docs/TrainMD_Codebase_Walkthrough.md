# TrainMD — Codebase Walkthrough (Plain English), v2

A guide for reviewing the whole project line by line. It assumes no prior
knowledge of the code. Read it top to bottom: the order follows how data and
control actually flow through the system.

**Companion docs:** `ARCHITECTURE.md` (the same flow as diagrams), `DECISIONS.md`
(dated record of every design choice), `problem_statement_v0.3.md` (the research
framing), `harness_spec_v0.1.md` (the spec the code implements), `PROVENANCE.md`
(the trial-record schema), `COMPARISON.md` (a reproducibility experiment).

**What changed since v1 of this walkthrough:** added the tool layer, the LLM agent
and its model clients, the evaluator's repair-validation and verification pipeline,
four-axis scoring, the provenance/record system, pricing, the case validator, the
idempotency and index-consistency fixes, and a new section (12) walking the actual
output files a run produces.

---

## Table of contents

1. What this project is, in one page
2. The concepts (glossary)
3. The big picture: how one benchmark run flows
4. Layer 1 — The workload
5. Layer 2 — The reference
6. Layer 3 — The operators
7. Layer 4 — The case builder
8. Layer 5 — The tool layer
9. Layer 6 — The agents and model clients
10. Layer 7 — The evaluator
11. Layer 8 — Scoring
12. Layer 9 — Provenance, the runner, and the output files
13. Layer 10 — The case validator
14. The tests
15. The Makefile: what each command does
16. Suggested review order

---

## 1. What this project is, in one page

TrainMD is **a benchmark** — an exam — for AI agents that debug machine-learning
training jobs. The thing we build and publish is the exam itself: training jobs we
deliberately broke in known ways, plus the machinery to test whether an agent can
(a) notice something is wrong, (b) say what is wrong, (c) point to the evidence, and
(d) propose a fix that actually works when the job is re-run.

Because *we* broke each job, we know the true cause and the true fix — that hidden
answer key is what lets us grade any agent fairly. No public dataset of broken
training runs with known causes exists, so **creating this dataset is the research
contribution.** The agents (including a real LLM agent) are *contestants* we run
through the exam. Everything is built so the expensive, unrepeatable parts (paid LLM
calls) are protected and never wasted, and so anyone can reproduce the numbers.

---

## 2. The concepts (glossary)

- **Workload** — a normal, correct training job (a small neural net on a dataset).
  The healthy patient.
- **Reference** — what "healthy" looks like, measured by running the correct job
  many times and recording the good-result range.
- **Operator** — code that injects *one* fault (e.g. learning rate too high). The
  disease. It records exactly what it changed (ground truth).
- **Incident** — the injected fault. **Crash** (job dies) or **silent** (job
  completes but is quietly bad). Silent is the hard, realistic focus.
- **Case** — one packaged exam question: a broken job plus what the agent may see,
  plus a sealed folder with the answer key.
- **Visible vs. hidden** — the agent sees code, config, logs, metrics; it never sees
  the test data, the true cause, the evidence key, or the pass thresholds. This wall
  makes the exam honest.
- **Recovery oracle** — the rule for "did the fix work?": apply the fix, re-run on
  hidden seeds, check the hidden score returns to the healthy range.
- **Agent** — a contestant. Stub agents (free, for testing) and the real LLM agent.
- **ReAct loop** — how the LLM agent works: think then act (call a tool) then see
  result, repeat, until it submits.
- **Tool** — a restricted action for investigating (read a log, query a metric).
  The only way the agent touches a case.
- **Trial** — one run of one agent on one case, with a full record.
- **Provenance** — the complete saved record of a trial (tokens, cost, code version,
  transcript, scores), for reproducibility and crash-safety.
- **Four axes** — how a trial is graded: detection, identification, evidence,
  recovery (plus a secondary safety count).

---

## 3. The big picture: how one benchmark run flows

```
 raw dataset (scikit-learn)
        |  data_prep.py -> VISIBLE (train/val) + HIDDEN (test)
        v
 a correct training job                     workloads/tabular_adult/train.py
        |  reference_run.py -> runs 10x to learn the "healthy" range
        v
 an OPERATOR breaks one copy                operators/silent/lr_warmup.py
        |  build_case.py -> packages a CASE (visible workspace + sealed key)
        v                                    (validate_case.py checks it)
 an AGENT investigates                      agents/llm_agent.py
        |  through the TOOL LAYER only       harness/tools/*
        |  the model is reached via          harness/llm/*
        |  and SUBMITS diagnosis + fix
        v
 SCORING grades 3 free axes inline          harness/scoring.py
        |  run_agent.py orchestrates + records via provenance.py
        v
 the EVALUATOR verifies the fix             harness/evaluator/verify_repair.py
        |  (reruns training on hidden seeds -- the recovery oracle)
        v
 everything saved as a trial record         results/... + index.jsonl
```

---

## 4. Layer 1 — The workload

**Folder: `workloads/tabular_adult/`**

### `data_prep.py` — where data comes from and how it's split
Downloads the "Adult" census-income dataset via **scikit-learn's OpenML fetcher**
(pinned to a fixed dataset version). Cleans it (one-hot encode, scale), then splits
with a fixed seed into: **train + validation** to the *visible* `.data/` folder; and
**test** to a *separate hidden* `.hidden_data/` folder the agent can never see. Writes
a SHA-256 **manifest** per side; the *visible* manifest never names the hidden files
(so even the test filename doesn't leak). This is the root of the visible/hidden wall.

### `train.py` — the training job itself
A deterministic PyTorch MLP trainer (fixed seeds, deterministic algorithms,
single-thread loading). Reads a config, trains, and writes: `metrics.jsonl`
(per-epoch train_loss + val_acc), `logs/stdout.log`, `config.resolved.yaml`,
`checkpoints/`, `exitcode`. It **never touches the hidden test set** and never writes
a "test" metric. It follows the **SageMaker container contract** (`/opt/ml/...`,
`SM_*` env vars) so a case looks like a real cloud job with no cloud involved.

---

## 5. Layer 2 — The reference

### `harness/reference_run.py`
Runs the *correct* workload 10x (10 seeds). For each, trains (visible metrics only),
then calls the evaluator to get the **hidden** test score. Records mean, std, min/max
into `reference/stats.yaml`, and derives the **tolerance band** (default mean minus
2*std) — the range a result must clear to count as healthy. This band is what the
recovery oracle later checks against.

### `scripts/verify_reference.py`
Compares two `stats.yaml` files, ignoring fields allowed to vary (time, memory). CI
uses it to prove a fresh run reproduces the committed reference — the automated
determinism check.

---

## 6. Layer 3 — The operators

**Folder: `operators/`**

### `operators/base.py` — the contract every fault follows
Defines the shared frozen dataclasses and the `IncidentOperator` interface:
`MutationRecord`/`Manifest` (exactly what changed — ground truth), `EvidenceRef`
(structural pointer to where the fault's evidence lives), `RepairSpecSchema` (what a
legal repair may change and in what range). Every operator implements `apply()` (do
the break), `evidence()` (where the proof is), `admissible_repairs()` (legal fixes).

### `operators/silent/lr_warmup.py` — the first concrete fault
Injects a too-high learning rate at three empirically-calibrated strengths
(mild/moderate/severe) that all *complete* but produce a quietly bad model. Its
`evidence()` enumerates **the complete set** of what the fault corrupts: the
`training.lr` config key, the `train_loss` series (full run), and the
`metric_visible_val_acc` series (full run). Its `admissible_repairs()` allows lr in a
range capped below the faulty value, so "change nothing" is never legal.
*Per-operator discipline (see DECISIONS): each operator's ground-truth evidence
enumerates every artifact/series the fault observably corrupts, reviewed once.*

---

## 7. Layer 4 — The case builder

### `harness/build_case.py`
Turns "workload + operator + strength + seed" into one **case**:
1. **Idempotency guard** — checks the hidden registry for an existing case with the
   same (workload, operator, strength, seed). If found, it **refuses** (or, with
   `--force`, rebuilds *in place* reusing the same case ID). A given tuple maps to
   exactly one case; it never silently duplicates.
2. Assigns an **opaque** ID (`case_0001`) so the folder name reveals nothing.
3. Copies only allowlisted workload files into `workspace/`, symlinks visible data.
4. Runs the operator to inject the fault; runs training once to produce artifacts.
5. **Build-time guard** — for a silent operator, insists the run completed with
   finite numbers and (via the evaluator) actually scored below tolerance; else the
   case is rejected.
6. Writes the **public card** (opaque ID, workload family, allowed tools, budget —
   nothing about the fault) and the **hidden** files (`card.hidden.yaml` with the
   true cause and workload identity, `evidence.yaml`, `verify.yaml`).

---

## 8. Layer 5 — The tool layer

**Folder: `harness/tools/`**

### `tools/tool_context.py` — the gatekeeper
Holds one agent's state on one case and enforces the rules per call: **budget**
(counts every call, refuses when exhausted), **path confinement** (resolves any
requested path and checks `is_relative_to(workspace_root)` — one structural check
that blocks `..`, absolute paths, and symlink escapes, so `hidden/` is physically
unreachable; no fragile string-matching), **transcript** (logs every call), and
**submission** (stores the final answer).

### `tools/tools.py` — the actual tools
`read_log` (paged), `query_metrics` (optionally aggregated/windowed), `read_config`,
`read_code` (paged), `list_files`, `submit` (once). `diff_config`/`run_training` are
deliberately deferred and return "not available." These are the only verbs an agent
has; every file access routes through the gatekeeper's path check.

---

## 9. Layer 6 — The agents and model clients

**Folders: `agents/`, `harness/llm/`**

### `agents/stub_agent.py` / `agents/stub_degenerate.py` — free test contestants
The **oracle** stub submits the correct answer; the **degenerate** stub submits a
deliberately bad one (detects something wrong, wrong class, no evidence, blind
guess repair). Used together, they prove scoring *discriminates* quality — the oracle
must out-score the degenerate on diagnosis while both recover. Zero API cost.

### `harness/llm/client.py` — the model interface + a fake model
Defines the provider-agnostic `LLMClient` interface (`complete()`), the response
shapes (text, tool calls, stop reason, token usage), and `FakeLLMClient`, which
replays scripted responses so the entire agent loop is testable for free.

### `agents/llm_agent.py` — the real ReAct agent
Builds a system prompt (task + exact tool signatures + submit schema) and runs the
loop: send conversation -> model returns tool calls -> execute each via the tool layer
-> append results -> repeat until `submit` or a turn/token cap. **Incremental usage
capture**: it adds each call's tokens to the trial record immediately, so a crash
never loses paid tokens. Malformed tool calls become error results (no crash); never
submitting still finalizes cleanly with no submission.

### `harness/llm/anthropic_client.py` — the real API connection
Implements `LLMClient` via the Anthropic SDK. Reads the key from `ANTHROPIC_API_KEY`
(never logged). Parses response blocks into our shapes. **Bounded retry**: up to 2
retries on transient errors (rate limit, 5xx, timeout, connection) with exponential
backoff; **no** retry on auth/400; a model-not-found error points to the model docs.

### `harness/pricing.py` — cost estimation
A small per-model price table (verified against Anthropic docs, flagged approximate)
and `estimate_cost`, which returns a `CostEstimate` with `is_estimate=True`. If a
cache price is unknown it falls back to full price — cost is never silently
undercounted.

---

## 10. Layer 7 — The evaluator

**Folder: `harness/evaluator/`**

### `evaluator/repair_spec.py` — validating the proposed fix
Parses and strictly validates a repair before anything runs: rejects unknown keys,
out-of-range values, non-numeric values, booleans, and non-finite (NaN/inf) values,
each with a machine-readable reason code. Catches illegal repairs *before* wasting
compute, and the reason codes feed the safety metric.

### `evaluator/verify_repair.py` — the recovery oracle
The heart of verification. Given a case and a validated repair: reads hidden
materials; takes the **workload identity from the hidden card only** (checked against
an allowlist, so a tampered public card can't redirect what runs); builds a **fresh**
workspace from the original source, replays the operator's mutation from the hidden
manifest, applies the fix on top (never trusting the agent's workspace); reruns
training on the **hidden seeds** and computes the hidden score; declares **recovered**
only if every seed completes and clears tolerance; hashes trusted inputs before/after
to prove nothing was modified; writes the result to `results/...` (never into
`hidden/`), naming it `recovery_<trial_run_id>.yaml` so re-verification overwrites in
place.

### `evaluator/evaluate_checkpoint.py` — the only reader of the hidden test set
Loads a checkpoint, loads the hidden test data, computes the hidden accuracy. The
single code path allowed to touch the hidden test set — concentrated here so the wall
is easy to audit.

---

## 11. Layer 8 — Scoring

### `harness/scoring.py`
Grades four axes plus safety:
1. **Detection** — did it notice an incident? (healthy controls included).
2. **Identification** — right fault class?
3. **Evidence** — precision/recall of submitted pointers vs. the hidden key, matched
   **mechanically**: `config_key` matches on key (normalized so source vs. resolved
   config count the same, but a non-config artifact is rejected); `metric_window`
   matches on series + interval overlap.
4. **Recovery** — did the fix work? (calls the evaluator).
- **Safety (secondary)** — count of rejected/forbidden actions.

**Cost split:** `score_diagnosis()` runs the three free, instant axes + safety inline;
`score_recovery` / `score_recovery_standalone` runs the expensive recovery axis
separately (it retrains) and merges the verdict back into the trial record and the
index. `aggregate_scores` averages across trials. This split means a paid trial is
graded on diagnosis the instant it returns, while recovery runs later, free,
restartable.

---

## 12. Layer 9 — Provenance, the runner, and the output files

**Files: `harness/provenance.py`, `harness/run_agent.py`; outputs under `results/`**

### `harness/provenance.py` — the trial record + the index
Defines the versioned **trial record** and the helpers that build, fill, write, and
index it. `capture_environment` records the exact code commit (plus a `git_dirty`
flag), a hash of the case card, Python/platform, the lockfile hash, timestamp,
wall-clock. `update_index` keeps `results/index.jsonl` — one line per trial — in sync
with the trial record on **every (re)score** (the trial record is the single source of
truth; the index is a derived view). `update_index` rewrites by `run_id`, so
re-scoring never leaves the index stale.

### `harness/run_agent.py` — the runner (crash-safety lives here)
Orchestrates one trial: capture environment -> build an empty record -> **write a
"partial" record to disk before the agent starts** (a crash checkpoint) -> run the
agent inside `try/finally`. Whatever happens, the `finally` scores the free diagnosis
axes, finalizes the record ("completed" or "crashed"), overwrites the partial, and
updates the index — *then* re-raises any crash. Provides the CLI (stub agent by name,
or a real LLM agent via `--model`) and prints the cost summary.

### The output files — what a run actually produces
For the worked example below, use the real `case_0001` Haiku run.

- **`results/<case_id>/trials/<agent>_<run_id>.yaml`** — the full trial record. Top-
  level: `schema_version`, `case_id`, `agent_name`, `run_id`, `status`. Then blocks:
  - `environment` — commit, `git_dirty`, hashes, python/platform, timestamp,
    wall-clock. (In the example, `git_dirty: true` flagged an uncommitted `.DS_Store`
    — exactly the honesty this field exists for.)
  - `model` — model_id, provider, temperature (others may be null until captured).
  - `usage` — llm_calls, input/output/cached tokens, total, estimated cost (with the
    estimate flag). Example: 9 calls, 52,801 in + 1,626 out, ~$0.061.
  - `submission` — the agent's answer: `diagnosis` (detected, operator_class),
    `evidence_refs` (list of structural pointers), `repair_spec` (the config patch).
  - `tool_transcript` — every tool call in order (what the agent did).
  - `llm_transcript` — every prompt/response turn (how it reasoned).
  - `scores` — the four axes + safety, embedded. Recovery is filled by the separate
    verify step. Example: detection ok, identification ok, evidence F1=1.0,
    recovery=recovered, safety clean.
  - `budget` — tool calls used vs. allowed.
- **`results/index.jsonl`** — one JSON line per trial: case_id, agent, run_id, model,
  the four score summaries, tokens, cost, commit, status. This is what you load into a
  dataframe to build the results table — never open every YAML.
- **`results/<case_id>/recovery_<trial_run_id>.yaml`** — the recovery verdict for a
  trial: verdict, per-seed hidden metrics, compute time, integrity hashes, and the
  `trial_run_id` linking it to its trial (so no orphans, and re-verify overwrites).

*Not committed:* `results/` is gitignored (raw outputs, bulky, and answer-key-adjacent
recovery data). Durable findings are captured in committed docs like `COMPARISON.md`.

---

## 13. Layer 10 — The case validator

### `harness/validate_case.py`
Runs structural/consistency invariants on any case (or all), so cases are never
hand-reviewed. Three groups: **WALL** (no hidden token in the visible workspace;
public card carries no incident info; hidden eval seeds disjoint from reference
seeds), **CONSISTENCY** (case_id matches across files; workload name consistent;
registry entry unique; tolerance recomputed from reference stats within epsilon;
faulty value below tolerance; mutations present in the resolved config with `--deep`;
**index matches the trial record**; **recovery files linked to real trials**), and
**WELL-FORMEDNESS** (required files exist; hidden card and verify.yaml have required
fields). `validate_all` also checks no two cases share the same tuple. Exit nonzero on
any failure — this replaces manual review and scales to any number of cases.

---

## 14. The tests

**Folder: `tests/`** — fast and free (real training only in a few marked slow tests).
Each guards a property:
- `test_workspace_isolation.py` — the wall holds; missing artifacts **fail** (can't
  be silently skipped).
- `test_operator_lr_warmup.py` — clean passes, every broken strength completes but
  fails; evidence covers both metric series.
- `test_build_case_idempotent.py` — refuse duplicate tuple without `--force`, reuse ID
  with `--force`, new tuple gets next ID.
- `test_tools.py` — paging, budgets, path traversal / symlink / hidden all rejected;
  a legitimately-named file is allowed.
- `test_llm_agent.py` — the ReAct loop on the fake client: happy path, never-submits,
  malformed call, crash preserves tokens, budget cap.
- `test_verify_repair.py` — oracle fix recovers; tampered public card has no effect;
  illegal/NaN/bool repairs rejected with zero reruns.
- `test_scoring.py` — evidence matching correct; oracle stub out-scores degenerate
  while both recover (discrimination).
- `test_provenance.py` — records conform, capture git state, compute cost, append
  index, flush a partial record on crash.
- `test_provenance_consistency.py` — index insert/rewrite/preserve; index stays
  synced after re-score; recovery overwrites idempotently.
- `test_validate_case.py` — every validator check has a pass and a fail case.
- `test_run_agent.py` — the runner produces a valid record and transcript.

---

## 15. The Makefile: what each command does

- `make data` — prepare the dataset (visible + hidden split, checksummed).
- `make reference` — run the workload 10x and write `reference/stats.yaml`.
- `make build-case` — build a case (idempotent; refuses duplicates).
- `make run-agent` — run an agent on a case (stub, or `--model` for LLM).
- `make smoke` — one live LLM trial on the cheapest model (paid).
- `make score` — score a trial's diagnosis axes.
- `make verify` — run the recovery axis on a trial (retrains on hidden seeds).
- `make validate` / `make validate-all` — run the case validator on one / all cases.
- `make clean` — remove generated data/outputs.

---

## 16. Suggested review order

1. `workloads/tabular_adult/data_prep.py` — the visible/hidden split (root of all).
2. `workloads/tabular_adult/train.py` — the job being investigated.
3. `harness/reference_run.py` — how "healthy" is defined.
4. `operators/base.py` then `operators/silent/lr_warmup.py` — fault + ground truth.
5. `harness/build_case.py` — how an exam question is packaged (central; spend time).
6. `harness/tools/tool_context.py` then `tools/tools.py` — the sealed interface +
   the path-confinement check (agent-side security core).
7. `harness/evaluator/repair_spec.py`, `verify_repair.py`, `evaluate_checkpoint.py` —
   the sealed grader and recovery oracle (verification-side security core; spend time
   on `verify_repair.py`).
8. `harness/scoring.py` — four axes + the cost split.
9. `harness/llm/client.py`, `agents/llm_agent.py`, `harness/llm/anthropic_client.py` —
   the contestant and its API connection.
10. `harness/provenance.py` and `harness/run_agent.py` — how a trial is recorded and
    made crash-safe. Then read a real trial YAML under `results/` (section 12).
11. `harness/validate_case.py` — the invariants that replace manual review.
12. The matching test file after each, to see the property being protected.

Keep `DECISIONS.md` open throughout — nearly every "but why this way?" has a dated
answer there.
