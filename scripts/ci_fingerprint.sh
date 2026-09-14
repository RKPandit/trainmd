#!/usr/bin/env bash
# CI diagnostic fingerprint — printed in EVERY job so the next reference/stats
# divergence is immediately attributable: same DATA hashes + different numbers ⇒
# cross-microarch float reduction; different DATA hashes ⇒ data-fetch/encode drift.
set +e
echo "=== CI fingerprint ==="
echo "CPU model : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
echo "CPU flags : $(grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' \
    | grep -E '^(avx|avx2|avx512f|avx512dq|fma|sse4_1|sse4_2)$' | tr '\n' ' ')"
D=workloads/tabular_adult
if ls "$D"/.data/*.npy >/dev/null 2>&1; then
  echo "data hashes (prepared splits):"
  sha256sum "$D"/.data/X_train.npy "$D"/.data/y_train.npy \
            "$D"/.data/X_val.npy "$D"/.data/y_val.npy \
            "$D"/.hidden_data/X_test.npy "$D"/.hidden_data/y_test.npy 2>/dev/null
else
  echo "data hashes : (.data not prepared in this job)"
fi
echo "======================"
