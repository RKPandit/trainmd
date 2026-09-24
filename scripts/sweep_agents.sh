#!/usr/bin/env bash
#
# make sweep-run NAME=<name> [MAX_COST=<usd>] — the paid agents phase.
#
# Checks BOTH provider API keys up front (naming whichever is missing), shows the
# plan's own cost estimate next to the cap, and refuses to start a run the cap
# cannot cover (rather than stopping partway). Wraps the run in `caffeinate` on
# macOS so a long sweep is not interrupted by sleep.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

NAME="${1:?usage: sweep_agents.sh NAME MAX_COST}"
MAX_COST="${2:?usage: sweep_agents.sh NAME MAX_COST}"
PLAN="sweeps/${NAME}_plan.yaml"

# --- Both API keys, up front, naming whichever is missing --------------------
missing=()
[ -n "${ANTHROPIC_API_KEY:-}" ] || missing+=("ANTHROPIC_API_KEY")
[ -n "${OPENAI_API_KEY:-}" ]    || missing+=("OPENAI_API_KEY")
if [ "${#missing[@]}" -ne 0 ]; then
  die "missing API key(s): ${missing[*]}" \
      "The cross-provider agents phase needs BOTH keys. Export the missing one(s) and retry."
fi

# --- Plan must exist ---------------------------------------------------------
[ -f "$PLAN" ] || die "plan not found: $PLAN" \
  "Create and commit it first:" \
  "  python -m harness.sweep plan --name $NAME"

# --- Show the plan's own estimate next to the cap; refuse an undersized cap ---
est="$(${SWEEP_PY:-uv run python} -c "import yaml; print(yaml.safe_load(open('$PLAN'))['header']['cost_estimate']['per_cell_total_usd'])")"
note "plan estimates \$$est (agents phase, expected total); cap is \$$MAX_COST"
if awk "BEGIN{exit !($MAX_COST < $est)}"; then
  if [ "${CONFIRM:-}" = "1" ]; then
    warn "cap \$$MAX_COST is below the plan estimate \$$est — proceeding (CONFIRM=1); the run will stop at the cap."
  else
    die "cap \$$MAX_COST is below the plan estimate \$$est." \
        "Raise it:   make sweep-run NAME=$NAME MAX_COST=$est" \
        "Or run capped on purpose:   make sweep-run NAME=$NAME MAX_COST=$MAX_COST CONFIRM=1"
  fi
fi

# --- Run (caffeinate on macOS; plain elsewhere) ------------------------------
prefix=()
if command -v "$CAFFEINATE" >/dev/null 2>&1; then
  prefix=("$CAFFEINATE" -i)
fi
note "Starting agents phase for '$NAME' (cap \$$MAX_COST) ..."
exec "${prefix[@]}" uv run --extra llm python -m harness.sweep run \
  --name "$NAME" --phase agents --max-cost-usd "$MAX_COST"
