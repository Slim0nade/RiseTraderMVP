# ============================================================================
# RiseTrader API Service - Production Dockerfile
# Multi-stage build for optimized production image
# ============================================================================

# ============================================================================
# Stage 1: Builder - Install dependencies and compile
# ============================================================================
FROM python:3.11-slim as builder

LABEL maintainer="RiseTrader Team"
LABEL description="Builder stage for RiseTrader API"

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    libzmq3-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib (required for technical analysis)
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Copy requirements and install Python dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install --user --no-cache-dir --no-warn-script-location \
    -r requirements.txt \
    -r requirements-api.txt

# ============================================================================
# Stage 2: Runtime - Lightweight production image
# ============================================================================
FROM python:3.11-slim

LABEL maintainer="RiseTrader Team"
LABEL description="RiseTrader FastAPI service with autonomous agents"
LABEL version="1.0.0"

# Create non-root user for security
RUN groupadd -r risetrader && useradd -r -g risetrader risetrader

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libzmq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy TA-Lib from builder
COPY --from=builder /usr/lib/libta_lib.* /usr/lib/
COPY --from=builder /usr/include/ta-lib/ /usr/include/ta-lib/

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY --chown=risetrader:risetrader src/ ./src/
COPY --chown=risetrader:risetrader config/ ./config/
COPY --chown=risetrader:risetrader alembic.ini ./

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/models && \
    chown -R risetrader:risetrader /app

# Set environment variables
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Performance tuning
    MALLOC_TRIM_THRESHOLD_=100000 \
    MALLOC_MMAP_THRESHOLD_=50000

# Health check - ping the health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER risetrader

# Expose API port
EXPOSE 8000

# Run uvicorn with production settings
CMD ["uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--access-log", \
     "--no-use-colors"]
