# TrainMD — Research Log

A running record of what was believed, what contradicted it, what was decided, and the
principle extracted. This is the *story* behind DECISIONS.md (which records only the
conclusions). Written in real time so it stays honest: retrospective accounts make every
decision look inevitable; this one keeps the not-knowing.

**Entry shape:** What I believed → What happened → What I decided (and the trade-off) →
The principle → Where it lives.

**How to maintain:** add an entry at the same moment you'd add a DECISIONS line. Five
minutes while the surprise is vivid beats an hour of reconstruction later.

---

## Part I — Origin (Aug 2026)

### 1. The pivot from memory research to a benchmark
**Believed:** The Hierarchical Graph Memory (HGM) idea was still a viable research talk.
**Happened:** A deep literature check found GAM — "Hierarchical Graph-based Agentic Memory" — published as an ACL 2026 long paper, essentially HGM's Topic→Thread→Event structure, atop a January 2026 wave (HiMem, TiMem, MAGMA, EverMemOS). The idea had been published while it sat idle.
**Decided:** Abandon HGM as a centerpiece. Chose a benchmark for LLM agents diagnosing ML training failures, building on my own Runix tool. Trade-off: a benchmark is less "novel architecture," more "rigorous instrument" — but it plays to my strengths (SageMaker, MLOps, claims-model debugging) and is achievable solo.
**Principle:** Presenting an idea in a crowded space you entered cold is the single worst impression in a science talk. Novelty must be verified, not assumed.
**Lives in:** problem_statement v0.1→v0.3, lit_review v1.0.

### 2. The claim got smaller, and that made the paper better
**Believed:** "First benchmark for ML training-failure diagnosis."
**Happened:** The kill-check found L4, DynFault, Deep4ge, AutoTrainer (diagnosis exists), MicroRemed/AIOpsLab/SREGym (verified remediation exists, in SRE), RFT-FaultBench (training-job remediation, RL-only, preliminary), and AgentHPO + the *autoresearch* study (agent-vs-HPO already compared; classical wins in a fixed space).
**Decided:** Narrow to a five-part combination — injected causal annotations + tool-mediated investigation + diagnosis scored separately from recovery + verified repair on hidden reruns + workload-held-out split. Reframe RQ5 as a neutral budget-curve comparison, no assumed winner. Trade-off: less grand, far more defensible.
**Principle:** Being contradicted by the literature and narrowing instead of abandoning is itself a slide in the talk. Interviewers trust a claim that shrank for good reasons more than one that only grew.
**Lives in:** lit_review v1.0 §2–§4, problem_statement v0.3 §2.

---

## Part II — Building the instrument (Sep 2026, weeks 1–2)

### 3. The hidden metric was not hidden
**Believed:** Naming a field `metric_hidden_test_acc` made it hidden.
**Happened:** The first code review found `train.py` computing test accuracy every epoch and writing it into `metrics.jsonl` and `stdout.log` — both agent-visible. The answer key was printed in the exam room. The naming split existed; the *architecture* didn't enforce it.
**Decided:** Workspace training never touches the test set. The hidden metric is computed only by a separate evaluator on saved checkpoints; test data lives in a *sibling* directory (not a subdirectory of the mounted data); even the visible manifest must not *name* the hidden files. Trade-off: a refactor of the evaluation boundary, plus seven isolation tests on every push.
**Principle:** Metadata leaks too — a manifest that lists `X_test.npy` leaks that a test set exists. Structure beats vigilance: the wall must hold even when someone is careless later.
**Lives in:** DECISIONS (evaluator-only hidden metric), tests/test_workspace_isolation.py.

