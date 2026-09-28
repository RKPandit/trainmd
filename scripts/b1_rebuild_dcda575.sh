#!/usr/bin/env bash
# Close the B1 provenance question (DECISIONS 2026-09-28): rebuild the 20 healthy controls EXACTLY as commit
# dcda575 (2026-09-17, the commit that published B1's control FPR 1/20) built them — its own Dockerfile,
# data prep and harness.build_case — on an AMD runner, then run dcda575's OWN B1 (every-epoch) over them and
# count band positions every-epoch vs final-epoch from the raw metrics. Nothing from the current tree is used
# to build or score. Usage (repo root, native amd64): scripts/b1_rebuild_dcda575.sh OUT_DIR
set -euo pipefail
out="$(realpath -m "$1")"; mkdir -p "$out"
REF=dcda575cc2c8e32022db8954c8a9aff7ac594217
git worktree add --detach old "$REF"
cd old
git log --oneline -1 | tee "$out/ref.txt"
docker build --platform linux/amd64 -t trainmd:canonical . 2>&1 | tail -3
make docker-data
for s in $(seq 50 69); do
  make docker-build-case OPERATOR=control.healthy.v1 STRENGTH=mild SEED="$s" 2>&1 | tail -1
done
RUN=(docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/work -w /work trainmd:canonical)
# (1) the published instrument, as it stood at dcda575
"${RUN[@]}" python -m harness.baselines --baseline b1 --cases 'cases/case_*' | tee "$out/b1_dcda575_cli.txt"
# (2) raw band positions from each case's own agent-visible metrics and public band
docker run -i --rm --platform linux/amd64 --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/work -w /work trainmd:canonical python - <<'PY' | tee "$out/band_positions.txt"
import glob, json, yaml
from pathlib import Path
rows = []
for cd in sorted(glob.glob("cases/case_*")):
    cd = Path(cd)
    if not (cd / "card.public.yaml").exists():
        continue
    band = yaml.safe_load((cd / "card.public.yaml").read_text())["reference_visible_metric"]
    lo, hi = band["mean"] - 2 * band["std"], band["mean"] + 2 * band["std"]
    hid = yaml.safe_load((cd / "hidden" / "card.hidden.yaml").read_text())
    ser = [json.loads(l)["metric_visible_val_acc"] for l in (cd / "workspace/run_output/metrics.jsonl").read_text().splitlines()
           if l.strip() and json.loads(l).get("end_of_epoch")]
    anyo = any(not (lo <= v <= hi) for v in ser)
    fin = not (lo <= ser[-1] <= hi)
    rows.append((cd.name, hid.get("operator_id"), hid.get("seed"), len(ser), anyo, fin, round(ser[-1], 6)))
    print(f"{cd.name} {hid.get('operator_id')} seed={hid.get('seed')} epochs={len(ser)} any_epoch_out={anyo} "
          f"final_epoch_out={fin} final={ser[-1]:.6f} band=[{lo:.6f},{hi:.6f}]")
h = [r for r in rows if r[1] == "control.healthy.v1"]
print(f"SUMMARY healthy={len(h)} any_epoch_out={sum(r[4] for r in h)} final_epoch_out={sum(r[5] for r in h)}")
PY
