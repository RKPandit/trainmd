# Sweep bundle — contents, integrity, restore procedure

The paid sweep (`harness/run_agent` via `harness.sweep run`) needs the built cases
on disk locally, but `cases/` is gitignored and a local rebuild is impossible: the
platform guard blocks an emulated build, and a rebuilt case would get a different
`case_build_id`, which the run precondition rejects. The `build-and-certify` CI job
therefore builds the canonical cases and ships them as an artifact.

## What the sweep reads on disk (traced)

| Path | Reader | Ships in bundle? |
|---|---|---|
| `cases/<id>/` (workspace, cards, `hidden/`) + `cases/registry.hidden.yaml` | agent phase; preconditions (gate/validate/audit); verify/scoring read `hidden/` | **yes (encrypted)** — not regenerable |
| `workloads/tabular_adult/.data`, `.hidden_data` | `verify_repair` reads the workload dir directly (`harness/evaluator/verify_repair.py`) for the retrain + hidden test set | **no** — regenerated locally |
| `workloads/tabular_adult_neutral/.data`, `.hidden_data` | verify (neutral cases) | **no** — created by `make link-neutral-workload` |

The agent phase never retrains (`run_training` is deferred, `harness/tools/tools.py`);
it reads `workspace/run_output/*` and the workspace code. `list_files` only checks
that `workspace/.data` *exists*. `verify_repair` builds its own temp workspace from
the workload dir, so it needs `workloads/<family>/.data` + `.hidden_data`, not the
case workspace.

## Integrity: no plaintext hidden material in a PUBLIC artifact

`RKPandit/trainmd` is a **public** repo, so Actions artifacts are downloadable by
anyone. The bundle must not publish hidden material:

- **`.data` / `.hidden_data` are EXCLUDED.** `data_prep.py` regenerates BOTH
  deterministically from committed inputs (`data_split.yaml` OpenML name/version +
  `prep_seed`), and asserts the result byte-for-byte against the committed,
  hash-pinned `reference/data_manifest.yaml` — a **loud failure** if OpenML ever
  drifts. So `make docker-data` locally reproduces the exact canonical data; the
  hidden TEST SET never ships.
- **`cases/*/hidden/` (the grading keys — operator, `accepted_classes`, oracle
  repairs, verify tolerances) is NOT regenerable**, so the cases tar is
  **encrypted** (AES256) with the `SWEEP_BUNDLE_KEY` repo secret. The ciphertext is
  safe to publish; the maintainer decrypts locally. The CI step is **fail-closed**:
  if the secret is unset it refuses to upload rather than leak plaintext.

`build_case._compute_build_id` hashes only the workload SOURCE files + mutations,
never `.data` or its symlink, so rewriting each `workspace/.data` to a relative
symlink in CI is build_id-neutral.

## One-time setup

Add a repo Actions secret `SWEEP_BUNDLE_KEY` (a strong passphrase). Keep the same
value locally (e.g. exported in your shell) to decrypt.

## Dispatch → download → restore

Dispatch `build-and-certify` (it emits `sweep_bundle` + `h8_xprovider_plan` from the
same run, so plan build_ids match the cases by construction):

    gh workflow run "CI (canonical container)" --ref <branch-or-main>

Once green (`gh run watch <run-id>`), from the repo root:

    cd /Users/rpandit/Documents/ai/trainmd
    RUN=<run-id>
    gh run download $RUN -n sweep_bundle      -D .        # -> ./sweep_bundle.tar.gz.gpg
    gh run download $RUN -n h8_xprovider_plan -D sweeps   # -> sweeps/h8_xprovider_plan.yaml

    # decrypt + extract the cases (restores cases/ incl. hidden/):
    gpg --batch --yes --passphrase "$SWEEP_BUNDLE_KEY" -d sweep_bundle.tar.gz.gpg | tar -xz

    # regenerate the (excluded) workload data — deterministic, hash-pinned:
    make docker-data
    make link-neutral-workload

    # if the downloaded plan differs from the committed one, commit it (it matches
    # the just-downloaded cases):
    git diff --stat sweeps/h8_xprovider_plan.yaml

Preconditions then pass: `cases/` present (gate/validate/audit), workload data
present (verify), plan committed with matching build_ids, `ANTHROPIC_API_KEY` set.
Run the sweep with an explicit cost cap:

    python -m harness.sweep run --name h8_xprovider --max-cost-usd <cap>
