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

## Current milestone

**M2.1** — repo scaffold, tabular workload, reference-run protocol green in CI.

## License

Apache-2.0
