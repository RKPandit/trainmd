.PHONY: data reference build-case verify-repair run-agent smoke score verify validate validate-all clean

WORKLOAD ?= tabular_adult
WORKLOAD_DIR := workloads/$(WORKLOAD)

# ---------------------------------------------------------------------------
# Targets — all commands run through `uv run` so they use the locked
# environment regardless of which shell is active.
# ---------------------------------------------------------------------------

data:
	uv run python $(WORKLOAD_DIR)/data_prep.py --workload-dir $(WORKLOAD_DIR)

reference: data
	uv run python -m harness.reference_run --workload-dir $(WORKLOAD_DIR)

OPERATOR ?= silent.lr_warmup.v1
STRENGTH ?= moderate
SEED ?= 42

build-case: data
	uv run python -m harness.build_case \
		--workload $(WORKLOAD) \
		--operator $(OPERATOR) \
		--strength $(STRENGTH) \
		--seed $(SEED)

CASE ?= cases/case_0001
SPEC ?= repair_spec.yaml

verify-repair:
	uv run python -m harness.evaluator.verify_repair \
		--case $(CASE) \
		--spec $(SPEC)

AGENT ?= stub_oracle

run-agent:
	uv run python -m harness.run_agent \
		--case $(CASE) \
		--agent $(AGENT)

SMOKE_MODEL ?= claude-haiku-4-5-20251001

smoke: build-case
	uv run --extra llm python -m harness.run_agent \
		--case $(CASE) \
		--model $(SMOKE_MODEL) \
		--provider anthropic

TRIAL ?= trial.yaml

score:
	uv run python -m harness.scoring \
		--case $(CASE) \
		--trial $(TRIAL)

verify:
	uv run python -m harness.scoring --verify \
		--case $(CASE) \
		--trial $(TRIAL)

validate:
	uv run python -m harness.validate_case --case $(CASE)

validate-all:
	uv run python -m harness.validate_case --all

clean:
	rm -rf $(WORKLOAD_DIR)/reference/runs
	rm -rf $(WORKLOAD_DIR)/.data
	rm -rf $(WORKLOAD_DIR)/.hidden_data
