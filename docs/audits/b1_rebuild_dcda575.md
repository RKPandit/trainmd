# B1 provenance — the 20 healthy controls rebuilt at dcda575 on AMD (correction #8)

> CI dispatch `task=b1-rebuild` (`scripts/b1_rebuild_dcda575.sh`), runs 36365463242 and 36366062685 (identical B1 output), AMD EPYC 7763. Built and scored ENTIRELY with commit dcda575's own Dockerfile, data prep, `harness.build_case` and `harness.baselines` — the code that published B1's control FPR (FINDINGS baseline table, 2026-09-17). DECISIONS 2026-09-28.

## dcda575's own B1 (`python -m harness.baselines --baseline b1`)

```
case_0001	detected=True	correct=False	id=True	evF1=0.00
case_0002	detected=True	correct=False	id=True	evF1=0.00
case_0003	detected=False	correct=True	id=True	evF1=1.00
case_0004	detected=True	correct=False	id=True	evF1=0.00
case_0005	detected=False	correct=True	id=True	evF1=1.00
case_0006	detected=True	correct=False	id=True	evF1=0.00
case_0007	detected=True	correct=False	id=True	evF1=0.00
case_0008	detected=True	correct=False	id=True	evF1=0.00
case_0009	detected=True	correct=False	id=True	evF1=0.00
case_0010	detected=False	correct=True	id=True	evF1=1.00
case_0011	detected=True	correct=False	id=True	evF1=0.00
case_0012	detected=True	correct=False	id=True	evF1=0.00
case_0013	detected=True	correct=False	id=True	evF1=0.00
case_0014	detected=True	correct=False	id=True	evF1=0.00
case_0015	detected=True	correct=False	id=True	evF1=0.00
case_0016	detected=False	correct=True	id=True	evF1=1.00
case_0017	detected=True	correct=False	id=True	evF1=0.00
case_0018	detected=True	correct=False	id=True	evF1=0.00
case_0019	detected=True	correct=False	id=True	evF1=0.00
case_0020	detected=True	correct=False	id=True	evF1=0.00
```

## Band positions from each case's own agent-visible metrics and public band

```
case_0001 control.healthy.v1 seed=50 epochs=20 any_epoch_out=True final_epoch_out=False final=0.856553 band=[0.851904,0.860692]
case_0002 control.healthy.v1 seed=51 epochs=20 any_epoch_out=True final_epoch_out=False final=0.858175 band=[0.851904,0.860692]
case_0003 control.healthy.v1 seed=52 epochs=20 any_epoch_out=False final_epoch_out=False final=0.856111 band=[0.851904,0.860692]
case_0004 control.healthy.v1 seed=53 epochs=20 any_epoch_out=True final_epoch_out=False final=0.857143 band=[0.851904,0.860692]
case_0005 control.healthy.v1 seed=54 epochs=20 any_epoch_out=False final_epoch_out=False final=0.856995 band=[0.851904,0.860692]
case_0006 control.healthy.v1 seed=55 epochs=20 any_epoch_out=True final_epoch_out=False final=0.855079 band=[0.851904,0.860692]
case_0007 control.healthy.v1 seed=56 epochs=20 any_epoch_out=True final_epoch_out=False final=0.858912 band=[0.851904,0.860692]
case_0008 control.healthy.v1 seed=57 epochs=20 any_epoch_out=True final_epoch_out=False final=0.858912 band=[0.851904,0.860692]
case_0009 control.healthy.v1 seed=58 epochs=20 any_epoch_out=True final_epoch_out=True final=0.861271 band=[0.851904,0.860692]
case_0010 control.healthy.v1 seed=59 epochs=20 any_epoch_out=False final_epoch_out=False final=0.855963 band=[0.851904,0.860692]
case_0011 control.healthy.v1 seed=60 epochs=20 any_epoch_out=True final_epoch_out=False final=0.852573 band=[0.851904,0.860692]
case_0012 control.healthy.v1 seed=61 epochs=20 any_epoch_out=True final_epoch_out=False final=0.856258 band=[0.851904,0.860692]
case_0013 control.healthy.v1 seed=62 epochs=20 any_epoch_out=True final_epoch_out=False final=0.857585 band=[0.851904,0.860692]
case_0014 control.healthy.v1 seed=63 epochs=20 any_epoch_out=True final_epoch_out=False final=0.858912 band=[0.851904,0.860692]
case_0015 control.healthy.v1 seed=64 epochs=20 any_epoch_out=True final_epoch_out=False final=0.855669 band=[0.851904,0.860692]
case_0016 control.healthy.v1 seed=65 epochs=20 any_epoch_out=False final_epoch_out=False final=0.856406 band=[0.851904,0.860692]
case_0017 control.healthy.v1 seed=66 epochs=20 any_epoch_out=True final_epoch_out=False final=0.855963 band=[0.851904,0.860692]
case_0018 control.healthy.v1 seed=67 epochs=20 any_epoch_out=True final_epoch_out=False final=0.851983 band=[0.851904,0.860692]
case_0019 control.healthy.v1 seed=68 epochs=20 any_epoch_out=True final_epoch_out=False final=0.857585 band=[0.851904,0.860692]
case_0020 control.healthy.v1 seed=69 epochs=20 any_epoch_out=True final_epoch_out=False final=0.855816 band=[0.851904,0.860692]
SUMMARY healthy=20 any_epoch_out=16 final_epoch_out=1
```
