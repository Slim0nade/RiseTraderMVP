# AGENT TEAM PROMPT: Data Engineering Sprint — Multi-Source Historical Backfill + Live MT4 Multi-Symbol Streaming

## MISSION
Backfill complete H1 and M1 historical candles (Jan 2020 → present) for 9 symbols from 3 external sources into PostgreSQL, add `TWELVEDATA` to the datasource ENUM, and wire the MT4 EA to stream live candles for all 9 symbols. This unblocks Phase 3 gate (crisis replay requires USA500 data) and Phase 4 (ML retraining requires multi-symbol history).

## CONTEXT

**Current DB state:** 13.5M+ candles, CrudeOIL only (from MT4 + Dukascopy). Missing: USA500, BRENT_OIL, GBPJPY, WHEAT, CORN, GASOLINE, TSLA, MSFT.

**Data source mapping (researched and confirmed):**

| Symbol | DB Name | Source | API Symbol | Timeframes | Date Range | Notes |
|--------|---------|--------|------------|------------|------------|-------|
| USA500 | USA500 | Dukascopy | USA500IDXUSD | M1, H1 | Jan 2020 → now | Free, tick→M1 aggregation |
| BRENT_OIL | BRENT_OIL | Dukascopy | BCOUSD | M1, H1 | Jan 2020 → now | Free, tick→M1 aggregation |
| GBPJPY | GBPJPY | Dukascopy | GBPJPY | M1, H1 | Jan 2020 → now | Free, tick→M1 aggregation |
| WHEAT | WHEAT | TwelveData | W_1 | M1, H1 | Jan 2020 → now | Free tier: 800 calls/day |
| CORN | CORN | TwelveData | C_1 | M1, H1 | Jan 2020 → now | Free tier: 800 calls/day |
| GASOLINE | GASOLINE | TwelveData | XB1 | M1, H1 | Jan 2020 → now | Free tier: 800 calls/day |
| TSLA | TSLA | yfinance | TSLA | D1 only | Jan 2020 → now | No M1/H1 available free |
| MSFT | MSFT | yfinance | MSFT | D1 only | Jan 2020 → now | No M1/H1 available free |
| CrudeOIL | CrudeOIL | Already present | — | M1, H1, D1 | Full history | 13.5M candles in DB |

**Existing infrastructure:**
- `scripts/download_free_data.py` — Dukascopy downloader (binary tick→M1 aggregation). Already works for CrudeOIL. Resumable.
- `scripts/import_csvs_to_db.py` — CSV importer with ON CONFLICT upsert, batch size 5000. Has `YFINANCE_STOCKS` and `DUKASCOPY_SYMBOLS` mappings.
- Unique constraint: `(time, source, timeframe, symbol)` — re-runs are safe, duplicates are upserted.
- Datasource ENUM: `BARCHART, MT4, BC, CSV, DUKASCOPY, HISTDATA` — **missing `TWELVEDATA`, needs Alembic migration**.
- MT4 EA streams on ports 5555/5556 via ZMQ. `mt4_sync_service.py` handles ingestion with buffer+flush pattern.
- `config/mt4_config.yaml` has symbol list for streaming (already includes the 9 symbols).

**Rate limit math for TwelveData free tier:**
- Each API call returns max 5000 M1 candles (~3.5 trading days)
- Jan 2020 → Mar 2026 ≈ 6.2 years ≈ 1560 trading days
- Per symbol: ~1560 / 3.5 ≈ 446 calls for M1
- Per symbol H1: ~1560 / (5000/6.5 hours per day) ≈ ~3 calls
- 3 symbols × ~450 calls = ~1350 total calls
- At 800 calls/day = **~2 days to complete all 3 symbols**
- Script MUST be resumable: query MAX(time) per symbol before each run, skip completed ranges

## DELEGATION

### TASK 1 — ALEMBIC MIGRATION: Add TWELVEDATA to datasource ENUM (risk-eng, 10 min)

**File:** `alembic/versions/005_add_twelvedata_datasource.py`

```python
"""Add TWELVEDATA to datasource enum

Revision ID: 005
Revises: 004
"""
from alembic import op

revision = '005_add_twelvedata_datasource'
down_revision = '004_create_optimization_tables'

def upgrade():
    op.execute("ALTER TYPE datasource ADD VALUE IF NOT EXISTS 'TWELVEDATA'")

def downgrade():
    # PostgreSQL does not support removing enum values
    pass
```

