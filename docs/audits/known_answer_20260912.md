# Known-answer gate — 2026-09-12 (fast mode)

49 checks, **0 FAIL**.

| case | operator | tier | agent | axis | expected | actual | status | reason |
|------|----------|------|-------|------|----------|--------|--------|--------|
| case_0001 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0001 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0001 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0001 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0001 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0001 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0001 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0002 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0002 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0002 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0002 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0002 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0002 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0002 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0003 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0003 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0003 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0003 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0003 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0003 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0003 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0004 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0004 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0004 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0004 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0004 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0004 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0004 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0005 | control.healthy.v1 | control | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0005 | control.healthy.v1 | control | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0005 | control.healthy.v1 | control | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0005 | control.healthy.v1 | control | oracle | recovery | no_unnecessary_repair | no_unnecessary_repair | PASS | oracle submits no repair on a control |
| case_0005 | control.healthy.v1 | control | degenerate | false_intervention | True | True | PASS | a repair on a healthy run is a false intervention |
| case_0005 | control.healthy.v1 | control | always_broken | detection_false_positive | True | True | PASS | controls must catch an always-detect agent |
| case_0005 | control.healthy.v1 | control | always_broken | false_intervention_report | info | False | PASS | INFO: no non-default knob on a clean control |
| case_0006 | control.healthy.v1 | control | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0006 | control.healthy.v1 | control | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0006 | control.healthy.v1 | control | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0006 | control.healthy.v1 | control | oracle | recovery | no_unnecessary_repair | no_unnecessary_repair | PASS | oracle submits no repair on a control |
| case_0006 | control.healthy.v1 | control | degenerate | false_intervention | True | True | PASS | a repair on a healthy run is a false intervention |
| case_0006 | control.healthy.v1 | control | always_broken | detection_false_positive | True | True | PASS | controls must catch an always-detect agent |
| case_0006 | control.healthy.v1 | control | always_broken | false_intervention_report | info | False | PASS | INFO: no non-default knob on a clean control |
| case_0007 | control.healthy.v1 | control | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0007 | control.healthy.v1 | control | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0007 | control.healthy.v1 | control | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0007 | control.healthy.v1 | control | oracle | recovery | no_unnecessary_repair | no_unnecessary_repair | PASS | oracle submits no repair on a control |
| case_0007 | control.healthy.v1 | control | degenerate | false_intervention | True | True | PASS | a repair on a healthy run is a false intervention |
| case_0007 | control.healthy.v1 | control | always_broken | detection_false_positive | True | True | PASS | controls must catch an always-detect agent |
| case_0007 | control.healthy.v1 | control | always_broken | false_intervention_report | info | False | PASS | INFO: no non-default knob on a clean control |
