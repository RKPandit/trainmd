.PHONY: data reference build-case clean

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

clean:
	rm -rf $(WORKLOAD_DIR)/reference/runs
	rm -rf $(WORKLOAD_DIR)/.data
	rm -rf $(WORKLOAD_DIR)/.hidden_data
