# TrainMD — Codebase Walkthrough (Plain English), v3

A guide for reviewing the whole project line by line. It assumes no prior
knowledge of the code. Read it top to bottom: the order follows how data and
control actually flow through the system.

**Frozen at commit `75b6e2d`** (the pre-sweep state: everything built, gates green,
no paid sweep run yet). This walkthrough describes the code as it exists at that commit.

**Companion docs:** `ARCHITECTURE.md` (the same flow as diagrams), `DECISIONS.md`
(dated record of every design choice), `problem_statement_v0.3.md` (the research
framing), `harness_spec_v0.3.md` (the as-built spec), `PROVENANCE.md`
(the trial-record schema, v1.1), `HYPOTHESES.md` (the pre-registered sweep design),
`RESEARCH_LOG.md` (the story behind the decisions).

**What changed since v1:** the tool layer, the LLM agent + model clients, the
evaluator's repair-validation and verification pipeline, four-axis scoring, the
provenance/record system, pricing, the case validator, the idempotency and index
fixes, and section 12 (the output files).

**What changed since v2 (this version):** the **crash tier** (`shape_mismatch`) and
the two remaining silent operators (`label_corruption`, `data_leakage`) with their
`datautil.py` nested-selection helper; **content-derived build IDs** + superseded-trial
detection; validator checks **C7–C11** and **W4**; the **control tier** (healthy runs,
`no_unnecessary_repair` / false intervention); `oracle_repair()` on every operator; the
**trusted probe agents** (oracle, degenerate) + the run guard + aggregate exclusion, and
the untrusted `always_broken` baseline; the two **validation gates** (known-answer +
audit-index, §17); the **static-context baseline agent** (the H6 control, §9); **schema
1.1** capture fields; and the **sweep runner** (`plan`/`run`/`report`, §18).

---

## Table of contents

1. What this project is, in one page
2. The concepts (glossary)
3. The big picture: how one benchmark run flows
4. Layer 1 — The workload
5. Layer 2 — The reference
6. Layer 3 — The operators (four faults + the control tier)
7. Layer 4 — The case builder
8. Layer 5 — The tool layer
9. Layer 6 — The agents and model clients (ReAct, static, trusted probes)
10. Layer 7 — The evaluator
11. Layer 8 — Scoring
12. Layer 9 — Provenance, the runner, and the output files
13. Layer 10 — The case validator
14. The tests
15. The Makefile: what each command does
16. Suggested review order
17. The validation gates (known-answer + audit-index)
18. The sweep runner (plan / run / report)

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
legal repair may change; `repair_type` is now one of `config_patch`/`code_patch`/
`data_fix`/`none`, and it carries `value_ranges` **and** `allowed_values` for discrete/
boolean repairs). The `layer` field is now one of **`dynamics`** (silent), **`execution`**
(crash), or **`control`** (healthy). Every operator implements `apply()` (do the break),
`evidence()` (where the proof is), `admissible_repairs()` (legal fixes), `accepted_classes()`
(the set of labels that correctly name it), and **`oracle_repair()`** — the known-good fix
that restores the reference (a `{repair_type, patches}` dict; `None` for a control). The
known-answer gate and the recovery oracle both lean on `oracle_repair()`.

### `operators/silent/lr_warmup.py` — the first concrete fault
Injects a too-high learning rate at three calibrated strengths (mild/moderate/severe) that
all *complete* but produce a quietly bad model. `evidence()` enumerates **the complete set**
the fault corrupts: `training.lr`, `train_loss` (full run), `metric_visible_val_acc` (full
run). `admissible_repairs()` caps lr below the faulty value, so "change nothing" is never
legal. `oracle_repair()` → `{training.lr: 0.01}`.
*Per-operator discipline (DECISIONS): each operator's evidence enumerates every artifact the
fault observably corrupts — the MINIMAL sufficient set (root cause + symptom), reviewed once.*