**Also update the SQLAlchemy model** in `src/database/models/market_data.py` line 40:
```python
# Add TWELVEDATA to the ENUM list
source: Mapped[str] = mapped_column(
    ENUM('BARCHART', 'MT4', 'BC', 'CSV', 'DUKASCOPY', 'HISTDATA', 'TWELVEDATA',
         name='datasource', create_type=False),
    nullable=False
)
```

**Run migration:**
```bash
docker-compose exec api alembic upgrade head
```

**Verify:**
```sql
SELECT unnest(enum_range(NULL::datasource));
-- Must show TWELVEDATA in the list
```

**Commit:** `feat(db): add TWELVEDATA to datasource enum [integration-pass]`

---

### TASK 2 — TWELVEDATA DOWNLOADER SCRIPT (quant-dev, 45 min)

**File:** `scripts/download_twelvedata.py`

**Specification:**

```python
"""
TwelveData Historical Downloader

Downloads M1 and H1 candles for WHEAT (W_1), CORN (C_1), GASOLINE (XB1)
from TwelveData API and inserts into PostgreSQL.

Free tier: 800 API calls/day, 5000 datapoints/call.
Resumable: queries MAX(time) per symbol/timeframe before starting.

Usage:
    # Download all symbols (respects rate limits)
    python3 scripts/download_twelvedata.py

    # Download specific symbol
    python3 scripts/download_twelvedata.py --symbol WHEAT

    # Dry run (show what would be downloaded)
    python3 scripts/download_twelvedata.py --dry-run

Environment:
    TWELVEDATA_API_KEY  - API key (free tier is fine)
    DATABASE_URL        - PostgreSQL connection string
"""
```

**Symbol mapping:**
```python
TWELVEDATA_SYMBOLS = {
    "WHEAT":    {"api_symbol": "W_1",  "db_symbol": "WHEAT",    "exchange": "CBOT"},
    "CORN":     {"api_symbol": "C_1",  "db_symbol": "CORN",     "exchange": "CBOT"},
    "GASOLINE": {"api_symbol": "XB1",  "db_symbol": "GASOLINE", "exchange": "NYMEX"},
}
```

**API endpoint:**
```
GET https://api.twelvedata.com/time_series
  ?symbol=W_1
  &interval=1min        (or 1h for H1)
  &start_date=2020-01-01
  &end_date=2020-01-05
  &outputsize=5000
  &apikey=YOUR_KEY
  &format=JSON
  &timezone=UTC
```

**Response format:**
```json
{
  "meta": {"symbol": "W_1", "interval": "1min", ...},
  "values": [
    {"datetime": "2020-01-02 10:00:00", "open": "560.25", "high": "561.00", "low": "559.50", "close": "560.75", "volume": "1234"},
    ...
  ],
  "status": "ok"
}
```

**Critical implementation details:**

1. **Resumability:** Before each symbol+timeframe, query:
   ```sql
   SELECT MAX(time) FROM market_data
   WHERE symbol = 'WHEAT' AND source = 'TWELVEDATA' AND timeframe = 'M1'
   ```
   Start from `MAX(time) + 1 minute` instead of 2020-01-01.

2. **Rate limiting:** Track API calls in-memory. After 790 calls, log remaining and sleep until midnight UTC, OR exit cleanly with a message to re-run tomorrow. Use `time.sleep()` with 1.5s between calls (safe margin under 8 calls/min free tier limit).

3. **Chunked date ranges:** Split the full date range into 3.5-day windows (5000 M1 candles per call). Use a generator:
   ```python
   def date_chunks(start: datetime, end: datetime, chunk_days: float = 3.5):
       current = start
       while current < end:
           chunk_end = min(current + timedelta(days=chunk_days), end)
           yield current, chunk_end
           current = chunk_end
   ```

4. **H1 aggregation:** Download M1 first, then aggregate to H1 locally using pandas resample:
   ```python
   df_h1 = df_m1.resample('1h').agg({
       'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
   }).dropna()
   ```
   Do NOT make separate API calls for H1 — save rate limit budget.

5. **DB insertion:** Use asyncpg with ON CONFLICT upsert, batch size 5000. Source = `'TWELVEDATA'`.

