FROM python:3.12-slim

# ── uv ────────────────────────────────────────────────────────────────────────
# Copy the uv binary from the official image — no pip install needed for uv itself.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ── env ───────────────────────────────────────────────────────────────────────
ENV AIRFLOW_HOME=/opt/airflow \
    AIRFLOW_VERSION=2.10.3 \
    PYTHON_VERSION=3.12

ENV CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

# UV settings for Docker:
#   UV_LINK_MODE=copy   — Docker layers live on different filesystems; copy
#                          prevents "can't hardlink across filesystems" errors.
#   UV_COMPILE_BYTECODE — pre-compile .pyc files for faster container startup.
#   UV_PYTHON_DOWNLOADS — don't let uv download its own Python; we use the
#                          one from python:3.12-slim.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# ── system deps ───────────────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libpq-dev \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# ── airflow user ──────────────────────────────────────────────────────────────
RUN groupadd -r -g 50000 airflow && \
    useradd -r -u 50000 -g airflow -d ${AIRFLOW_HOME} -s /bin/bash airflow

RUN mkdir -p ${AIRFLOW_HOME}/dags ${AIRFLOW_HOME}/logs ${AIRFLOW_HOME}/plugins && \
    chown -R 50000:50000 ${AIRFLOW_HOME} && \
    chmod -R 755 ${AIRFLOW_HOME}

# ── Airflow core ──────────────────────────────────────────────────────────────
# Uses the official Airflow constraint file to pin every transitive dep.
# --mount=type=cache keeps the uv download cache warm across rebuilds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
        "apache-airflow[postgres]==${AIRFLOW_VERSION}" \
        --constraint "${CONSTRAINT_URL}" \
        psycopg2-binary

# ── CPU-only PyTorch ──────────────────────────────────────────────────────────
# Install torch from the CPU wheel index BEFORE requirements-airflow.txt so
# pip/uv's resolver sees torch already satisfied and never fetches the
# ~4 GB CUDA variant that PyPI serves on Linux by default.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# ── project requirements ──────────────────────────────────────────────────────
COPY requirements-airflow.txt /tmp/requirements-airflow.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
        -r /tmp/requirements-airflow.txt

# ── entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER airflow
WORKDIR ${AIRFLOW_HOME}

EXPOSE 8080

CMD ["/entrypoint.sh"]