### 4. Cross-platform floats are not noise you can ignore
**Believed:** A reference computed on macOS would reproduce on Linux CI.
**Happened:** CI failed: val_acc mean 0.855801 (Mac) vs 0.856848 (Linux). Different BLAS backends sum in different orders; twenty epochs amplify 1e-7 per step into ~0.001 — the *same order as seed-to-seed std* (0.0017). A tolerance band from Mac numbers would be measurably wrong for Linux verification.
**Decided:** Linux/CI is the canonical reference environment; macOS is a smoke-test platform. Committed snapshots are always CI-generated.
**Principle:** Cross-platform drift comparable to seed noise means the reference and the verification must share a platform. A reproducibility claim targets the shipped environment, not developer hardware.
**Lives in:** DECISIONS (canonical environment).

### 5. A verifier that has only ever said "yes" is unverified
**Believed:** The recovery oracle worked because the oracle repair recovered.
**Happened:** Every rejection test exercised the *validator*, not the rerun; nothing proved the evaluator could say "not recovered" to a well-formed repair. Worse, the empirical sweep found that for lr_warmup **every admissible learning rate recovers** — so recovery couldn't distinguish a correct diagnosis from a blind in-range guess.
**Decided:** Test the not-recovered path explicitly (via elevated tolerance); document lr_warmup as a deliberately *easy* recovery case; make RQ4/RQ5 depend on operators with large repair spaces where guessing can't recover. Trade-off: admitting the first operator's recovery axis carries little information.
**Principle:** A benchmark with an easy first operator is fine; a benchmark that doesn't *know* its first operator is easy is not. Reviewers respect limitations you name before they do.
**Lives in:** DECISIONS (sweep finding, worded to state the limitation plainly).

### 6. Trusted sources only — the security core
**Believed:** The evaluator could reuse the agent's workspace to verify a repair.
**Happened:** Reviewing `verify_repair.py`: workload identity came from the *public* card (agent-reachable), so a tampered card could redirect which code the sealed rerun executed. Also: NaN passed the range check (`v < lo or v > hi` is false for NaN), and `True` passed as numeric (bool subclasses int).
**Decided:** Rebuild a fresh workspace from trusted source + the hidden mutation manifest; take workload identity from the hidden card only, allowlisted, with no fallback (a fallback would reintroduce the hole); reject bool and non-finite explicitly; hash all trusted inputs before/after.
**Principle:** The wall is only as strong as the least-trusted input it consults. A security fix with a compatibility fallback isn't a security fix.
**Lives in:** DECISIONS (trusted workload identity; validator hardening).

### 7. The cost split — a durable checkpoint between two cost centers
**Believed:** Score everything inline when a trial returns.
**Happened:** Recovery scoring retrains on three hidden seeds. Fusing it with the paid LLM call would trigger ~3 training runs per trial and, worse, a crash in the cheap-but-slow half could destroy the record of the expensive-and-unrepeatable half.
**Decided:** Diagnosis axes (free, instant) scored inline; recovery scored as a separate restartable step from the saved submission. Trade-off: two steps for a complete record, but paid tokens are never at risk.
**Principle:** When two operations have different cost and repeatability, put a saved artifact between them.
**Lives in:** DECISIONS (scoring split), harness_spec v0.2 §8.

---

## Part III — The line-by-line audits (what tests could not see)

### 8. Reading the output caught five things 200+ green tests didn't
**Believed:** A green suite plus a validator meant the results were clean.
**Happened, across three audits of actual output files:** (a) `index.jsonl` still showed evidence F1=0.0 after a re-score produced 0.8 — the re-score persisted nowhere; (b) two duplicate recovery files for one trial, unlinked; (c) `git_dirty: true` from a *tracked* COMPARISON.md sitting inside gitignored `results/` — archiving the folder "deleted" it; (d) two orphaned recovery files from development-time oracle checks; (e) the C8 check meant to catch orphans globbed only `recovery_*.yaml` and was blind to them — case_0003 validated 16/16 while carrying two orphans.
**Decided:** Each finding became a permanent check: index synced on every re-score; recovery files named by trial and idempotent; standalone verify calls write nothing; C8 detects orphans by *content shape*, not filename. And the manual audit stays the practice while operators are new.
**Principle:** Tests check what you thought to test. Reading the artifact finds what you didn't. Convert each manual find into a machine check, then keep reading.
**Lives in:** DECISIONS (provenance consistency; C8 broadening); validate_case.py C7/C8.

