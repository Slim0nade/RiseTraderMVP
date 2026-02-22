# MT4 Symbol Universe & Leverage Map
## Last Updated: 2026-02-22

## Account Status
- Balance: $10,041 | Equity: $10,245
- Open: 0.5 lot CrudeOIL SHORT @ 62.800 (SL 65.10, no TP)
- 5 pending orders: 2x #TSLA BUY_LIMIT, 1x GOLD. BUY_STOP, 1x USA100 SELL_LIMIT, 1x USA500 SELL_LIMIT

## Total Symbols: 174 (across 7 asset classes)

---

## TIER 1 — EXTREME LEVERAGE (50x+)

| Symbol | Price | Leverage | Margin/lot | Spread | Swap Long | Swap Short | Tradeable |
|--------|-------|----------|-----------|--------|-----------|------------|-----------|
| GBPJPY. | 208.32 | 2,560x | $8,135 | 4 pips | **+8** (PAID) | -15 | YES |
| JPN225 | 57,285 | 1,024x | $559,538 | 35 pts | -5.45 | -1.52 | YES |
| 5Y_T-NOTES | 109.51 | 100x | $1,096 | 7¢ | -0.66 | -0.66 | YES |
| 10Y_T-NOTES | 112.95 | 100x | $1,130 | 7¢ | -0.66 | -0.66 | YES |
| HK50 | 26,719 | 52x | $51,328 | 25 pts | -5 | -1 | YES |

### Key Insights:
- GBPJPY. has POSITIVE swap long — carry trade opportunity
- T-Notes at 100x with tightest spreads on platform (7 cents)
- JPN225 at 1024x — extreme leverage, use with extreme caution

---

## TIER 2 — HIGH LEVERAGE (15x–35x) — Best Risk/Reward

| Symbol | Price | Leverage | Margin/lot | Spread | Tick Value | Tradeable |
|--------|-------|----------|-----------|--------|------------|-----------|
| EURUSD. | 1.1833 | 33.3x | $3,551 | 2.5 pip | $1 | YES |
| SOYBEAN | 1,139.65 | 27.0x | $4,221 | $1.20 | $1 | YES |
| COTTON#2 | 63.61 | 24.9x | $2,555 | $0.27 | $10 | YES |
| CORN | 427.12 | 22.4x | $1,905 | $1.00 | $1 | YES |
| HEATING_OIL | 2.4071 | 18.2x | $13,251 | 21 pts | $10 | YES |
| GASOLINE | 1.9128 | 17.7x | $10,819 | 20 pts | $10 | YES |
| PLATINUM | 2,054.8 | 17.4x | $11,821 | $19 | $10 | YES |
| WHEAT | 541.25 | 16.6x | $3,254 | $1.00 | $1 | YES |
| BRENT_OIL | 67.55 | 16.4x | $4,124 | 5¢ | $10 | YES |
| CrudeOIL | 62.35 | 15.4x | $4,055 | 4¢ | $1 | YES |
| COPPER | 5.6855 | 14.1x | $4,019 | 150 pts | $1 | YES |

---

## TIER 3 — MODERATE LEVERAGE (5x–13x)

| Symbol | Price | Leverage | Margin/lot | Tradeable |
|--------|-------|----------|-----------|-----------|
| GOLD. | 4,933.59 | 11.1x | $44,409 | YES |
| USA30 | 49,686 | 10.0x | $49,690 | YES |
| USA100 | 22,070 | 10.0x | ~$22K | YES |
| USA500 | 6,877.74 | 10.0x | $6,879 | YES |
| USA2000 | 2,655.02 | 10.0x | $26,558 | YES |
| PALLADIUM | 1,738.26 | 9.9x | $17,604 | YES |
| NATURAL_GAS | 3.005 | 9.3x | $3,229 | YES |
| DOLLAR_INDX | 97.15 | 6.7x | $14,589 | YES |
| CHINA50 | 14,855 | 6.7x | $223,350 | YES |
| FRA40 | 8,398.2 | 5.6x | $14,915 | YES |
| SILVER. | 75.686 | 5.5x | $138,346 | YES |

---

## TIER 4 — LOW LEVERAGE (3x–5x) — Stocks & Some Indices

| Symbol | Leverage | Margin % | Tradeable |
|--------|----------|----------|-----------|
| UK100 | 4.9x | 20.3% | YES |
| EUR50 | ~5x | ~20% | YES |
| SWI20 | ~5x | ~20% | YES |
| AUS200 | ~5x | ~20% | YES |
| #TSLA | 3.3x | 30.2% | CHECK (was false) |
| Most US stocks | ~3x | ~30% | VARIES |
| European stocks | ~3x | ~30% | VARIES |

---

## DEAD/UNTRADEABLE SYMBOLS

| Symbol | Issue |
|--------|-------|
| EURUSD (no dot) | trade_allowed: false — use EURUSD. |
| COFFEE | Bid/Ask = 0, no margin, dead feed |
| COCOA | Bid/Ask = 0, no margin, dead feed |
| SUGAR#11 | trade_allowed: false |
| GER40 | Bid/Ask = 0, dead feed |

