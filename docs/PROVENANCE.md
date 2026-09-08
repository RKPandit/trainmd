# Trial Record Provenance

Every agent trial produces a self-contained provenance record at
`results/<case_id>/trials/<agent>_<run_id>.yaml`.

## Schema v1.0

| Block | Field | Type | Notes |
|-------|-------|------|-------|
| (top) | `schema_version` | str | `"1.0"` |
| (top) | `case_id` | str | Opaque case identifier |
| (top) | `agent_name` | str | Agent name (e.g. `stub_oracle`) |
| (top) | `run_id` | str | `<UTC timestamp>_<6-char hex>` |
| (top) | `status` | str | `"partial"`, `"completed"`, or `"crashed"` |
| environment | `harness_git_commit` | str | 40-char hex or `"unknown"` |
| environment | `git_dirty` | bool | `true` if uncommitted changes |
| environment | `case_card_hash` | str | SHA-256 of `card.public.yaml` |
| environment | `python_version` | str | `sys.version` |
| environment | `platform` | str | `platform.platform()` |
| environment | `uv_lock_hash` | str\|null | SHA-256 of `uv.lock` |
| environment | `timestamp_utc` | str | ISO-8601 UTC |
| environment | `wall_clock_sec` | float | Elapsed wall time |
| model | `model_id` | str\|null | e.g. `"claude-sonnet-4-20250514"` |
| model | `model_version` | str\|null | |
| model | `provider` | str\|null | e.g. `"anthropic"` |
| model | `temperature` | float\|null | |
| model | `top_p` | float\|null | |
| model | `max_tokens` | int\|null | |
| model | `stop_reason` | str\|null | |
| model | `request_seed` | int\|null | |
| usage | `llm_calls` | int | Number of LLM API calls |
| usage | `input_tokens` | int | |
| usage | `output_tokens` | int | |
| usage | `cached_tokens` | int | |
| usage | `total_tokens` | int | input + output |
| usage | `estimated_cost_usd` | float\|null | From pricing table |
| (top) | `submission` | dict\|null | Agent's final submission |
| (top) | `tool_transcript` | list[dict] | All tool calls |
| (top) | `llm_transcript` | list[dict] | Raw LLM exchanges (empty for stubs) |
| scores | `detection` | dict\|null | Binary detection result |
| scores | `identification` | dict\|null | Operator class match |
| scores | `evidence` | dict\|null | Precision/recall/F1 |
| scores | `recovery` | dict\|null | `null` at trial time; filled by `verify` |
| scores | `safety` | dict\|null | Rejected/forbidden action counts |
| budget | `tool_calls_used` | int | |
| budget | `tool_calls_total` | int | |

## Index file (`results/index.jsonl`)

One JSON line per trial, appended immediately after each trial completes.
Fields: `case_id`, `agent_name`, `run_id`, `model_id`, `detection_correct`,
`identification_correct`, `evidence_f1`, `recovery_verdict`, `total_tokens`,
`estimated_cost_usd`, `cost_is_estimate`, `harness_git_commit`, `status`,
`timestamp_utc`.

`recovery_verdict` is `"pending"` at trial time and updated to the actual
verdict by `make verify` / `score_recovery_standalone()`.

## Crash recovery

1. A **partial** record is written before the agent starts.
2. The agent runs inside a `try/finally` block.
3. On any exception, the `finally` block flushes whatever transcript was
   captured with `status: "crashed"`.
4. Only partial records can be overwritten — completed/crashed records are
   immutable (raises `FileExistsError`).

## Cost estimation

`harness/pricing.py` contains an approximate per-model price table.
`estimate_cost()` returns a `CostEstimate(cost_usd, is_estimate=True)`.
The `is_estimate` flag ensures no unverified cost figure silently reaches
a results table — verify against the provider's pricing page before
reporting in the paper.

## Reproducibility

Each record captures:
- **Git commit + dirty flag** — exact harness version
- **uv.lock hash** — exact dependency versions
- **case_card_hash** — exact case configuration
- **Python version + platform** — runtime environment