### `operators/silent/label_corruption.py` — the subtle silent fault
Flips a fraction of training labels via the config knob `data.label_noise_fraction`. Because
Adult is robust to label noise, the operator SATURATES: the ladder is 0.33/0.38/0.42 (an
earlier 0.15/0.25/0.35 left mild AND moderate inside the noise band). Evidence: the config
key + `train_loss` (inflated) + `metric_visible_val_acc` (depressed). `oracle_repair()` →
`{data.label_noise_fraction: 0.0}`. Which labels flip is deterministic from the DATA (not the
training seed) so the evaluator's hidden-seed reruns see the identical corrupted set.

### `operators/crash/shape_mismatch.py` — the execution (crash) tier
`layer="execution"`. Sets `model.input_dim` to a wrong value so `nn.Linear` raises at the
first batch — the run FAILS (no checkpoint). Recovery is binary: only the exact correct value
(105) completes; any other in-range value crashes. Evidence is a **`line_range`** on
`logs/stdout.log` (the traceback), not a metric window. Build-time guard is INVERTED for this
tier: a crash operator whose run *completes* is rejected. `oracle_repair()` → `{model.input_dim: 105}`.

### `operators/silent/data_leakage.py` — the flagship (positive-symptom) fault
The hard one: visible val-acc goes UP while hidden test-acc goes DOWN. It adds a
label-correlated auxiliary feature column (`|y − Bernoulli(p)|`) via **innocuously-named**
config keys (`data.include_aux_feature`, `data.aux_feature_strength`) — the keys avoid the W1
isolation tokens, so an agent must read the code, not the naming, to find the leak. The aux
column is computed **per split** in `train.py`; at hidden-test time the evaluator substitutes a
pure `Bernoulli(0.5)` noise column (no label), so the leaked signal vanishes and accuracy
collapses. Evidence cites BOTH mutated config keys (an operator's mutated keys are always
evidence) + the inflated visible metric. `oracle_repair()` → `{data.include_aux_feature: False}`.

### `workloads/tabular_adult/datautil.py` — the nested-selection helper
`nested_prefix_indices(n, fraction)` returns a deterministic PREFIX of one data-derived
permutation (seeded by item-count via SHA-256, never `hash()`), so a larger fraction is a
strict SUPERSET of a smaller one — difficulty is monotone in `fraction` BY CONSTRUCTION, with
no empirical jitter. It lives as a **workload file** (not under `harness/`) because the sealed
`train.py` runs as a standalone subprocess and cannot import `harness`; it is copied verbatim
into every workspace and its name is innocuous (it sits in the agent-visible workspace, so it
must trip no isolation token). A byte-identical-copy test guards it. `train.py` uses it for the
label flip; future data operators (tiny_subset, class_imbalance) will reuse it.

### `operators/control/healthy.py` — the control tier
`control.healthy.v1`, `layer="control"`. A genuinely NON-faulty run: `apply()` is a no-op
(empty mutations), `evidence()` is `[]`, `admissible_repairs()` allows no repair
(`repair_type="none"`), `oracle_repair()` is `None`, and `accepted_classes()` = {none, healthy,
no_incident, no_fault, nothing_wrong}. It measures FALSE-POSITIVE behaviour: a submitted repair
or evidence on a healthy run is a scored false intervention. The build-time guard is INVERTED
(a control must CLEAR tolerance — a genuinely healthy run). Isolation: its public card is
shape-identical to a faulty case (W1/W2 forbid "control"/"healthy" in the workspace and card).

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
5. **Tier-aware build-time guard** — silent: completed + finite + scored BELOW tolerance;
   crash: must FAIL (non-zero exit, no checkpoint); control: completed + finite + CLEARS
   tolerance (inverted). Operators may add a `build_guard_checks()` hook (data_leakage uses
   it to insist the misleading symptom is real — val-acc above the mean+2σ upper band).
6. Writes the **public card** (opaque ID, workload family, allowed tools, budget, and the
   healthy-run **reference band** for the visible metric — nothing about the fault) and the
   **hidden** files (`card.hidden.yaml`, `evidence.yaml`, `verify.yaml` with the `oracle_repair`).