**Note:** Many forex pairs exist with AND without trailing dot. The dot versions are the tradeable ones.

---

## ENERGY COMPLEX (Full Detail for Crack Spread Trading)

| Symbol | Price | Contract Size | Tick Value | Tick Size | Leverage | Margin % |
|--------|-------|--------------|------------|-----------|----------|----------|
| CrudeOIL | 62.35 | 1,000 bbl | $1.00 | 0.001 | 15.4x | 6.5% |
| BRENT_OIL | 67.55 | 1,000 bbl | $10.00 | 0.001 | 16.4x | 6.1% |
| HEATING_OIL | 2.4071 | 100,000 gal | $10.00 | 0.0001 | 18.2x | 5.5% |
| GASOLINE | 1.9128 | 100,000 gal | $10.00 | 0.0001 | 17.7x | 5.7% |
| NATURAL_GAS | 3.005 | 10,000 mmBtu | $1.00 | 0.001 | 9.3x | 10.8% |

### Crack Spread Implementation Notes:
- HEATING_OIL and GASOLINE both have $10/tick — 10x more volatile per tick than CrudeOIL ($1/tick)
- Contract size mismatch: Crude=1,000 vs HO/Gas=100,000 — need careful lot ratio calculation
- 3:2:1 crack = BUY 3 Crude : SELL 2 Gasoline : SELL 1 Heating Oil (or inverse)
- Must normalize by contract value, not lots
- Both HO and GAS have tight spreads (20-21 pts) relative to tick value

---

## AGRICULTURE COMPLEX (Untapped Opportunity)

| Symbol | Price | Contract Size | Tick Value | Leverage | Margin 0.01 lot |
|--------|-------|--------------|------------|----------|-----------------|
| CORN | 427.12 | 100 | $1.00 | 22.4x | ~$19 |
| WHEAT | 541.25 | 100 | $1.00 | 16.6x | ~$33 |
| SOYBEAN | 1,139.65 | 100 | $1.00 | 27.0x | ~$42 |
| COTTON#2 | 63.61 | 10,000 | $10.00 | 24.9x | ~$26 |

### Seasonality Patterns:
- CORN: Plant Mar-May, Harvest Sep-Nov. Tends to rally spring, weaken fall.
- WHEAT: Plant Sep-Oct (winter), Harvest Jun-Jul. Weather-sensitive spring rally.
- SOYBEAN: Plant May-Jun, Harvest Sep-Oct. South America inverse calendar.
- COTTON: Plant Apr-Jun, Harvest Oct-Dec. Weather + demand driven.

---

## OPTIMAL $10K PORTFOLIO ALLOCATION (Proposed)

For 8 uncorrelated positions at 0.01 lots each:

| Instrument | Margin | Role |
|-----------|--------|------|
| 10Y_T-NOTES | $11 | Rate cycle / safe haven |
| CORN | $19 | Seasonal agriculture |
| COTTON#2 | $26 | Seasonal agriculture #2 |
| WHEAT | $33 | Seasonal agriculture #3 |
| COPPER | $40 | Macro growth indicator |
| CrudeOIL | $41 | Primary energy (expertise) |
| GBPJPY. | $81 | Carry trade + FX diversification |
| GASOLINE | $108 | Crack spread leg |
| HEATING_OIL | $133 | Crack spread leg |
| **TOTAL** | **$492** | **< 5% of account** |

---

## CRITICAL DISCOVERIES

1. **HEATING_OIL + GASOLINE are LIVE** — Crack spread trading is directly implementable
2. **GBPJPY. positive swap long** — Carry trade earns money just by holding
3. **T-Notes at 100x** — Most capital-efficient instruments on the platform
4. **Agriculture at 16-27x leverage** — Completely untouched, strong seasonal edges
5. **BRENT vs WTI spread** — Both available, spread trades possible
6. **NATURAL_GAS at 9.3x** — Weather-driven volatility, seasonal patterns
7. **Contract size mismatches** — CRITICAL for spread trading; HO/GAS are 100,000 vs Crude 1,000

## STRATEGIES NOT YET IMPLEMENTED (From Research Docs)

1. **Crack Spread** (CrudeOIL vs HEATING_OIL/GASOLINE) — 60-65% win rate per academic research
2. **Seasonality Overlay** — Month-of-year filter for all commodity strategies (68-72% reliability)
3. **Volatility Regime Filter** — ATR percentile rank to switch between trend/mean-reversion
4. **Carry Trade** — GBPJPY. long with positive swap
5. **Bond Duration Play** — 10Y_T-NOTES in rate-cutting cycle
6. **WTI-Brent Spread** — Mean-reversion between CrudeOIL and BRENT_OIL
7. **Agriculture Seasonal** — CORN/WHEAT/SOYBEAN planting/harvest cycle trades
8. **Dr. Copper Macro** — COPPER as leading indicator for global growth trades
9. **Cross-Asset Hedging** — DOLLAR_INDX inverse to commodities
