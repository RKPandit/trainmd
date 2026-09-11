# TrainMD — Pre-Release Hardening Program

**Goal:** a public benchmark that thousands can run where (1) no bug undermines a claim in
the paper, (2) every remaining bug is *findable* because the system is auditable, and (3) we
have found and documented more bugs than any reviewer will. "Zero bugs" is not a credible
target; "rigorous, auditable, and honest" is — and it is what makes a later-found bug raise
credibility rather than destroy it.

**Organizing principle:** defenses are grouped by the *class of bug they catch*, because
coverage of classes — not the count of tests — is what determines whether the unknown bugs
matter. Each defense states what it catches, its cost, and when it gates.

**Gates:** G1 before the first sweep · G2 before the paper's numbers are final · G3 before
public release.

---

## Tier 0 — The bugs that would make everything meaningless (integrity)

These are the properties that, if broken, invalidate every result. They already have the
strongest defenses; this tier is about *proving* them adversarially, not trusting them.

### 0.1 Red-team the wall (G1)
Attack the sealed evaluation as a hostile agent would, and assert every attack fails:
- Path escapes: `..`, absolute paths, symlinks pointing out, unicode/encoded path tricks,
  case-variant filenames, very long paths.
- Read the answer through side channels: does `list_files` glob into `hidden/`? Can
  `read_log` be pointed at `card.hidden.yaml` via a crafted `artifact_id`? Does any error
  message *echo hidden content* (e.g. a KeyError that prints the key path from the manifest)?
- Repair-as-attack: a repair spec that patches `verify.yaml`-adjacent keys, a code patch that
  edits the evaluator, a patch that makes training write to the hidden dir.
- Tamper every public artifact (card, config, train.py) and assert the verdict is unchanged.
**Catches:** any leak or influence path we didn't think of. **Cost:** ~1 day. Turn every
attack into a permanent test (`tests/test_redteam_wall.py`).

### 0.2 Prove no hidden value reaches any visible artifact, mechanically (G1)
Extend the isolation scan from *tokens* to *values*: after building every case, scan all
agent-visible bytes for the literal hidden numbers — `faulty_value`, `tolerance_lower`,
hidden-metric mean/std, hidden seeds, the `build_id` of hidden-only content. A token scan
misses a number; a value scan doesn't.
**Catches:** numeric leaks (a tolerance printed in a log by a future change). **Cost:** hours.

### 0.3 Recovery oracle self-consistency (G1)
For every case: the *clean* config must verify as recovered; the *faulty* config must verify
as not-recovered (silent) or not-completed (crash); the oracle repair must recover. Run this
as a standing check over the whole case set, not per operator.
**Catches:** an evaluator that says "recovered" when it shouldn't, for *any* case.
**Cost:** CPU-only, overnight.

---

## Tier 1 — Bugs that corrupt the science silently (scoring correctness)

The scoring layer has so far been validated mostly by reading real trials and noticing the
score disagreed with the transcript. That does not scale and cannot be trusted to have caught
everything. These defenses do not require knowing where the bug is.

### 1.1 Known-answer stubs at scale (G1, then before every sweep)
Run the **oracle stub** and the **degenerate stub** through the *entire* case set. The oracle
must score ~perfect on all four axes on every case; the degenerate must score badly on
diagnosis while (for lenient operators) recovering. Any case where the oracle is not perfect
has wrong ground truth — found without knowing which operator to suspect.
**Catches:** every "ground truth is subtly wrong" bug (evidence gaps, missing accepted
classes, wrong key paths). **Cost:** free. Make it `make gate-known-answer`.

### 1.2 Impossible-combination audit over the index (G1, every sweep)
Assert score combinations that cannot be right never occur: recovered ∧ ¬detected; crash
case with recovery=recovered but no completion; evidence recall 1.0 ∧ identification wrong on
an easy operator (flag for review); `no_submission` with any non-null axis; token counts of
zero on a completed LLM trial; cost inconsistent with tokens×price.
**Catches:** scorer/record inconsistencies at scale. **Cost:** hours; a script over
`index.jsonl`.

### 1.3 Mutation-test the scorer (G2)
Deliberately break the scorer in small ways (flip a comparison, drop normalization, off-by-one
an interval) and assert the test suite *catches each mutation*. A scorer whose tests pass
under mutation has tests that aren't testing it.
**Catches:** hollow tests. **Cost:** ~half a day with `mutmut` or by hand on
`scoring.py`/`repair_spec.py`.

### 1.4 Property-based tests on matching (G2)
Use Hypothesis to generate random evidence refs / repair specs / class strings and assert
invariants: matching is symmetric where it should be, normalization is idempotent, no
exception on malformed input (always a reason code), interval overlap is commutative,
`allowed_values` never accepts a non-bool for a bool key.
**Catches:** edge cases no hand-written test imagined. **Cost:** ~half a day.

### 1.5 Randomized spot-audit as a standing practice (every sweep)
Read a *genuinely random* 5% of trials (seeded random selection, logged) and compare
score-to-transcript by hand. Record the audit in `docs/AUDITS.md` with the sample and any
discrepancy. This bounds the residual error rate honestly.
**Catches:** whatever is left, with a measured rate. **Cost:** ~1 hr per sweep.

---

## Tier 2 — Bugs that make results non-reproducible (determinism & environment)

### 2.1 Clean-clone reproduction drill (G2, G3)
On a fresh machine/container with no cache: clone → `uv sync` → `make data` → `make
reference` → build all cases → validate-all → run known-answer stubs → compare every number
to the committed snapshots. Do it on Linux (canonical) and once on macOS (expect the
documented platform delta, nothing else).
**Catches:** hidden dependence on local state, untracked files, path assumptions.
**Cost:** hours. Document exactly what a third party must do; that document *is* the
reproducibility appendix.

