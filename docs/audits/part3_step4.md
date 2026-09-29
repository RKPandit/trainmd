# Part 3 step 4 — AMD proofs and image benign qualification

> CI run 36567921113 (dispatch task `image-step4`, branch `part3-step4` at 3be25d4). Every job on AuthenticAMD (three
> qualification jobs first landed on Intel, were refused by the AMD guard, and were re-run). DECISIONS 2026-09-29.

## Operator proofs (`tests/test_image_operators.py -m image_native`; the evaluator's verification on seeds 100–102)

| shard | result | CPU |
|---|---|---|
| clean config passes verification | 1 passed | AMD EPYC 7763 |
| pixel-tag leakage (3 strengths) + neutral twin identical | 7 passed | AMD EPYC 7763 |
| label flip (3 strengths) | 3 passed | AMD EPYC 7763 |
| decay unit (3 strengths) | 3 passed | AMD EPYC 9V74 |
| confident subset + neutral (6 fail verification; neutral identical; checkpoint bitwise-identical to clean, 6/6) | 13 passed | AMD EPYC 7763 |
| channel mismatch (3 fail verification; crash block = lines 2–37, 3/3) | 6 passed | AMD EPYC 9V74 |

Clean path (`image-clean-path`, EPYC 7763): the 30-seed reference re-run with the gated dropout / grad-clip paths
reproduces the committed band EXACTLY.

## Benign qualification (dev seeds 0–29; `scripts/qualify_image_benign.py`, STAGE4 4.0.6's test)

| type | form | qualified | mean Δ hidden (σ_ref) | 90% CI | SD ratio | visible shift (σ_vis) | byte-identical to clean | CPU |
|---|---|---|---|---|---|---|---|---|
| bs256 | changed | ✅ | −0.618 | [−0.986, −0.249] | 1.345 | −0.578 | 0/30 | EPYC 9V74 |
| ep10 | changed | ✅ | +0.140 | [−0.128, +0.409] | 0.947 | +0.106 | 0/30 | EPYC 7763 |
| wd1e3 | changed | ✅ | +0.012 | [−0.102, +0.125] | 1.089 | +0.032 | 0/30 | EPYC 9V45 |
| do01 | added | ✅ | +0.127 | [−0.060, +0.314] | 0.913 | +0.079 | 0/30 | EPYC 7763 |
| lr004 | changed | ✅ | +0.370 | [+0.142, +0.597] | 0.827 | +0.223 | 0/30 | EPYC 7763 |
| clip1 | added | ✅ | +0.198 | [−0.105, +0.502] | 0.945 | +0.076 | **0/30** | EPYC 9V45 |
| schedule_noop | added | ✅ | +0.000 | [+0.000, +0.000] | 1.000 | +0.000 | 30/30 | EPYC 7763 |

**Finding (differs from the design):** gradient clipping at 1.0 is BINDING on the image workload (0/30 runs
byte-identical to clean), unlike workload 1, where it was non-binding (max pre-clip norm ≈ 0.59). It still qualifies
(the change does not degrade the model), but on this workload clip1 is not the "one config line, byte-identical"
control. The schedule no-op is, 30/30, so the "new key, no effect" role is covered by it.
