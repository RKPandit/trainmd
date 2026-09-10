# Reproducibility Experiment: Haiku 4.5 on case_0001

## Purpose

Two independent trials of `claude-haiku-4-5-20251001` on `case_0001` at temperature 1.0,
run on different dates against different harness commits, to measure score stability and
cost variance before committing to a full multi-model sweep.

| | Run-1 | Run-2 |
|---|---|---|
| **run_id** | `20260909T021346Z_2bdcbe` | `20260909T202240Z_d45719` |
| **harness commit** | `5c788eb` | `0066901` |
| **git_dirty** | true | true |

---

## Side-by-side results

| Metric | Run-1 | Run-2 |
|---|---|---|
| detection_correct | true | true |
| identification_correct | true | true |
| evidence_precision | 1.0 | 1.0 |
| evidence_recall | 1.0 | 1.0 |
| evidence_f1 | 1.0 | 1.0 |
| recovery_verdict | recovered | recovered |
| repair_type | config_patch | config_patch |
| repair_key | training.lr | training.lr |
| repair_value | 0.001 | 0.001 |
| recovery_seed_100 | 0.847413 | 0.847413 |
| recovery_seed_101 | 0.846381 | 0.846381 |
| recovery_seed_102 | 0.849034 | 0.849034 |
| llm_calls | 7 | 9 |
| tool_calls_used | 12 / 40 | 13 / 40 |
| input_tokens | 33,696 | 52,801 |
| output_tokens | 1,348 | 1,626 |
| total_tokens | 35,044 | 54,427 |
| estimated_cost_usd | $0.040436 | $0.060931 |
| wall_clock_seconds | 17.98 | 21.91 |

---

## Investigation-path comparison

### Run-1 tool sequence (12 calls)

```
list_files
read_config
query_metrics  series=train_loss
query_metrics  series=val_acc
read_config    section=lr
read_config    section=batch_size
read_config    section=optimizer
read_code      start_line=1    end_line=100
read_code      start_line=100  end_line=200
read_code      start_line=200  end_line=307
read_log
submit
```

Run-1 followed a tight path: orient (list_files, read_config), check metrics, drill into
individual config sections, read the full training script in three clean chunks, read the
log, and submit.

### Run-2 tool sequence (13 calls)

```
list_files
read_config
read_log
query_metrics  series=train_loss
query_metrics  series=val_acc
read_code      start_line=1    end_line=100
read_code      start_line=100                  ← wasted call (returned 1 line)
read_code      start_line=100  end_line=307
read_code      start_line=199  end_line=307
read_code      start_line=298  end_line=307
query_metrics  series=train_loss  start_epoch=15  end_epoch=19
query_metrics  series=val_acc    start_epoch=15  end_epoch=19
submit
```

Run-2 read the log earlier (call 3 vs call 11), read code in more overlapping chunks
(including a wasted `read_code start_line=100` with no `end_line` that returned a single
line), and added two targeted epoch-15–19 metric queries before submitting. These extra
calls account for the token and cost difference.

### Key differences

- **Log timing**: Run-2 read the log third; Run-1 read it eleventh (just before submit).
- **Code chunking**: Run-1 split cleanly into 1–100, 100–200, 200–307. Run-2 had
  overlapping ranges and one wasted call.
- **Targeted metric queries**: Run-2 queried epochs 15–19 specifically for both
  train_loss and val_acc before submitting — a confirmation step Run-1 skipped.
- **Config drill-down**: Run-1 made three separate `read_config` calls for lr,
  batch_size, and optimizer. Run-2 relied on the initial full config read.

---

## Findings

1. **Score stability**: All four scoring axes (detection, identification, evidence F1,
   recovery) are identical across runs. Recovery per-seed accuracies match to 6 decimal
   places. The case is easy enough for Haiku that nondeterminism in the investigation
   path does not affect the outcome.

2. **Cost variance**: ~55% token variance (35,044 vs 54,427) and ~51% cost variance
   ($0.040 vs $0.061). The extra tokens in Run-2 come from overlapping code reads, a
   wasted tool call, and two additional targeted metric queries. For sweep budgeting,
   assume the higher figure as a conservative per-trial ceiling for this case.

3. **Implications for sweep**: case_0001 appears saturated for Haiku 4.5 — two runs,
   two perfect scores, identical repairs. A full sweep should focus budget on harder
   cases or weaker models where variance in scores (not just cost) is expected.

---

## Caveat: `git_dirty`

Both runs have `git_dirty: true` in their provenance records. This means uncommitted
changes existed in the working tree at trial time. The harness commits differ
(`5c788eb` vs `0066901`), and the dirty state means the exact code executed is not
fully reproducible from the commit hash alone. Future trials should run from a clean
working tree to ensure full provenance traceability.
