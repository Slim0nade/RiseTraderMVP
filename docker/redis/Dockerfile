# ============================================================================
# RiseTrader Redis 7 - Caching and Pub/Sub
# Optimized for agent state management and real-time data
# ============================================================================

FROM redis:7-alpine

LABEL maintainer="RiseTrader Team"
LABEL description="Redis 7 for caching and pub/sub messaging"
LABEL version="1.0.0"

# Install additional tools
RUN apk add --no-cache \
    curl \
    bash

# Copy custom Redis configuration
COPY docker/redis/redis.conf /usr/local/etc/redis/redis.conf

# Create data directory
RUN mkdir -p /data && \
    chown -R redis:redis /data

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD redis-cli ping || exit 1

# Expose Redis port
EXPOSE 6379

# Switch to redis user
USER redis

# Run Redis with custom config
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
