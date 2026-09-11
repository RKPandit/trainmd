# G1 Hardening Gate — Detailed Plan

**Purpose:** the pre-sweep gate from HARDENING_PLAN.md. Everything here is free (no paid
trials), catches bug *classes* without knowing the instance, and produces *informative*
output that shortens debugging. Split into two batches, each its own Claude Code plan.

---

## The informative-test standard (applies to every item)

Encode this verbatim in every prompt; it is the requirement that cuts debugging effort.

1. **Name the vulnerability class** in the test/check name and docstring
   (e.g. `test_wall_path_escape_dotdot`, "guards: hidden dir reachable via traversal").
2. **On failure, print the finding, not just fail:** which case/trial, which axis or file,
   expected vs actual, and *why* (the rule that fired). A gate is a table, not a boolean.
3. **Prove every check is non-hollow:** for each gate/check, a companion test *plants a
   violation* and asserts the check catches it (the validator pattern). A check with no
   planted-violation test is not accepted.
4. **Parametrize over ALL operators / ALL cases** (from the registry / `cases/`), so a
   future operator cannot dodge a check.
5. **Severity:** `FAIL` for integrity/correctness; `INFO` for reporting (e.g. superseded
   trials, lenient-recovery notes). Gates exit nonzero only on FAIL.
6. **Persist the audit:** every gate writes a dated markdown table to
   `docs/audits/<gate>_<date>.md` — the record a reviewer can read.
7. **Fast + full modes:** any gate that retrains has `--fast` (no recovery reruns) and
   `--full` (with); CI runs fast on push, full nightly.

---

## Batch 1 — the silent-corruption class

### 1A. Operator protocol: `oracle_repair()` (foundation)
- Add to `IncidentOperator`: `oracle_repair() -> RepairSubmission-shaped dict` — the
  repair that restores the reference (lr→0.01; label_noise→absent/0.0; include_aux_feature
  →false; input_dim→105). Required; registry-coverage test asserts every operator defines it
  and that it is *admissible* under its own `admissible_repairs()` and *excludes* the faulty
  value.
- `build_case` writes it to `hidden/verify.yaml` as `oracle_repair` (hidden side only).
- Planted-violation test: an operator whose oracle_repair is inadmissible is rejected at
  registry validation.

### 1B. Healthy controls (foundation + a third tier)
**Design decisions (recommended; confirm):**
- Operator `control.healthy.v1`, `layer: "control"` (third value in the Literal). No
  mutation; `apply()` is a no-op returning an empty manifest; single strength.
- **Build guard (tier-aware, inverted):** must complete, finite, and hidden metric **≥
  tolerance_lower** (i.e. genuinely healthy). A control that fails tolerance is rejected.
- **Ground truth:** `accepted_classes = {none, healthy, no_incident, no_fault,
  nothing_wrong}`; `evidence = []`; `admissible_repairs` = *no repair* (empty allowed
  keys); `oracle_repair = None`.
- **Submit tool:** accept "no repair" explicitly — `repair_spec: null` **or**
  `{repair_type: "none", patches: {}}`. Document it in the schema/prompt.
- **Scoring on controls (per axis):** detection correct iff `detected == false`;
  identification correct iff class in accepted set; evidence: gt empty → F1 = 1.0 iff
  submitted refs empty, else 0.0 (citing evidence for a non-fault is a false positive);
  recovery → replaced by **`no_unnecessary_repair`**: correct iff no patches submitted. A
  submitted repair on a control is scored as a false intervention (recorded, counted).
- **Aggregation:** report detection **false-positive rate on controls** as a first-class
  number; report false-intervention rate.
- **Prompt (global change):** the system prompt states that *some runs are healthy* and
  that the correct submission then is `detected=false`, class `none`, no evidence, no
  repair. Do **not** disclose the base rate.