**Content-derived build IDs (supersession).** Each build computes a `case_build_id` =
SHA-256 over the canonical hidden content (operator, strength, seed, mutations) + the workload
source hashes (train.py, config.yaml, datautil.py), written into BOTH cards. It is
content-derived, not a UUID: a no-op rebuild yields the SAME id (so it strands nothing), while
a material change (a re-ladder, a code edit) yields a new id. Trials record the id they ran
against; when a case is rebuilt, prior trials become "superseded" and are flagged (validator
C10, audit R9) so analysis filters them in one line.

**Effect-size labels (the H1/H2 x-axis).** The hidden card also stores `faulty_visible_value`
(the faulty run's final visible val-acc), `visible_sigma_distance` and `hidden_sigma_distance`
(distance from the reference mean in units of σ), and `symptom_direction` ∈ {negative, positive,
within_band, crash, none} — measured against the healthy BAND (a value inside the band is
INVISIBLE, the floor H2 measures). data_leakage is the only `positive`. These are unrecoverable
after a paid sweep, so they are captured at build time and checked by validator C11.

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
- **max_tokens continuation**: a response cut off mid-thought (`stop_reason=max_tokens`)
  with no tool call is treated as a CONTINUATION, not the end — the agent prompts it to
  continue (capped at 3), so a verbose model isn't silenced by the plumbing.
- **Healthy-run guidance**: the prompt states some runs are healthy and the correct answer
  then is detected=false, class "none", no evidence, no repair.
- **The `anchor` flag**: `anchor="off"` omits the numeric reference-band line from the prompt
  (the H1/H6 sweep factor); `prompt_version` records the condition (`react-1` / `react-1-noanchor`).
- **Shared prompt pieces**: `HEALTHY_RUNS_TEXT`, `SUBMIT_FORMAT_TEXT`, `SUBMIT_SCHEMA`,
  `build_case_info`, `reference_band_line` are exported so the static agent reuses them VERBATIM
  (they are literal slices of the one template — drift is impossible).

### `agents/static_agent.py` — the static full-context baseline (the H6 control)
The control condition for tool-mediated investigation: it assembles the ENTIRE run (config,
resolved config, train.py, datautil.py, end-of-epoch metrics, stdout.log) into one prompt and
makes ONE LLM call, versus the ReAct loop. It shares system-prompt text, submit schema,
reference band, and healthy-runs guidance verbatim and differs ONLY in investigation mode, so a
score gap is attributable to tools, not wording. It reads every artifact through the SEALED tool
layer (never the filesystem); the assembly reads are tagged `phase="context_assembly"` and
counted so they can be netted out. **Hard fail on partial context**: if an assembly read is
refused for budget, it aborts with no model call — it never diagnoses on a truncated view. Log
cap 20 000 chars (head+tail marked). One bounded no-submit follow-up, then no submission.

### `agents/oracle_agent.py` / `degenerate_agent.py` / `always_broken_agent.py` — probes
Harness-only baselines. `OracleAgent` and `DegenerateAgent` are **trusted** — they read
`hidden/` DIRECTLY (not via the sealed tools): the oracle submits the exactly-correct answer;
the degenerate submits the oracle repair (so it recovers by construction) but the wrong class
and no evidence (the discrimination probe). `AlwaysBrokenAgent` is NOT trusted (tool layer only):
it detects on every case and resets every non-default knob it can read — the "how far does
blindly diffing the config get you?" floor, caught by the controls. `run_trial` REFUSES to run a
trusted agent without `allow_trusted=True`; their records carry `trusted: true`; `aggregate_scores`
excludes them and prints how many. (`stub_degenerate` remains a simple pipeline smoke stub;
`degenerate_agent` is the generic gate probe.)

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

**Tier-aware scoring.** Detection reads the tier: on a **control**, the correct `detected` is
false, so flagging a healthy run is a detection false positive. Evidence: when ground truth is
empty (a control), F1 = 1.0 iff the agent submitted no refs, else 0.0 (a ref on a non-fault is a
false positive). Recovery on a control is NOT `verify_repair` — it is `no_unnecessary_repair`
(correct iff no patches were submitted); a submitted repair sets `false_intervention=true`.
`aggregate_scores` computes `recovery_rate` over non-control trials only and adds
`detection_false_positive_rate_on_controls` and `false_intervention_rate` as first-class
numbers, and **excludes `trusted` records** (printing how many). `confidence`/`rationale` on a
submission are stored raw but ignored by scoring (calibration later).

---

## 12. Layer 9 — Provenance, the runner, and the output files

**Files: `harness/provenance.py`, `harness/run_agent.py`; outputs under `results/`**

### `harness/provenance.py` — the trial record + the index
Defines the versioned **trial record** (now **schema 1.1**) and the helpers that build, fill,
write, and index it. `capture_environment` records the exact code commit (plus a `git_dirty`
flag), a hash of the case card, the **`case_build_id`** (for supersession), Python/platform, the
lockfile hash, timestamp, wall-clock. `mark_card_superseded` sets a `card_superseded` flag by
comparing the trial's recorded build id to the case's current one. `update_index` keeps
`results/index.jsonl` in sync on **every (re)score** (the record is the source of truth; the
index is a derived view), rewriting by `run_id`. The index now carries the required condition
columns `termination_reason`, `agent_type`, `anchor`, `repeat_index`, `symptom_direction` so
analysis groups by condition without opening every record.

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
    `evidence_refs`, `repair_spec`, and (schema 1.1) optional `confidence` + `rationale`.
  - `tool_transcript` — every tool call in order (each tagged with its `phase`).
  - `llm_transcript` — every turn (schema 1.1 adds `api_model` and `latency_sec` per turn).
  - `scores` — the four axes + safety, embedded. Recovery is filled by the separate verify step.
  - `budget` — tool calls used vs. allowed.
  - **Schema 1.1 capture blocks** (unrecoverable after a paid sweep, so captured now):
    `prompt` (full system-prompt text + its sha256 + `prompt_version`, drift-guarded);
    `conditions` (sweep_name, agent_type, anchor, repeat_index); `termination_reason` ∈
    {submitted, ended_without_submit, max_turns, continuation_capped, token_budget_stop,
    assembly_failed, no_submit_after_followup, crashed} — which distinguishes the MODEL's
    choice from the HARNESS stopping it; `symptom_direction` (copied from the hidden card);
    and `static_context` for static-agent trials (context_tokens_sent, truncation,
    assembly_tool_calls).
- **`results/index.jsonl`** — one JSON line per trial: identity, the four score summaries,
  tokens, cost, commit, status, plus the required condition columns above.
- **`results/<case_id>/recovery_<trial_run_id>.yaml`** — the recovery verdict for a
  trial: verdict, per-seed hidden metrics, compute time, integrity hashes, and the
  `trial_run_id` linking it to its trial (so no orphans, and re-verify overwrites).
- **`sweeps/<name>_plan.yaml`** (TRACKED) — the pre-registered cell list + cost estimate; the
  executable pre-registration. **`sweeps/<name>_manifest.yaml`** (TRACKED) — the compute
  statement (hardware once + per-phase totals). **`sweeps/<name>_progress.jsonl`** — the
  resume log for the paid phase.
- **`docs/audits/<gate>_<date>.md`** (TRACKED) — the known-answer, index, and sweep audit
  tables.

*Not committed:* `results/` and `cases/` are gitignored (raw outputs / answer-key material).
`sweeps/`, `docs/audits/`, and the docs are tracked — they are the paper's evidence trail.

---

## 13. Layer 10 — The case validator

### `harness/validate_case.py`
Runs structural/consistency invariants on any case (or all), so cases are never
hand-reviewed — currently **20 checks per case**. Groups:
- **WALL** — W1 no hidden token in the visible workspace (incl. dynamic operator-id tokens
  and "control"/"healthy"); W2 public card carries no incident info; W3 hidden eval seeds
  disjoint from reference seeds; **W4 the FORMATTED hidden values** (faulty_value,
  tolerance_lower, hidden mean/std, the exact seed-list literal) appear nowhere agent-visible
  — reported with file + byte offset (not bare integers, which false-positive on step counts).
- **CONSISTENCY** — C1 case_id matches across files; C2 workload name; C3 registry unique;
  C4 tolerance recomputed from stats within epsilon; C5 faulty value below tolerance (INVERTED
  for control: must clear); C6 mutations in the resolved config (`--deep`); **C7 index matches
  the record**; **C8 recovery files linked to real trials**; **C9 the public reference band
  equals the reference stats**; **C10 (INFO) reports trials scored against a superseded build**;
  **C11 the effect-size labels agree with the stats** (sigma distances + symptom_direction).
- **WELL-FORMEDNESS** — F1 required files; F2 hidden-card fields (control may have empty
  mutations); **F3 verify.yaml fields (incl. oracle_repair, value_ranges OR allowed_values)**;
  **F4 accepted_classes present**; **F5 checkpoint presence matches tier**; **F6 control shape
  (empty evidence, no repair keys, null oracle_repair)**.
`validate_all` also checks no two cases share the same tuple. Exit nonzero on any FAIL (INFO
checks never fail); this replaces manual review and scales to any number of cases.
*Every check ships a companion PLANTED-VIOLATION test that injects the fault and asserts the
check catches and names it — a check with no planted test is not accepted.*

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
- `test_validate_case.py` — every validator check (incl. W4, C9–C11, control tier) has a pass
  and a planted-fail case.
- `test_run_agent.py` — the runner produces a valid record and transcript.
- `test_operator_label_corruption.py` / `test_operator_data_leakage.py` /
  `test_operator_shape_mismatch.py` — clean passes, every strength fails/crashes with margin
  on all calibration seeds; nested-superset + cross-process determinism; the misleading symptom.
- `test_datautil` assertions + `test_operator_evidence.py` — mutated keys are always evidence,
  across the whole registry.
- `test_oracle_repair.py` — every operator's oracle_repair is admissible and not the faulty value.
- `test_control_healthy.py` / `test_control_scoring.py` — control operator shape + tier scoring.
- `test_trusted_agents.py` — the run guard refuses trusted agents; aggregation excludes them.
- `test_gate_known_answer.py` / `test_audit_index.py` — the gates catch planted ground-truth
  corruptions; a clean set is clean.
- `test_static_agent.py` — one call/one submit, sealed reads, budget hard-fail, verbatim
  shared prompt sections.
- `test_prompt_versioning.py` — the prompt-template drift guard; submit-schema parity.
- `test_supersession.py` — build_id both directions + C10.
- `test_sweep.py` / `test_sweep_manifest.py` — the orchestrator (enumerate/MISSING, cost
  fallback, resume, cost cap, circuit breaker, anchor=off, H-metrics) on stubs, zero cost.

---

## 15. The Makefile: what each command does

- `make data` — prepare the dataset (visible + hidden split, checksummed).
- `make reference` — run the workload 10x and write `reference/stats.yaml`.
- `make build-case` — build a case (idempotent; refuses duplicates).
- `make run-agent` — run an agent on a case (stub, or `--model` for LLM; `--agent-type`, `--anchor`).
- `make smoke` — one live LLM trial on the cheapest model (paid).
- `make score` — score a trial's diagnosis axes.
- `make verify` — run the recovery axis on a trial (retrains on hidden seeds).
- `make validate` / `make validate-all` — run the case validator on one / all cases.
- **`make gate-known-answer`** — the known-answer gate (fast; `FULL=1` for recovery reruns).
- **`make audit-index`** — the impossible-combination audit over `results/`.
- `make clean` — remove generated data/outputs.

The sweep runner is invoked directly: `python -m harness.sweep plan|run|report` (§18).

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
12. `harness/gate_known_answer.py` and `harness/audit_index.py` — the gates that certify
    ground truth before any paid run (§17).
13. `agents/static_agent.py` and the trusted probes — the H6 control + baselines (§9).
14. `harness/sweep.py` — the orchestrator that ties it all together (§18).
15. The matching test file after each, to see the property being protected.

Keep `DECISIONS.md` open throughout — nearly every "but why this way?" has a dated
answer there.

---

## 17. The validation gates (known-answer + audit-index)

These are the pre-sweep safety net: free, oracle/stub-driven checks that catch bug
*classes* before a paid sweep grades against a broken ground truth. Every check names its
vulnerability class and ships a planted-violation test.

### `harness/gate_known_answer.py` — `make gate-known-answer`
Runs three probe agents over EVERY case and asserts what MUST be true if ground truth is
right. The **oracle** (its evidence and class derived from the OPERATOR, its repair from the
verify FILE — so it can't mirror a corrupted file it is graded against) must be exactly
correct: detection ✓, identification ✓, evidence F1 == 1.0, and (full mode) recovery ==
recovered / no_unnecessary_repair. The **degenerate** must be strictly out-scored on
identification and evidence (and flagged a false intervention on controls). The
**always-broken** agent must score zero evidence and be caught by the controls (detection FPR
== 1.0). ANY oracle deviation means ground truth is wrong for that case — the table names it.
Output: a table (`case | operator | tier | agent | axis | expected | actual | status | reason`)
to `docs/audits/known_answer_<date>.md`; nonzero exit on any FAIL.

### `harness/audit_index.py` — `make audit-index`
A NAMED rule list over `results/index.jsonl` + records, each FAIL or INFO with a rationale:
recovered-but-not-detected, no-submission-yet-scored, crash-recovered-but-incomplete,
control-patch-with-no-intervention, detected-false-with-evidence, completed-LLM-with-zero-input-
tokens, cost≠tokens×price, and INFO rules (identified-not-detected, superseded-in-results,
recall-1.0-with-wrong-class, confidence-out-of-range). `assert_clean_for_aggregation` REFUSES to
aggregate over an index with FAIL violations unless forced — a broken index can't silently
produce a headline number. Output → `docs/audits/index_<date>.md`.

---

## 18. The sweep runner (plan / run / report)

### `harness/sweep.py`
The orchestrator that turns `HYPOTHESES.md`'s design into an auditable, resumable, cost-capped
run. Three subcommands:
- **`plan`** — enumerate the design (operators × strengths × seeds + controls) × (agent ×
  anchor × repeat) into a **committed** `sweeps/<name>_plan.yaml` (seeded random cell order);
  estimate cost per (operator, agent) from prior trials with a **conservative max-observed
  fallback** when a pair has no priors (and report the measured-vs-fallback split); flag any
  MISSING case (nonzero exit). `--build-missing` generates absent cases in one idempotent
  command. The committed plan is the executable pre-registration.
- **`run --phase agents`** — the PAID phase. REFUSES unless the known-answer gate is green,
  audit-index has no FAIL, validate-all is green, every planned case's `case_build_id` matches
  the plan (drift guard), the plan file is git-clean, and `ANTHROPIC_API_KEY` is set. Resumable
  via a progress file (a crash costs one trial); a hard **`--max-cost-usd`** stops before
  exceeding the cap; a **circuit breaker** (`--max-consecutive-failures`) stops a systemic
  failure instead of marching through all cells; retry-once-then-skip. Diagnosis scored inline;
  recovery NOT run here.
- **`run --phase verify`** — the FREE phase, afterwards: `score_recovery_standalone` on
  non-control submitted trials, recording CPU-core-hours / wall / peak memory (ru_maxrss
  normalized to MB). Never interleaved with the paid phase.
- **`report`** — aggregate per (operator, agent, anchor) + the explicit H1/H3/H4/H6 metrics +
  controls (FPR, false-intervention) → `docs/audits/sweep_<name>_<date>.md`.

`harness/sweep_manifest.py` writes the tracked `sweeps/<name>_manifest.yaml` — the paper's
compute statement: hardware identity captured once + per-phase token/cost/CPU totals;
`actual_spend_usd` is entered manually from the provider console at the end. Agent construction,
the trial function, cost, and the estimate are all injectable, so the whole orchestration is
tested on stubs at zero cost.
