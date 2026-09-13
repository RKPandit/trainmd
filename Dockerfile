# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Canonical TrainMD environment (Stage 1).
#   - linux/amd64, Python 3.11 — matches CI (ubuntu-latest) and the historical
#     "x86_64 canonical" decision. ALWAYS build/run with --platform=linux/amd64
#     (the Makefile docker-* targets do this); on an arm64 host it runs under
#     qemu, which is a DEVELOPMENT CONVENIENCE — the canonical numbers are the
#     ones CI produces on native amd64 (see docs/DECISIONS.md).
#   - Dependencies are frozen from the committed uv.lock. On Linux torch is the
#     CPU wheel from download.pytorch.org (per pyproject [tool.uv]); on macOS it
#     is the PyPI arm64 wheel — a different build, so reference numbers differ
#     across platforms by design.
# Base pinned by DIGEST (not a floating tag). Arch is selected by the build
# flag `--platform linux/amd64` (the Makefile `image` target always sets it).
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84

# uv, pinned by image tag (matches the local uv 0.9.10 that produced uv.lock).
COPY --from=ghcr.io/astral-sh/uv:0.9.10 /uv /uvx /usr/local/bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Single-threaded math for REPRODUCIBILITY. torch.use_deterministic_algorithms
    # makes individual ops deterministic but multi-thread float reductions are
    # still order-nondeterministic; pinning every BLAS/OMP pool to 1 makes
    # training bit-reproducible run-to-run (the canonical requirement). Set via
    # env (not train.py) so no workload source changes -> no case supersession.
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    TORCH_NUM_THREADS=1

# torch's CPU wheel needs libgomp at run time; ca-certificates for HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Sync deps (frozen) into /opt/venv WITHOUT installing the local project — the
# repo is mounted at /work at run time and imported from there.
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra llm --extra test

ENV PATH="/opt/venv/bin:$PATH"

# Non-root user; /work is the mounted repo. No network is opened by the image
# itself — only a trial that calls the Anthropic API reaches out at run time.
RUN useradd -m -u 1000 runner \
    && mkdir -p /work \
    && chown -R runner:runner /work /opt/venv
USER runner
WORKDIR /work

CMD ["python", "-c", "import torch, numpy, sklearn, sys; print('python', sys.version.split()[0], '| torch', torch.__version__, '| numpy', numpy.__version__, '| sklearn', sklearn.__version__)"]
