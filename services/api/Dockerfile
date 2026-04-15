# syntax=docker/dockerfile:1.7
#
# MooseGlove API image.
#
# Design notes
# ------------
# * requirements.txt is committed to the repo with hashes (via
#   `pip-compile --generate-hashes`). The Dockerfile does NOT run
#   pip-compile at build time — that used to add ~4 minutes per build
#   and made the dep set non-reproducible. To bump a dep, run
#   `pip-compile --generate-hashes --upgrade-package <name>
#    services/api/requirements.in` locally and commit both files.
#
# * The fastembed model (BAAI/bge-small-en-v1.5, ~130 MB) is
#   downloaded during image build and cached in /opt/fastembed.
#   This eliminates the HF Hub fetch on every container start
#   (including the rate-limit warning) and makes cold starts instant.
#
# * Two-stage build: builder compiles C extensions (spaCy, fastembed,
#   pyrush, etc.) with build-essential; runtime copies only the
#   installed packages and the model cache.

ARG PYTHON_VERSION=3.11-slim-bookworm

# -----------------------------------------------------------------------------
# Stage 1: builder — compile dependencies and pre-fetch the embedding model
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies from the committed, hash-pinned requirements.txt.
# No pip-compile here — that's a local / CI operation, not a build operation.
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Pre-download the fastembed embedding model into /opt/fastembed.
# Runtime points FASTEMBED_CACHE_PATH at the same dir, so the model is
# available the instant the container starts — no HF Hub call.
# Passing cache_dir explicitly as a kwarg is more robust than relying
# on env var ordering between import and construction.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN mkdir -p /opt/fastembed \
    && PYTHONPATH=/install/lib/python3.11/site-packages python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed'); print('fastembed model cached')" \
    && du -sh /opt/fastembed

# -----------------------------------------------------------------------------
# Stage 2: runtime
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}

WORKDIR /app

# Install the tiny runtime tools the api needs beyond Python itself.
# curl is used by the container healthcheck downstream; tini gives us
# PID 1 signal handling so Ctrl+C on docker compose stop works cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder
COPY --from=builder /install /usr/local

# Copy the pre-fetched fastembed model cache
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
COPY --from=builder /opt/fastembed /opt/fastembed

# Copy application code
COPY services/api/app ./app
COPY prompts ./prompts
COPY data ./data

# Non-root user. /app and /opt/fastembed need to be readable by appuser.
RUN useradd -m -r -u 1000 appuser \
    && chown -R appuser:appuser /app /opt/fastembed
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
