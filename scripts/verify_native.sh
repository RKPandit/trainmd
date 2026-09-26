#!/usr/bin/env bash
#
# scripts/verify_native.sh NAME CASES_RUN — memoized recovery verification, NATIVELY on AMD EPYC
# (HYPOTHESES, Stage 4 Part 1 pre-run addendum). Run after the agents phase:
#
#   1. export the DISTINCT repaired configurations (+ a 20-trial spot-check sample) in the canonical
#      container — no trial records are shipped;
#   2. encrypt that list with $SWEEP_BUNDLE_KEY and push it on a branch verify-NAME (via a temporary
#      git worktree: your checkout is never touched);
#   3. dispatch CI task verify-native on that branch (re-dispatching until an AMD runner is assigned),
#      which trains each distinct config once, re-runs the spot-check FRESH and fails on any difference;
#   4. download + decrypt the memo and import it into verify_memo/ (AuthenticAMD entries only).
#
# Then:  make sweep-verify NAME=NAME VERIFY_MEMO=require   (reads the memo; never trains locally)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

NAME="${1:?usage: verify_native.sh NAME CASES_RUN}"
CASES_RUN="${2:?usage: verify_native.sh NAME CASES_RUN   (the certify run your cases were restored from)}"
require_cmd "$GH" gh "Install the GitHub CLI and run 'gh auth login'."
require_cmd "$GPG" gpg
require_env SWEEP_BUNDLE_KEY "It encrypts the config list and decrypts the memo (the repo secret's value)."

TMP=".verify_tmp"; rm -rf "$TMP"; mkdir -p "$TMP"
JOBS_GPG="sweeps/${NAME}_verify_jobs.json.gpg"
BRANCH="verify-${NAME}"

note "Exporting the distinct repaired configurations of '$NAME' (canonical container) ..."
make docker-verify-export NAME="$NAME" OUT="$TMP/verify_jobs.json"
"$GPG" --batch --yes --symmetric --cipher-algo AES256 --passphrase "$SWEEP_BUNDLE_KEY" \
  -o "$TMP/jobs.gpg" "$TMP/verify_jobs.json"
rm -f "$TMP/verify_jobs.json"

note "Pushing the encrypted list on branch $BRANCH (temporary worktree) ..."
WT="$(mktemp -d)"
git worktree add -q --detach "$WT" HEAD
( cd "$WT" && git checkout -q -B "$BRANCH" && mkdir -p sweeps && cp "$OLDPWD/$TMP/jobs.gpg" "$JOBS_GPG" \
  && git add "$JOBS_GPG" && git commit -q -m "verify(native): encrypted distinct-config list for $NAME" \
  && git push -q -f origin "$BRANCH" )
git worktree remove --force "$WT"

run_id=""
for attempt in $(seq 1 12); do
  before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$GH" workflow run ci.yml --ref "$BRANCH" -f task=verify-native -f sweep="$NAME" -f cases_run="$CASES_RUN"
  rid=""
  for _ in $(seq 1 30); do
    sleep 10
    rid="$("$GH" run list --workflow ci.yml --branch "$BRANCH" --event workflow_dispatch --limit 5 \
            --json databaseId,createdAt -q "[.[]|select(.createdAt >= \"$before\")][0].databaseId")"
    [ -n "$rid" ] && [ "$rid" != "null" ] && break
  done
  [ -n "$rid" ] && [ "$rid" != "null" ] || die "could not find the dispatched verify-native run."
  note "attempt $attempt: run $rid — waiting for the AMD check ..."
  amd=""
  while [ -z "$amd" ]; do
    sleep 20
    amd="$("$GH" run view "$rid" --json jobs -q '.jobs[]|select(.name=="verify-native")|.steps[]|select(.name|startswith("Require an AMD"))|.conclusion' 2>/dev/null || true)"
  done
  if [ "$amd" = "success" ]; then run_id="$rid"; break; fi
  note "attempt $attempt: runner was not AMD — re-dispatching."
done
[ -n "$run_id" ] || die "12 dispatches without an AMD runner; try again later."

note "Run $run_id is on AMD — waiting for it to finish ..."
until [ "$("$GH" run view "$run_id" --json status -q .status)" = "completed" ]; do sleep 60; done
concl="$("$GH" run view "$run_id" --json conclusion -q .conclusion)"
[ "$concl" = "success" ] || die "verify-native run $run_id concluded '$concl' (a key mismatch or a SPOT-CHECK" \
  "difference fails the run — see its log). Nothing was imported."

"$GH" run download "$run_id" -n verify_memo -D "$TMP"
"$GPG" --batch --yes --quiet --decrypt --passphrase "$SWEEP_BUNDLE_KEY" -o "$TMP/memo.tar.gz" "$TMP/verify_memo.tar.gz.gpg"
tar -xzf "$TMP/memo.tar.gz" -C "$TMP"
${VERIFY_PY:-uv run python} -m harness.verify_memo import --dir "$TMP/verify_memo_out"
${VERIFY_PY:-uv run python} - "$TMP/verify_memo_out/SUMMARY.json" "$run_id" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print(f"=== verify-native summary (run {sys.argv[2]}) ===")
print(f"  platform:      {s['platform']['vendor']} / {s['platform']['model']}")
print(f"  trials:        {s['n_trials']} to verify -> {s['n_distinct']} DISTINCT configurations trained")
print(f"  spot-check:    {s['spot_check_identical']}/{len(s['spot_checks'])} fresh re-runs identical to the memo")
PY
rm -rf "$TMP"
if [ -d "results_release/$NAME" ]; then
  note "'$NAME' is a PUBLISHED sweep: its recovery verdicts are not rewritten (sweep-verify refuses);" \
       "read native values from verify_memo/ instead."
else
  note "Next:  make sweep-verify NAME=$NAME VERIFY_MEMO=require"
fi