6. **Progress logging:** Every 50 API calls, log:
   ```
   [WHEAT M1] 150/446 calls | 2021-03-15 → 2021-03-18 | 4823 candles | 790/800 daily budget
   ```

7. **Error handling:** On HTTP 429 (rate limit), sleep 60s and retry. On HTTP 400/500, log and skip chunk (don't crash). On network error, retry 3× with exponential backoff.

8. **Weekend/holiday gaps:** TwelveData returns no data for non-trading hours. This is expected — do NOT fill gaps.

**Tests:**
- Unit: Mock API response, verify DataFrame parsing and H1 aggregation
- Integration: Download 1 day of WHEAT M1, insert to DB, verify row count and unique constraint

**Commit:** `feat(data): TwelveData downloader for WHEAT, CORN, GASOLINE with rate limiting [integration-pass]`

---

### TASK 3 — DUKASCOPY BACKFILL FOR USA500, BRENT_OIL, GBPJPY (quant-dev, 30 min)

**File:** Extend `scripts/download_free_data.py`

**Current state:** The script already has a `DukascopyDownloader` class that works. It needs 3 additions:

1. **Add symbol mapping:**
```python
DUKASCOPY_INSTRUMENTS = {
    "CrudeOIL":  "WTIUSD",       # Already exists
    "USA500":    "USA500IDXUSD",  # NEW
    "BRENT_OIL": "BCOUSD",       # NEW
    "GBPJPY":   "GBPJPY",        # NEW
    "XAUUSD":   "XAUUSD",        # Already exists
}
```

2. **Add resumability:** Before downloading, query MAX(time) from DB:
```python
async def get_resume_point(symbol: str, timeframe: str) -> Optional[datetime]:
    """Query the latest candle timestamp in DB for this symbol+source."""
    async with get_db_context() as db:
        result = await db.execute(text(
            "SELECT MAX(time) FROM market_data "
            "WHERE symbol = :sym AND source = 'DUKASCOPY' AND timeframe = :tf"
        ), {"sym": symbol, "tf": timeframe})
        row = result.first()
        return row[0] if row and row[0] else None
```

3. **Add H1 aggregation from M1:** Same resample logic as TwelveData task:
```python
def aggregate_m1_to_h1(m1_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate M1 candles to H1 using standard OHLCV rules."""
    return m1_df.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()
```

4. **Add CLI for new symbols:**
```bash
# Download all 3 new symbols (runs sequentially to avoid hammering Dukascopy)
python3 scripts/download_free_data.py --symbols USA500,BRENT_OIL,GBPJPY --start 2020-01-01

# Download single symbol
python3 scripts/download_free_data.py --symbols USA500 --start 2020-01-01
```

**Performance note:** Dukascopy downloads are ~1 hour of tick data per HTTP request. For 6 years × 3 symbols × ~6500 trading hours = ~19,500 requests. At 0.5s per request (decompression + aggregation), that's ~2.7 hours. This is acceptable — run overnight.

**Commit:** `feat(data): Dukascopy backfill for USA500, BRENT_OIL, GBPJPY with resume [integration-pass]`

---

### TASK 4 — YFINANCE D1 DOWNLOADER FOR TSLA, MSFT (risk-eng, 15 min)

**File:** Extend `scripts/import_csvs_to_db.py` OR create `scripts/download_yfinance.py`

**Simplest approach:** Standalone script using `yfinance` library.

```python
"""
yfinance D1 downloader for TSLA and MSFT.
D1 only — yfinance does not provide reliable M1/H1 for equities.

Usage:
    python3 scripts/download_yfinance.py
    python3 scripts/download_yfinance.py --symbol TSLA
"""
import yfinance as yf

YFINANCE_SYMBOLS = {
    "TSLA": "TSLA",
    "MSFT": "MSFT",
}

def download_symbol(symbol: str, start: str = "2020-01-01"):
    ticker = yf.Ticker(YFINANCE_SYMBOLS[symbol])
    df = ticker.history(start=start, interval="1d")
    # Columns: Open, High, Low, Close, Volume, Dividends, Stock Splits
    # Rename to lowercase, insert to DB with source='CSV', timeframe='D1'
```

**DB insertion:** source=`'CSV'`, import_symbol=`'{symbol}_YF'`, timeframe=`'D1'`.

**Resumability:** Query MAX(time) same as other scripts.

**Note:** TSLA and MSFT are D1 ONLY. For live intraday, they must come from MT4 streaming (Task 5). Make this clear in log output.

**Commit:** `feat(data): yfinance D1 backfill for TSLA, MSFT [integration-pass]`

---

### TASK 5 — MT4 LIVE MULTI-SYMBOL STREAMING (risk-eng, 30 min)

**Goal:** Ensure the MT4 EA and `mt4_sync_service.py` stream H1 (and M1) candles for all 9 symbols in real-time.

**Current state:** The EA publishes candle data on ZMQ PUB port 5556. The sync service subscribes and ingests. But it's unclear if the EA is configured to stream all 9 symbols or just CrudeOIL.

**Step 1 — Verify MT4 EA symbol list.**
Check `mt4/experts/RiseTraderMT4Server.mq4` for the symbol subscription list. The EA must have all 9 symbols in its watch list:
```
CrudeOIL, USA500, BRENT_OIL, GBPJPY., WHEAT, CORN, GASOLINE, #TSLA, #MSFT
```
Note the MT4 naming conventions: GBPJPY has trailing dot, equities have # prefix.

If the EA uses a hardcoded symbol list, update it. If it reads from a config, update the config.

**Step 2 — Update symbol normalization in `mt4_sync_service.py`.**
Add missing symbols to `SYMBOL_NORMALIZATION`:
```python
SYMBOL_NORMALIZATION = {
    "GBPJPY.": "GBPJPY",
    "#TSLA": "TSLA",
    "#MICROSOFT": "MSFT",
    "#MSFT": "MSFT",
    "GOLD.": "XAUUSD",
    "WHEAT.": "WHEAT",
    "CORN.": "CORN",
    "GASOLINE.": "GASOLINE",
    "USA500.": "USA500",
    "BRENT_OIL.": "BRENT_OIL",
    # Fallback: rstrip('.') handles others
}
```

**Step 3 — Verify timeframe configuration.**
The MT4 EA must be configured to send at minimum H1 candles for all symbols. Check if timeframe is per-symbol or global. Ensure M1 is also streamed for symbols that need it (CrudeOIL at minimum for live trading on M5 in the future).

**Step 4 — Performance guard.**
9 symbols × M1 = 9 candles per minute. That's trivial for the buffer+flush pattern (current batch size handles thousands). But verify the ZMQ PUB socket doesn't drop messages under load. Add a sequence number check if not already present.

**Step 5 — Verify with live data.**
After EA restart, monitor logs for 5 minutes:
```bash
docker-compose logs -f api 2>&1 | grep -E "candle_ingested|flushed_write_buffer"
```
Expect to see all 9 symbols appearing in the ingestion logs.

**Commit:** `feat(mt4-stream): multi-symbol H1+M1 streaming for 9 instruments [integration-pass]`

---

### TASK 6 — M1→H1 REAL-TIME AGGREGATION SERVICE (quant-dev, 30 min)

**Goal:** Create a service that aggregates M1 candles into H1 candles in real-time, so the live trading service always has fresh H1 data even between hourly closes.

**File:** `src/services/candle_aggregator.py`

```python
"""
Real-time M1→H1 candle aggregator.

Subscribes to M1 candle inserts (via Redis pub/sub or DB polling)
and maintains rolling H1 candles that update every minute.

This solves the "stale H1" problem: instead of waiting for the
hourly close, the live trading service gets a partial H1 candle
that reflects the latest M1 data.
"""

class CandleAggregator:
    """
    Maintains in-memory partial H1 candles from M1 stream.

    Each symbol has a buffer of M1 candles for the current hour.
    On each new M1, the partial H1 is recomputed:
      open  = first M1 open of the hour
      high  = max of all M1 highs
      low   = min of all M1 lows
      close = last M1 close (updates every minute)
      volume = sum of all M1 volumes

    When the hour rolls over, the completed H1 is flushed to DB
    and the buffer resets.
    """

    def __init__(self):
        self._buffers: Dict[str, List[Dict]] = {}  # symbol → M1 candles in current hour
        self._current_hour: Dict[str, datetime] = {}  # symbol → hour start

    def ingest_m1(self, symbol: str, candle: Dict) -> Optional[Dict]:
        """
        Feed one M1 candle. Returns completed H1 if hour rolled over, else None.
        The partial H1 is always available via get_partial_h1().
        """

    def get_partial_h1(self, symbol: str) -> Optional[Dict]:
        """
        Get the current partial H1 candle (updates every M1 tick).
        Returns None if no M1 data received yet for this hour.
        """
```

**Integration with live_trading_service.py:**
In `_fetch_candles`, append the partial H1 from the aggregator to the DB-fetched H1 list:
```python
# After fetching H1 from DB (line ~747):
if hasattr(self, '_aggregator') and self._aggregator:
    partial = self._aggregator.get_partial_h1(db_sym)
    if partial and partial != candles_raw[-1]:  # Don't duplicate completed candle
        candles_raw.append(partial)
        candle_objs.append(Candle(...))
```

This means the live trading service gets 300 completed H1 candles + 1 in-progress H1 that updates every minute. The stale candle fingerprint from the 8-failure fix will now detect changes every minute instead of every hour.

**Depends on:** Task 5 (MT4 streaming M1 data). If M1 isn't streaming yet, the aggregator has no input. Wire it to the `mt4_sync_service.py` flush callback.

**Tests:**
- Unit: Feed 60 synthetic M1 candles → verify H1 output matches expected OHLCV
- Unit: Feed 30 M1 candles → verify partial H1 has correct running high/low
- Unit: Hour rollover → verify completed H1 flushed + buffer reset

**Commit:** `feat(aggregator): real-time M1→H1 candle aggregation for live trading [integration-pass]`

---

### TASK 7 — DATA INTEGRITY VERIFICATION (mcp-verifier, 20 min)

**After Tasks 1-6 complete, verify the entire data pipeline:**

1. **ENUM migration:**
```sql
SELECT unnest(enum_range(NULL::datasource));
-- Must include TWELVEDATA
```

2. **Row counts per symbol:**
```sql
SELECT symbol, source, timeframe, COUNT(*), MIN(time), MAX(time)
FROM market_data
WHERE symbol IN ('USA500', 'BRENT_OIL', 'GBPJPY', 'WHEAT', 'CORN', 'GASOLINE', 'TSLA', 'MSFT')
GROUP BY symbol, source, timeframe
ORDER BY symbol, timeframe;
```

**Expected minimums (Jan 2020 → Mar 2026, ~1560 trading days):**

| Symbol | Timeframe | Min Rows | Source |
|--------|-----------|----------|--------|
| USA500 | M1 | 500,000+ | DUKASCOPY |
| USA500 | H1 | 9,000+ | DUKASCOPY |
| BRENT_OIL | M1 | 500,000+ | DUKASCOPY |
| BRENT_OIL | H1 | 9,000+ | DUKASCOPY |
| GBPJPY | M1 | 500,000+ | DUKASCOPY |
| GBPJPY | H1 | 9,000+ | DUKASCOPY |
| WHEAT | M1 | 400,000+ | TWELVEDATA |
| WHEAT | H1 | 7,000+ | TWELVEDATA |
| CORN | M1 | 400,000+ | TWELVEDATA |
| CORN | H1 | 7,000+ | TWELVEDATA |
| GASOLINE | M1 | 400,000+ | TWELVEDATA |
| GASOLINE | H1 | 7,000+ | TWELVEDATA |
| TSLA | D1 | 1,500+ | CSV |
| MSFT | D1 | 1,500+ | CSV |

3. **No duplicates check:**
```sql
SELECT symbol, timeframe, source, time, COUNT(*)
FROM market_data
WHERE symbol IN ('USA500', 'BRENT_OIL', 'GBPJPY', 'WHEAT', 'CORN', 'GASOLINE')
GROUP BY symbol, timeframe, source, time
HAVING COUNT(*) > 1
LIMIT 10;
-- Must return 0 rows
```

4. **COVID period coverage (critical for Phase 3 gate):**
```sql
SELECT symbol, timeframe, COUNT(*)
FROM market_data
WHERE symbol = 'USA500'
  AND time BETWEEN '2020-02-01' AND '2020-05-01'
  AND timeframe = 'H1'
GROUP BY symbol, timeframe;
-- Must have 1000+ H1 candles covering the COVID crash
```

5. **Live streaming verification:**
```sql
SELECT symbol, timeframe, MAX(time), NOW() - MAX(time) as staleness
FROM market_data
WHERE source = 'MT4'
  AND symbol IN ('CrudeOIL', 'USA500', 'GBPJPY')
GROUP BY symbol, timeframe
ORDER BY symbol;
-- Staleness should be < 5 minutes for M1, < 65 minutes for H1
```

6. **Aggregator partial H1 test:**
```python
# Call aggregator.get_partial_h1("CrudeOIL")
# Verify it returns a candle with timestamp in the current hour
# Verify close price is within 0.1% of last M1 close
```

**Commit:** `test(data): verify 9-symbol backfill integrity + live streaming [integration-pass]`

---

### TASK 8 — PHASE 3 GATE RE-RUN (mcp-verifier, after data backfill complete)

**This task can ONLY run after USA500 H1 data is backfilled (Tasks 2-3).**

Re-run the crisis replay backtests that were blocked by missing data:

1. **COVID replay (Feb-Apr 2020):**
```bash
# Run vix_regime strategy on USA500 H1 during COVID crash
# Run crash_portfolio strategy
# Target: reproduce +150% return during COVID crash
```

2. **Energy crisis replay (2022):**
```bash
# Run crack_spread + wti_brent_spread on CrudeOIL + BRENT_OIL H1
# Target: reproduce +60% return during energy crisis
```

3. **Update Phase 3 gate report** at `docs/phase-gates/phase3-gate-report.md` with real numbers from these backtests.

**Commit:** `feat(phase3-gate): re-run crisis replays with backfilled USA500 data [integration-pass]`

---

## EXECUTION ORDER

```
SERIAL (must be first):
  risk-eng → Task 1 (Alembic migration, 10 min) — everything else depends on TWELVEDATA enum

PARALLEL GROUP 1 (after Task 1):
  quant-dev → Task 2 (TwelveData downloader, 45 min)
  quant-dev → Task 3 (Dukascopy backfill extension, 30 min) — can use separate worktree
  risk-eng  → Task 4 (yfinance D1 downloader, 15 min)
  risk-eng  → Task 5 (MT4 multi-symbol streaming, 30 min)

SERIAL (after Tasks 2-3 downloaders are WRITTEN but before full backfill completes):
  quant-dev → Task 6 (M1→H1 aggregator, 30 min)

DATA BACKFILL EXECUTION (after scripts are written + tested):
  Run Dukascopy first (free, no rate limit): USA500, BRENT_OIL, GBPJPY — ~2.7 hours
  Run TwelveData second (rate limited): WHEAT, CORN, GASOLINE — ~2 days
  Run yfinance last (fastest): TSLA, MSFT — ~1 minute

VERIFICATION (after backfill completes):
  mcp-verifier → Task 7 (data integrity, 20 min)
  mcp-verifier → Task 8 (Phase 3 gate re-run, after USA500 data confirmed)
```

## ABSOLUTE RULES (from CLAUDE.md)
- No hardcoded ATR, ML confidence, correlation, VaR, or Kelly inputs
- All price data must be REAL from external sources — no synthetic/fake candles
- ON CONFLICT upsert for all DB inserts — scripts must be safely re-runnable
- Source ENUM must match actual data origin (DUKASCOPY, TWELVEDATA, CSV)
- Anti-stop-hunt offsets preserved on all live trading stops
- Every commit tagged `[integration-pass]`
- File ownership: quant-dev owns downloaders + aggregator, risk-eng owns DB migration + MT4 sync, mcp-verifier owns verification

## SUCCESS CRITERIA
1. `SELECT COUNT(DISTINCT symbol) FROM market_data WHERE symbol IN ('USA500','BRENT_OIL','GBPJPY','WHEAT','CORN','GASOLINE','TSLA','MSFT')` returns 8
2. Each symbol has H1 candles covering Feb-Apr 2020 (COVID period)
3. TwelveData script is resumable — can be re-run after rate limit resets
4. MT4 streaming shows all 9 symbols in ingestion logs
5. Candle aggregator produces partial H1 candles that update every minute
6. Phase 3 gate report updated with real crisis replay numbers
7. Zero duplicate rows (unique constraint enforced)

## ENVIRONMENT VARIABLES NEEDED
```bash
# Add to .env before running TwelveData script:
TWELVEDATA_API_KEY=your_free_tier_key_here
# Get free key at: https://twelvedata.com/account/api-keys
```
