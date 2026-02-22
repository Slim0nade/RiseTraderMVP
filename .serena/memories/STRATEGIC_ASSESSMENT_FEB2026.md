# Strategic Assessment — February 2026
## What We Have vs What We're Missing

### Current State
- 6 strategies implemented: crude_oil_v3, ma_crossover, rsi, trend_following, mean_reversion, value_area
- Only 2 are robust out-of-sample: MSFT Mean Reversion (0.88), MSFT MA Crossover (0.75)
- crude_oil_v3 flagged as "LUCKY" by Monte Carlo — curve-fitted
- crude_oil_v3 works in crashes (+37.9% COVID, +60.5% 2022) but fails in normal markets (-11.5% 2024)
- value_area strategy built (537 lines) but NEVER backtested
- ML forecast pipeline is DOWN
- Candle data pipeline STALE since Jan 13, 2026

### Historical Trading Analysis (442 closed trades, 2020-2023)
- Best trades: +$96K during 2022 energy crisis (crude oil)
- Worst trades: -$145K from 3-lot over-leveraged positions
- Pattern: Massive wins in regime shifts, massive losses from position-sizing errors
- Critical flaw: Jumping from 0.1 to 3.0 lots (30x size increase) during high conviction

### Missed Opportunities (Ranked by Expected Impact)

#### 1. CRACK SPREAD TRADING (Highest Priority)
- HEATING_OIL and GASOLINE confirmed LIVE and tradeable
- Academic evidence: 60-65% win rate, 1.8-2.2x profit factor
- Structural economic relationship (refinery economics) — mean-reverts reliably
- Implementation: BUY crude + SELL refined products (or inverse)
- Contract size normalization needed: Crude 1,000 bbl vs HO/GAS 100,000 gal

#### 2. SEASONALITY FILTER (Lowest Effort, High Impact)
- Research docs show 68-72% reliability for crude oil seasonal patterns
- Q1 (Jan-Mar): Winter demand rally
- Q2 (Apr-Jun): Refinery maintenance squeeze
- Q3 (Jul-Sep): Summer driving demand
- Q4 (Oct-Dec): WEAKEST — filter OUT trades
- ZERO seasonal logic in any of the 6 strategies
- Adding month-of-year filter to crude_oil_v3 could flip OOS from negative to positive

#### 3. VOLATILITY REGIME SWITCHING (Architectural Gap)
- RegimeDetectionAgent listed in architecture but NEVER implemented
- crude_oil_v3 only works in high-vol regimes
- Simple fix: 20-day ATR percentile rank
  - >70th percentile = "volatile" → enable trend strategies
  - <30th percentile = "quiet" → enable mean reversion / value area
  - Middle = "normal" → reduce sizing
- This single filter would coordinate all 6 strategies coherently

#### 4. AGRICULTURE SEASONAL TRADING (New Market, High Leverage)
- CORN (22.4x), SOYBEAN (27x), COTTON (24.9x), WHEAT (16.6x)
- All have well-documented planting/harvest seasonal cycles
- $19-42 margin per 0.01 lot — incredibly capital efficient
- Strong trending behavior suits MA crossover (already proven on equities)

#### 5. POSITION SIZING FIX (Risk Management)
- Current: 0.5 lot CrudeOIL = $2,041 margin = 20% of account on ONE trade
- Dalio guideline: <5% per uncorrelated bet
- Kelly/fractional sizing not implemented
- 2% risk rule: Max $200 risk per trade → max 0.1 lots on CrudeOIL with 2x ATR stop
- This single change would have prevented -$85K and -$59K historical blowups

#### 6. WTI-BRENT SPREAD
- Both CrudeOIL (WTI) and BRENT_OIL available
- Spread mean-reverts around $3-7 historically
- Current spread: $5.20 (67.55 - 62.35) — near middle of range
- Lower risk than directional crude trading

#### 7. CARRY TRADE — GBPJPY.
- 2,560x leverage with POSITIVE swap long (+8 pts/day)
- Get paid to hold long positions
- Only need trend filter to avoid holding during GBP weakness
- Ultra capital efficient: $81 margin for 0.01 lot

#### 8. BOND DURATION PLAY
- 10Y_T-NOTES at 100x leverage, $11 margin for 0.01 lot
- Tightest spread on entire platform (7 cents)
- Rate-cutting cycle = bond prices rise
- Most capital-efficient directional trade available

#### 9. CROSS-ASSET HEDGING
- DOLLAR_INDX available — inverse correlation to commodities
- COPPER as leading macro indicator
- Portfolio approach: hedge crude longs with USD strength bets during uncertainty
- Could reduce drawdowns 30-40% based on correlation analysis

### Return Projections ($10K account)
- Conservative (current + filters): 15-25% annual ($1,500-$2,500)
- Moderate (multi-instrument, diversified): 30-50% annual ($3,000-$5,000)
- Aggressive (full system, leveraged): 50-100%+ annual (25-30% max DD risk)

### Immediate Action Items
1. Backtest value_area on CrudeOIL H1 (already coded, never tested)
2. Add seasonality filter to crude_oil_v3
3. Build crack spread strategy (HEATING_OIL + GASOLINE + CrudeOIL)
4. Implement ATR-based regime detector
5. Cap position sizing at 2% risk per trade
6. Clean up ghost backtest from Feb 15
7. Fix candle data pipeline (stale since Jan 13)
8. Port MA crossover to WHEAT and CORN