### 9. Scores are stable under nondeterminism; cost is not
**Believed:** Two runs of the same case would be roughly identical.
**Happened:** Run-1 and Run-2 of Haiku on case_0001 took visibly different investigation paths (7 vs 9 LLM calls; Run-2 did targeted epoch-15–19 queries Run-1 didn't) — and produced **identical four-axis scores**, while cost varied ~50% (35K vs 54K tokens).
**Decided:** Report ≥3 repeats per cell; budget cost at the high end; note scores may be stable on clear-cut cases but harder operators may need more repeats.
**Principle:** Separate the reproducibility of *outcomes* from the reproducibility of *cost*. They are different claims.
**Lives in:** docs/COMPARISON.md.

---

## Part IV — Operators: each one exercised a path no test had touched

### 10. Measure the symptom; intuition was wrong three times
**Believed (lr_warmup):** Evidence lives in epochs 0–4 (the warm-up window). **Happened:** Haiku cited epochs 15–19 — the divergence zone — and was right. Ground truth was the narrow one.
**Believed (label_corruption):** Noisy labels would push train loss *down* (memorization). **Happened:** train_loss went **up 104%** — the dominant signal; val_acc only −1.9%.
**Believed (data_leakage):** val_acc "above the reference mean" proves inflation. **Happened:** Half of *healthy* runs sit above the mean. Inflation requires clearing mean+2σ.
**Decided:** Every operator's evidence set is finalized only after running it and reading the curves. Ground truth enumerates every series the fault observably corrupts, matched at fault granularity (config_key on key; metric_window by series + interval overlap) — the fault-localization convention.
**Principle:** "Measure, don't assume" — the symptom is often not what the mechanism suggests.
**Lives in:** DECISIONS (per-operator evidence review; evidence-matching convention; upper-band threshold).

### 11. The naming collision, and the hash that changed every process
**Happened (label_corruption):** (a) A config key `label_corruption_fraction` would have false-positived the W1 isolation scan against the operator id segment `label_corruption`; renamed to `label_noise_fraction` — the standard ML term anyway. (b) The corruption seed used Python's built-in `hash()`, which is salted per process, so *each evaluator subprocess flipped a different set of labels* — the "fault" was a different fault on every rerun. Invisible to the in-process test; caught by reading the line.
**Decided:** Fault randomness derives from `hashlib` on (data, strength) only — never the training seed — with a test that spawns *two separate subprocesses* and compares.
**Principle:** The fault must be a fixed, reproducible object, because the hidden-manifest replay model requires re-applying the *identical* fault. The training seed varies training; it must not vary the fault.
**Lives in:** DECISIONS (process-stable hashing).

### 12. Identification was silently unmatchable for every operator but one
**Happened:** Haiku diagnosed label_corruption correctly but named it `data_corruption`; identification scored *false*. Root cause: a hardcoded class map covered only lr_warmup; every other operator fell back to its raw id, which nothing would ever match. Then on shape_mismatch, three runs gave three different labels (`data_corruption`, `config_mismatch`, `data_shape_mismatch`) — one wrong, one vague, one arguably right.
**Decided:** Each operator declares `accepted_classes()` **by principle** (the fault's core concept), not by expanding to match observed outputs; a missing set fails loudly (validator F4 + a flag), never silently.
**Principle:** Enumerate all legitimately-correct answers up front. Tuning the answer key to the test-taker quietly inflates scores and makes the set depend on which models you ran first.
**Lives in:** DECISIONS (identification synonym matching; principled accepted_classes).

### 13. The crash tier: binary recovery, log evidence, and a schema that couldn't express it
**Happened (shape_mismatch):** Step 0 proved the crash mechanism *before* any code (input_dim=10 → "mat1 and mat2 shapes cannot be multiplied"); found recovery is **binary** — every non-105 value crashes, so no "completes-but-bad" middle exists. Then the first live trial: Haiku fixed the crash correctly but scored evidence 0.5, because it cited the traceback as a fake `metric_window` — the tool schema's enum only allowed `config_key`/`metric_window`; `line_range` didn't exist. It *couldn't* cite a log. A second run then exposed that the resolved config wrote `input_dim` at top level while the operator mutated `model.input_dim` — the agent cited the key exactly as it saw it and was marked wrong.
**Decided:** Enum expanded to all four evidence kinds; resolved config nests keys identically to where operators set them, with a test; binary recovery documented; code_span **excluded** from ground truth — evidence is the *minimal sufficient* set (root cause + symptom), and code that merely propagates the fault is mechanism, not evidence.
**Principle:** A new *kind* of operator exercises code paths no test touched. Each of three operators surfaced gaps the previous ones structurally could not — which is the entire argument for smoke-testing every operator with a live model before scaling.
**Lives in:** DECISIONS (crash tier entries; minimal-sufficient evidence).

### 14. Haiku fixes shape mismatches but cannot name them
**Happened:** Three runs, three wrong-or-loose labels, while the *repair* was exactly right each time. The model reliably fixes the fault and reliably mislabels its category.
**Principle:** "Fixed it correctly" and "understood it correctly" are different things, and a pass/fail benchmark would miss the distinction entirely. Four-axis scoring has resolution. (An early hint of a real finding.)

---

## Part V — The flagship (Sep 10–11, 2026)

### 15. Data leakage: hard vs. unfair
**Believed:** Make it hard by hiding the leak.
**Happened, in design:** If the leaking column is precomputed into data files, the agent — whose only tools are read_log/query_metrics/read_config/read_code/list_files — has no way to ever find it. That's not hard; it's undiagnosable. If the config key is named `leak_feature`, the flag hands over the answer. That's not hard; it's labeled.
**Decided:** Innocuous key (`include_aux_feature`); derivation in `train.py` written as a plausible pipeline step whose *implementation* honestly references the label (readable via read_code); train/val aux is label-correlated, hidden-test aux is pure noise (serving-time unavailability); recovery = flag→false, verified. Three fair signals, none a giveaway. Boolean repairs required a type-safe `allowed_values` extension (0 == False in Python; `0 in [False]` is True).
**Principle:** A fault must be diagnosable from the tools the agent actually has. Hardness comes from requiring *reasoning about provenance*, not from hiding the evidence.
**Lives in:** DECISIONS (data_leakage entries), operator_sources.md.

### 16. Haiku found the leak, wrote the word "leakage," and talked itself out of it
**Happened (first live trial, case_0004):** val_acc 0.9009 (inflated, far above the ~0.852 upper band); hidden test 0.8001 (collapsed, below 0.8435). Haiku read `_compute_aux_column`, derived by hand that "the auxiliary feature equals (label XOR noise)," and wrote: *"The auxiliary feature is BASED ON THE LABELS… which could lead to data leakage or overfitting. However, this might be intentional for the experiment."* Then it moved on — to the optimizer, weight decay, dtypes, the seed list. It never submitted. Cost: $0.115, 89K tokens, the most it had ever investigated.
**Two things this revealed, one bug and one finding:**
- *Bug:* the final turn hit `stop_reason=max_tokens` with no tool call, and the ReAct loop's "no tool calls → done" rule ended the trial with no submission at 14/40 tools. The harness silenced the model mid-reasoning and treated silence as completion. A verbose model would lose every hard case through no diagnostic failure.
- *Finding (provisional, n=1):* the model was not fooled by the metrics and not blind to the code. It **diagnosed the leak and distrusted its own diagnosis** — because the code looked deliberate and the metrics looked excellent. It called 0.90 "stable and high"; it had no anchor for what *normal* accuracy on this workload is, so implausibly-good read as good. This is exactly how real leakage survives in production: nobody suspects the feature making the model look good.
**Decided:** (a) max_tokens is a continuation, not completion — capped, counted, tested; (b) give the agent a *healthy reference band* on the public card — the visible val metric's mean±σ only, never the hidden test metric — so "0.90 vs expected ~0.857" becomes a discoverable anomaly. Trade-off: this is a *global* difficulty change (every silent case gets a below-band cue too), accepted for fairness. (c) absent-when-clean for *all* operator knobs, after noticing the shared `train.py` exposes every operator's hook and Haiku spent turns chasing the `input_dim` override — shape_mismatch's fingerprint — as a distractor.
**Principle:** Plumbing can masquerade as model failure — rule it out before interpreting a null result. And: a positive symptom is harder to diagnose than a negative one; whether agents *systematically* rationalize away positive-symptom faults is the hypothesis the sweep must test. If it holds across models and repeats, it is the paper's headline.
**Lives in:** DECISIONS (continuation policy; reference anchor; absent-when-clean; cross-operator fingerprints). Re-run pending.


### 17. The flagship re-run: anchored, the model trusted itself
**Happened (case_0004 re-run, Sep 11):** after the four fixes (continuation-on-truncation, the healthy-reference band on the public card, absent-when-clean knobs, calibration recorded), Haiku diagnosed the leak *decisively* — 9 turns, **0 truncations**, $0.061 (half of Run-1's $0.115). Its reasoning: *"This is data leakage: the auxiliary feature is computed from the labels and added to the input features, allowing the model to achieve artificially high validation accuracy."* No hedge, no "might be intentional." It submitted the exact admissible repair (`include_aux_feature: false`), and recovery verified.
**What changed between the runs:** room to finish, *and* an anchor saying 0.90 is far outside healthy (0.854–0.860). The two are confounded — one run each — so we cannot attribute the diagnosis to the anchor alone. But the direction is clear: the Run-1 "rationalized it away" behavior was **contingent on lacking a baseline**, not intrinsic to the model. That is a *better* finding than the one-run version, because it names the condition under which the failure occurs: a positive-symptom fault is dismissed as intentional when the agent has no reference for what "normal" looks like.
**Two scoring artifacts the re-run exposed — both plumbing, neither model failure:**
- *Identification:* Haiku's reasoning said "data leakage"; its structured label said `data_corruption`. The submit schema's description listed `"data_corruption"` as an *example* — and Haiku had used that exact string for label_corruption too. The example was anchoring the label. Fix: no real fault names in the schema description.
- *Evidence F1 0.57:* Haiku cited `data.aux_feature_strength` — the operator's own *second* mutated key — and it scored as a miss because ground truth listed only the flag. Fix: every key an operator mutates is evidence (now a cross-operator invariant test). Re-scored, free: **0.57 → 0.75**.
**Principle:** Plumbing masquerades as model failure in *both* directions — it can silence a correct diagnosis (truncation) and it can mislabel one (an example string in a schema). Rule out the harness before interpreting any score. Prediction logged beforehand: 65% Haiku diagnoses it. It did.
**Lives in:** DECISIONS (continuation policy; reference anchor; de-anchored operator_class; mutated-keys-are-evidence invariant).

### 18. Fix C broke replay — and the skipped tests would have caught it
**Believed:** Removing the `data:` block from the clean config (absent-when-clean) was a config-only change; the evaluator logic was "unchanged," so its slow tests could be skipped.
**Happened:** `make verify` on case_0004 crashed: `KeyError: 'data'`. The evaluator replays the operator's mutation into a fresh clean config via `_set_nested`, which navigated into a `data` section that no longer existed. Operators' `apply()` created the section; the replay path didn't. Both data-knob operators' recovery was broken. The paid trial itself was fine — only the free, re-runnable recovery step failed (the cost split earning its keep again).
**Decided:** `_set_nested` creates missing intermediate sections (and handles the YAML case where an empty `data:` parses to `None`); the same helper serves replay *and* the repair-patch applier; and a new invariant test runs **every registered operator through the evaluator end to end** — so a convention change anywhere can no longer silently break replay for some operator.
**Principle:** "Unchanged logic" is not a safe reason to skip a test when the *data the test runs against* changed. And: **CI green (full suite) before any paid run** — the trial ran before that gate; no harm this time, but the sequence matters more as runs get expensive.
**Lives in:** DECISIONS (absent-when-clean requires every config-writing path to create sections); tests/test_verify_repair.py (every-operator round-trip).

### 19. One red test became a property of the workload
**Believed:** `label_corruption` mild (15% flips) failed tolerance — it did, on seed 42 (0.8355, 0.008 below the bar).
**Happened:** The full operator suite showed mild *passing* tolerance on seed 1 (0.8452). Seed-42 calibration had put it 0.008 under a bar with 0.002 seed noise — a coin flip on other seeds. The instinct offered was to tolerate the red test ("pre-existing, unrelated"). Sweeping instead revealed the real picture: **18%, 20%, 22%, even 25% label noise barely moves hidden accuracy on Adult** (seed 2 hovers at the tolerance line at every fraction); only 35% clears margin. Moreover the ladder was **non-monotonic** — 25% gave *higher* accuracy than 22% on seed 2 — because each fraction's flip set was seeded by the fraction itself, so a higher rate flipped a *different* random subset, not a superset.
**Decided:** (a) never tolerate a red test — it was telling the truth; (b) a strength is valid only if it fails on **all** calibration seeds with margin (~2× reference std), not on one seed; (c) **nested flip sets** — one fixed permutation of indices from the data alone, flip the first ⌈p·N⌉ — so difficulty is monotone in p by construction; (d) cap severe below 0.50 (symmetric noise at 0.5 is zero information — a different, degenerate fault, not "corruption"); (e) tolerance is a property of the *clean* reference and is never widened to accommodate a marginal fault.
**The finding:** Adult + a small MLP is robust to symmetric label noise — a fifth of the labels wrong produces under a one-point degradation. Label corruption on tabular data is therefore a genuinely *subtle* silent operator, nearly invisible in aggregate accuracy. That motivates per-class metrics and predicts the vision workload will be far more noise-sensitive — a testable claim.
**Principle:** Calibrating a ladder on one seed is not calibration. Taken seriously, a single failing test yielded both a real property of the workload and an infrastructure improvement (nested sets) every fractional operator will inherit.
**Lives in:** DECISIONS (margin-across-seeds rule; nested flip sets; label-noise robustness finding; tolerance never widened). Re-ladder pending sweep 2.

---

## Part VI — The pre-sweep gate (Sep 11, 2026)

### 20. Known-answer at scale — the first gate run

Before spending a dollar on the sweep, we built the G1 gate: run an *oracle* (the exactly-correct
answer), a *degenerate* (right recovery, wrong everything else), and an *always-broken* knob-scanner
over every case, and assert what must hold if ground truth is right. Prediction logged before the
run: the oracle passes everywhere; if it doesn't, ground truth — not the model — is wrong.

First run (fast mode, 4 operators + 3 new healthy controls, 7 cases): **49 checks, 0 FAIL.** The
oracle was exactly correct on every case and tier; the degenerate was strictly out-scored on
identification and evidence on every faulty case and flagged as a false intervention on every
control; the always-broken agent was caught by the controls (detection FPR = 1.0) and scored zero
evidence everywhere. The impossible-combination audit over `results/` was likewise **0 FAIL**, with
one INFO rule firing exactly as designed: 9 prior trials flagged as scored against a superseded
build (the label_corruption re-ladder). A clean first table is not a boring result — it is the
gate certifying that the ground truth the sweep will grade against is internally consistent.

Three things this forced into existence, each of which had been latent:
- **A healthy control tier.** Until now every case had a fault, so "false positive" and "false
  intervention" were unmeasurable. Controls make over-eagerness a first-class, scored axis
  (`no_unnecessary_repair`, `detection_false_positive_rate_on_controls`). The design bite: the
  oracle can't read the same evidence file it is graded against, or a dropped ref mirrors on both
  sides and hides — so the gate derives the oracle's evidence and class from the *operator* and the
  repair from the *file*, which is what makes the planted-corruption tests actually catch drift.
- **`oracle_repair()` as a protocol method.** The known-good fix was implicit; now it is declared,
  admissibility-checked, and hidden-side only.
- **A trusted/contestant boundary.** The probe agents read hidden ground truth, so `run_trial`
  refuses them without `--allow-trusted` and aggregation excludes `trusted` records — a trusted
  answer can never leak into a headline number by accident.

Lesson: the gate's value is not the failures it finds on day one but that it converts "is the
ground truth right?" from a hope into a command you can run for free before every sweep.

---

## Part VII — Standing lessons (the ones that keep recurring)

- **Prove it on hard cases before scaling.** Three operators, roughly a dozen real bugs, every one found on a single deliberate case for pennies instead of across a hundred. The instinct to build two more operators before the sweep was right.
- **Each new kind of thing exercises an untested path.** Silent-easy → silent-hard → crash → misleading-symptom: each surfaced a gap the previous ones structurally could not. Expect the vision and text workloads to do the same.
- **Convert every manual find into a machine check, then keep reading.** Tests guard what you thought of; audits find what you didn't.
- **Enumerate legitimate answers by principle; never tune ground truth to the test-taker.** Applied to evidence, config artifacts, identification, and repairs alike.
- **Plumbing before conclusions.** The `unknown_` print, the max_tokens cutoff, the stale index — each looked like a result until it was recognized as infrastructure.
- **Know when to stop building.** The paper lives in the sweep results, not the operator count. After ~6–7 operators, run the experiment.
- **Plumbing masquerades as model failure in both directions.** It can silence a correct diagnosis (truncation) or mislabel one (an example string in a schema). Rule out the harness before interpreting any score — and log a prediction before each decisive run so the result can't be rationalized afterward.
- **Never tolerate a red test.** Three times a "pre-existing" failure was the truth trying to get through. One seed is not evidence; one run is not a finding.
- **CI green before any paid run.** Skipping "unchanged logic" tests after a data/convention change is unsafe; the cost split saves the money but not the time.
- **Watch for accidental complexity.** The shared `train.py` accumulating one `if dcfg.get(...)` per operator is the early signal; refactor to a single injection hook before the second and third workloads triple it. The tell: when a new operator requires editing files that aren't its own.

---

## Open questions the sweep must answer
1. Is "found-it-then-rationalized-it-away" a systematic failure on positive-symptom faults, across models and repeats?
2. ~~Does the reference anchor make leakage diagnosable?~~ **Answered (n=1): yes — with an anchor and room to finish, Haiku diagnosed it decisively.** Open: is the effect attributable to the anchor, the continuation fix, or both? (A run with the anchor removed would isolate it.) And does it hold across models and repeats?
3. Do the four axes separate cleanly across silent-easy / silent-hard / crash, as RQ1 predicts?
4. How many repeats per cell are needed for stable scores on the *hard* operators (the easy ones needed few)?
5. Is the vision workload more label-noise-sensitive than tabular, as entry 19 predicts?
6. Does difficulty come from the fault, not the data — i.e. do the hard tabular operators defeat models as reliably as modality-specific ones would?
