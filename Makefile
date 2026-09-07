.PHONY: data reference clean

WORKLOAD ?= tabular_adult
WORKLOAD_DIR := workloads/$(WORKLOAD)

# ---------------------------------------------------------------------------
# Targets — all commands run through `uv run` so they use the locked
# environment regardless of which shell is active.
# ---------------------------------------------------------------------------

data:
	uv run python $(WORKLOAD_DIR)/data_prep.py --workload-dir $(WORKLOAD_DIR)

reference: data
	uv run python harness/reference_run.py --workload-dir $(WORKLOAD_DIR)

clean:
	rm -rf $(WORKLOAD_DIR)/reference/runs
	rm -rf $(WORKLOAD_DIR)/.data
