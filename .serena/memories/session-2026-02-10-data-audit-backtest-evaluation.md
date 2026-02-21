# Data Audit & Backtest Evaluation - February 10, 2026 (UPDATED 22:18 UTC)

## Database State (market_data table)

### Current Data Coverage
| Symbol | Timeframe | Candles | Start | End | Source | Status |
|--------|-----------|---------|-------|-----|--------|--------|
| CrudeOIL | M1 | 5,509,161 | 2009-08-04 | 2026-02-10 | MT4/Dukascopy | Complete |
| CrudeOIL | M5 | 441,834 | 2018-12-06 | 2024-12-06 | MT4 | Needs update to 2026 |
| CrudeOIL | H1 | 94,922 | 2009-08-04 | 2026-01-13 | MT4 | Complete |
| DXY | M1 | 5,684,328 | 2008-05-04 | 2025-03-31 | Dukascopy | Complete (zero volume) |
| MSFT | M5 | 4,555 | 2025-11-13 | 2026-02-10 | MT4 | Only 3 months |
| MSFT | M30 | 760 | 2025-11-13 | 2026-02-10 | MT4 | Only 3 months |
| MSFT | H1 | 5,074 | 2023-03-15 | 2026-02-10 | CSV/MT4 | Complete |
| MSFT | D1 | 10,056 | 1986-03-13 | 2026-02-10 | CSV | Complete (40 years) |
| TSLA | M5 | 4,557 | 2025-11-13 | 2026-02-10 | MT4 | Only 3 months |
| TSLA | M30 | 760 | 2025-11-13 | 2026-02-10 | MT4 | Only 3 months |
| TSLA | H1 | 5,074 | 2023-03-15 | 2026-02-10 | CSV/MT4 | Complete |
| TSLA | D1 | 3,929 | 2010-06-29 | 2026-02-10 | CSV | Complete (16 years) |
| VIX | M1 | 1,931,996 | 2014-03-17 | 2025-04-01 | Dukascopy | M1 only, needs aggregation |
| GOLD | M1 | ~28K/month | 2023-01 to ? | Downloading | Dukascopy v3 | IN PROGRESS (month 6/37) |
| USA500 | M1 | ~27K/month | 2023-01 to ? | Downloading | Dukascopy v3 | IN PROGRESS (month 6/37) |

### Download Progress (as of 22:18 UTC Feb 10)
- GOLD: 5 months complete (2023-01 thru 2023-05), downloading 2023-06
- USA500: 5 months complete (2023-01 thru 2023-05), downloading 2023-06
- Script: download_dukascopy_v3.py (sequential, no threading, resume support)
- ETA: ~3 hours remaining (~31 months x 6 min/month)
- After download: run import_csvs_to_db.py to load into PostgreSQL
- After import: aggregation to M5/M30/H1 handled by download script

### Data Quality
1. CrudeOIL M1: 34,201 duplicate timestamps (0.62%) - minor overlap from sources
2. DXY: ALL 5.7M candles have zero volume
3. VIX: ALL 1.9M candles have zero volume
4. TSLA/MSFT M5/M30: Only 3 months (Nov 2025 - Feb 2026) from MT4 live feed
5. Price integrity: CLEAN - no OHLC violations across any symbol

## Comprehensive Backtest and Optimization Results

### Static Optimization (Best Params, Full 2024 H1)
| Symbol | Strategy | Params | Return | Sharpe | PF | MaxDD | Trades |
|--------|----------|--------|--------|--------|-----|-------|--------|
| TSLA | ma_crossover | fast=10, slow=50 | +83.94% | 11.01 | 2.90 | -22.9% | 26 |
| TSLA | rsi | period=10, os=30, ob=80 | +47.68% | 7.13 | 2.29 | - | - |
| TSLA | mean_reversion | lb=15, std=2.0 | +40.60% | 8.94 | 2.66 | - | - |
| MSFT | ma_crossover | fast=15, slow=35 | +28.59% | 11.02 | 2.12 | -7.3% | 24 |
| MSFT | rsi | period=7, os=35, ob=75 | +20.69% | 9.43 | 2.04 | - | - |
| MSFT | mean_reversion | lb=20, std=2.0 | +12.30% | 7.52 | 2.19 | -4.6% | 33 |
| CrudeOIL | rsi | period=14, os=20, ob=75 | +26.94% | 5.02 | 1.65 | - | - |
| CrudeOIL | crude_oil_v3 | optimized | +13.01% | 3.56 | 1.65 | - | - |
| CrudeOIL | mean_reversion | lb=30, std=3.0 | +5.01% | 2.09 | - | - | - |

