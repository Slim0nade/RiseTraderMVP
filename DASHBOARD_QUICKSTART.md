# RiseTrader Dashboard - Quick Start Guide

## One-Line Start

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/dashboard && ./start.sh
```

---

## Manual Start (3 Steps)

### 1. Install Dependencies

```bash
cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/dashboard
npm install
```

### 2. Configure Environment (Optional)

Edit `.env` if needed:

```bash
VITE_API_BASE_URL=http://localhost:8003
VITE_WS_URL=ws://localhost:8003/ws
VITE_API_KEY=
```

### 3. Start Development Server

```bash
npm run dev
```

Dashboard opens at: http://localhost:3000

---

## What You Get

### 8 Pages
1. **Dashboard** (/) - System overview with metrics
2. **Agents** (/agents) - Monitor 10 trading agents
3. **Market Data** (/market) - Real-time price charts
4. **Trading** (/trading) - Positions & trade history
5. **Strategies** (/strategies) - Strategy management
6. **Performance** (/performance) - Analytics & charts
7. **Forecasts** (/forecasts) - ML predictions
8. **Settings** (/settings) - User preferences

### Features
- Real-time WebSocket updates
- 36 API endpoints integrated
- Interactive charts with Recharts
- Responsive design (mobile/tablet/desktop)
- Dark theme by default
- Toast notifications
- Error boundaries
- Type-safe with TypeScript

---

## Prerequisites

- Node.js 18+ ([Download](https://nodejs.org/))
- RiseTrader API running at http://localhost:8003
- Modern browser (Chrome/Firefox/Safari)

---

## Common Commands

```bash
# Development
npm run dev              # Start dev server (port 3000)

# Production
npm run build            # Build for production
npm run preview          # Preview production build

# Code Quality
npm run lint             # Run ESLint
npm run type-check       # TypeScript check

# Maintenance
npm install              # Install/update dependencies
npm update               # Update all dependencies
npm audit                # Security check
```

---

## Project Structure

```
dashboard/
├── src/
│   ├── pages/          # 8 page components
│   ├── components/     # Reusable UI components
│   ├── api/            # API client & 36 endpoints
│   ├── store/          # Zustand state stores
│   ├── hooks/          # Custom React hooks
│   └── types/          # TypeScript types
├── public/             # Static assets
├── package.json        # Dependencies
└── vite.config.ts      # Build config
```

---

## Troubleshooting

### Issue: "Cannot connect to API"
**Solution:** Ensure RiseTrader API is running:
```bash
# In main project directory
python main.py
# Should see: API running at http://localhost:8003
```

### Issue: "WebSocket connection failed"
**Solution:** Check `.env` file has correct WebSocket URL:
```bash
VITE_WS_URL=ws://localhost:8003/ws
```

### Issue: "npm install fails"
**Solution:** Clear cache and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

### Issue: "Port 3000 already in use"
**Solution:** Kill process on port 3000:
```bash
lsof -ti:3000 | xargs kill -9
```

---

## Next Steps

After starting the dashboard:

1. **Verify API Connection**
   - Check green "API Online" badge in header
   - Look for "Live" WebSocket indicator

2. **Explore Pages**
   - Dashboard: View system overview
   - Agents: Monitor agent status
   - Market Data: Check real-time charts
   - Trading: See positions (if any)

3. **Configure Settings**
   - Go to Settings page (/settings)
   - Set default symbol/timeframe
   - Configure alert preferences

4. **Watch Real-Time Updates**
   - Position updates appear automatically
   - Agent status changes show live
   - Charts update in real-time

---

## Production Deployment

### Quick Deploy

```bash
# Build
npm run build

# Output in dist/ folder
ls -la dist/
```

### Deploy Options

1. **Static Hosting** (Netlify/Vercel)
   ```bash
   npm run build
   netlify deploy --prod --dir=dist
   ```

2. **Docker**
   ```bash
   docker build -t risetrader-dashboard .
   docker run -p 3000:80 risetrader-dashboard
   ```

3. **Nginx**
   ```bash
   npm run build
   sudo cp -r dist/* /var/www/risetrader/dashboard/
   ```

See `DEPLOYMENT.md` for detailed instructions.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `package.json` | Dependencies & scripts |
| `vite.config.ts` | Build configuration |
| `.env` | Environment variables |
| `src/App.tsx` | Main app with routing |
| `src/api/endpoints.ts` | All API endpoints |
| `src/types/index.ts` | Type definitions |

---

## Documentation

- **README.md** - Getting started guide
- **DEPLOYMENT.md** - Deployment instructions
- **DASHBOARD_COMPLETE.md** - Complete feature summary
- **DASHBOARD_INDEX.md** - File structure index
- **This file** - Quick start reference

---

## Support

### API Endpoints
- Health: http://localhost:8003/health
- Docs: http://localhost:8003/docs
- OpenAPI: http://localhost:8003/openapi.json

### Dashboard
- Local: http://localhost:3000
- All routes: /, /agents, /market, /trading, /strategies, /performance, /forecasts, /settings

### Getting Help
- Check browser console for errors
- Review API logs
- Check network tab for API calls
- Verify WebSocket connection in Network tab

---

## Performance Tips

1. **Keep API running** - Dashboard needs API for data
2. **Use modern browser** - Chrome/Firefox recommended
3. **Enable cache** - TanStack Query caches API responses
4. **WebSocket priority** - Faster than polling
5. **Close unused tabs** - Reduces resource usage

---

## Development Tips

1. **Hot reload** - Changes appear instantly
2. **TypeScript errors** - Fix type errors before building
3. **ESLint** - Run `npm run lint` regularly
4. **Component organization** - Keep components small
5. **State management** - Use Zustand stores for shared state

---

## Tech Stack Summary

| Category | Technology |
|----------|------------|
| Framework | React 18 |
| Language | TypeScript |
| Build Tool | Vite |
| Styling | TailwindCSS |
| Charts | Recharts |
| State | Zustand + TanStack Query |
| Routing | React Router |
| API | Axios |

---

## Quick Stats

- **43 source files**
- **8 pages**
- **19 components**
- **36 API endpoints**
- **4 state stores**
- **3 custom hooks**
- **~5,500 lines of code**

---

## Status

**COMPLETE & PRODUCTION-READY**

All features implemented:
- Real-time updates
- Full API integration
- Responsive design
- Error handling
- Type safety
- Documentation

Ready to:
- Start development
- Deploy to production
- Customize for your needs

---

**Start now:** `cd dashboard && ./start.sh`

---

*RiseTrader Dashboard v1.0.0 - November 2024*
