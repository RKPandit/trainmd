# TrainMD

Evidence-grounded diagnosis and verified recovery of controlled ML training incidents.

See [docs/problem_statement_v0.3.md](docs/problem_statement_v0.3.md) for the full research scope
and [docs/harness_spec_v0.3.md](docs/harness_spec_v0.3.md) for the implementation spec.

## Quickstart (canonical container — reproducible by a stranger)

The canonical environment is a pinned **linux/amd64, Python 3.11** Docker image
(deps frozen from `uv.lock`). One build, then everything that produces or checks
a committed artifact runs inside it. Requires Docker (Desktop or engine).

```bash
git clone <repo-url> && cd trainmd
make image                 # build the pinned image (amd64; digest → docker/IMAGE_DIGEST)
make image-digest          # print the built + committed image digest
make docker-test           # full test suite inside the container
make docker-validate-all   # 20-check validation of every case
make docker-gate-known-answer   # oracle/stub gate (no LLM calls)
```

On an arm64 host (Apple Silicon) these run under qemu emulation — a **development
convenience**. The canonical numbers are the ones **CI produces on native amd64**
(`ubuntu-latest`); the workflow builds the same image and runs the suite +
`validate-all` + `gate-known-answer` in it on push/PR and nightly.

Local (host) dev without Docker still works via `uv` (`make test`, `make validate-all`,
…), but artifacts committed to the repo are the container's.

## Reference stats

Data prep is **byte-identical across platforms** (verified by SHA-256 of every split).
The committed `reference/stats.yaml` is the **verified canonical reference**: with every
BLAS/OpenMP thread pool pinned to 1 (`train.py` enforces this) and the data pinned to committed
hashes, the native linux/amd64 reference is **byte-exact within a microarchitecture; across
heterogeneous native amd64 microarchitectures the means reproduce within ~1e-3 (≤0.5σ) and
σ-estimates within ~3e-3** (float reduction order differs across AVX-512/AVX2 — LIMITATIONS L18;
DECISIONS 2026-09-14). The CI reference-diff is tolerance-based accordingly (means ≤2e-3,
`tolerance_lower` ≤6e-3 + an exact derivation check). `train.py` refuses to run unpinned so no host run can produce
non-canonical numbers. **Sweep 1's training ran pre-pinning** (unpinned threading; the
reference band it used was still canonical — see `docs/LIMITATIONS.md` L11); **Sweep 2
onward is fully canonical.** See `docs/DECISIONS.md`.

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
