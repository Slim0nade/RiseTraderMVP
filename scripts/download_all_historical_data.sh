#!/bin/bash
# =============================================================================
# RiseTrader - Download Full Historical Data
# =============================================================================
# Downloads M1 data from Dukascopy for GOLD, USA500, and aggregates to M5/M30/H1.
# Also aggregates existing VIX M1 data to higher timeframes.
#
# Run from the project root:
#   docker exec -it risetrader-api bash -c "cd /app && bash scripts/download_all_historical_data.sh"
#
# Or directly:
#   cd /path/to/RiseTraderMVP && bash scripts/download_all_historical_data.sh
# =============================================================================

set -e

echo "============================================="
echo "RiseTrader Historical Data Download"
echo "Date: $(date)"
echo "============================================="

# --- STEP 1: Download GOLD (XAUUSD) from Dukascopy ---
echo ""
echo ">>> STEP 1: Downloading GOLD M1 data from Dukascopy (2015-present)..."
echo "    Dukascopy symbol: XAUUSD -> stored as 'GOLD' in database"
python3 scripts/import_dukascopy.py \
    --symbol GOLD \
    --start 2015-01-01 \
    --end $(date +%Y-%m-%d) \
    --timeframe M1 \
    --batch-days 30 \
    --aggregate

echo ">>> GOLD download complete!"

# --- STEP 2: Download USA500 (S&P 500) from Dukascopy ---
echo ""
echo ">>> STEP 2: Downloading USA500 M1 data from Dukascopy (2015-present)..."
echo "    Dukascopy symbol: USA500IDXUSD -> stored as 'USA500' in database"
python3 scripts/import_dukascopy.py \
    --symbol USA500 \
    --start 2015-01-01 \
    --end $(date +%Y-%m-%d) \
    --timeframe M1 \
    --batch-days 30 \
    --aggregate

echo ">>> USA500 download complete!"

# --- STEP 3: Update CrudeOIL M5 data (currently ends at 2024-12-06) ---
echo ""
echo ">>> STEP 3: Updating CrudeOIL M5 data..."
python3 scripts/import_dukascopy.py \
    --symbol CrudeOIL \
    --start 2024-12-01 \
    --end $(date +%Y-%m-%d) \
    --timeframe M1 \
    --batch-days 30

# Aggregate all CrudeOIL M1 to higher timeframes
python3 scripts/import_dukascopy.py \
    --symbol CrudeOIL \
    --start 2009-08-01 \
    --aggregate-only

echo ">>> CrudeOIL update complete!"

# --- STEP 4: Aggregate VIX M1 to higher timeframes ---
echo ""
echo ">>> STEP 4: Aggregating VIX M1 to M5/H1..."
python3 scripts/import_dukascopy.py \
    --symbol VIX \
    --start 2014-01-01 \
    --aggregate-only

echo ">>> VIX aggregation complete!"

# --- STEP 5: Verify data ---
echo ""
echo "============================================="
echo "DATA VERIFICATION"
echo "============================================="
python3 scripts/check_data_status.py 2>/dev/null || python3 -c "
import asyncio
from sqlalchemy import text
import sys
sys.path.insert(0, '.')
from src.database.config import create_engine_from_env, create_session_factory

async def check():
    engine = create_engine_from_env()
    sf = create_session_factory(engine)
    async with sf() as session:
        result = await session.execute(text('''
            SELECT symbol, timeframe, COUNT(*) as candles,
                   MIN(time)::date as start, MAX(time)::date as end
            FROM market_data
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
        '''))
        rows = result.fetchall()
        print(f\"{'Symbol':<12} {'TF':<5} {'Candles':>10} {'Start':>12} {'End':>12}\")
        print('-' * 55)
        for r in rows:
            print(f'{r[0]:<12} {r[1]:<5} {r[2]:>10,} {str(r[3]):>12} {str(r[4]):>12}')

asyncio.run(check())
"

echo ""
echo "============================================="
echo "ALL DOWNLOADS COMPLETE!"
echo "============================================="
echo "Next steps:"
echo "  1. Run backtests: Use the MCP tools or dashboard"
echo "  2. Check data quality: GET /api/eda/symbols-overview"
echo "  3. Optimize strategies: Use optimize_strategy tool"
