# Multi-stage hardened production Dockerfile for Arbitrum Autonomous Trading Bot
# Stage 1: Build & dependency resolution
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/gcp/requirements_bot.txt requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Hardened runtime container (Non-root, minimal attack surface)
FROM python:3.11-slim

LABEL maintainer="Antigravity Trading Agent"
LABEL description="Autonomous On-Chain Arbitrum Trading Bot"

# Create unprivileged system user and group (UID/GID 10001)
RUN groupadd -g 10001 tradingbot && \
    useradd -u 10001 -g tradingbot -s /usr/sbin/nologin -M tradingbot

WORKDIR /app

# Copy python dependencies from builder
COPY --from=builder /root/.local /home/tradingbot/.local

# Copy application source code
COPY . /app

# Ensure proper file ownership
RUN chown -R tradingbot:tradingbot /app /home/tradingbot

# Environment configuration
ENV PATH=/home/tradingbot/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TRADINGAGENTS_SECURITY_MODE=production

# Drop all privileges and run as non-root
USER 10001:10001

# Healthcheck to verify process liveness
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8899/health').getcode() == 200 else 1)" || exit 1

ENTRYPOINT ["python", "scripts/autonomous_arbitrum_trader.py"]
