# Part 3 — graded-strength calibration of the image_fmnist faults (development seeds 0–5)

> Generated from the CI artifacts (runs 36510935977, 36513288844, 36516996997; every job on AuthenticAMD — the CPU of each job is listed). `scripts/calibrate_image_faults.py`; ladder rule stated before running (mild = weakest candidate passing every bar on every seed, severe = strongest passing, moderate = closest to their midpoint; graded iff strictly monotone). DECISIONS 2026-09-28.

Bars from the adopted reference: positive symptom visible ≥ **0.921565**; degradation hidden ≤ **0.850111** (every seed); metric tier also mean hidden ≥ tolerance 0.868318.

## Corner-tag leakage (silent, positive symptom)

| candidate | pass | passes | detail | visible min–max (mean) | hidden min–max (mean) | CPU |
|---|---|---|---|---|---|---|
| noise=0.7 | first pass | — | visible>=bar 0/6, hidden<=bar 1/6 | 0.8860–0.8994 (0.8949) | 0.8466–0.8902 (0.8691) | AMD EPYC 7763 64-Core Processor |
| noise=0.6 | first pass | — | visible>=bar 0/6, hidden<=bar 3/6 | 0.8962–0.9066 (0.9010) | 0.8164–0.8694 (0.8495) | AMD EPYC 7763 64-Core Processor |
| noise=0.5 | first pass | — | visible>=bar 0/6, hidden<=bar 4/6 | 0.9024–0.9150 (0.9082) | 0.8346–0.8648 (0.8452) | AMD EPYC 7763 64-Core Processor |
| noise=0.4 | first pass | — | visible>=bar 1/6, hidden<=bar 4/6 | 0.9076–0.9238 (0.9164) | 0.7870–0.8560 (0.8233) | AMD EPYC 7763 64-Core Processor |
| noise=0.3 | first pass | — | visible>=bar 5/6, hidden<=bar 6/6 | 0.9204–0.9352 (0.9311) | 0.7268–0.8090 (0.7777) | AMD EPYC 7763 64-Core Processor |
| noise=0.2 | first pass | ✅ | visible>=bar 6/6, hidden<=bar 6/6 | 0.9382–0.9494 (0.9423) | 0.7076–0.7916 (0.7599) | AMD EPYC 7763 64-Core Processor |
| noise=0.15 | SECOND pass | ✅ | visible>=bar 6/6, hidden<=bar 6/6 | 0.9526–0.9574 (0.9560) | 0.6688–0.7590 (0.7319) | AMD EPYC 9V74 80-Core Processor |
| noise=0.1 | SECOND pass | ✅ | visible>=bar 6/6, hidden<=bar 6/6 | 0.9560–0.9672 (0.9617) | 0.6416–0.7648 (0.7111) | AMD EPYC 9V74 80-Core Processor |
| noise=0.05 | SECOND pass | ✅ | visible>=bar 6/6, hidden<=bar 6/6 | 0.9674–0.9786 (0.9719) | 0.5688–0.7198 (0.6242) | AMD EPYC 9V74 80-Core Processor |

**Ladder:** {"graded": true, "mild": "noise=0.2", "moderate": "noise=0.15", "severe": "noise=0.05", "mean_effect": {"noise=0.2": 0.056267, "noise=0.15": 0.069967, "noise=0.05": 0.0859}, "reason": "strictly monotone mean effect"}

## Partner-label swaps (silent, degradation)

