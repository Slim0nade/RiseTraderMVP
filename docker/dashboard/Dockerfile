# ============================================================================
# RiseTrader Dashboard - Production Dockerfile
# React TypeScript frontend with Nginx
# ============================================================================

# ============================================================================
# Stage 1: Build React application
# ============================================================================
FROM node:18-alpine as builder

LABEL maintainer="RiseTrader Team"
LABEL description="Builder stage for RiseTrader Dashboard"

WORKDIR /app

# Copy package files
COPY dashboard/package.json dashboard/package-lock.json* ./

# Install dependencies
RUN npm ci --only=production && \
    npm cache clean --force

# Copy source code
COPY dashboard/ ./

# Build arguments for API URL
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Build the application
RUN npm run build

# ============================================================================
# Stage 2: Nginx server
# ============================================================================
FROM nginx:1.25-alpine

LABEL maintainer="RiseTrader Team"
LABEL description="RiseTrader React dashboard"
LABEL version="1.0.0"

# Install curl for health checks
RUN apk add --no-cache curl

# Copy built application from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
COPY docker/dashboard/nginx.conf /etc/nginx/nginx.conf
COPY docker/dashboard/default.conf /etc/nginx/conf.d/default.conf

# Create nginx cache directory
RUN mkdir -p /var/cache/nginx && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

# Expose port 80
EXPOSE 80

# Run as non-root user
USER nginx

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
