FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base

WORKDIR /app

# Copy configuration files
COPY pyproject.toml uv.lock ./

# UV_COMPILE_BYTECODE for generating .pyc files -> faster application startup.
# UV_LINK_MODE=copy to silence warnings about not being able to use hard links
# since the cache and sync target are on separate file systems.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev

# Strip CUDA torch and reinstall CPU-only to avoid ~2GB image bloat
# EKS nodes are amd64 (x86_64) with no GPU; PyPI defaults to CUDA wheels for Linux amd64
RUN --mount=type=cache,target=/root/.cache/uv \
    for dir in /app/.venv/lib/python*/site-packages/torch* \
               /app/.venv/lib/python*/site-packages/nvidia* \
               /app/.venv/lib/python*/site-packages/functorch*; do \
        [ -e "$dir" ] && rm -rf "$dir"; \
    done && \
    . /app/.venv/bin/activate && \
    uv pip install \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# Copy source code
COPY src /app/src

FROM python:3.12.8-slim AS final

EXPOSE 8000

# PYTHONUNBUFFERED=1 to disable output buffering
ENV PYTHONUNBUFFERED=1
ARG VERSION=0.1.0
ENV APP_VERSION=$VERSION

WORKDIR /app

# Copy the virtual environment from the base stage
COPY --from=base /app /app

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"] 