### Rolling Window Optimization (Out-of-Sample, H1 2024)
| Symbol | Strategy | Rolling Return | Robustness | Rating | Avg Test/Mo |
|--------|----------|---------------|------------|--------|-------------|
| MSFT | mean_reversion | +15.06% | 0.88 | STRONG | +1.78% |
| MSFT | ma_crossover | +8.34% | 0.75 | STRONG | +2.07% |
| TSLA | ma_crossover | +18.43% | 0.67 | MODERATE | +7.26% |
| MSFT | rsi | +8.17% | 0.50 | MODERATE | +2.01% |
| CrudeOIL | mean_reversion | -7.93% | 0.60 | WEAK | -0.78% |
| CrudeOIL | rsi | -8.24% | 0.50 | WEAK | -0.76% |
| TSLA | rsi | -7.70% | 0.40 | WEAK | -1.42% |
| TSLA | mean_reversion | -3.97% | 0.25 | AVOID | -0.98% |

### Monte Carlo Validation
| Strategy | Base Return | MC Mean | Percentile | Verdict |
|----------|-----------|---------|------------|---------|
| TSLA ma_crossover | 83.94% | 157.7% | below 25th | UNLUCKY (robust) |
| MSFT ma_crossover | 28.59% | 97.96% | below 25th | UNLUCKY (robust) |
| CrudeOIL rsi | 26.94% | 14.87% | above 75th | LUCKY (overfitting) |

### Sub-Period Results
- TSLA Q4 2024 ma_crossover (fast=5, slow=20): +47.58% in 3 months
- TSLA Q4 2024 mean_reversion (lb=15, std=2.0): +21.75% in 3 months
- CrudeOIL Q4 H1 rsi (period=14, os=20, ob=80): +12.45% in 4 months

### M5 Timeframe (Nov 2025 - Feb 2026, 3 months)
- TSLA rsi M5: +11.42%
- TSLA ma_crossover M5: +8.49%
- MSFT ma_crossover M5: +6.08%

## Key Findings
1. MSFT Mean Reversion is the most robust strategy - 88% robustness, 7/8 positive windows
2. TSLA MA Crossover has highest absolute returns but moderate out-of-sample consistency
3. CrudeOIL strategies all fail out-of-sample - instrument too noisy for current strategies
4. Best realistic weekly returns: ~1.5-3.5%/week in favorable TSLA periods
5. 25%/week target (1,300% annualized) not achievable with current strategies and 1-lot sizing
6. Position sizing is the main limiter - fixed 1-lot = minimal leverage

## Technical Notes
- DB unique constraint: (time, source, timeframe, symbol) - 4 columns
- SQLAlchemy datasource enum: BARCHART, MT4, BC, CSV, DUKASCOPY, HISTDATA
- Dukascopy bi5: LZMA compressed, price = raw_int x 0.001
- v3 downloader: sequential, resume support, 3 retries, 15s timeout
- M30 exists in DB but NOT in MCP backtest API
- python3.12 on host Mac at /usr/local/bin/python3.12

## Files Created/Modified
- scripts/download_dukascopy_v3.py - Sequential downloader (fixes deadlock)
- scripts/import_csvs_to_db.py - Direct PostgreSQL import via psycopg2
- scripts/download_stocks_yfinance.py - yfinance stock downloader
- src/database/models/market_data.py - Fixed datasource enum
- RiseTrader_Backtest_Report.xlsx - Comprehensive backtest report

## Recommended Next Steps
1. Wait for GOLD/USA500 downloads (~3 hrs remaining)
2. Import into DB via import_csvs_to_db.py
3. Run backtests on GOLD/USA500
4. Aggregate VIX/DXY M1 to higher timeframes
5. Implement dynamic position sizing for higher returns
6. Build regime-detection overlay or ML-based strategy
7. Consider adding more instruments