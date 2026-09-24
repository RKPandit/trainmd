#!/usr/bin/env bash
#
# make restore-cases — full local restore of the built cases from the latest GREEN
# build-and-certify run, in one command:
#   find latest green run -> remove any stale ciphertext -> download the
#   sweep_bundle artifact -> decrypt with $SWEEP_BUNDLE_KEY -> extract ->
#   make docker-data -> make link-neutral-workload -> make docker-validate-all.
#
# Preconditions are checked UP FRONT with actionable errors. The extract is
# staged and swapped in ATOMICALLY: a partial download/decrypt/extract never
# touches the live cases/, and a failure rolls the previous cases/ back — the
# tree is never left half-restored.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

WORKFLOW="${CERTIFY_WORKFLOW:-ci.yml}"
BUNDLE_CIPHERTEXT="sweep_bundle.tar.gz.gpg"
ARTIFACT_NAME="sweep_bundle"

# --- Preconditions UP FRONT --------------------------------------------------
require_cmd "$GH" gh "Install the GitHub CLI (https://cli.github.com) and run 'gh auth login'."
require_cmd "$GPG" gpg
require_cmd "$TAR" tar

require_env SWEEP_BUNDLE_KEY \
  "It is the passphrase that decrypts the bundle, and must match the repo secret" \
  "used by the certify run. Export it, then retry:" \
  "  export SWEEP_BUNDLE_KEY=..."

# Find the latest green run that actually produced a sweep_bundle artifact
# (build-and-certify runs on workflow_dispatch and on the nightly schedule).
note "Looking for the latest green build-and-certify run with a $ARTIFACT_NAME artifact ..."
run_id=""; run_url=""
run_rows="$("$GH" run list --workflow "$WORKFLOW" --status success --limit 40 \
             --json databaseId,url --jq '.[] | "\(.databaseId)\t\(.url)"' 2>/dev/null || true)"
while IFS=$'\t' read -r id url; do
  [ -n "$id" ] || continue
  names="$("$GH" api "repos/{owner}/{repo}/actions/runs/$id/artifacts" \
            --jq '.artifacts[].name' 2>/dev/null || true)"
  if grep -qx "$ARTIFACT_NAME" <<<"$names"; then
    run_id="$id"; run_url="$url"; break
  fi
done <<<"$run_rows"

[ -n "$run_id" ] || die \
  "no green build-and-certify run with a $ARTIFACT_NAME artifact was found." \
  "Produce one first:" \
  "  make certify" \
  "(artifacts also expire after 7 days — re-run certify if the last one aged out)."

note "Using run $run_id ($run_url)"

# --- Remove any stale ciphertext, then download ------------------------------
rm -f "$BUNDLE_CIPHERTEXT"
note "Downloading $ARTIFACT_NAME ..."
"$GH" run download "$run_id" -n "$ARTIFACT_NAME" -D . \
  || die "failed to download the $ARTIFACT_NAME artifact from run $run_id ($run_url)."
[ -f "$BUNDLE_CIPHERTEXT" ] || die \
  "the $ARTIFACT_NAME artifact did not contain $BUNDLE_CIPHERTEXT (run $run_id)."

# --- Stage decrypt + extract off to the side; swap in atomically -------------
STAGING="$(mktemp -d ./.restore_staging.XXXXXX)"
BACKUP=""
cleanup() {
  # On any failure: if we had moved the old cases/ aside but not completed the
  # swap, roll it back so the tree is never left without cases/.
  if [ -n "$BACKUP" ] && [ -d "$BACKUP" ] && [ ! -d cases ]; then
    mv "$BACKUP" cases
  fi
  [ -n "$BACKUP" ] && rm -rf "$BACKUP" 2>/dev/null || true
  rm -rf "$STAGING" 2>/dev/null || true
}
trap cleanup EXIT

note "Decrypting ..."
"$GPG" --batch --yes --quiet --decrypt --passphrase "$SWEEP_BUNDLE_KEY" \
  -o "$STAGING/cases.tar.gz" "$BUNDLE_CIPHERTEXT" \
  || die "decryption failed — the passphrase in \$SWEEP_BUNDLE_KEY does not match the" \
         "secret used by run $run_id ($run_url)." \
         "Set SWEEP_BUNDLE_KEY to that run's SWEEP_BUNDLE_KEY value and retry."

note "Extracting ..."
"$TAR" -xzf "$STAGING/cases.tar.gz" -C "$STAGING" \
  || die "extraction failed — the downloaded bundle from run $run_id is corrupt."
[ -d "$STAGING/cases" ] || die "the bundle did not contain a cases/ directory (run $run_id)."

# Atomic swap (all paths on the same filesystem — STAGING is under the repo).
if [ -d cases ]; then
  BACKUP="./.cases_backup.$$"
  mv cases "$BACKUP"
fi
mv "$STAGING/cases" cases

# Re-point each workspace/.data symlink to the (regenerable) data dir, matching
# what build-and-certify does before packaging (the bundle carries no data).
for link in cases/*/workspace/.data; do
  [ -L "$link" ] || continue
  ln -sfn ../../../workloads/tabular_adult/.data "$link"
done

# Backup no longer needed once the new cases/ is in place.
[ -n "$BACKUP" ] && rm -rf "$BACKUP" && BACKUP=""

case_count="$(find cases -maxdepth 1 -type d -name 'case_*' | wc -l | tr -d ' ')"
note "Restored $case_count cases from run $run_id."

# --- Regenerate data, link the neutral family, validate ----------------------
note "Regenerating data (make docker-data) ..."
make docker-data
note "Linking the neutral workload family ..."
make link-neutral-workload
note "Validating every case (make docker-validate-all) ..."
make docker-validate-all

# --- Summary -----------------------------------------------------------------
note ""
note "=== restore-cases summary ==="
note "  source run:  $run_id ($run_url)"
note "  cases:       $case_count restored, validate-all PASSED"
note "  data:        regenerated + neutral family linked"
