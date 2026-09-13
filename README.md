# TrainMD

Evidence-grounded diagnosis and verified recovery of controlled ML training incidents.

See [docs/problem_statement_v0.3.md](docs/problem_statement_v0.3.md) for the full research scope
and [docs/harness_spec_v0.3.md](docs/harness_spec_v0.3.md) for the implementation spec.

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone <repo-url> && cd trainmd
uv sync              # creates .venv/ and installs pinned dependencies from uv.lock
make data            # downloads and prepares the Adult dataset
make reference       # runs 10 seeded training jobs, writes reference/stats.yaml
```

## Reference stats

The committed `reference/stats.yaml` is generated on Linux x86_64 in CI.
Local macOS runs will produce slightly different metric values due to
cross-platform BLAS divergence (~0.001) and will **not** match the
committed snapshot — this is expected. See `docs/DECISIONS.md` for details.

## Hardening gates (pre-sweep, free)

Before any paid sweep, run the G1 gates. They are oracle/stub-driven (no LLM
calls) and write dated audit tables to `docs/audits/`.

```
make gate-known-answer          # oracle/degenerate/always-broken over every case (fast)
make gate-known-answer FULL=1   # same, plus recovery reruns (retrains — slow)
make audit-index                # impossible-combination audit over results/index.jsonl
```

- **`gate-known-answer`** asserts, per case, that the oracle is exactly correct
  (detection, identification, evidence F1 == 1.0, and in full mode recovery),
  that the oracle strictly out-scores the degenerate, and that healthy controls
  catch an always-detect agent. Any oracle deviation means ground truth is wrong
  for that case — the table names it. Exits nonzero on any FAIL.
- **`audit-index`** flags logically impossible score combinations (e.g. recovered
  but not detected, a repair on a healthy control) as FAIL, and reporting-only
  conditions (superseded trials) as INFO. Exits nonzero on any FAIL.

`--fast` (default) skips recovery reruns; `--full` / `FULL=1` includes them. The
current CI workflow (`.github/workflows/reference.yml`) runs the reference-run
protocol on **push and pull_request**; there is no nightly/full job yet (it arrives
in Stage 1 with the container). Gate/validate/audit are run locally and their dated
tables land in `docs/audits/`.

## Running a sweep

`harness/sweep.py` orchestrates a full experiment. The plan file is the committed
pre-registration; the run is precondition-gated, resumable, and cost-capped.

```
# 1. Plan (writes sweeps/<name>_plan.yaml). --build-missing generates absent cases.
python -m harness.sweep plan --name sweep1 [--build-missing]
# 2. Commit sweeps/sweep1_plan.yaml — it is the pre-registration.
# 3. Paid agent phase (refuses unless gate/audit/validate green, plan committed,
#    build_ids match, API key set). --max-cost-usd is REQUIRED.
python -m harness.sweep run --name sweep1 --phase agents --max-cost-usd 20
# 4. Free recovery phase (CPU only), after all agent trials.
python -m harness.sweep run --name sweep1 --phase verify
# 5. Report → docs/audits/sweep_<name>_<date>.md
python -m harness.sweep report --name sweep1
```

Safety: a hard `--max-cost-usd` stops before exceeding the cap; `--max-consecutive-failures`
(default 3) stops on a systemic failure; progress files make every phase resumable (a crash
costs one trial). The tracked `sweeps/<name>_manifest.yaml` is the compute statement (hardware
captured once + per-phase token/cost/CPU totals; `actual_spend_usd` entered manually at end).

## Findings & limitations

The scientific narrative and its caveats live in the running docs:
[docs/FINDINGS.md](docs/FINDINGS.md) (what we learned and the evidence),
[docs/HYPOTHESES.md](docs/HYPOTHESES.md) (pre-registration + per-hypothesis verdicts),
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) (what the results do and do not support, with the
disclosure rule and Sweep-2 remedies), [docs/DECISIONS.md](docs/DECISIONS.md), and
[docs/RESEARCH_LOG.md](docs/RESEARCH_LOG.md). Machine-generated evidence is under `docs/audits/`.

## Current milestone

**Sweep 1 complete** (Haiku 4.5, tabular_adult, 324 trials / 27 cases, two agents,
anchor on/off) with disclosed post-hoc corrections and an external claim-tightening
review — see `docs/FINDINGS.md`, `docs/HYPOTHESES.md` Results, and `docs/LIMITATIONS.md`.
**Next (Stage 1):** Linux container + canonical re-run, then Sweep 2 (second model /
workload, factorial symptom×operator, three-arm anchor). Earlier milestones (M2.1 repo
scaffold + reference-run protocol green in CI) are done.

## License

Apache-2.0
