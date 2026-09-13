.PHONY: data reference build-case verify-repair run-agent smoke score verify validate validate-all clean test \
	image image-digest docker-data docker-reference docker-build-case docker-validate-all \
	docker-gate-known-answer docker-audit-index docker-test docker-sweep docker-shell \
	docker-build-all-cases docker-case-margins

WORKLOAD ?= tabular_adult
WORKLOAD_DIR := workloads/$(WORKLOAD)

# train.py refuses to run unless every BLAS/OpenMP pool is pinned to 1 (a
# determinism guard — see docs/DECISIONS.md). The container sets these via ENV;
# host targets that train must set them too. Prefix training recipes with this.
THREAD_CAPS := OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

# ---------------------------------------------------------------------------
# Targets — all commands run through `uv run` so they use the locked
# environment regardless of which shell is active.
# ---------------------------------------------------------------------------

data:
	uv run python $(WORKLOAD_DIR)/data_prep.py --workload-dir $(WORKLOAD_DIR)

reference: data
	$(THREAD_CAPS) uv run python -m harness.reference_run --workload-dir $(WORKLOAD_DIR)

OPERATOR ?= silent.lr_warmup.v1
STRENGTH ?= moderate
SEED ?= 42

build-case: data
	$(THREAD_CAPS) uv run python -m harness.build_case \
		--workload $(WORKLOAD) \
		--operator $(OPERATOR) \
		--strength $(STRENGTH) \
		--seed $(SEED)

CASE ?= cases/case_0001
SPEC ?= repair_spec.yaml

verify-repair:
	$(THREAD_CAPS) uv run python -m harness.evaluator.verify_repair \
		--case $(CASE) \
		--spec $(SPEC)

AGENT ?= stub_oracle

run-agent:
	$(THREAD_CAPS) uv run python -m harness.run_agent \
		--case $(CASE) \
		--agent $(AGENT)

SMOKE_MODEL ?= claude-haiku-4-5-20251001

smoke: build-case
	$(THREAD_CAPS) uv run --extra llm python -m harness.run_agent \
		--case $(CASE) \
		--model $(SMOKE_MODEL) \
		--provider anthropic

TRIAL ?= trial.yaml

score:
	uv run python -m harness.scoring \
		--case $(CASE) \
		--trial $(TRIAL)

verify:
	$(THREAD_CAPS) uv run python -m harness.scoring --verify \
		--case $(CASE) \
		--trial $(TRIAL)

validate:
	uv run python -m harness.validate_case --case $(CASE)

validate-all:
	uv run python -m harness.validate_case --all

# G1 hardening gates (free — no paid trials).
# Fast by default (skips recovery reruns); FULL=1 runs recovery.
gate-known-answer:
	uv run python -m harness.gate_known_answer $(if $(FULL),--full,--fast)

audit-index:
	uv run python -m harness.audit_index

test:
	$(THREAD_CAPS) uv run --extra test python -m pytest tests/

clean:
	rm -rf $(WORKLOAD_DIR)/reference/runs
	rm -rf $(WORKLOAD_DIR)/.data
	rm -rf $(WORKLOAD_DIR)/.hidden_data

# ---------------------------------------------------------------------------
# Canonical container (Stage 1) — linux/amd64, Python 3.11, deps frozen.
# The container is the DEFAULT for anything that produces a committed artifact
# (reference stats, built cases). `docker-<target>` mirrors the host target but
# runs inside the pinned image with the repo mounted at /work. On an arm64 host
# these run under qemu (a dev convenience); the canonical numbers are CI's
# native-amd64 output. See docs/DECISIONS.md and README quickstart.
# ---------------------------------------------------------------------------
IMAGE ?= trainmd:canonical
PLATFORM := linux/amd64
# Image ref by digest once built (RepoDigests), else the image Id.
IMAGE_DIGEST = $(shell docker inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' $(IMAGE) 2>/dev/null)
# Run as the HOST user so bind-mount writes work on both macOS (Docker Desktop)
# and Linux CI (workspace owned by the runner uid). The image venv is
# world-readable, so any uid can run python; HOME points somewhere writable.
DOCKER_USER := $(shell id -u):$(shell id -g)
DOCKER_RUN = docker run --rm --platform $(PLATFORM) --user $(DOCKER_USER) -e HOME=/tmp \
	-e TRAINMD_IN_CONTAINER=1 -e TRAINMD_IMAGE_DIGEST="$(IMAGE_DIGEST)" \
	-v "$(PWD)":/work -w /work $(IMAGE)
# Paid trials need the API key passed through (the only run-time network egress).
DOCKER_RUN_LLM = docker run --rm --platform $(PLATFORM) --user $(DOCKER_USER) -e HOME=/tmp \
	-e TRAINMD_IN_CONTAINER=1 -e TRAINMD_IMAGE_DIGEST="$(IMAGE_DIGEST)" \
	-e ANTHROPIC_API_KEY -v "$(PWD)":/work -w /work $(IMAGE)

image:
	docker build --platform $(PLATFORM) -t $(IMAGE) .

image-digest:
	@echo "image:  $(IMAGE)"
	@echo "digest: $(IMAGE_DIGEST)"
	@echo "committed:"; cat docker/IMAGE_DIGEST 2>/dev/null || echo "  (docker/IMAGE_DIGEST not written yet)"

docker-data:
	$(DOCKER_RUN) python $(WORKLOAD_DIR)/data_prep.py --workload-dir $(WORKLOAD_DIR)

docker-reference:
	$(DOCKER_RUN) python -m harness.reference_run --workload-dir $(WORKLOAD_DIR)

docker-build-case:
	$(DOCKER_RUN) python -m harness.build_case \
		--workload $(WORKLOAD) --operator $(OPERATOR) --strength $(STRENGTH) --seed $(SEED)

docker-validate-all:
	$(DOCKER_RUN) python -m harness.validate_case --all

docker-gate-known-answer:
	$(DOCKER_RUN) python -m harness.gate_known_answer $(if $(FULL),--full,--fast)

docker-audit-index:
	$(DOCKER_RUN) python -m harness.audit_index

docker-test:
	$(DOCKER_RUN) python -m pytest tests/

# Sweep: pass args via SWEEP_ARGS, e.g. make docker-sweep SWEEP_ARGS="report --name sweep1".
SWEEP_ARGS ?= report --name sweep1
docker-sweep:
	$(DOCKER_RUN_LLM) python -m harness.sweep $(SWEEP_ARGS)

docker-shell:
	docker run --rm -it --platform $(PLATFORM) -e TRAINMD_IN_CONTAINER=1 \
		-v "$(PWD)":/work -w /work $(IMAGE) bash

# Build the entire 27-case design from a fresh checkout, in-container, against
# the current reference (regenerate it first for a canonical build). Cases are
# generated, NOT committed — this is the one command a stranger runs.
docker-build-all-cases:
	$(DOCKER_RUN) python -m harness.sweep plan --name canonical --build-missing

# Per-case margin report: faulty_value vs the current tolerance, flag < 2x std.
docker-case-margins:
	$(DOCKER_RUN) python scripts/case_margins.py
