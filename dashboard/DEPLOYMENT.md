# RiseTrader Dashboard - Deployment Guide

## Prerequisites

- Node.js 18+ installed
- npm or yarn package manager
- RiseTrader API running at http://localhost:8003
- Git (for version control)

## Local Development

### 1. Install Dependencies

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/dashboard
npm install
```

### 2. Configure Environment

Create `.env` file:

```env
VITE_API_BASE_URL=http://localhost:8003
VITE_WS_URL=ws://localhost:8003/ws
VITE_API_KEY=
```

### 3. Start Development Server

```bash
npm run dev
```

Dashboard available at http://localhost:3000

## Production Build

### 1. Build for Production

```bash
npm run build
```

This creates optimized production build in `dist/` directory.

### 2. Preview Production Build

```bash
npm run preview
```

### 3. Build Statistics

Check bundle size:

```bash
npm run build -- --mode production
```

## Deployment Options

### Option 1: Static Hosting (Netlify/Vercel)

#### Netlify

1. Install Netlify CLI:
```bash
npm install -g netlify-cli
```

2. Build and deploy:
```bash
npm run build
netlify deploy --prod --dir=dist
```

3. Configure environment variables in Netlify dashboard:
   - `VITE_API_BASE_URL`
   - `VITE_WS_URL`
   - `VITE_API_KEY`

#### Vercel

1. Install Vercel CLI:
```bash
npm install -g vercel
```

2. Deploy:
```bash
vercel --prod
```

3. Set environment variables via Vercel dashboard

### Option 2: Docker Deployment

Create `Dockerfile`:

```dockerfile
# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

Create `nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://api:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /ws {
        proxy_pass http://api:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;
}
```

Build and run:

```bash
docker build -t risetrader-dashboard .
docker run -p 3000:80 risetrader-dashboard
```

### Option 3: Docker Compose with API

Add to main `docker-compose.yml`:

```yaml
  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    environment:
      - VITE_API_BASE_URL=http://api:8003
      - VITE_WS_URL=ws://api:8003/ws
    depends_on:
      - api
    networks:
      - risetrader
```

### Option 4: Nginx Reverse Proxy

If serving from same server as API:

```nginx
# /etc/nginx/sites-available/risetrader

server {
    listen 80;
    server_name your-domain.com;

    # Dashboard
    location / {
        root /var/www/risetrader/dashboard/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api {
        proxy_pass http://localhost:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;
}
```

Enable and restart:

```bash
sudo ln -s /etc/nginx/sites-available/risetrader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Environment Configuration

### Development

```env
VITE_API_BASE_URL=http://localhost:8003
VITE_WS_URL=ws://localhost:8003/ws
VITE_API_KEY=
```

### Staging

```env
VITE_API_BASE_URL=https://staging-api.risetrader.com
VITE_WS_URL=wss://staging-api.risetrader.com/ws
VITE_API_KEY=your-staging-key
```

### Production

```env
VITE_API_BASE_URL=https://api.risetrader.com
VITE_WS_URL=wss://api.risetrader.com/ws
VITE_API_KEY=your-production-key
```

## SSL/HTTPS Setup

### Using Let's Encrypt

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo certbot renew --dry-run
```

### Update WebSocket URL

Change to `wss://` for secure WebSocket:

```env
VITE_WS_URL=wss://api.risetrader.com/ws
```

## Performance Optimization

### 1. Enable Gzip Compression

Already configured in nginx.conf above.

### 2. Enable Caching

Add to nginx config:

```nginx
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### 3. CDN Integration

Use CDN for static assets:

- Cloudflare
- AWS CloudFront
- Fastly

### 4. Pre-compression

Pre-compress assets:

```bash
npm install -g gzipper
gzipper compress --verbose ./dist
```

## Monitoring

### 1. Error Tracking

Add Sentry:

```bash
npm install @sentry/react @sentry/tracing
```

Configure in `src/main.tsx`:

```typescript
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: "your-sentry-dsn",
  environment: import.meta.env.MODE,
  tracesSampleRate: 1.0,
});
```

### 2. Analytics

Add Google Analytics or Mixpanel:

```html
<!-- Add to index.html -->
<script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
```

### 3. Performance Monitoring

Use Lighthouse CI or WebPageTest for continuous monitoring.

## CI/CD Pipeline

### GitHub Actions Example

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Dashboard

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        working-directory: ./dashboard
        run: npm ci

      - name: Build
        working-directory: ./dashboard
        run: npm run build
        env:
          VITE_API_BASE_URL: ${{ secrets.API_BASE_URL }}
          VITE_WS_URL: ${{ secrets.WS_URL }}
          VITE_API_KEY: ${{ secrets.API_KEY }}

      - name: Deploy to Server
        uses: easingthemes/ssh-deploy@main
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          REMOTE_HOST: ${{ secrets.REMOTE_HOST }}
          REMOTE_USER: ${{ secrets.REMOTE_USER }}
          SOURCE: "dashboard/dist/"
          TARGET: "/var/www/risetrader/dashboard/"
```

## Health Checks

### 1. Add Health Check Endpoint

Dashboard automatically checks `/health` endpoint.

### 2. Uptime Monitoring

Use services like:
- UptimeRobot
- Pingdom
- StatusCake

## Rollback Strategy

### Quick Rollback

Keep previous builds:

```bash
# Before new deployment
cp -r /var/www/risetrader/dashboard /var/www/risetrader/dashboard.backup

# Rollback if needed
rm -rf /var/www/risetrader/dashboard
mv /var/www/risetrader/dashboard.backup /var/www/risetrader/dashboard
```

### Git-based Rollback

```bash
git log --oneline
git checkout <previous-commit-hash>
npm run build
# Deploy
```

## Troubleshooting

### Build Fails

```bash
# Clear cache
rm -rf node_modules dist
npm install
npm run build
```

### WebSocket Connection Issues

1. Check CORS settings on API
2. Verify WebSocket URL (ws:// vs wss://)
3. Check firewall rules
4. Verify nginx WebSocket proxy config

### API Connection Issues

1. Check VITE_API_BASE_URL
2. Verify CORS on API
3. Check network connectivity
4. Verify API is running

### Performance Issues

1. Enable production build
2. Check bundle size with `npm run build -- --mode production`
3. Enable gzip compression
4. Use CDN for assets
5. Check browser console for errors

## Security Checklist

- [ ] HTTPS enabled
- [ ] API key stored securely
- [ ] CORS configured properly
- [ ] Content Security Policy headers
- [ ] Rate limiting on API
- [ ] Regular dependency updates
- [ ] Error messages don't expose sensitive info
- [ ] Authentication implemented
- [ ] Input validation on forms

## Maintenance

### Regular Updates

```bash
# Update dependencies
npm update

# Check for security vulnerabilities
npm audit

# Fix vulnerabilities
npm audit fix
```

### Backup Strategy

1. Backup source code (Git)
2. Backup environment variables
3. Backup nginx configuration
4. Regular database backups (API)

## Support

For issues or questions:
- Check logs: Browser console, nginx error logs
- Review API documentation
- Contact: support@risetrader.com