- **Isolation:** the public card of a control must be indistinguishable in shape from a
  faulty case (no field reveals "control"); W1/W2 scans extended with `control`, `healthy`.
- **Validator:** tier-aware for `control` (checkpoint required; faulty_value ≥ tolerance;
  evidence empty; no admissible keys). Registry tuple uniqueness applies.
- **Initial set:** seeds 0,1,2 → 3 controls now (≈20–25% of the case set later).
- **Planted-violation tests:** a control whose run falls below tolerance is rejected; a
  control card containing the word "control" fails W2; a submission with patches on a
  control scores `no_unnecessary_repair = false`.

### 1C. Generic oracle + degenerate + always-broken agents (test harness only)
- `agents/oracle_agent.py`: **trusted, harness-only** — constructed with `case_dir`, reads
  `hidden/` directly (never via the sealed tool layer), submits: detected per tier, first
  accepted class, *exactly* the hidden evidence refs, `oracle_repair` (or no repair for
  controls). Marked `is_trusted = True`; `run_agent` refuses to run it against any case
  unless `--allow-trusted` is passed, and it is never listed as a contestant.
- `agents/degenerate_agent.py` (generic): detected=true, class `"unrelated_fault"`, no
  evidence, oracle repair (blind-but-admissible) — the discrimination probe.
- `agents/always_broken_agent.py`: detected=true on every case, random accepted-looking
  class, no evidence, patches every non-default knob it can see back to a default guess.
- Tests: each satisfies the Agent protocol; the oracle is rejected by `run_agent` without
  the flag.

### 1D. Known-answer gate — `make gate-known-answer` (the centerpiece)
- Runs the **oracle over every case**; asserts per case: detection ✓, identification ✓,
  evidence **F1 == 1.0**, recovery (full mode) == recovered / no_unnecessary_repair ✓.
- Runs the **degenerate** over every case; asserts on every case: oracle strictly
  out-scores degenerate on identification and evidence; recovery behavior matches the
  operator's documented leniency (lenient: both recover; strict: degenerate may not).
- Runs **always-broken** over every case; asserts: detection FPR on controls == 1.0 (i.e.
  the controls catch it), evidence 0 everywhere.
- **Output:** a table `case | operator | tier | axis | expected | actual | status | reason`
  saved to `docs/audits/known_answer_<date>.md`; nonzero exit on any oracle deviation.
  Any oracle miss = **ground truth is wrong for that case** — the table names it.
- **Also folds in 0.3 oracle self-consistency (full mode):** per case, clean config →
  recovered; faulty config → not_recovered (silent) / did-not-complete (crash) / recovered
  (control); oracle_repair → recovered. Table.
- Planted-violation tests: corrupt one case's `evidence.yaml` → gate reports that case's
  evidence axis; corrupt a `verify.yaml` oracle_repair → gate reports recovery; a control
  whose accepted_classes lacks `none` → gate reports identification.

### 1E. Impossible-combination audit — `make audit-index`
- Script over `results/index.jsonl` + records with a **named rule list**, each with a
  rationale string. Rules (FAIL unless noted):
  - `recovered ∧ ¬detected` (fixed it without noticing)
  - `no_submission` with any non-null score axis
  - crash case: `recovered` but the repaired rerun did not complete
  - control: patches submitted ∧ `no_unnecessary_repair == true` (contradiction)
  - `detected == false` ∧ evidence refs non-empty
  - identification correct ∧ `detected == false` (named a fault but said none) — INFO
  - completed LLM trial with `input_tokens == 0`
  - `estimated_cost` ≠ tokens × price within 1% (when not `is_estimate`-null)
  - superseded trial present in an aggregate — INFO
  - evidence recall 1.0 ∧ identification wrong on an *easy* operator — INFO (review)
- **Output:** `rule | count | sample trial ids | rationale` → `docs/audits/index_<date>.md`.
- `aggregate_scores` refuses (or warns) to aggregate over an index with FAIL violations.
- Planted-violation tests: synthesize a record per rule and assert the rule fires — and
  that a clean index yields zero.

