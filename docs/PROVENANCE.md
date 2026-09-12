# Trial Record Provenance

Every agent trial produces a self-contained provenance record at
`results/<case_id>/trials/<agent>_<run_id>.yaml`.

## Schema v1.1

**v1.1 (pre-sweep capture):** added `prompt`, `conditions`, `termination_reason`,
`symptom_direction` (top-level); `max_tokens_truncations` (usage); `api_model`, `latency_sec`
(per llm_transcript entry); `confidence`, `rationale` (submission — stored raw, scoring
ignores them). The sweep manifest (`sweeps/<name>_manifest.yaml`, tracked) records estimated
+ actual spend and a runner-filled hardware/compute block. See "Pre-sweep capture" below.

| Block | Field | Type | Notes |
|-------|-------|------|-------|
| (top) | `schema_version` | str | `"1.1"` |
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

### Pre-sweep capture (v1.1)

| Block | Field | Type | Notes |
|-------|-------|------|-------|
| prompt | `system_prompt_text` | str\|null | Full rendered system prompt |
| prompt | `prompt_hash` | str\|null | SHA-256 of the rendered prompt |
| prompt | `prompt_version` | str\|null | e.g. `"react-1"` / `"static-1"` (drift-guarded) |
| conditions | `sweep_name` | str\|null | Set by the runner |
| conditions | `agent_type` | str\|null | `"react"` / `"static"` |
| conditions | `anchor` | str\|null | `"on"` / `"off"` |
| conditions | `repeat_index` | int\|null | |
| (top) | `termination_reason` | str | submitted / ended_without_submit / max_turns / continuation_capped / token_budget_stop / assembly_failed / no_submit_after_followup / crashed |
| (top) | `symptom_direction` | str\|null | Copied from the hidden card (H1/H2 x-axis) |
| llm_transcript[] | `api_model` | str\|null | Model string the API returned |
| llm_transcript[] | `latency_sec` | float | Wall time of that API call |
| submission | `confidence` | float\|null | Stored raw (un-clamped); scoring ignores it |
| submission | `rationale` | str\|null | ≤500 chars; scoring ignores it |

Hidden card (`card.hidden.yaml`, build-time): `faulty_visible_value`, `visible_sigma_distance`,
`hidden_sigma_distance`, `symptom_direction` ∈ {negative, positive, within_band, crash, none}
— the effect-size x-axis, validated by C11.

Sweep manifest (`sweeps/<sweep_name>_manifest.yaml`, **tracked**): `estimated_spend_usd`,
`actual_spend_usd` (entered manually at sweep end), `hardware` {cpu_model, cpu_cores, ram_gb,
os, uv_lock_hash, git_commit}, `per_phase_totals` — runner-filled slots default to null.

Index line adds required columns: `termination_reason`, `agent_type`, `anchor`, `repeat_index`,
`symptom_direction` (group by condition without opening records).

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
