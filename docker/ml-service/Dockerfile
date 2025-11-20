# ============================================================================
# RiseTrader ML Service - Production Dockerfile
# Optimized for ML inference with PyTorch and XGBoost
# ============================================================================

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.11-slim as builder

LABEL maintainer="RiseTrader Team"
LABEL description="Builder stage for RiseTrader ML Service"

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./
RUN pip install --user --no-cache-dir --no-warn-script-location \
    -r requirements.txt

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.11-slim

LABEL maintainer="RiseTrader Team"
LABEL description="RiseTrader ML inference service"
LABEL version="1.0.0"

# Create non-root user
RUN groupadd -r mlservice && useradd -r -g mlservice mlservice

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy ML source code
COPY --chown=mlservice:mlservice src/ml/ ./src/ml/
COPY --chown=mlservice:mlservice src/database/ ./src/database/
COPY --chown=mlservice:mlservice src/utils/ ./src/utils/
COPY --chown=mlservice:mlservice config/ ./config/

# Create directories for models and data
RUN mkdir -p /app/models /app/data /app/logs && \
    chown -R mlservice:mlservice /app

# Set environment variables
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # PyTorch optimizations
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    # Disable CUDA by default (enable with env var)
    CUDA_VISIBLE_DEVICES=""

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import torch; import xgboost" || exit 1

# Switch to non-root user
USER mlservice

# Expose MLflow port (if running MLflow server)
EXPOSE 5000

# Default command - can be overridden
CMD ["python", "-m", "src.ml.inference.predict"]