### 2.2 Determinism across process, seed, and platform — every operator (G1)
Generalize the label_corruption L4/L5 tests to a parametrized suite over *all* operators:
cross-process identical; fault independent of training seed; case rebuild byte-identical
(excluding timing fields).
**Catches:** any operator that reintroduces per-process or seed-coupled randomness.

### 2.3 Dependency pinning drill (G3)
`uv.lock` is the contract. Verify that `torch`, `numpy`, and `scikit-learn` versions are pinned
and that the reference reproduces under the *locked* versions on a fresh resolve. Record the
exact versions in the paper.

---

## Tier 3 — Bugs that make the benchmark unfair or gameable (validity)

### 3.1 Cheating-agent tests (G1)
Write agents that try to win without diagnosing and assert they score badly:
- **Always-broken**: `detected=true` on every case, random class, no evidence, most-common
  repair → healthy controls must catch it; evidence 0.
- **Repair-only guesser**: submits the most common admissible repair with no investigation →
  recovers on lenient operators (documented), fails identification/evidence.
- **Knob-scanner**: reads config, patches every non-default knob back to default → measures
  how much "diff the config" alone achieves (an important *baseline* to report, not a bug).
**Catches:** any axis winnable without diagnosis. **Requires** healthy controls — build them.

### 3.2 Healthy controls (G1 — not yet built, required)
Clean cases the agent must call "nothing wrong." Without them detection is trivially gameable.
Validate they pass the clean verifier and that `accepted_classes` includes `none`.

### 3.3 Difficulty sanity (G2)
Across the sweep, the four axes must *separate* operators as designed (easy > hard). If the
flagship scores as easy as lr_warmup for every model, the flagship isn't hard — investigate
before publishing that claim.

### 3.4 Prompt-contamination audit (G2)
Grep the agent prompt and tool schemas for any fault name, operator id, key path, or example
that could anchor a label (the `data_corruption` lesson). Assert none present; test it.

---

## Tier 4 — Bugs in the artifacts themselves (data quality)

### 4.1 Validator coverage review (G2)
List every invariant the validator checks; for each *bug found by manual audit so far*, confirm
there is now a validator check (or a test) that would catch its recurrence. Any past bug without
a check gets one. This closes the loop on the research log.

### 4.2 Schema validation of every artifact (G2)
Formal schemas (pydantic/jsonschema) for `card.public.yaml`, `card.hidden.yaml`,
`evidence.yaml`, `verify.yaml`, the trial record, and `index.jsonl`; validate on write *and*
on read. Unknown fields and missing fields fail loudly.
**Catches:** drift between what code writes and what code expects.

### 4.3 Superseded-trial hygiene (G2)
The `build_id` supersession flag must be present on every trial; analysis scripts must filter
to current-build trials by default and *print* how many were excluded.

---

## Tier 5 — What outsiders will actually hit (public-release readiness)

### 5.1 Fresh-eyes review (G3)
Have one person who has never seen the repo follow README only and try to (a) reproduce the
reference, (b) build a case, (c) run the stub agent, (d) run one paid trial. Every point they
get stuck is a bug in the docs. Do this *before* the paper, not after.

### 5.2 Error-message audit (G3)
Every failure a user can plausibly hit (missing API key, wrong model id, no data prepared, a
stale case, a superseded trial) must produce a message that says what to do. Grep for bare
`KeyError`/`AssertionError` surfaces on user paths.

### 5.3 CI as the contract (G3)
CI runs the *full* suite including slow integration tests (nightly if too slow for every push),
the known-answer gate, validate-all, and the clean-clone drill weekly. A green badge on the
README should mean "everything in this document passed," not "the fast tests passed."

### 5.4 Known limitations, written first (G3)
A `LIMITATIONS.md` that states plainly: which operators have lenient recovery (lr_warmup),
that identification uses enumerated class sets, that evidence is minimal-sufficient, the
single-workload status, the simulated (not real) cloud faults, seed/cost variance, and the
residual spot-audit error rate. Reviewers respect limitations you name before they do; a
public user who finds one of these has found nothing.

### 5.5 Responsible disclosure path (G3)
A `SECURITY.md`/issue template: "if you find a way to see hidden data or fake a recovery, tell
us." A benchmark that invites attack on its wall signals it can take it.

---

## Sequencing (what gates what)

- **Before the first sweep (G1):** 0.1, 0.2, 0.3, 1.1, 1.2, 2.2, 3.1, 3.2, plus the in-flight
  structural fixes (nested sets, build_id). These are cheap, mostly free, and catch the silent
  classes. Then run the sweep.
- **Before final numbers (G2):** 1.3, 1.4, 1.5 (per sweep), 2.1, 3.3, 3.4, 4.1, 4.2, 4.3.
- **Before public release (G3):** 2.3, 5.1–5.5.

**The one rule that matters more than any item above:** every bug found by any method
becomes a permanent check (test, validator invariant, or gate) *and* a research-log entry.
The program is not a checklist to finish; it is a ratchet that only tightens.

---

## Honesty clause (for the paper and the README)
State the audit method and its results: N invariants, M tests, the known-answer gate, the
random spot-audit sample size and its discrepancy count, and the list of bugs found and fixed
during development (from the research log). A benchmark that documents twelve fixed bugs and
the invariants preventing their recurrence is *more* credible than one claiming none.
