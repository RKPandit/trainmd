# TrainMD — What We Built, Why It Took So Long, and What To Do Differently

A plain-English retrospective. Written for someone who has never seen this project, and for
future-us starting the next one. Every claim points at a file you can open.

---

## 1. What the project is, in four sentences

We deliberately break machine-learning training jobs in known ways, then test whether AI
agents can figure out what went wrong and fix it. Because *we* broke each job, we know the
right answer, so we can grade any agent fairly. The agent only sees what a real engineer
would see — logs, metrics, config, code — and never the answer key. A proposed fix only
counts if an independent, sealed checker re-runs the training and confirms the model
actually recovers.

**Where to look:** `docs/problem_statement_v0.3.md` (scope and research questions),
`docs/CURRENT_STATE.md` (what exists right now — the one page that is always true).

---

## 2. What we actually built

### The training job and the faults
- `workloads/tabular_adult/` — a small, deterministic neural network on census data. The
  "healthy patient."
- `operators/` — one file per fault. Each knows how to break the job, what evidence the
  fault leaves, and what a legal fix looks like:
  - `silent/lr_warmup.py` — learning rate too high (the job finishes, the model is bad)
  - `silent/label_corruption.py` — some training labels flipped
  - `silent/data_leakage.py` — a feature that secretly contains the answer, so the
    metrics look **great** while the real model is bad
  - `metric/metric_inflation.py` — the model is fine; the *reported number* is wrong
  - `crash/shape_mismatch.py` — the job crashes outright
  - `control/healthy.py` — nothing is wrong (the agent must say so)
- `operators/base.py` — the contract every fault follows.

### The exam machinery
- `harness/build_case.py` — packages one exam question: a broken job plus a sealed answer key.
- `harness/tools/tool_context.py` + `tools.py` — the only way an agent can look at anything.
  It counts every action and physically blocks access to the answer key.
- `agents/llm_agent.py` — the AI agent that investigates step by step.
- `agents/static_agent.py` — a control: same model, but shown everything at once instead.
- `harness/evaluator/verify_repair.py` — the sealed grader. Rebuilds a clean copy from
  trusted files, applies the proposed fix, retrains, and checks the result on data the agent
  never saw.
- `harness/scoring.py` — grades four things: did it notice, did it name it, did it cite the
  right evidence, did the fix work.
- `harness/sweep.py` — runs hundreds of trials as one pre-declared experiment, resumable,
  with a hard spending cap.

### The trust machinery (this is where most of the time went)
- `harness/validate_case.py` — ~20 automatic checks on every exam question.
- `harness/gate_known_answer.py` — runs a "perfect answer" agent over every case. If it
  doesn't score perfectly, our answer key is wrong.
- `harness/platform_guard.py`, `harness/thread_pins.py` — refuse to generate results on the
  wrong hardware or with settings that make numbers irreproducible.
- `scripts/check_current_state.py`, `check_scorer_versions.py`, `check_analysis_numbers.py`,
  `check_manifest_schema.py` — guards that fail the build when a document and the code
  disagree.
- `scripts/export_release.py` + `rebuild_tables.py` + `results_release/` — every number in
  every report can be recomputed by a stranger from committed data, with no access to us.
- `Dockerfile` + `.github/workflows/` — one command reproduces everything on a pinned Linux
  image.

A **comprehensive test suite** protects all of it (`tests/`). (An exact count is deliberately omitted: it changes every PR, so a committed number would rot; the case count IS guarded because it changes rarely and deliberately — CURRENT_STATE §f.)

---

## 3. Why it took so long — the honest answer

Not because the code was hard. Because **almost every assumption we made turned out to be
wrong, and each wrong assumption was invisible until something specific exposed it.**

Here is the actual pattern, which repeated a dozen times:

> We build something. All tests pass. We believe it works. Then we look at the *actual
> output* — or run one more case, or one more seed, or on one more machine — and discover
> the thing was quietly wrong the whole time.

The tests were never enough, because **tests only check what you thought to check.** Every
single serious problem was found by reading real output, not by a failing test.

### The hardest part
The hardest part was not writing the benchmark. It was **proving the benchmark measures what
we claim it measures.** That is a different and much harder job:

- Building a fault is a day. Proving the fault is *reliably* a fault on every seed, on every
  machine, is a week.
- Scoring an answer is easy. Proving the scorer isn't secretly rewarding the wrong thing
  takes an adversarial test for every rule.
- Getting a result is cheap ($12). Making that result *survive a skeptical reader* took an
  order of magnitude more effort than getting it.

---

## 4. The twelve things that went wrong (and what each taught us)

Each of these cost real time. Each is now prevented by a check.

