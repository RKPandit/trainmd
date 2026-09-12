# TrainMD

Evidence-grounded diagnosis and verified recovery of controlled ML training incidents.

See [docs/problem_statement_v0.3.md](docs/problem_statement_v0.3.md) for the full research scope
and [docs/harness_spec_v0.1.md](docs/harness_spec_v0.1.md) for the implementation spec.

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

`--fast` (default) skips recovery reruns; `--full` / `FULL=1` includes them. CI
runs fast on push, full nightly. Audit tables land in `docs/audits/`.

## Current milestone

**M2.1** — repo scaffold, tabular workload, reference-run protocol green in CI.

## License

Apache-2.0
