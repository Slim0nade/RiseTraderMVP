# RiseTrader Backtest Results (Updated Mar 9, 2026)

## Data Status
| Symbol | Source | Timeframes Available | Total Candles | Range | Status |
|--------|--------|---------------------|---------------|-------|--------|
| CrudeOIL | MT4/Dukascopy | M1(5.5M), M5(442K), H1(95K) | 6.0M+ | 2009-2026 | Complete |
| TSLA | CSV/MT4 | M5(4.6K), M30(760), H1(5K), D1(3.9K) | 14.3K | 2010-2026 | Complete |
| MSFT | CSV/MT4 | M5(4.6K), M30(760), H1(5K), D1(10K) | 20.4K | 1986-2026 | Complete |
| XAUUSD | Dukascopy | H1(42K) | 42K | 2019-2025 | 99.9% zero volume |
| GBPJPY | Dukascopy | H1(42.7K) | 42.7K | 2019-2025 | Complete |
| BRENT_OIL | Dukascopy | H1(38.7K) | 38.7K | 2019-2025 | 98.6% zero volume |
| USA500 | Dukascopy | H1(13.1K) | 13.1K | 2023-2025 | 79.3% zero volume |

## Strategy Performance (CrudeOIL H1, Jan 2024 – Mar 2025, $10K initial)

### Tier 1: Top Performers
| Strategy | Return | Sharpe | Win Rate | Profit Factor | Max DD | Avg P&L | Trades |
|----------|--------|--------|----------|---------------|--------|---------|--------|
| **Value Area** | +208.94% | 16.94 | 83.95% | 3.42 | -7.16% | $50.88 | 162 |
| **ML Reversal (XGB)** | +156.62% | 12.63 | 79.37% | 4.25 | -16.01% | $103.11 | 63 |

### Tier 2: Marginal
| Strategy | Return | Sharpe | Win Rate | Profit Factor | Max DD |
|----------|--------|--------|----------|---------------|--------|
| Crude Oil v3 | +3.48% | 1.13 | 31.34% | 1.16 | -8.13% |

### Tier 3: Negative
| Strategy | Return | Sharpe | Win Rate | Profit Factor | Max DD |
|----------|--------|--------|----------|---------------|--------|
| RSI | -8.89% | -1.08 | 63.83% | 0.81 | -22.62% |
| MA Crossover | -17.47% | -2.61 | 33.06% | 0.74 | -24.77% |

### ML Reversal Analysis
- **Highest profit factor** (4.25) — each trade avg $103 profit
- **High selectivity** — only 63 trades vs 162 for value_area
- **Model**: XGB-conservative (max_depth=4, lr=0.2, 100 trees), reversal_f1=0.116
- **Weakness**: Higher max DD (-16%) vs value_area (-7%)
- **Opportunity**: Optimize min_confidence threshold and ATR multipliers

### Historical Crash Performance (from Feb 2026 analysis)
| Period | Best Strategy | Return | Sharpe |
|--------|--------------|--------|--------|
| COVID Crash (Feb-Apr 2020) | CrudeOIL MA f15/s20 | +154.7% | 10.0 |
| 2022 Energy Crisis | CrudeOIL MA f8/s40 | +60.5% | 9.0 |
| COVID Recovery (May-Dec 2020) | CrudeOIL MA f12/s25 | +37.2% | 5.4 |

## Available Strategies (12 total in SyntheticEngine, 6 in VectorizedEngine)

### SyntheticEngine (tick-by-tick)
1. crude_oil_v3, 2. ma_crossover, 3. rsi, 4. mean_reversion, 5. trend_following, 6. value_area
7. crack_spread, 8. wti_brent_spread, 9. seasonal_ma_corn, 10. seasonal_ma_wheat, 11. gbpjpy_carry
12. **ml_reversal** (NEW Mar 9)

### VectorizedEngine (batch, 100x faster)
1. ma_crossover, 2. rsi, 3. crude_oil_v3, 4. mean_reversion, 5. value_area
6. **ml_reversal** (NEW Mar 9)

## ML Reversal Results (Mar 9, 2026 — NEW)

### CrudeOIL H1, Jan 2024 – Mar 2025, $10K Initial
| Strategy | Return | Sharpe | Win Rate | Profit Factor | Avg P&L |
|----------|--------|--------|----------|---------------|---------|
| **ML Reversal (XGB)** | **+156.62%** | **12.63** | **79.37%** | **4.25** | **$103.11** |
| Value Area | +208.94% | 16.94 | 83.95% | 3.42 | $50.88 |
| MA Crossover | -17.47% | -2.61 | 33.06% | 0.74 | -$13.75 |
| Crude Oil v3 | +3.48% | 1.13 | 31.34% | 1.16 | $4.67 |
| RSI | -8.89% | -1.08 | 63.83% | 0.81 | -$10.07 |

- ML Reversal: Highest profit factor (4.25) and avg trade ($103)
- Value Area: Best absolute return due to 2.5× more trades (162 vs 63)
- 12 strategies now registered (11 Phase 1-2 + ml_reversal)

## Account Status
- Balance: $9,474.91, Equity: $9,474.91
- No open positions, no pending orders