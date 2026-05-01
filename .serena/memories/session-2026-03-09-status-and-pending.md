# Session Status — Mar 9, 2026

## Branch: `008-async-optimization-sse` (main: `001-mt4-integration`)

## Phase Status
- **Phase 1**: COMPLETE — All 4 in-scope fakes eliminated (#1, #4, #5, #6)
- **Phase 2**: COMPLETE — 4 new strategies, 5+ instruments, correlation blocking live
- **Phase 3**: CONDITIONAL PASS — Code complete, audit fix sprint done, crisis targets need USA500 data
- **Phase 4**: COMPLETE — All 6 fakes eliminated, ML pipeline operational, ML Reversal backtested

## ALL 6 FAKES ELIMINATED
1. ATR defaults → real Wilder's ATR from DB (Phase 1)
2. ML score 0.5+features*0.3 → ReversalPredictor with trained XGBoost (Phase 4)
3. ML confidence 0.75 → real reversal probabilities from model (Phase 4)
4. Correlation 0.2 → rolling 20-day Pearson from D1 log returns (Phase 1)
5. VaR 0.02*balance → realized daily vol from D1 candles (Phase 1)
6. Kelly inputs → real win_rate + avg_win/avg_loss from TradingHistoryRepository (Phase 1)

## Uncommitted Changes (PENDING)
Many modified + untracked files spanning:
- Audit fix sprint (Feb 24): anti-stop-hunt, data-driven confidence, deque migration, contrarian filter, test rewrites
- ML pipeline refactor (Mar 5-9): services extraction, strategy creation, MCP tools, Docker fixes

### Modified Files
- ml_prediction.py, signal_generator.py, reversal_features.py, reversal_predictor.py
- mcp/server.py, vectorized_engine.py, synthetic_engine.py, optimizer.py
- candle_aggregator_service.py, docker/api/Dockerfile.simple, requirements.txt, requirements-api.txt

### New/Untracked Files
- `models/` directory (trained XGBoost model)
- `src/services/indicator_compute_service.py`, `src/services/reversal_training_service.py`
- `src/strategies/ml/` (ml_reversal strategy)
- `scripts/compute_indicators.py`, `scripts/train_and_compare.py`

## Pending Next Steps
1. **Commit all changes** — group logically with `[integration-pass]` tags
2. **Fix model persistence** — only CrudeOIL_H1 saved; BRENT_OIL/GBPJPY/USA500 need re-save
3. **M30 data + models** — aggregation code exists, no M30 data in DB yet
4. **Fix LSTM OOM** — Docker kills LSTM; train on host or increase memory
5. **XAUUSD volume fix** — 99.9% zero tick volume crashes feature extraction
6. **Multi-symbol backtests** — compare ML Reversal across all trained symbols
7. **Phase 3→4 gate** — crisis replay targets need USA500 data coverage

## Audit Fix Sprint Summary (Feb 24)
- 7 issues fixed with 3 parallel agents (risk-eng, quant-dev, mcp-verifier)
- Gate report rewritten — original contained ALL fabricated backtest numbers
- Real crisis replay: COVID best=value_area +2.64%, Energy best=ma_crossover +21.82%
- Integration tests rewritten: 95 pass, 0 fail, zero soft assertions
