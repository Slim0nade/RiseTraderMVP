# RiseTrader Dashboard

Professional trading dashboard for the RiseTrader autonomous trading platform.

## Features

- Real-time P&L and position monitoring
- 10 autonomous agent status visualization
- Interactive trading charts with Recharts
- WebSocket real-time data streaming
- ML forecast visualization
- Strategy management
- Performance analytics
- Responsive design (mobile, tablet, desktop)

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **TanStack Query** - Data fetching
- **Zustand** - State management
- **Recharts** - Charts
- **React Router** - Routing
- **Axios** - HTTP client

## Quick Start

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```env
VITE_API_BASE_URL=http://localhost:8003
VITE_WS_URL=ws://localhost:8003/ws
VITE_API_KEY=your-api-key
```

### 3. Start Development Server

```bash
npm run dev
```

Dashboard will be available at http://localhost:3000

### 4. Build for Production

```bash
npm run build
```

Built files will be in `dist/` directory.

## Project Structure

```
dashboard/
├── src/
│   ├── api/              # API client and endpoints
│   ├── components/       # React components
│   │   ├── agents/      # Agent monitoring components
│   │   ├── charts/      # Chart components
│   │   ├── common/      # Shared components
│   │   ├── layout/      # Layout components
│   │   └── trading/     # Trading components
│   ├── hooks/           # Custom React hooks
│   ├── pages/           # Page components
│   ├── store/           # Zustand stores
│   ├── types/           # TypeScript types
│   ├── utils/           # Utility functions
│   ├── App.tsx          # Main app component
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── index.html           # HTML template
├── package.json         # Dependencies
├── tsconfig.json        # TypeScript config
├── vite.config.ts       # Vite config
└── tailwind.config.js   # Tailwind config
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript type checking

## API Integration

The dashboard connects to the RiseTrader API at `http://localhost:8003` and uses 36 endpoints:

### Health & System
- GET `/health`
- GET `/api/system/status`

### Market Data
- GET `/api/market-data/{symbol}/latest`
- GET `/api/market-data/{symbol}`
- GET `/api/market-data/symbols`

### Trading
- GET `/api/trading/positions`
- GET `/api/trading/positions/{id}`
- POST `/api/trading/positions/{id}/close`
- GET `/api/trading/history`
- POST `/api/trading/execute`

### Agents
- GET `/api/agents/status`
- GET `/api/agents/{name}/status`
- POST `/api/agents/{name}/start`
- POST `/api/agents/{name}/stop`
- POST `/api/agents/{name}/restart`

### Forecasts
- GET `/api/forecasts/latest`
- GET `/api/forecasts/{symbol}/history`
- POST `/api/forecasts/generate`

### Strategies
- GET `/api/strategies`
- GET `/api/strategies/{id}`
- POST `/api/strategies`
- PUT `/api/strategies/{id}`
- DELETE `/api/strategies/{id}`
- PATCH `/api/strategies/{id}/toggle`

### Performance
- GET `/api/performance/metrics`
- GET `/api/performance/equity-curve`
- GET `/api/performance/daily-pnl`

## WebSocket Events

Real-time updates via WebSocket:

- `new_tick` - Market data tick
- `position_opened` - New position
- `position_updated` - Position update
- `position_closed` - Position closed
- `agent_status_changed` - Agent status change
- `forecast_generated` - New forecast
- `pnl_updated` - P&L update
- `risk_alert` - Risk alert
- `system_alert` - System alert

## Pages

### Dashboard (/)
- System overview
- Key metrics
- Recent trades
- Agent status
- Performance summary

### Agents (/agents)
- 10 agent monitoring
- Start/stop/restart controls
- Event logs
- Health metrics

### Market Data (/market)
- Real-time price charts
- Symbol/timeframe selector
- OHLCV data
- Market statistics

### Trading (/trading)
- Open positions
- Close position controls
- Trade history
- P&L tracking

### Strategies (/strategies)
- Strategy list
- Enable/disable strategies
- Performance per strategy
- Configuration

### Performance (/performance)
- P&L metrics
- Equity curve
- Daily performance chart
- Risk analysis

### Forecasts (/forecasts)
- ML predictions
- Confidence levels
- Multiple horizons
- Model comparison

### Settings (/settings)
- API key management
- Theme toggle
- Default preferences
- Alert settings

## Theming

Dark theme by default with custom color scheme:

- Primary: Blue (#3b82f6)
- Success: Green (#22c55e)
- Danger: Red (#ef4444)
- Warning: Yellow (#f59e0b)
- Dark: Slate shades

## Performance Optimization

- Component memoization with React.memo
- Query caching with TanStack Query
- Lazy loading with React.lazy
- Code splitting by route
- WebSocket connection pooling
- Debounced updates

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Contributing

1. Create feature branch
2. Make changes
3. Run type check: `npm run type-check`
4. Run linter: `npm run lint`
5. Test thoroughly
6. Submit pull request

## License

Proprietary - RiseTrader © 2024
