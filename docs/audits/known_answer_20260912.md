# Known-answer gate — 2026-09-12 (fast mode)

189 checks, **0 FAIL**.

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
| case_0008 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0008 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0008 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0008 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0008 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0008 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0008 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0009 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0009 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0009 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0009 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0009 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0009 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0009 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0010 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0010 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0010 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0010 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0010 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0010 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0010 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0011 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0011 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0011 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0011 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0011 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0011 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0011 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0012 | crash.shape_mismatch.v1 | execution | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0012 | crash.shape_mismatch.v1 | execution | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0012 | crash.shape_mismatch.v1 | execution | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0012 | crash.shape_mismatch.v1 | execution | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0012 | crash.shape_mismatch.v1 | execution | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0012 | crash.shape_mismatch.v1 | execution | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0012 | crash.shape_mismatch.v1 | execution | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0013 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0013 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0013 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0013 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0013 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0013 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0013 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0014 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0014 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0014 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0014 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0014 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0014 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0014 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0015 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0015 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0015 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0015 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0015 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0015 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0015 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0016 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0016 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0016 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0016 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0016 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0016 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0016 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0017 | silent.data_leakage.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0017 | silent.data_leakage.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0017 | silent.data_leakage.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0017 | silent.data_leakage.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0017 | silent.data_leakage.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0017 | silent.data_leakage.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0017 | silent.data_leakage.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0018 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0018 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0018 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0018 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0018 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0018 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0018 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0019 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0019 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0019 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0019 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0019 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0019 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0019 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0020 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0020 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0020 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0020 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0020 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0020 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0020 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0021 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0021 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0021 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0021 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0021 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0021 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0021 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0022 | silent.label_corruption.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0022 | silent.label_corruption.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0022 | silent.label_corruption.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0022 | silent.label_corruption.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0022 | silent.label_corruption.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0022 | silent.label_corruption.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0022 | silent.label_corruption.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0023 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0023 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0023 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0023 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0023 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0023 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0023 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0024 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0024 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0024 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0024 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0024 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0024 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0024 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0025 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0025 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0025 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0025 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0025 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0025 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0025 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0026 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0026 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0026 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0026 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0026 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0026 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0026 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
| case_0027 | silent.lr_warmup.v1 | dynamics | oracle | detection | True | True | PASS | oracle must detect per tier |
| case_0027 | silent.lr_warmup.v1 | dynamics | oracle | identification | True | True | PASS | oracle class must be accepted |
| case_0027 | silent.lr_warmup.v1 | dynamics | oracle | evidence_f1 | 1.0 | 1.0 | PASS | oracle cites exactly the hidden refs |
| case_0027 | silent.lr_warmup.v1 | dynamics | oracle | recovery | recovered | skipped(fast) | PASS | oracle repair must restore reference |
| case_0027 | silent.lr_warmup.v1 | dynamics | degenerate | identification_discrimination | oracle>degenerate | oracle=True,deg=False | PASS | oracle must out-identify the degenerate |
| case_0027 | silent.lr_warmup.v1 | dynamics | degenerate | evidence_discrimination | oracle>degenerate | oracle=1.0,deg=0.0 | PASS | oracle must out-evidence the degenerate |
| case_0027 | silent.lr_warmup.v1 | dynamics | always_broken | evidence_zero | 0.0 | 0.0 | PASS | always-broken cites no evidence |
