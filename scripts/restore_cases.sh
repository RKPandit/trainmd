#!/usr/bin/env bash
#
# make restore-cases — full local restore of the built cases from a GREEN
# build-and-certify run (RUN_ID=<id> to name it; default: the latest), in one command:
#   find latest green run -> remove any stale ciphertext -> download the
#   sweep_bundle artifact -> decrypt with $SWEEP_BUNDLE_KEY -> extract ->
#   make docker-data -> make link-neutral-workload -> make docker-validate-all.
#
# The restored bundle's case count must equal the expected design count
# (EXPECT_CASES=<n>; default: docs/CURRENT_STATE.md `case_count`), checked in STAGING before the
# swap — a stale bundle (e.g. an older nightly on another branch) is refused, never restored.
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

# Expected case count: explicit EXPECT_CASES, else the design count recorded in CURRENT_STATE (kept
# equal to the code's design by scripts/check_current_state.py). No expectation -> refuse.
EXPECT_CASES="${EXPECT_CASES:-$(awk '/^case_count:/{print $2; exit}' docs/CURRENT_STATE.md 2>/dev/null || true)}"
[[ "$EXPECT_CASES" =~ ^[0-9]+$ ]] || die \
  "no expected case count: set EXPECT_CASES=<n> (or keep docs/CURRENT_STATE.md case_count current)."

run_id=""; run_url=""
if [ -n "${RUN_ID:-}" ]; then
  # Explicit target: that run must have succeeded and carry the bundle artifact.
  note "Using the requested run $RUN_ID ..."
  view="$("$GH" run view "$RUN_ID" --json conclusion,url \
           --jq '"\(.conclusion)\t\(.url)"' 2>/dev/null || true)"
  conclusion="${view%%$'\t'*}"; url="${view#*$'\t'}"
  [ "$conclusion" = "success" ] || die \
    "run $RUN_ID is not a successful run (conclusion: '${conclusion:-unknown}'); refusing to restore from it."
  names="$("$GH" api "repos/{owner}/{repo}/actions/runs/$RUN_ID/artifacts" \
            --jq '.artifacts[].name' 2>/dev/null || true)"
  grep -qx "$ARTIFACT_NAME" <<<"$names" || die \
    "run $RUN_ID has no $ARTIFACT_NAME artifact (expired after 7 days, or not a certify run)."
  run_id="$RUN_ID"; run_url="$url"
else
  # Find the latest green run that actually produced a sweep_bundle artifact
  # (build-and-certify runs on workflow_dispatch and on the nightly schedule, on ANY branch —
  # which is why the case count is checked below before anything is swapped in).
  note "Looking for the latest green build-and-certify run with a $ARTIFACT_NAME artifact ..."
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
fi

[ -n "$run_id" ] || die \
  "no green build-and-certify run with a $ARTIFACT_NAME artifact was found." \
  "Produce one first:" \
  "  make certify" \
  "(artifacts also expire after 7 days — re-run certify if the last one aged out)."

note "Using run $run_id ($run_url); expecting $EXPECT_CASES cases"

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
staged_count="$(find "$STAGING/cases" -maxdepth 1 -type d -name 'case_*' | wc -l | tr -d ' ')"
note "Bundle from run $run_id holds $staged_count cases (expected $EXPECT_CASES)."
[ "$staged_count" = "$EXPECT_CASES" ] || die \
  "the bundle from run $run_id holds $staged_count cases, but $EXPECT_CASES are expected." \
  "Refusing to restore it; your existing cases/ is untouched. Name the right run:" \
  "  make restore-cases RUN_ID=<green certify run id>"

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
note "Validating every case (make docker-validate-all, with failure classification) ..."
# Both kinds of failure still FAIL the restore, but the message says which it is: a defect in the
# restored CASES (the bundle is bad) versus an inconsistency in LOCAL results/ (the bundle is fine —
# fix results/, e.g. an unindexed trial record). See harness/validate_case.py LOCAL_RESULTS_CHECKS.
set +e
validate_out="$(make docker-validate-all VALIDATE_ARGS=--classify 2>&1)"
validate_rc=$?
set -e
printf '%s\n' "$validate_out"
if [ "$validate_rc" -ne 0 ]; then
  classification="$(printf '%s\n' "$validate_out" | grep '^CLASSIFICATION:' | tail -1)"
  case "$classification" in
    *"case=FAIL"*)
      die "validate-all FAILED on the RESTORED CASES themselves (see CASE DEFECTS above)." \
          "The bundle from run $run_id ($run_url) is not valid: do not use these cases." \
          "They are in cases/ for inspection; re-run restore-cases from a different green run." ;;
    *"case=OK"*"local_results=FAIL"*)
      die "validate-all FAILED, but NOT because of the bundle: all $case_count restored cases pass every" \
          "case check. The failures are inconsistencies in your LOCAL results/ (see LOCAL RESULTS" \
          "INCONSISTENT above) — fix results/ (e.g. index an unindexed trial record), not the cases." ;;
    *)
      die "validate-all FAILED and the failure could not be classified (see output above)." ;;
  esac
fi

# --- Summary -----------------------------------------------------------------
note ""
note "=== restore-cases summary ==="
note "  source run:  $run_id ($run_url)"
note "  case count:  $case_count (expected $EXPECT_CASES)"
note "  cases:       $case_count restored, validate-all PASSED"
note "  data:        regenerated + neutral family linked"
