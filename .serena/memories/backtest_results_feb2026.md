# RiseTrader Backtest Results - February 10, 2026 (Final Update)

## Data Status
| Symbol | Source | Timeframes Available | Total Candles | Range | Status |
|--------|--------|---------------------|---------------|-------|--------|
| CrudeOIL | MT4/Dukascopy | M1(5.5M), M5(442K), H1(95K) | 6.0M+ | 2009-2026 | Complete |
| TSLA | CSV/MT4 | M5(4.6K), M30(760), H1(5K), D1(3.9K) | 14.3K | 2010-2026 | Complete |
| MSFT | CSV/MT4 | M5(4.6K), M30(760), H1(5K), D1(10K) | 20.4K | 1986-2026 | Complete |
| DXY | Dukascopy | M1(5.7M) | 5.7M | 2008-2025 | Complete (no volume) |
| VIX | Dukascopy | M1(1.9M) | 1.9M | 2014-2025 | Needs aggregation |
| GOLD | Dukascopy v3 | M1 (downloading) | ~28K/month | 2023-2026 | DOWNLOADING (month 6/37) |
| USA500 | Dukascopy v3 | M1 (downloading) | ~27K/month | 2023-2026 | DOWNLOADING (month 6/37) |

## Strategy Performance Rankings

### Tier 1: Deploy-Ready (STRONG rolling window validation)
1. **MSFT Mean Reversion H1** (lookback=10, std=1.5)
   - Rolling return: +15.06%, Robustness: 0.88, 7/8 positive windows
   - Stable params: lookback=10, std=1.5 consistently selected
   - Avg monthly OOS return: +1.78%

2. **MSFT MA Crossover H1** (fast=15, slow=35)
   - Rolling return: +8.34%, Robustness: 0.75
   - Static optimized: +28.59%, Sharpe 11.02
   - Monte Carlo: UNLUCKY (robust - actual below MC mean)

### Tier 2: Use with Caution (MODERATE validation)
3. **TSLA MA Crossover H1** (fast=10, slow=50)
   - Static: +83.94% (highest absolute return), Sharpe 11.01
   - Rolling: +18.43%, Robustness: 0.67
   - Monte Carlo: UNLUCKY (robust)
   - Q4 2024 sub-period: +47.58% in 3 months

4. **MSFT RSI H1** (period=7, oversold=35, overbought=65-75)
   - Rolling: +8.17%, Robustness: 0.50

### Tier 3: Avoid (WEAK or negative OOS)
5. CrudeOIL RSI H1: +26.94% static BUT -8.24% rolling (LUCKY/overfitting)
6. CrudeOIL Mean Reversion H1: -7.93% rolling, 0.60 robustness
7. TSLA RSI H1: -7.70% rolling, 0.40 robustness
8. TSLA Mean Reversion H1: -3.97% rolling, 0.25 robustness (AVOID)

## Maximum Achievable Returns (Realistic)
- Best annual (static optimized): TSLA ma_crossover 83.94% = ~1.6%/week
- Best quarterly: TSLA Q4 ma_crossover 47.58% = ~3.6%/week
- Best monthly window: TSLA April 2024 rolling = +25.34% (1 trade)
- 25%/week target requires: dynamic position sizing, leverage, or new strategy architecture

## CRASH PLAYBOOK (Feb 2026)

### Crash Strategy Performance (Backtested across all regimes)
| Period | Strategy | Return | Sharpe | Trades |
|--------|----------|--------|--------|--------|
| COVID Crash (Feb-Apr 2020) | CrudeOIL MA f15/s20 H1 | +154.7% | 10.0 | 67 |
| COVID Recovery (May-Dec 2020) | CrudeOIL MA f12/s25 H1 | +37.2% | 5.4 | 96 |
| 2021 Bull Run | CrudeOIL MA f5/s30 H1 | +36.4% | 5.3 | 129 |
| 2022 Energy Crisis | CrudeOIL MA f8/s40 H1 | +60.5% | 9.0 | 46 |
| 2022 Energy Crisis | CrudeOIL RSI p10/os35/ob75 H1 | +59.2% | 9.9 | 66 |
| COVID Crash | CrudeOIL RSI p21/os25/ob70 H1 | +38.9% | 4.4 | 13 |
| COVID Crash | CrudeOIL crude_v3 H1 | +37.9% | 7.9 | 15 |
| 2024 Flat | CrudeOIL MA f12/s30 H1 | -11.5% | -1.9 | 99 |

### Parameter Stability (8 Regimes, 2020-2024)
- Fast period: mean=10.5, std=3.0, CV=0.29 → STABLE
- Slow period: mean=31.25, std=6.5, CV=0.21 → STABLE
- Recommended universal crash params: fast=10, slow=30

### Monte Carlo Validation of Crash Strategies
- CrudeOIL MA 2022: Actual 60.5% vs MC mean 46.8% → REAL EDGE (timing adds +14%)
- CrudeOIL RSI 2022: Actual 59.2% vs MC mean 49.3% → REAL EDGE
- CrudeOIL MA COVID: Actual 154.7% vs MC mean 13.6% → TIMING IS EVERYTHING

### VIX Regime Rules
- VIX < 15: Stand aside, mean reversion only, 0.25x size
- VIX 15-20: Normal operations, all strategies, 1.0x
- VIX 25-30: DISABLE mean reversion, MA crossover only, 1.5x
- VIX 30-40: CRISIS DEPLOY, MA crossover + RSI, 2.0x
- VIX 40-60: MAX DEPLOY, MA crossover + crude_v3, 2.5x
- VIX 60+: Scale back to 2.0x (peak fear = near bottom)

### TSLA Market Maker Analysis (Feb 10, 2026)
- Price: $423.09 (down from $495 Dec high)
- Support: $387.53 (institutional floor, high-vol hammer Feb 5)
- Resistance: $465 (Dec 17 distribution rejection)
- Short interest: 64.41M shares (1.93%), DECLINING
- Catalysts: SpaceX-xAI merger ($1.25T), SpaceX IPO 2026
- Pattern: Distribution at $490, accumulation at $387-400
- Crash play: If market crashes → TSLA tests $350 → V-recovery to $500+

### Critical Crash Rules
1. Mean reversion FAILS in crashes - DISABLE when VIX > 25
2. MA crossover works in ALL crisis types
3. Wide stops (3.0+ ATR) essential during crashes
4. Scale out 50% at +20%, let runners ride
5. NEVER hold CrudeOIL over weekends during crisis

### Deliverables
- RiseTrader_Crash_Playbook.xlsx (6 sheets: Playbook, Crash Detection, Position Sizing, TSLA MM, Monte Carlo, Action Plan)
- RiseTrader_Optimization_Report.xlsx (5 sheets)

## Account Status
- Balance: $9,474.91, Equity: $9,474.91
- No open positions, no pending orders

## Key Technical Details
- DB: PostgreSQL at localhost:5433, user=postgres, pw=risetrader2024, db=risetrader
- DB constraint: UNIQUE(time, source, timeframe, symbol)
- Datasource enum: BARCHART, MT4, BC, CSV, DUKASCOPY, HISTDATA
- Column mapping: close price stored as `last`, change/change_percent NOT NULL
- Dukascopy: LZMA compressed bi5, price=raw_int*0.001
- v3 downloader: sequential, resume, retries - fixes thread deadlock from v2
- python3.12 on host Mac for psycopg2/requests scripts
- 6 strategies available: crude_oil_v3, ma_crossover, rsi, mean_reversion, trend_following, value_area
