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

## Current milestone

**M2.1** — repo scaffold, tabular workload, reference-run protocol green in CI.

## License

Apache-2.0
