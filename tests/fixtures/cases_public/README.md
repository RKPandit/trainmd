# Public-only fixture cases

Two cases copied from a canonical build so the agent tests that read ONLY the agent-visible surface
run in CI, which builds no cases (before this, `tests/test_static_agent.py` skipped every test in CI —
the third silently-skipping test group; DECISIONS 2026-09-23).

- `case_0001` — a faulty case; `case_0109` — a control case (identified from the public release
  metadata, `results_release/h8_xprovider/cases/case_0109.json`; local build id matched).
- Contents: `card.public.yaml` + `workspace/` (config, code, run outputs) — exactly what an agent sees.
  **No `hidden/`**, no hidden card, no answer key (test-enforced in `tests/test_fixture_cases.py`).
- `card.public.yaml` gains `reference_visible_metric.n` (= reference `num_seeds`, 30) so the prompt-v2
  stats arm can render; otherwise byte-copied.
- `workspace/.data` is a relative symlink to `workloads/tabular_adult/.data` (present after
  `make docker-data`, as in CI).

Frozen snapshot: it is not rebuilt when a workload changes. Tests that need ground truth (scoring,
trusted agents) cannot use it by design.
