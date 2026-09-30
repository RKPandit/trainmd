#!/usr/bin/env bash
#
# make restore-image-cases — add the 230 certified IMAGE cases (Part 3; CI task image-certify) to a local cases/
# that already holds workload 1's certified 200 (run `make restore-cases` first). IMAGE_RUN=<id> names the
# image-certify run (default: the latest green run with an image_bundle artifact).
#
# Checked in STAGING before anything is touched: the bundle decrypts with $SWEEP_BUNDLE_KEY, its
# IMAGE_BUNDLE_META.txt says AuthenticAMD, every hidden card's build_cpu is AuthenticAMD, it holds exactly the
# image design (case_0201–case_0430, scripts/check_image_bundle.py), and the local registry holds exactly
# workload 1's ids. Then the image case dirs and registry entries are added (replacing any earlier image cases);
# on failure the previous state is restored. Finally the image data is regenerated, the neutral families linked,
# and every case validated.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib_ops.sh
. "$SCRIPT_DIR/lib_ops.sh"
cd "${TRAINMD_REPO_ROOT:-$SCRIPT_DIR/..}"

WORKFLOW="${CERTIFY_WORKFLOW:-ci.yml}"
ARTIFACT_NAME="image_bundle"
CIPHERTEXT="image_bundle.tar.gz.gpg"
REQUIRE_VENDOR="${REQUIRE_VENDOR:-AuthenticAMD}"

require_cmd "$GH" gh "Install the GitHub CLI (https://cli.github.com) and run 'gh auth login'."
require_cmd "$GPG" gpg
require_cmd "$TAR" tar
require_env SWEEP_BUNDLE_KEY "The passphrase of the image-certify run's bundle (the repo secret SWEEP_BUNDLE_KEY):" \
  "  export SWEEP_BUNDLE_KEY=..."
[ -f cases/registry.hidden.yaml ] || die "no local cases/ — restore workload 1's cases first:  make restore-cases"

run_id="${IMAGE_RUN:-}"
if [ -z "$run_id" ]; then
  note "Looking for the latest green run with an $ARTIFACT_NAME artifact ..."
  while IFS=$'\t' read -r id _url; do
    [ -n "$id" ] || continue
    if "$GH" api "repos/{owner}/{repo}/actions/runs/$id/artifacts" --jq '.artifacts[].name' 2>/dev/null \
         | grep -qx "$ARTIFACT_NAME"; then run_id="$id"; break; fi
  done < <("$GH" run list --workflow "$WORKFLOW" --status success --limit 40 \
             --json databaseId,url --jq '.[] | "\(.databaseId)\t\(.url)"' 2>/dev/null || true)
fi
[ -n "$run_id" ] || die "no green image-certify run with an $ARTIFACT_NAME artifact (dispatch task image-certify)."
note "Using image-certify run $run_id"

rm -f "$CIPHERTEXT"
"$GH" run download "$run_id" -n "$ARTIFACT_NAME" -D . || die "failed to download $ARTIFACT_NAME from run $run_id."
STAGING="$(mktemp -d ./.restore_image_staging.XXXXXX)"
ROLLBACK=""
cleanup() {
  if [ -n "$ROLLBACK" ]; then
    note "Rolling back ..."
    python3 - "$STAGING" <<'PY' || true
import sys, shutil, pathlib
st = pathlib.Path(sys.argv[1])
for d in (st / "added.txt").read_text().split() if (st / "added.txt").exists() else []:
    shutil.rmtree(pathlib.Path("cases") / d, ignore_errors=True)
for d in (st / "old_image").glob("case_*"):
    shutil.move(str(d), "cases/" + d.name)
if (st / "registry.backup.yaml").exists():
    shutil.copy2(st / "registry.backup.yaml", "cases/registry.hidden.yaml")
PY
  fi
  rm -rf "$STAGING" "$CIPHERTEXT" 2>/dev/null || true
}
trap cleanup EXIT

"$GPG" --batch --yes --quiet --decrypt --passphrase "$SWEEP_BUNDLE_KEY" -o "$STAGING/b.tar.gz" "$CIPHERTEXT" \
  || die "decryption failed — \$SWEEP_BUNDLE_KEY does not match the secret used by run $run_id."
"$TAR" -xzf "$STAGING/b.tar.gz" -C "$STAGING" || die "the bundle from run $run_id is corrupt."
meta="$STAGING/IMAGE_BUNDLE_META.txt"
[ -f "$meta" ] || die "the bundle carries no IMAGE_BUNDLE_META.txt; refusing. Your cases/ is untouched."
grep -qx "build_cpu_vendor=$REQUIRE_VENDOR" "$meta" || die "the bundle was not built on $REQUIRE_VENDOR; refusing."
off_cpu="$(for c in "$STAGING"/cases/case_*/hidden/card.hidden.yaml; do
             grep -q "^build_cpu: $REQUIRE_VENDOR " "$c" || basename "$(dirname "$(dirname "$c")")"; done | head -5)"
[ -z "$off_cpu" ] || die "cases not built on $REQUIRE_VENDOR: $off_cpu. Refusing; your cases/ is untouched."
python3 scripts/check_image_bundle.py "$STAGING/cases" || die "the bundle is not the image design; refusing."
python3 - <<'PY' || die "the local registry is not exactly workload 1's certified design; run make restore-cases first."
import sys, yaml
sys.path.insert(0, ".")
from scripts.build_image_shard import allocation, image_ids
alloc = allocation(); img = set(image_ids())
reg = yaml.safe_load(open("cases/registry.hidden.yaml")) or {}
w1 = {k: v for k, v in reg.items() if k not in img}
want = {k: v for k, v in alloc.items() if k not in img}
sys.exit(0 if w1 == want else 1)
PY

# --- merge (rollback-protected) -------------------------------------------------------------------------------
cp cases/registry.hidden.yaml "$STAGING/registry.backup.yaml"
mkdir -p "$STAGING/old_image"
ROLLBACK=1
for d in cases/case_*; do
  n="$(basename "$d")"
  [ -d "$STAGING/cases/$n" ] && mv "$d" "$STAGING/old_image/$n"
done
: > "$STAGING/added.txt"
for d in "$STAGING"/cases/case_*; do
  n="$(basename "$d")"; mv "$d" "cases/$n"; echo "$n" >> "$STAGING/added.txt"
done
python3 - "$STAGING/cases/registry.hidden.yaml" <<'PY'
import sys, yaml, os
img = yaml.safe_load(open(sys.argv[1])) or {}
reg = yaml.safe_load(open("cases/registry.hidden.yaml")) or {}
reg = {k: v for k, v in reg.items() if k not in img}
reg.update(img)
tmp = "cases/registry.hidden.yaml.tmp"
open(tmp, "w").write(yaml.dump(reg, default_flow_style=False, sort_keys=True))
os.replace(tmp, "cases/registry.hidden.yaml")
PY

note "Regenerating the image data and linking the neutral families ..."
make docker-data WORKLOAD=image_fmnist
make link-neutral-workload
note "Validating every case (workload 1 + image) ..."
make docker-validate-all || die "validate-all FAILED after adding the image cases (rolled back)."
ROLLBACK=""
note ""
note "=== restore-image-cases: $(wc -l < "$STAGING/added.txt" | tr -d ' ') image cases added from run $run_id; validate-all PASSED ==="