### 1F. Hidden-value scan — validator W4
- After build, scan every agent-visible byte (workspace files, public card, logs, resolved
  config) for the **formatted** hidden values: `faulty_value`, `tolerance_lower`, hidden
  mean/std (6-decimal string forms), and the exact hidden-seed list literal
  (`[100, 101, 102]` / `100, 101, 102`). **Not** bare integers (`100` false-positives on
  step counts). Report file + offset + which value.
- Planted-violation test: write `tolerance_lower`'s value into a log line → W4 fails and
  names the file/offset.

### 1G. Records
- DECISIONS.md: control tier semantics (no_unnecessary_repair); oracle_repair on the
  protocol; trusted-agent guard; the informative-test standard; W4.
- RESEARCH_LOG.md: entry for "known-answer at scale" and whatever the first gate run
  reveals (run the gate on the current 4 operators + 3 controls and *record the table* —
  the first run is itself a finding).
- README: `make gate-known-answer`, `make audit-index`.

---

## Batch 2 — the adversarial class

### 2A. Red-team the wall — `tests/test_redteam_wall.py`
Every attack is a test named for its class; each must be refused with a reason code and
must **not echo hidden content in the error message** (assert the error text contains no
hidden value/path):
- Path escapes via tools: `..`, absolute, `run_output/../../hidden/verify.yaml`, symlink
  planted inside the workspace pointing at `hidden/`, encoded (`%2e%2e`), null byte,
  unicode-normalization variants, case variants, overlong path.
- Reach other trials/results: `read_code("../../results/...")`, `list_files("**/results/**")`.
- Glob into hidden: `list_files("**/hidden/*")`, `list_files("../**")`.
- `read_log`/`read_config` with `artifact_id` pointing at `card.hidden.yaml` /
  `verify.yaml` / `evidence.yaml`.
- Submit-as-attack: patches on `verify`-adjacent or unknown keys; nested-dict values; a
  10k-key patch; `repair_type: code_patch` (unsupported → rejected); patches targeting the
  evaluator/hidden paths.
- Tamper every public artifact (card, config, train.py, datautil) and assert the recovery
  verdict is **unchanged** (trusted-source rebuild).
- **Error-echo audit:** for every rejection path, assert the message contains none of the
  hidden values/paths (generic message only).

### 2B. Cheating-agent baselines — reported, not just tested
- Run always-broken, repair-guesser (submits each case's most common admissible-looking
  repair without investigation), and **knob-scanner** (reads config, patches every
  non-default knob to a default guess) over all cases.
- Assert: always-broken FPR on controls = 1.0; evidence 0 for all three; knob-scanner's
  recovery rate is *reported* (it is a legitimate baseline for the paper — "how far does
  'diff the config' get you?").
- Output table → `docs/audits/cheating_baselines_<date>.md`.

### 2C. Determinism suite over all operators — `tests/test_determinism_all.py`
Parametrized over the registry: cross-process identical metrics; fault independent of
training seed (for operators declaring `has_internal_randomness`); rebuild byte-identical
excluding timing fields; nested-superset property for fractional operators.
Planted-violation test: an operator using Python `hash()` is caught.

### 2D. Records + audit run
Run the red-team suite and cheating baselines; record tables; DECISIONS + log entries.

---

## Confirm before prompting (your decisions)
1. Control recovery semantics = `no_unnecessary_repair` (a submitted repair on a control is a
   scored false intervention). **Recommended: yes.**
2. Agent is told healthy cases exist, not the base rate. **Recommended: yes.**
3. `oracle_repair()` becomes a required protocol method. **Recommended: yes.**
4. Two batches, two plan reviews. **Recommended: yes.**
5. Initial controls: 3 (seeds 0–2), scaled to ~20–25% at case-generation time.