| # | What happened | Root cause | The permanent fix |
|---|---|---|---|
| 1 | The "hidden" answer was printed into the agent's own log file | We named a field "hidden" and assumed that made it hidden | Structural separation: only `evaluator/evaluate_checkpoint.py` may read the test set (`tests/test_workspace_isolation.py`) |
| 2 | Same code, same seed, different results on different machines | Multi-threaded math adds numbers in different orders | `harness/thread_pins.py` — training *refuses to start* unless threading is pinned |
| 3 | A fault was a *different* fault on every run | Used Python's built-in `hash()`, which is randomized per process | `hashlib` everywhere; a test that runs two separate processes and compares (`tests/test_operator_label_corruption.py`) |
| 4 | Every model scored 0 on "naming the fault" | Our answer key listed exact strings; models wrote correct synonyms | Match on the fault's *concept*, defined in advance, not on observed model output (`harness/scoring.py`) |
| 5 | A model proposed the *better* fix and we scored it as no answer | Our repair format couldn't express "remove this setting" | `null` means "unset" (`harness/evaluator/repair_spec.py`) |
| 6 | 9.6% of answers were thrown away | The model put a valid answer in the wrong field | `harness/submission_repair.py` recovers it — and we report both rates, because the misplacement is itself a finding |
| 7 | 138 results said "the fix failed" when training never ran | The grader launched training without the thread settings and it aborted | `verify_error` is now a separate verdict from "the fix failed" (`harness/evaluator/verify_repair.py`) |
| 8 | Our headline number was inflated | We averaged an obvious fault with a subtle one and called it "the comparison" | Report per-fault, never pooled (`harness/sweep_stats.py`) |
| 9 | A "calibration problem" was really a threading bug | We diagnosed a difference before proving the measurement was stable | Reproduce twice on independent machines before believing any difference |
| 10 | Our citation list contained invented paper titles | AI-generated metadata was never checked by a human | `docs/CITATIONS.md` — every source human-verified, with the section a number comes from |
| 11 | Documents contradicted each other about basic facts | Too many documents, each a "current truth" | `docs/CURRENT_STATE.md` — one page, plus a guard that fails the build on drift |
| 12 | 25% of healthy runs were being silently discarded | The builder rejected healthy runs that looked slightly odd — exactly the hard cases | Keep them all, label them (`operators/control/healthy.py`, §5.1) |

---

## 5. The seven lessons worth carrying to the next project

**1. Read the output, not the summary.**
Every serious bug was found by opening an actual result file. Tests passed the whole time.
Budget time for reading raw output as a *scheduled activity*, not something you do when
suspicious.

**2. Turn every manual find into a machine check — then keep reading.**
Each of the twelve rows above became a test or a guard. That's why the same class never
came back. But the guards only catch what you already know; reading is how you find the
next class.

**3. Measure; don't assume.**
We were wrong about which metric would move, which direction it would move, where the
evidence would appear, and how strong a fault needed to be — four times, on four operators.
Now every fault is calibrated by running it before its answer key is written
(`scripts/calibrate_*.py`, `scripts/step0_*.py`).

**4. One seed is not evidence. One run is not a finding. Two machines agreeing is not "all
machines."**
Every time we generalized from a single observation, we were eventually wrong. The fixes:
30-seed reference distributions, multiple repeats, two independent machines, and stated
bounds instead of "it's stable."

**5. Write down what you expect *before* you run it.**
`docs/HYPOTHESES.md` is committed before each experiment. It is the only reason we could
report a *failed* prediction honestly instead of quietly reframing it as a success. A
benchmark paper with an honest refutation is more trustworthy than one where everything
worked.

**6. When a result matches what you predicted, that is the moment to check it hardest.**
Our worst near-miss: a measured change looked exactly like the bug we expected. Taking it
apart showed the real cause was something else entirely. A confirming result feels like
permission to stop looking. It isn't.

**7. Separate "is this wrong?" from "does this make me comfortable?"**
Late in the project we started asking, before building anything: *does a skeptical reader's
conclusion depend on this?* If the honest answer was "no, it just makes me feel better," it
got deferred with a written condition for reviving it (`docs/STAGE3_PLAN.md`, deferred
table). We should have adopted that rule months earlier.

---

## 6. What we would do differently from day one

1. **Pin the environment first.** Container, fixed threading, one canonical machine — before
   generating a single number. We retrofitted this and had to regenerate everything.
2. **Write the "one page of truth" on day one** and let every other document be a detailed
   record beneath it.
3. **Build the dumb baseline before the clever thing.** We are only now building the
   one-line rule that our AI agent has to beat. If it turns out to match the agent, that
   changes what the whole project is about — and we would have wanted to know in week one.
4. **Human-verify every citation as it is added**, never in a cleanup pass.
5. **Get an outside reader early.** Two independent reviews found more real problems in one
   pass each than we found in weeks. We were inside the project; some errors are only
   visible from outside.
6. **Decide up front what a failed result looks like**, and treat reaching it as success.

---

## 7. Where to look, by question

| If you want to know… | Open this |
|---|---|
| What is true right now | `docs/CURRENT_STATE.md` |
| Why a decision was made | `docs/DECISIONS.md` |
| What we learned, as a story | `docs/RESEARCH_LOG.md` |
| What we predicted before each experiment | `docs/HYPOTHESES.md` |
| What the results mean | `docs/FINDINGS.md` |
| What we do *not* claim | `docs/LIMITATIONS.md` |
| Whether a source really says that | `docs/CITATIONS.md` |
| How the system works | `docs/harness_spec_v0.3.md`, `docs/ARCHITECTURE.md` |
| A file-by-file tour | `docs/TrainMD_Codebase_Walkthrough.md` |
| The raw data behind every number | `results_release/` + `scripts/rebuild_tables.py` |
| What's next | `docs/STAGE3_PLAN.md` |

---

## 8. The one-paragraph version

We spent most of the time not on building a benchmark, but on proving it measures what we
say it measures — and nearly every hour of that was forced by a specific, discovered error,
not by perfectionism. Tests caught almost none of them; reading real output caught almost
all of them. The result is a benchmark where a stranger can verify every citation, regenerate
every number from committed data, re-run the certification themselves, and read a written
record of every mistake we made and how we fixed it. That is the actual deliverable. The
scientific findings sit on top of it — and they are only worth anything because of it.
