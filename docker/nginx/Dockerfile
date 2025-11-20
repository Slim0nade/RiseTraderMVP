# ============================================================================
# RiseTrader Nginx Gateway - Production Dockerfile
# Reverse proxy and load balancer
# ============================================================================

FROM nginx:1.25-alpine

LABEL maintainer="RiseTrader Team"
LABEL description="RiseTrader Nginx reverse proxy"
LABEL version="1.0.0"

# Install additional tools
RUN apk add --no-cache \
    curl \
    openssl \
    certbot \
    certbot-nginx

# Copy nginx configuration files
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/conf.d/ /etc/nginx/conf.d/

# Create SSL directory
RUN mkdir -p /etc/nginx/ssl

# Generate self-signed certificate for development
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx-selfsigned.key \
    -out /etc/nginx/ssl/nginx-selfsigned.crt \
    -subj "/C=US/ST=State/L=City/O=RiseTrader/CN=localhost"

# Create dhparam for SSL
RUN openssl dhparam -out /etc/nginx/ssl/dhparam.pem 2048

# Create log directory
RUN mkdir -p /var/log/nginx && \
    chown -R nginx:nginx /var/log/nginx

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose HTTP and HTTPS
EXPOSE 80 443

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
