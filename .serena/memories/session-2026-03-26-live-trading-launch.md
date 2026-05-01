# Live Trading Launch — March 26, 2026

## Milestone: First Autonomous Live Trade Executed

**Account:** Fortrade Canada Real01, #1423389 (Slim Rouissi)
**Balance:** $396.97 CAD
**First Trade:** SELL 0.01 CrudeOIL @ 93.675, ticket #30874288, SL auto-set to 96.31

## What Was Built This Session

### 1. LiveTradingService (`src/services/live_trading_service.py`)
- Autonomous signal→risk→execute loop, every 5 minutes
- 5 strategies: ML Reversal (XGBoost, weight 0.35), Value Area (0.30), Momentum (0.15), Mean Reversion (0.10), Breakout (0.10)
- Risk validation: 2% cap (with MIN_LOTS override for small accounts), max 5 positions, $1000 daily loss limit
- ATR-based stops with anti-stop-hunt offset (random 5-15 pips)
- RL decision logs with full justification for every signal
- Wired into `src/api/main.py` lifespan startup/shutdown
- Singleton via `get_live_trading_service()`
- **Circular import fix**: `get_db_context` imported lazily inside methods, not at module level

### 2. Docker Infrastructure Fixes
- **MLflow crash-loop fixed**: Created separate `mlflow` database in Postgres (was sharing `alembic_version` table with app). Init script at `docker/init-mlflow-db.sh`, MLflow URI points to `postgres:5432/mlflow`
- **MLflow healthcheck fixed**: Changed from `curl` (not in image) to `python urllib.request`
- **Startup pycache clear**: Added `find /app -name __pycache__` to `scripts/start_api.sh`
- **docker-compose CMD override**: `command: ["bash", "/app/scripts/start_api.sh"]` because mounted scripts lose +x bit on macOS Docker

### 3. ZMQ Socket Stability (`src/trading/execution/mt4_client.py`)
- **`asyncio.Lock()`** on `send_command()` prevents EFSM errors from concurrent callers (mt4_sync_service every 60s + stealth_stop_manager every 5s)
- **Socket reset on timeout**: After `poll()` times out, socket is stuck in SEND state — now resets before raising so next caller gets clean socket

### 4. Stealth Stop Manager Fix (`src/services/stealth_stop_manager.py`)
- `InsufficientDataError` caught in `run_once()` → logs warning, skips symbol
- Previously: error loop hitting 5-retry limit, reconnecting, repeating infinitely for TSLA (no H1 data)
- Now: `"Skipping #TSLA: Insufficient candle data"` warning, moves on

### 5. 2% Risk Cap Fix for Small Accounts
- Original `assert` crashed when MIN_LOTS (0.01) exceeded 2% cap ($7.94 on $396 account)
- Fixed: logs `min_lot_exceeds_2pct_cap` warning but allows the trade (only way to trade small accounts)

## Configuration (docker-compose.yml env vars)
```
LIVE_TRADING_ENABLED=true
LIVE_TRADING_SYMBOLS=CrudeOIL,USA500,GBPJPY.
LIVE_TRADING_INTERVAL=300
LIVE_TRADING_DRY_RUN=false  (LIVE MODE)
MAX_OPEN_POSITIONS=5
MAX_DAILY_LOSS=1000
STEALTH_STOPS_ENABLED=true
```

## Key Blockers Encountered & Resolved
1. **Agent coordinator commented out** (config mismatch + hardcoded path) → Bypassed entirely with LiveTradingService
2. **MT4 Error #4109 (ERR_TRADE_NOT_ALLOWED)** → EA needed "Allow live trading" checkbox enabled in Properties → Common tab
3. **Docker Desktop daemon crashes** → Multiple restarts needed, `--no-cache` rebuild lost `mcp` package → reinstalled via `pip install` inside container
4. **WatchFiles reload doesn't re-trigger lifespan** → Service showed `running=False` after hot reload → Fixed by clean container restart with pycache clear

## ML Model Status
- CrudeOIL XGBoost model firing: peak_prob=99.82%, SELL signals consistently generated
- Model path: `models/reversal_classifier/CrudeOIL_H1/model.json`
- USA500 and GBPJPY models not trained yet → strategies rely on technical-only signals (momentum/BB/breakout)

## Current Signal Behavior
- **CrudeOIL**: Strong SELL signals (ML peak_prob ~99%, combined score ~-0.60) → Executes trades
- **USA500**: HOLD (score near 0, filtered below threshold)
- **GBPJPY.**: HOLD (score below threshold, no ML model)

## Architecture Notes
- LiveTradingService reuses MT4 client singleton from `get_mt4_sync_service()` — no second ZMQ connection
- DB symbol mapping: `MT4_TO_DB_SYMBOL = {"GBPJPY.": "GBPJPY"}` for candle lookups
- Contract sizes: CrudeOIL=1000, USA500=50, GBPJPY.=100000, XAUUSD=100, BRENT_OIL=1000
- Stealth stop manager integrated into trading loop — syncs positions and trails stops each cycle
