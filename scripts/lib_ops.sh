# shellcheck shell=bash
# Shared helpers for the operator convenience scripts (certify / restore-cases /
# sweep / doctor). Sourced, never executed. Every script that sources this runs
# under `set -euo pipefail`.
#
# External tools are indirected through env vars (GH, GPG, DOCKER, TAR,
# CAFFEINATE) so the test suite can inject fakes without a network, a container,
# or a real GitHub. Defaults are the real binaries, so normal use is unchanged.

GH="${GH:-gh}"
GPG="${GPG:-gpg}"
DOCKER="${DOCKER:-docker}"
TAR="${TAR:-tar}"
CAFFEINATE="${CAFFEINATE:-caffeinate}"

# die MESSAGE...  — print an actionable error to stderr and exit 1.
die() {
  printf 'error: %s\n' "$1" >&2
  shift || true
  for line in "$@"; do printf '       %s\n' "$line" >&2; done
  exit 1
}

warn() { printf 'WARN  %s\n' "$*" >&2; }
note() { printf '%s\n' "$*"; }

# require_cmd BINARY HUMAN_NAME [INSTALL_HINT]
require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die \
    "required tool '${2:-$1}' not found on PATH." "${3:-Install it and retry.}"
}

# require_env VAR HINT...  — fail if the named env var is empty.
require_env() {
  local var="$1"; shift
  if [ -z "${!var:-}" ]; then
    die "$var is not set." "$@"
  fi
}