| candidate | pass | passes | detail | visible min–max (mean) | hidden min–max (mean) | CPU |
|---|---|---|---|---|---|---|
| fraction=0.1 | first pass | — | hidden<=bar 1/6 | 0.8464–0.8882 (0.8687) | 0.8400–0.8786 (0.8616) | AMD EPYC 7763 64-Core Processor |
| fraction=0.15 | first pass | — | hidden<=bar 3/6 | 0.8512–0.8776 (0.8611) | 0.8428–0.8726 (0.8547) | AMD EPYC 7763 64-Core Processor |
| fraction=0.2 | first pass | — | hidden<=bar 5/6 | 0.8056–0.8678 (0.8407) | 0.8060–0.8688 (0.8396) | AMD EPYC 7763 64-Core Processor |
| fraction=0.25 | first pass | ✅ | hidden<=bar 6/6 | 0.7864–0.8274 (0.8010) | 0.7876–0.8188 (0.7990) | AMD EPYC 7763 64-Core Processor |
| fraction=0.3 | first pass | ✅ | hidden<=bar 6/6 | 0.6996–0.8018 (0.7594) | 0.6942–0.7964 (0.7558) | AMD EPYC 7763 64-Core Processor |
| fraction=0.35 | SECOND pass | ✅ | hidden<=bar 6/6 | 0.6516–0.7468 (0.7032) | 0.6508–0.7536 (0.7010) | AMD EPYC 7763 64-Core Processor |
| fraction=0.4 | SECOND pass | ✅ | hidden<=bar 6/6 | 0.6192–0.6564 (0.6374) | 0.6120–0.6554 (0.6376) | AMD EPYC 7763 64-Core Processor |
| fraction=0.45 | SECOND pass | ✅ | hidden<=bar 6/6 | 0.5208–0.6008 (0.5524) | 0.5228–0.5920 (0.5497) | AMD EPYC 7763 64-Core Processor |

**Ladder:** {"graded": true, "mild": "fraction=0.25", "moderate": "fraction=0.35", "severe": "fraction=0.45", "mean_effect": {"fraction=0.25": 0.086494, "fraction=0.35": 0.184527, "fraction=0.45": 0.335794}, "reason": "strictly monotone mean effect"}

## LR schedule counted in steps (silent, degradation)

| candidate | pass | passes | detail | visible min–max (mean) | hidden min–max (mean) | CPU |
|---|---|---|---|---|---|---|
| gamma=0.98 | single pass | ✅ | hidden<=bar 6/6 | 0.8396–0.8518 (0.8458) | 0.8332–0.8418 (0.8370) | AMD EPYC 7763 64-Core Processor |
| gamma=0.97 | single pass | ✅ | hidden<=bar 6/6 | 0.8186–0.8374 (0.8273) | 0.8064–0.8268 (0.8148) | AMD EPYC 7763 64-Core Processor |
| gamma=0.95 | single pass | ✅ | hidden<=bar 6/6 | 0.7788–0.8090 (0.7986) | 0.7628–0.7930 (0.7814) | AMD EPYC 7763 64-Core Processor |
| gamma=0.9 | single pass | ✅ | hidden<=bar 6/6 | 0.7168–0.7588 (0.7444) | 0.7150–0.7448 (0.7328) | AMD EPYC 7763 64-Core Processor |
| gamma=0.8 | single pass | ✅ | hidden<=bar 6/6 | 0.5962–0.6726 (0.6436) | 0.6032–0.6614 (0.6361) | AMD EPYC 7763 64-Core Processor |

**Ladder:** {"graded": true, "mild": "gamma=0.98", "moderate": "gamma=0.9", "severe": "gamma=0.8", "mean_effect": {"gamma=0.98": 0.048527, "gamma=0.9": 0.15276, "gamma=0.8": 0.249427}, "reason": "strictly monotone mean effect"}

## Reported-subset metric (metric tier)

| candidate | pass | passes | detail | visible min–max (mean) | hidden min–max (mean) | CPU |
|---|---|---|---|---|---|---|
| fraction=0.95 | single pass | — | visible>=bar 0/6, mean hidden >= tolerance | 0.9099–0.9202 (0.9139) | 0.8802–0.8972 (0.8893) | AMD EPYC 9V74 80-Core Processor |
| fraction=0.9 | single pass | ✅ | visible>=bar 6/6, mean hidden >= tolerance | 0.9284–0.9378 (0.9331) | 0.8802–0.8972 (0.8893) | AMD EPYC 9V74 80-Core Processor |
| fraction=0.85 | single pass | ✅ | visible>=bar 6/6, mean hidden >= tolerance | 0.9442–0.9536 (0.9484) | 0.8802–0.8972 (0.8893) | AMD EPYC 9V74 80-Core Processor |
| fraction=0.8 | single pass | ✅ | visible>=bar 6/6, mean hidden >= tolerance | 0.9555–0.9673 (0.9615) | 0.8802–0.8972 (0.8893) | AMD EPYC 9V74 80-Core Processor |
| fraction=0.7 | single pass | ✅ | visible>=bar 6/6, mean hidden >= tolerance | 0.9769–0.9823 (0.9796) | 0.8802–0.8972 (0.8893) | AMD EPYC 9V74 80-Core Processor |

