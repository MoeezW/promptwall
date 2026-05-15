# syntax=docker/dockerfile:1.7

# ── Stage 1: builder ──────────────────────────────────────────────────────
# Install dependencies with uv into a virtualenv we'll copy into the runtime
# stage. We keep all of `optimum`, `transformers`, and `torch` here because
# `optimum-cli` needs torch to export the model to ONNX on first run.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# uv ships as a single static binary; pinning the version keeps builds reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /uvx /usr/local/bin/

# Build deps for psycopg, ONNX export, and the spaCy model wheel install.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Resolve dependencies first; the source copy is invalidated less often.
COPY packages/core/pyproject.toml packages/core/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

# Now the project source.
COPY packages/core/src ./src
COPY packages/core/migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen


# ── Stage 2: runtime ──────────────────────────────────────────────────────
# Copy only the resolved virtualenv and source. Then strip torch — the ONNX
# Runtime path doesn't need it at inference time, and removing it cuts ~750 MB
# off the image. See docs/adrs/0004-onnx-runtime-over-torch.md.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PROMPTWALL_LOG_RENDERER=json

# Runtime-only system deps. psycopg's binary wheel doesn't need libpq at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN useradd --create-home --uid 10001 promptwall

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations
COPY policies /policies

# Strip torch and its CUDA shims. They came in transitively for the model
# export step in the builder stage; at runtime ONNX Runtime is enough.
RUN /opt/venv/bin/pip uninstall -y \
        torch \
        triton \
        nvidia-cublas-cu12 \
        nvidia-cuda-cupti-cu12 \
        nvidia-cuda-nvrtc-cu12 \
        nvidia-cuda-runtime-cu12 \
        nvidia-cudnn-cu12 \
        nvidia-cufft-cu12 \
        nvidia-curand-cu12 \
        nvidia-cusolver-cu12 \
        nvidia-cusparse-cu12 \
        nvidia-nccl-cu12 \
        nvidia-nvjitlink-cu12 \
        nvidia-nvtx-cu12 \
        2>/dev/null || true

WORKDIR /app
USER promptwall

ENV PROMPTWALL_POLICY_PATH=/policies/default.yaml \
    PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/ || exit 1

CMD ["python", "-m", "promptwall.main"]
