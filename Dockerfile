# syntax=docker/dockerfile:1.4
# Stage 1: Build virtual environment and wheels
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r requirements.txt

# Stage 2: Hardened Runtime Container
FROM python:3.11-slim-bookworm AS runner

# Security: Dedicated unprivileged system user and group (UID/GID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -M -d /app appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TRADINGAGENTS_SECURITY_MODE=production

WORKDIR /app

# Copy virtualenv from builder (owned by root, executable by all)
COPY --from=builder --chown=root:root /opt/venv /opt/venv

# Copy application source code (owned by root, read-only for appuser)
COPY --chown=root:root core /app/core
COPY --chown=root:root execution /app/execution
COPY --chown=root:root crypto_pipeline /app/crypto_pipeline
COPY --chown=root:root simulation /app/simulation
COPY --chown=root:root visualization /app/visualization
COPY --chown=root:root pyproject.toml /app/pyproject.toml

# Prepare isolated directories for writable state (keystores, cache, results, sessions) with mode 700
RUN mkdir -p /app/data /app/results /app/keystores /app/sessions && \
    chown -R appuser:appgroup /app/data /app/results /app/keystores /app/sessions && \
    chmod 700 /app/keystores /app/data /app/results /app/sessions

# Non-root execution
USER 10001:10001

# Healthcheck targeting local loopback interface
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8899/api/health')" || exit 1

EXPOSE 8899

# Run server with factory and no server header
CMD ["uvicorn", "visualization.server.app:create_visualization_app", "--factory", "--host", "0.0.0.0", "--port", "8899", "--no-server-header"]
