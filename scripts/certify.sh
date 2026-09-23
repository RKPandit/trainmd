#!/usr/bin/env bash
#
# make certify — dispatch the build-and-certify workflow on main, print the run
# id + URL, and poll to completion with a clear PASS/FAIL line.
#
# Fails loudly UP FRONT if SWEEP_BUNDLE_KEY is not a repo secret: build-and-certify
# fail-closes at its packaging step without it (it refuses to upload plaintext
# hidden/ grading keys), so there is no point spending ~45 min to hit that wall.
#
# Idempotent: it only dispatches and watches — it writes nothing to the tree and
# leaves no state behind. Re-running starts a fresh run.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

WORKFLOW="${CERTIFY_WORKFLOW:-ci.yml}"
REF="${CERTIFY_REF:-main}"
GATE_SCOPE="${GATE_SCOPE:-subset}"   # subset (default) | full

require_cmd "$GH" gh "Install the GitHub CLI (https://cli.github.com) and run 'gh auth login'."

# --- Precondition: SWEEP_BUNDLE_KEY must be a REPO SECRET ---------------------
if ! secrets="$("$GH" secret list 2>/dev/null)"; then
  die "could not list repo secrets via 'gh secret list'." \
      "Check 'gh auth status' and that you have admin on this repo."
fi
if ! grep -q '^SWEEP_BUNDLE_KEY[[:space:]]' <<<"$secrets"; then
  die "SWEEP_BUNDLE_KEY is not set as a repo secret." \
      "build-and-certify fail-closes at packaging without it (it will not upload" \
      "plaintext hidden/ grading keys). Set it first:" \
      "  gh secret set SWEEP_BUNDLE_KEY"
fi

# --- Dispatch ----------------------------------------------------------------
before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
note "Dispatching $WORKFLOW on $REF (gate_scope=$GATE_SCOPE) ..."
"$GH" workflow run "$WORKFLOW" --ref "$REF" -f gate_scope="$GATE_SCOPE"

# --- Find the run we just created (newest dispatch on this ref, created >= before)
run_id=""; run_url=""
for _ in $(seq 1 30); do
  row="$("$GH" run list --workflow "$WORKFLOW" --event workflow_dispatch \
          --branch "$REF" --limit 1 \
          --json databaseId,url,createdAt \
          --jq '.[0] | "\(.databaseId)\t\(.url)\t\(.createdAt)"' 2>/dev/null || true)"
  if [ -n "$row" ]; then
    created="$(cut -f3 <<<"$row")"
    if [[ "$created" > "$before" || "$created" == "$before" ]]; then
      run_id="$(cut -f1 <<<"$row")"
      run_url="$(cut -f2 <<<"$row")"
      break
    fi
  fi
  sleep 3
done

[ -n "$run_id" ] || die "dispatched, but could not locate the new run after 90s." \
  "Check: gh run list --workflow $WORKFLOW --event workflow_dispatch --branch $REF"

note "run id:  $run_id"
note "run url: $run_url"

# --- Poll to completion; PASS/FAIL from the run's own exit status -------------
if "$GH" run watch "$run_id" --exit-status --interval "${CERTIFY_POLL_INTERVAL:-15}"; then
  note "CERTIFY: PASS  ($run_url)"
else
  note "CERTIFY: FAIL  ($run_url)"
  exit 1
fi
