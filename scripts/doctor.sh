#!/usr/bin/env bash
#
# make doctor — one-shot, READ-ONLY health check. The command to run when
# something feels wrong. Prints a status line per check; exits nonzero only if a
# hard problem (a FAIL) is found — WARNs never fail the command.
#
# It never writes to the tree, and one unavailable check (e.g. Docker down)
# degrades to UNKNOWN and the rest still run.
set -uo pipefail          # NOT -e: a failing check must not abort the report.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

IMAGE="${IMAGE:-trainmd:canonical}"
fails=0
ok()      { printf '  OK    %s\n'      "$*"; }
warnln()  { printf '  WARN  %s\n'      "$*"; }
failln()  { printf '  FAIL  %s\n'      "$*"; fails=$((fails+1)); }
unknown() { printf '  ????  %s\n'      "$*"; }

echo "== trainmd doctor =="

# 1. Working tree clean? ------------------------------------------------------
if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  ok "git working tree clean"
else
  n="$(git status --porcelain | wc -l | tr -d ' ')"
  warnln "git working tree has $n uncommitted change(s) — 'git status' to review"
fi

# 2. Cloud-sync duplicate files ("* 2.*" / "* 2") ----------------------------
dupes="$(find . -path ./.git -prune -o \( -name '* 2' -o -name '* 2.*' \) -print 2>/dev/null | sed 's|^\./||')"
gitdupes="$(find .git \( -name '* 2' -o -name '* 2.*' \) -print 2>/dev/null)"
combined="$(printf '%s\n%s\n' "$dupes" "$gitdupes" | grep -v '^$' || true)"
count="$(printf '%s\n' "$combined" | grep -c . || true)"
if [ "$count" = "0" ]; then
  ok "no '* 2' sync-duplicate files"
else
  if [ -n "$gitdupes" ]; then
    failln "$count '* 2' sync-duplicate file(s), INCLUDING inside .git/ (these corrupt git):"
  else
    warnln "$count '* 2' sync-duplicate file(s) (cloud-sync copies; safe to delete):"
  fi
  printf '%s\n' "$combined" | head -15 | while IFS= read -r f; do printf '          %s\n' "$f"; done
  [ "$count" -gt 15 ] && printf '          ... and %s more\n' "$((count-15))"
fi

# 3. Corrupted git refs / objects --------------------------------------------
fsck="$(git fsck --connectivity-only --no-progress 2>&1 | grep -iE 'error|corrupt|missing|fatal|bad ' || true)"
if [ -z "$fsck" ]; then
  ok "git refs/objects healthy (fsck clean)"
else
  failln "git fsck reported problems:"
  while IFS= read -r l; do printf '          %s\n' "$l"; done <<<"$fsck"
fi

# 4. Local case count vs design ----------------------------------------------
have="$(find cases -maxdepth 1 -type d -name 'case_*' 2>/dev/null | wc -l | tr -d ' ')"
design="$(uv run python -c 'from scripts.build_all_cases import case_design_tuples; print(len(case_design_tuples()))' 2>/dev/null || true)"
if [ -z "$design" ]; then
  unknown "case count: $have built (design count unavailable — could not import the design)"
elif [ "$have" = "0" ]; then
  warnln "no cases built (design is $design) — run 'make restore-cases' or 'make docker-build-all-cases'"
elif [ "$have" = "$design" ]; then
  ok "case count: $have built == $design in design"
else
  warnln "case count: $have built != $design in design (partial build?)"
fi

# 5. Cases canonical (platform stamp) — read ONLY via the evaluator container --
if [ "$have" = "0" ]; then
  unknown "platform stamp: no cases to check"
elif ! "$DOCKER" info >/dev/null 2>&1; then
  unknown "platform stamp: UNKNOWN (Docker not available)"
else
  rep="$("$DOCKER" run --rm --platform linux/amd64 -v "$PWD":/work -w /work "$IMAGE" \
          python -m harness.cases_platform_report 2>/dev/null || true)"
  if [ -z "$rep" ]; then
    unknown "platform stamp: UNKNOWN (could not run reporter — is the image built? 'make image')"
  else
    parsed="$(printf '%s' "$rep" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["non_canonical"], d["canonical"], ",".join(d["vendors"]))' 2>/dev/null || true)"
    if [ -z "$parsed" ]; then
      unknown "platform stamp: UNKNOWN (unexpected reporter output)"
    else
      nonc="${parsed%% *}"; rest="${parsed#* }"; canon="${rest%% *}"; vendors="${rest#* }"
      if [ "$nonc" = "0" ]; then
        ok "platform stamp: $canon/$((canon+nonc)) canonical (vendors: $vendors)"
      else
        failln "platform stamp: $nonc case(s) NON-canonical (vendors: $vendors) — rebuild on native amd64"
      fi
    fi
  fi
fi

# 6. SWEEP_BUNDLE_KEY set (env)? ---------------------------------------------
if [ -n "${SWEEP_BUNDLE_KEY:-}" ]; then
  ok "SWEEP_BUNDLE_KEY set (restore-cases can decrypt)"
else
  warnln "SWEEP_BUNDLE_KEY not set — 'make restore-cases' will stop; export it to decrypt bundles"
fi

# 7. Both provider API keys set? ---------------------------------------------
keymiss=()
[ -n "${ANTHROPIC_API_KEY:-}" ] || keymiss+=("ANTHROPIC_API_KEY")
[ -n "${OPENAI_API_KEY:-}" ]    || keymiss+=("OPENAI_API_KEY")
if [ "${#keymiss[@]}" -eq 0 ]; then
  ok "provider API keys set (ANTHROPIC_API_KEY, OPENAI_API_KEY)"
else
  warnln "provider API key(s) not set: ${keymiss[*]} — 'make sweep-run' needs both"
fi

# 8. main up to date with origin? --------------------------------------------
local_main="$(git rev-parse main 2>/dev/null || true)"
remote_main="$(git ls-remote origin -h refs/heads/main 2>/dev/null | cut -f1)"
if [ -z "$local_main" ] || [ -z "$remote_main" ]; then
  unknown "main vs origin: UNKNOWN (could not reach origin or no local main)"
elif [ "$local_main" = "$remote_main" ]; then
  ok "main up to date with origin/main"
else
  warnln "local main != origin/main — 'git fetch' then rebase/merge"
fi

# 9. Last CI status on main ---------------------------------------------------
ci="$("$GH" run list --branch main --limit 1 \
       --json conclusion,status,workflowName,url \
       --jq '"\(.[0].status)\t\(.[0].conclusion)\t\(.[0].workflowName)\t\(.[0].url)"' 2>/dev/null || true)"
if [ -z "$ci" ] || [ "$ci" = "$(printf '\t\t\t')" ]; then
  unknown "last CI on main: UNKNOWN (gh unavailable/unauthenticated)"
else
  st="$(cut -f1 <<<"$ci")"; concl="$(cut -f2 <<<"$ci")"; url="$(cut -f4 <<<"$ci")"
  if [ "$st" != "completed" ]; then
    warnln "last CI on main: $st (in flight) — $url"
  elif [ "$concl" = "success" ]; then
    ok "last CI on main: success — $url"
  else
    failln "last CI on main: $concl — $url"
  fi
fi

echo "===================="
if [ "$fails" -eq 0 ]; then
  echo "doctor: no hard failures."
else
  echo "doctor: $fails FAIL(s) above."
  exit 1
fi