**Ladder:** {"graded": true, "mild": "fraction=0.9", "moderate": "fraction=0.8", "severe": "fraction=0.7", "mean_effect": {"fraction=0.9": 0.047041, "fraction=0.8": 0.075425, "fraction=0.7": 0.093538}, "reason": "strictly monotone mean effect"}

## Channel-mismatch crash

- in_ch=2: crashed with traceback 6/6 — `RuntimeError: Given groups=1, weight of size [16, 2, 3, 3], expected input[128, 1, 28, 28] to have 2 channels, but got 1 channels instead`
- in_ch=3: crashed with traceback 6/6 — `RuntimeError: Given groups=1, weight of size [16, 3, 3, 3], expected input[128, 1, 28, 28] to have 3 channels, but got 1 channels instead`
- in_ch=4: crashed with traceback 6/6 — `RuntimeError: Given groups=1, weight of size [16, 4, 3, 3], expected input[128, 1, 28, 28] to have 4 channels, but got 1 channels instead`

## Neutral-key twins (image_fmnist_neutral)

All identical: **True** — tag noise=0.7 seed 0, tag noise=0.7 seed 1, tag noise=0.5 seed 0, tag noise=0.5 seed 1, report fraction=0.95 seed 0, report fraction=0.95 seed 1, report fraction=0.85 seed 0, report fraction=0.85 seed 1

## Proposed ladders (mild / moderate / severe) and the MILD rung's worst-seed margin

| fault | ladder | graded | mild rung, worst seed vs its bar |
|---|---|---|---|
| Corner-tag leakage (silent, positive symptom) | noise=0.2 / noise=0.15 / noise=0.05 | yes | visible +0.0166 over its bar; hidden 0.0585 under its bar |
| Partner-label swaps (silent, degradation) | fraction=0.25 / fraction=0.35 / fraction=0.45 | yes | hidden 0.0313 under its bar |
| LR schedule counted in steps (silent, degradation) | gamma=0.98 / gamma=0.9 / gamma=0.8 | yes | hidden 0.0083 under its bar |
| Reported-subset metric (metric tier) | fraction=0.9 / fraction=0.8 / fraction=0.7 | yes | visible +0.0069 over its bar; mean hidden 0.8893 (tolerance 0.868318) |
| Channel-mismatch crash | in_ch 2 / 3 / 4 | crash 18/18 | — |

**First-pass verdicts kept on record:** corner-tag leakage and partner-label swaps were NOT graded in their first passes (one and two passing candidates); both effects were monotone, and the disclosed second passes extended the grids upward. Margins are on DEVELOPMENT seeds; every built case is re-checked by the build guard on its own seed.


## RULE v2 — the ladders adopted for building (pre-build deviation, author 2026-09-29)

**Amended rule, applied uniformly to every non-crash fault** (`scripts/calibrate_image_faults.py::ladder_v2`): mild =
the WEAKEST candidate that clears its bar(s) on EVERY development seed by **≥ 1 σ** of that metric's reference σ
(visible 0.008633, hidden 0.008604); severe = the strongest passing candidate; moderate = the passing candidate
between them closest to their midpoint; graded iff strictly monotone. Re-applied to the results above — no new runs.

| fault | rule v1 ladder | **rule v2 ladder (adopted)** | v2 mild, worst seed vs its bar |
|---|---|---|---|
| Corner-tag leakage | noise 0.20 / 0.15 / 0.05 | **noise 0.20 / 0.15 / 0.05** (unchanged) | visible +0.0166; hidden 0.0585 under |
| Partner-label swaps | 0.25 / 0.35 / 0.45 | **0.25 / 0.35 / 0.45** (unchanged) | hidden 0.0313 under |
| LR schedule in steps | γ 0.98 / 0.90 / 0.80 | **γ 0.97 / 0.90 / 0.80** | hidden 0.0233 under |
| Reported-subset metric | q 0.90 / 0.80 / 0.70 | **q 0.85 / 0.80 / 0.70** | visible +0.0227 |
| Channel mismatch | in_ch 2 / 3 / 4 | **in_ch 2 / 3 / 4** | crash |
