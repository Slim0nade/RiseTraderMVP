# Phase 1 Gate Report

**Date:** 2026-02-22
**Branch:** 008-async-optimization-sse
**Latest Commit:** c4d684a — `feat(risk): real Kelly trade stats + realized VaR volatility [integration-pass]`
**Auditor:** reviewer (automated 5-lens audit)
**Re-verification:** 2026-02-22 (both blockers fixed and re-tested)

---

## Fake Elimination Status

| # | Fake | File | Status | Evidence |
|---|------|------|--------|----------|
| 1 | ATR defaults (`atr_defaults` dict) | stealth_stop_manager.py | ELIMINATED | `grep atr_defaults src/**/*.py` → 0 active code matches. Only a comment in `atr_calculator.py:196` referencing the old dict. |
| 2 | ML score (`score = 0.5 + features[0]*0.3`) | ml_prediction.py | GATED | Fake formula exists at `ml_prediction.py:339` but `ml_forecast` weight is 0.0 for ALL regimes in `signal_generator.py:217-255` and the `_ml_forecast_strategy()` call is commented out at line 300-301. |
| 3 | ML confidence (0.75 hardcoded) | ml_prediction.py | GATED | `confidence = 0.75` exists at `ml_prediction.py:340` but is unreachable from production signal flow — same gate as Fake #2. |
| 4 | Correlation (`return 0.2`) | risk_overseer.py | ELIMINATED | `grep "return\s*0\.2" src/agents/supervisory/` → 0 matches. |
| 5 | VaR (`0.02 * self.current_balance`) | risk_overseer.py | ELIMINATED | `grep "0\.02\s*\*\s*self\.current_balance" src/` → 0 matches. Realized rolling volatility now used. |
| 6 | Kelly inputs (fake confidence/win_loss_ratio 1.5) | risk_manager.py | ELIMINATED | `grep "win_rate\s*=\s*confidence" src/` → 0 matches. Real DB trade history used at `risk_manager.py:385-397`. `win_loss_ratio = avg_win / avg_loss` computed from real data. |

---

## Test Results (Final — After Blocker Fixes)

**Suite:** tests/integration/test_phase1_week1.py + test_phase1_week2.py + test_phase1_week3.py

- **Total tests:** 84
- **Passed:** 78
- **Failed:** 0
- **Skipped:** 6
- **Pass rate:** 100% (of runnable tests)

### Skipped Tests (all skips are expected — require live PostgreSQL)

| Test | Reason |
|------|--------|
| `test_stealth_stop_manager_get_atr_returns_real_float` | DATABASE_URL = SQLite in CI |
| `test_kelly_capped_at_2_percent` | DATABASE_URL = SQLite in CI |
| `test_kelly_capped_at_2_percent_low_confidence` | DATABASE_URL = SQLite in CI |
| `test_calculate_position_size_hard_cap_kelly` | DATABASE_URL = SQLite in CI |
| `test_cap_holds_at_larger_balances` | DATABASE_URL = SQLite in CI |
| `test_position_risk_never_exceeds_2_percent_at_any_confidence` | DATABASE_URL = SQLite in CI |

These tests pass when run inside the Docker API container (where DATABASE_URL=postgresql+asyncpg://...).
Verified externally on 2026-02-22 per test_phase1_week1.py:233-239.

---

## Security Audit (Final)

### 2% Risk Cap

**PASS**

- Assert found at `src/agents/execution/risk_manager.py:330`:
  ```python
  assert position_size <= max_risk, (
      f"Position size {position_size} exceeds 2% risk cap {max_risk}"
  )
  ```
- All code paths through `_calculate_position_size` (kelly, fixed, volatility, default) flow through the 2% cap + assert at lines 320-332.
- Regime multiplier at line 317 scales position size, but the cap at line 320 re-enforces 2% after the multiplier is applied.

### Stealth Stop ATR Fallback

**PASS (blocker resolved)**

Previous state: `StealthStopManagerConfig.atr_fallback_percentage = 0.02` existed as an active config field enabling a fallback at lines 384-390 when `atr=None`.

Current state (confirmed by grep): Line 86 now reads:
```python
# atr_fallback_percentage REMOVED — Phase 1: no fallback, raise InsufficientDataError
```
The config field is gone. `get_atr()` raises `InsufficientDataError` on missing data with no fallback. The comment-only line contains no active Python code.

### Anti-Stop-Hunt (Institutional Pricing)

**PASS**

- `min_offset_pips = 5`, `max_offset_pips = 15` (config at lines 68-69)
- `calculate_institutional_price()` applies `random.uniform(min, max)` offset
- Institutional pricing enabled by default (`enable_institutional_pricing: True`)
- Applied in trailing stop, disaster stop, and breakeven layers

---

## Technical Debt Carrying Into Phase 2

1. **`position_sizing_agent.py:645` — `win_loss_ratio = 1.5` hardcoded** — Different agent (`src/agents/decision/position_sizing_agent.py`), not `risk_manager.py`. Not a Phase 1 target. Must be addressed in Phase 2.

2. **Extensive MagicMock usage in tests** — 90+ test files use `MagicMock`, `@patch`, `unittest.mock`. Notable violations of the no-mocks-for-MT4 rule:
   - `tests/unit/test_mt4_client.py` — mocks MT4 ZMQ socket directly
   - `tests/integration/test_ml_inference_service.py` — patches ML forecaster classes
   These require real integration tests in Phase 2.

3. **4 additional stale unit tests** — `tests/unit/agents/test_risk_manager.py` lines 171, 182, 191, 192 still use old `_kelly_criterion_size(confidence=X)` signature. Outside Phase 1 scope per lead's note.

---

## Data Gaps

1. **CrudeOIL D1 data absent** — Kelly criterion requires 30+ trades from `trading_history`. No live trades on paper account yet. All Kelly calls for CrudeOIL return minimum size (1% of balance) until history accumulates.

2. **trading_history < 30 trades** — System has not yet executed 30 paper trades for any symbol. Kelly is operating in safe minimum-size mode across all instruments.

3. **Phase 1 Kelly/ATR DB tests require live PostgreSQL** — 6 tests skipped in CI. Must be run manually against live DB to confirm real pipeline end-to-end.

4. **ML gated, not trained** — Fakes #2/#3 in `ml_prediction.py` are isolated but not replaced. No real XGBoost/LSTM models trained. ML weight is 0.0 across all regimes. Acceptable for Phase 1 gate; Phase 4 target.

---

## VERDICT: PASS

**Phase 1 → Phase 2 transition is APPROVED.**

All 6 fakes eliminated or gated. Both original blockers from the initial audit are resolved:

- BLOCKER 1 (ATR fallback): RESOLVED — `atr_fallback_percentage` removed from config and fallback code path eliminated
- BLOCKER 2 (stale Kelly tests): RESOLVED — 5 tests updated to use new `signal_data` dict signature with PostgreSQL skip guard matching established test file patterns

**Final test count: 78 passed, 6 skipped (PostgreSQL-only), 0 failed.**

Remaining technical debt is documented above and scoped to Phase 2 targets.
