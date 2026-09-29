#!/usr/bin/env bash
# Part 3 two-runner byte-identity check, one runner's half (DECISIONS 2026-09-27): prepare + verify the pinned
# Fashion-MNIST data, train the compact CNN on a few seeds, and fingerprint weights + metrics. Run INSIDE the
# canonical container (thread caps set there). Usage: scripts/image_repro.sh OUT_JSON [SEEDS...]
set -euo pipefail
out_json="$1"; shift
seeds=("${@:-0 1 2}")
W=workloads/image_fmnist
python "$W/data_prep.py" --workload-dir "$W"
cpu="$(awk -F: '/^vendor_id/{gsub(/[ \t]/,"",$2); v=$2} /^model name/{sub(/^[ \t]+/,"",$2); m=$2} END{print v" / "m}' /proc/cpuinfo)"
dirs=()
for s in ${seeds[@]}; do
  d="$W/output/repro_seed$s"
  rm -rf "$d"
  python "$W/train.py" --seed "$s" --output-dir "$d"
  dirs+=("$d")
done
python scripts/fingerprint_training.py fingerprint "${dirs[@]}" --out "$out_json" --host-note "$cpu"
