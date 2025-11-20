# ============================================================================
# RiseTrader PostgreSQL 17 with Extensions
# Time-series optimized database for financial data
# ============================================================================

FROM postgres:17-alpine

LABEL maintainer="RiseTrader Team"
LABEL description="PostgreSQL 17 with TimescaleDB and financial extensions"
LABEL version="1.0.0"

# Install build dependencies and extensions
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    g++ \
    make \
    cmake \
    git \
    openssl-dev \
    && apk add --no-cache \
    curl \
    wget

# Install TimescaleDB extension (for time-series data)
# Note: TimescaleDB for Alpine Linux - compile from source or use prebuilt
RUN apk add --no-cache --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing \
    timescaledb

# Create initialization directory
RUN mkdir -p /docker-entrypoint-initdb.d

# Copy initialization scripts
COPY docker/postgres/init.sql /docker-entrypoint-initdb.d/01-init.sql
COPY docker/postgres/extensions.sql /docker-entrypoint-initdb.d/02-extensions.sql

# Copy custom PostgreSQL configuration
COPY docker/postgres/postgresql.conf /etc/postgresql/postgresql.conf

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-risetrader} || exit 1

# Set default environment variables
ENV POSTGRES_DB=risetrader \
    POSTGRES_USER=postgres \
    PGDATA=/var/lib/postgresql/data

# Expose PostgreSQL port
EXPOSE 5432

# Use custom configuration
CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
