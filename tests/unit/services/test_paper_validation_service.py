"""
Unit tests for PaperValidationService.

Pure math, no database, no mocks of MT4/MCP.
All inputs are constructed inline.

Test coverage:
  T1  50 trades, 60% win rate, PF=1.5, 2 regimes → criteria_met=True
  T2  50 trades, 50% win rate → criteria_met=False (win rate gate)
  T3  30 trades, 80% win rate → criteria_met=False (< 50 signals gate)
  T4  6 consecutive losses → criteria_met=False (consec-loss gate)
  T5  Only 1 regime seen → criteria_met=False (regime diversity gate)
  T6  BUY: price drops to SL → outcome="loss"
  T7  BUY: price rises to TP → outcome="win"
  T8  SELL: price rises to SL → outcome="loss"
  T9  SELL: price drops to TP → outcome="win"
  T10 PnL sign is correct for BUY win, BUY loss, SELL win, SELL loss
  T11 check_outcomes returns [] when no open trade exists for symbol
  T12 check_outcomes returns [] while neither SL nor TP is touched
  T13 max concurrent trades per symbol enforced (3 max)
  T14 profit_factor is inf when there are no losing trades
  T15 win_rate and profit_factor are 0.0 / 0.0 on empty resolved list
  T16 criteria_detail sub-keys match the boolean breakdowns
  T17 4-hour time gap guard enforced
  T18 1×ATR price gap guard enforced
  T19 concurrent trades resolve independently
  T20 open_trades count sums all symbols
"""

import pytest
from datetime import datetime, timezone, timedelta
from src.services.paper_validation_service import PaperTrade, PaperValidationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fill_trades(
    svc: PaperValidationService,
    n_wins: int,
    n_losses: int,
    regime: str = "trending",
    regime2: str = "ranging",
    split_regimes: bool = True,
    win_pnl: float = 15.0,
    loss_pnl: float = 10.0,
) -> None:
    """Push a controlled mix of wins and losses into svc.

    Trades are interleaved (win, loss, win, loss …) so that consecutive losses
    never exceed 1 in a row, keeping the max_consecutive_losses gate satisfied
    when n_wins >= n_losses.  Each trade uses a unique symbol so they don't
    collide in the open-trade map.

    The second regime is introduced on the very first loss (if
    split_regimes=True) to satisfy the MIN_REGIME_TYPES criterion.

    win_pnl / loss_pnl control the dollar amounts so the caller can set any
    profit factor they need.
    """
    lots = 0.01
    win_tp_delta = win_pnl / (lots * 1000)   # price move that yields win_pnl
    loss_sl_delta = loss_pnl / (lots * 1000) # price move that yields loss_pnl

    win_idx = 0
    loss_idx = 0

    # Emit an interleaved stream so max consecutive losses stays at 1.
    while win_idx < n_wins or loss_idx < n_losses:
        if win_idx < n_wins:
            sym = f"SYM_W_{win_idx}"
            entry = 100.0
            sl = entry - loss_sl_delta      # SL below entry (never hit)
            tp = entry + win_tp_delta
            svc.record_signal(sym, "BUY", entry, sl, tp, regime, lots)
            results = svc.check_outcomes(sym, tp)     # hit TP → win
            assert len(results) == 1
            win_idx += 1

        if loss_idx < n_losses:
            sym = f"SYM_L_{loss_idx}"
            entry = 100.0
            sl = entry - loss_sl_delta
            tp = entry + win_tp_delta       # TP above entry (never hit)
            r = regime2 if (split_regimes and loss_idx == 0) else regime
            svc.record_signal(sym, "BUY", entry, sl, tp, r, lots)
            results = svc.check_outcomes(sym, sl)     # hit SL → loss
            assert len(results) == 1
            loss_idx += 1


# ---------------------------------------------------------------------------
# T1: All criteria met
# ---------------------------------------------------------------------------

class TestCriteriaMet:
    def test_50_trades_60pct_win_rate_pf_1pt5_two_regimes(self):
        """30 wins / 20 losses at 15/10 PnL → PF=1.5, WR=60%, 50 resolved, 2 regimes."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=30, n_losses=20, win_pnl=15.0, loss_pnl=10.0)

        status = svc.get_validation_status()

        assert status["criteria_met"] is True
        assert status["total_signals"] == 50
        assert status["wins"] == 30
        assert status["losses"] == 20
        assert abs(status["win_rate"] - 0.60) < 1e-6
        assert len(status["regimes_seen"]) == 2
        # Profit factor: (30 * 15) / (20 * 10) = 450 / 200 = 2.25 — well above 1.3
        assert status["profit_factor"] > 1.3

    def test_criteria_detail_all_true(self):
        """Each sub-key in criteria_detail must be True when criteria_met is True."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=30, n_losses=20, win_pnl=15.0, loss_pnl=10.0)

        detail = svc.get_validation_status()["criteria_detail"]

        assert detail["min_signals"] is True
        assert detail["min_win_rate"] is True
        assert detail["min_profit_factor"] is True
        assert detail["max_consec_losses"] is True
        assert detail["min_regimes"] is True


# ---------------------------------------------------------------------------
# T2: Win rate gate
# ---------------------------------------------------------------------------

class TestWinRateGate:
    def test_50_trades_50pct_win_rate_fails(self):
        """50% win rate is below the 55% floor."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=25, n_losses=25, win_pnl=15.0, loss_pnl=10.0)

        status = svc.get_validation_status()

        assert status["criteria_met"] is False
        assert status["criteria_detail"]["min_win_rate"] is False
        # All other numeric gates should pass independently.
        assert status["total_signals"] == 50
        assert status["criteria_detail"]["min_signals"] is True

    def test_exactly_55pct_passes_win_rate_gate(self):
        """55 wins / 45 losses = 55% win rate — exactly on the boundary, must pass."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=55, n_losses=45, win_pnl=15.0, loss_pnl=10.0)

        status = svc.get_validation_status()

        assert status["criteria_detail"]["min_win_rate"] is True
        assert abs(status["win_rate"] - 0.55) < 1e-6


# ---------------------------------------------------------------------------
# T3: Minimum signals gate
# ---------------------------------------------------------------------------

class TestMinSignalsGate:
    def test_30_trades_80pct_win_fails(self):
        """Only 30 resolved trades, even with excellent metrics."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=24, n_losses=6, win_pnl=15.0, loss_pnl=10.0)

        status = svc.get_validation_status()

        assert status["criteria_met"] is False
        assert status["criteria_detail"]["min_signals"] is False
        assert status["total_signals"] == 30
        # Win rate is 80% — well above floor.
        assert status["win_rate"] == pytest.approx(0.80, abs=1e-6)

    def test_exactly_49_trades_fails(self):
        """49 resolved trades is one short of the 50-trade minimum."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=30, n_losses=19, win_pnl=15.0, loss_pnl=10.0)

        status = svc.get_validation_status()

        assert status["total_signals"] == 49
        assert status["criteria_detail"]["min_signals"] is False
        assert status["criteria_met"] is False


# ---------------------------------------------------------------------------
# T4: Consecutive losses gate
# ---------------------------------------------------------------------------

class TestConsecutiveLossesGate:
    def test_6_consecutive_losses_fails(self):
        """Six losses in a row exceeds the MAX_CONSECUTIVE_LOSSES=5 cap."""
        svc = PaperValidationService()

        # First, build a bank of 50 wins across two regimes so every other
        # criterion is satisfied.
        _fill_trades(svc, n_wins=50, n_losses=0, win_pnl=15.0, loss_pnl=10.0)

        # Introduce the second regime so min_regimes passes.
        # (_fill_trades with n_losses=0 still adds the second regime on loss[0]
        # but there are no losses — add a win in a different regime instead.)
        svc.record_signal("REGIME2_SYM", "BUY", 100.0, 99.0, 101.5, "ranging", 0.01)
        svc.check_outcomes("REGIME2_SYM", 101.5)  # win

        # Now push 6 consecutive losses.
        for i in range(6):
            sym = f"CONSEC_LOSS_{i}"
            svc.record_signal(sym, "BUY", 100.0, 99.0, 101.0, "trending", 0.01)
            svc.check_outcomes(sym, 99.0)  # hit SL → loss

        status = svc.get_validation_status()

        assert status["max_consecutive_losses"] == 6
        assert status["criteria_detail"]["max_consec_losses"] is False
        assert status["criteria_met"] is False

    def test_5_consecutive_losses_passes_gate(self):
        """Exactly 5 consecutive losses is still within the allowed limit."""
        svc = PaperValidationService()

        # 50 wins across two regimes.
        _fill_trades(svc, n_wins=50, n_losses=0)
        svc.record_signal("REGIME2_GATE", "BUY", 100.0, 99.0, 101.5, "ranging", 0.01)
        svc.check_outcomes("REGIME2_GATE", 101.5)

        for i in range(5):
            sym = f"LOSS_5_{i}"
            svc.record_signal(sym, "BUY", 100.0, 99.0, 101.0, "trending", 0.01)
            svc.check_outcomes(sym, 99.0)

        status = svc.get_validation_status()

        assert status["max_consecutive_losses"] == 5
        assert status["criteria_detail"]["max_consec_losses"] is True


# ---------------------------------------------------------------------------
# T5: Regime diversity gate
# ---------------------------------------------------------------------------

class TestRegimeDiversityGate:
    def test_only_one_regime_fails(self):
        """All 50 trades in the same regime — MIN_REGIME_TYPES=2 not satisfied."""
        svc = PaperValidationService()

        lots = 0.01
        for i in range(30):
            sym = f"WIN_{i}"
            svc.record_signal(sym, "BUY", 100.0, 99.0, 101.5, "trending", lots)
            svc.check_outcomes(sym, 101.5)

        for i in range(20):
            sym = f"LOSS_{i}"
            entry = 100.0
            sl = entry - 10.0 / (lots * 1000)
            svc.record_signal(sym, "BUY", entry, sl, 101.0, "trending", lots)
            svc.check_outcomes(sym, sl)

        status = svc.get_validation_status()

        assert len(status["regimes_seen"]) == 1
        assert status["criteria_detail"]["min_regimes"] is False
        assert status["criteria_met"] is False

    def test_two_regimes_passes_gate(self):
        """Trades split across trending + ranging satisfy the diversity gate."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=30, n_losses=20)

        status = svc.get_validation_status()

        assert len(status["regimes_seen"]) == 2
        assert status["criteria_detail"]["min_regimes"] is True


# ---------------------------------------------------------------------------
# T6–T9: SL / TP hit logic
# ---------------------------------------------------------------------------

class TestSlTpHitLogic:
    def test_buy_sl_hit_is_loss(self):
        """BUY: current_price <= stop_loss → outcome='loss'."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending")

        resolved = svc.check_outcomes("OIL", 57.99)

        assert len(resolved) == 1
        assert resolved[0].outcome == "loss"
        assert resolved[0].exit_price == 57.99

    def test_buy_tp_hit_is_win(self):
        """BUY: current_price >= take_profit → outcome='win'."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending")

        resolved = svc.check_outcomes("OIL", 64.01)

        assert len(resolved) == 1
        assert resolved[0].outcome == "win"
        assert resolved[0].exit_price == 64.01

    def test_buy_sl_exact_boundary(self):
        """BUY: current_price exactly == stop_loss triggers loss."""
        svc = PaperValidationService()
        svc.record_signal("GOLD", "BUY", 1900.0, 1880.0, 1940.0, "ranging")

        resolved = svc.check_outcomes("GOLD", 1880.0)

        assert len(resolved) == 1
        assert resolved[0].outcome == "loss"

    def test_buy_tp_exact_boundary(self):
        """BUY: current_price exactly == take_profit triggers win."""
        svc = PaperValidationService()
        svc.record_signal("GOLD", "BUY", 1900.0, 1880.0, 1940.0, "ranging")

        resolved = svc.check_outcomes("GOLD", 1940.0)

        assert len(resolved) == 1
        assert resolved[0].outcome == "win"

    def test_sell_sl_hit_is_loss(self):
        """SELL: current_price >= stop_loss → outcome='loss'."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "SELL", 60.0, 62.0, 56.0, "trending")

        resolved = svc.check_outcomes("OIL", 62.01)

        assert len(resolved) == 1
        assert resolved[0].outcome == "loss"
        assert resolved[0].exit_price == 62.01

    def test_sell_tp_hit_is_win(self):
        """SELL: current_price <= take_profit → outcome='win'."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "SELL", 60.0, 62.0, 56.0, "trending")

        resolved = svc.check_outcomes("OIL", 55.99)

        assert len(resolved) == 1
        assert resolved[0].outcome == "win"
        assert resolved[0].exit_price == 55.99

    def test_sell_sl_exact_boundary(self):
        """SELL: current_price exactly == stop_loss triggers loss."""
        svc = PaperValidationService()
        svc.record_signal("GBPJPY", "SELL", 190.0, 193.0, 184.0, "trending")

        resolved = svc.check_outcomes("GBPJPY", 193.0)

        assert len(resolved) == 1
        assert resolved[0].outcome == "loss"

    def test_sell_tp_exact_boundary(self):
        """SELL: current_price exactly == take_profit triggers win."""
        svc = PaperValidationService()
        svc.record_signal("GBPJPY", "SELL", 190.0, 193.0, 184.0, "trending")

        resolved = svc.check_outcomes("GBPJPY", 184.0)

        assert len(resolved) == 1
        assert resolved[0].outcome == "win"


# ---------------------------------------------------------------------------
# T10: PnL calculation
# ---------------------------------------------------------------------------

class TestPnlCalculation:
    """P&L = price_move × lots × 1000 (approximate contract-unit formula)."""

    def test_buy_win_positive_pnl(self):
        """BUY resolves at TP above entry → positive P&L."""
        svc = PaperValidationService()
        lots = 0.01
        entry, tp = 60.0, 62.0
        expected_pnl = (tp - entry) * lots * 1000  # 2.0 * 0.01 * 1000 = 20.0

        svc.record_signal("OIL", "BUY", entry, 58.0, tp, "trending", lots)
        resolved = svc.check_outcomes("OIL", tp)

        assert len(resolved) == 1
        assert abs(resolved[0].pnl - expected_pnl) < 1e-9

    def test_buy_loss_negative_pnl(self):
        """BUY resolves at SL below entry → negative P&L."""
        svc = PaperValidationService()
        lots = 0.01
        entry, sl = 60.0, 58.0
        expected_pnl = (sl - entry) * lots * 1000  # -2.0 * 0.01 * 1000 = -20.0

        svc.record_signal("OIL", "BUY", entry, sl, 63.0, "trending", lots)
        resolved = svc.check_outcomes("OIL", sl)

        assert len(resolved) == 1
        assert abs(resolved[0].pnl - expected_pnl) < 1e-9
        assert resolved[0].pnl < 0.0

    def test_sell_win_positive_pnl(self):
        """SELL resolves at TP below entry → positive P&L."""
        svc = PaperValidationService()
        lots = 0.01
        entry, tp = 60.0, 57.0
        expected_pnl = (entry - tp) * lots * 1000  # 3.0 * 0.01 * 1000 = 30.0

        svc.record_signal("OIL", "SELL", entry, 63.0, tp, "ranging", lots)
        resolved = svc.check_outcomes("OIL", tp)

        assert len(resolved) == 1
        assert abs(resolved[0].pnl - expected_pnl) < 1e-9
        assert resolved[0].pnl > 0.0

    def test_sell_loss_negative_pnl(self):
        """SELL resolves at SL above entry → negative P&L."""
        svc = PaperValidationService()
        lots = 0.01
        entry, sl = 60.0, 63.0
        expected_pnl = (entry - sl) * lots * 1000  # -3.0 * 0.01 * 1000 = -30.0

        svc.record_signal("OIL", "SELL", entry, sl, 56.0, "ranging", lots)
        resolved = svc.check_outcomes("OIL", sl)

        assert len(resolved) == 1
        assert abs(resolved[0].pnl - expected_pnl) < 1e-9
        assert resolved[0].pnl < 0.0

    def test_lots_scale_pnl(self):
        """Doubling lots doubles P&L."""
        lots_a, lots_b = 0.01, 0.02
        entry, tp = 60.0, 62.0

        svc_a = PaperValidationService()
        svc_a.record_signal("OIL", "BUY", entry, 58.0, tp, "trending", lots_a)
        res_a = svc_a.check_outcomes("OIL", tp)

        svc_b = PaperValidationService()
        svc_b.record_signal("OIL", "BUY", entry, 58.0, tp, "trending", lots_b)
        res_b = svc_b.check_outcomes("OIL", tp)

        assert len(res_a) == 1 and len(res_b) == 1
        assert abs(res_b[0].pnl - 2 * res_a[0].pnl) < 1e-9


# ---------------------------------------------------------------------------
# T11–T12: check_outcomes edge cases
# ---------------------------------------------------------------------------

class TestCheckOutcomesEdgeCases:
    def test_returns_empty_list_when_no_open_trade(self):
        """Checking a symbol that was never recorded returns empty list."""
        svc = PaperValidationService()

        result = svc.check_outcomes("UNKNOWN", 100.0)

        assert result == []

    def test_returns_empty_list_while_price_between_sl_and_tp(self):
        """No resolution when price is strictly between SL and TP."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending")

        # Price is between SL and TP — trade must stay open.
        result = svc.check_outcomes("OIL", 61.0)

        assert result == []
        assert len(svc._open_trades.get("OIL", [])) == 1

    def test_trade_removed_from_open_after_resolution(self):
        """Once resolved, the symbol's list should be empty."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending")
        svc.check_outcomes("OIL", 64.0)  # resolves

        assert len(svc._open_trades.get("OIL", [])) == 0
        # Second call on the now-closed symbol returns empty list.
        assert svc.check_outcomes("OIL", 65.0) == []

    def test_open_trades_count_in_status(self):
        """open_trades in status reflects total not-yet-resolved positions across all symbols."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending")
        svc.record_signal("GOLD", "SELL", 1900.0, 1920.0, 1860.0, "ranging")

        status = svc.get_validation_status()

        assert status["open_trades"] == 2


# ---------------------------------------------------------------------------
# T13: Max concurrent trades per symbol enforced
# ---------------------------------------------------------------------------

class TestMaxConcurrentTrades:
    def test_max_3_concurrent_per_symbol(self):
        """Cannot open more than MAX_CONCURRENT_PER_SYMBOL=3 trades on same symbol."""
        from datetime import timedelta
        svc = PaperValidationService()

        # Record 3 trades with sufficient spacing (manually adjust entry_time)
        for i in range(3):
            svc.record_signal("OIL", "BUY", 60.0 + i * 5.0, 55.0, 70.0 + i * 5.0,
                              "trending", 0.01, atr=2.0)
            # Manually adjust entry_time to bypass time gap guard
            if svc._open_trades.get("OIL"):
                svc._open_trades["OIL"][-1].entry_time = (
                    datetime.now(timezone.utc) - timedelta(hours=5 * (3 - i))
                )

        assert len(svc._open_trades.get("OIL", [])) == 3

        # 4th trade should be rejected
        svc.record_signal("OIL", "BUY", 80.0, 75.0, 90.0, "trending", 0.01, atr=2.0)
        assert len(svc._open_trades.get("OIL", [])) == 3


# ---------------------------------------------------------------------------
# T14: Profit factor edge cases
# ---------------------------------------------------------------------------

class TestProfitFactorEdgeCases:
    def test_profit_factor_is_inf_when_no_losses(self):
        """Zero gross loss → profit_factor reported as inf."""
        svc = PaperValidationService()
        for i in range(55):
            sym = f"W_{i}"
            regime = "ranging" if i == 0 else "trending"
            svc.record_signal(sym, "BUY", 100.0, 99.0, 102.0, regime, 0.01)
            results = svc.check_outcomes(sym, 102.0)  # all win
            assert len(results) == 1

        status = svc.get_validation_status()

        assert status["profit_factor"] == float("inf")
        assert status["criteria_detail"]["min_profit_factor"] is True

    def test_profit_factor_numerically_correct(self):
        """5 wins of $20 and 5 losses of $10 → PF = 100 / 50 = 2.0."""
        svc = PaperValidationService()
        lots = 0.01
        win_move = 20.0 / (lots * 1000)  # price move that yields $20 PnL
        loss_move = 10.0 / (lots * 1000)  # price move that yields $10 loss

        for i in range(5):
            sym = f"PF_WIN_{i}"
            svc.record_signal(sym, "BUY", 100.0, 99.0, 100.0 + win_move, "trending", lots)
            svc.check_outcomes(sym, 100.0 + win_move)

        for i in range(5):
            sym = f"PF_LOSS_{i}"
            sl = 100.0 - loss_move
            r = "ranging" if i == 0 else "trending"
            svc.record_signal(sym, "BUY", 100.0, sl, 101.0, r, lots)
            svc.check_outcomes(sym, sl)

        status = svc.get_validation_status()

        assert abs(status["profit_factor"] - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# T15: Empty state
# ---------------------------------------------------------------------------

class TestEmptyState:
    def test_empty_service_returns_zero_stats(self):
        """A freshly created service reports all zeros and criteria_met=False."""
        svc = PaperValidationService()

        status = svc.get_validation_status()

        assert status["total_signals"] == 0
        assert status["wins"] == 0
        assert status["losses"] == 0
        assert status["open_trades"] == 0
        assert status["win_rate"] == 0.0
        assert status["gross_profit"] == 0.0
        assert status["gross_loss"] == 0.0
        assert status["max_consecutive_losses"] == 0
        assert status["regimes_seen"] == []
        assert status["criteria_met"] is False

    def test_profit_factor_zero_loss_zero_profit(self):
        """No trades at all → profit_factor is inf (0/0 defaults to no-loss path)."""
        svc = PaperValidationService()
        status = svc.get_validation_status()
        # gross_loss == 0 → float('inf')
        assert status["profit_factor"] == float("inf")


# ---------------------------------------------------------------------------
# T16: criteria_detail sub-keys are consistent with top-level criteria_met
# ---------------------------------------------------------------------------

class TestCriteriaDetailConsistency:
    def test_criteria_met_is_logical_and_of_all_detail_keys(self):
        """criteria_met must equal AND of all five sub-keys."""
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=30, n_losses=20)

        status = svc.get_validation_status()
        detail = status["criteria_detail"]

        expected = all(detail.values())
        assert status["criteria_met"] == expected

    def test_single_failing_gate_propagates_to_criteria_met(self):
        """When exactly one gate fails, criteria_met must be False."""
        # Win rate gate failure: 25/50 = 50%.
        svc = PaperValidationService()
        _fill_trades(svc, n_wins=25, n_losses=25)

        status = svc.get_validation_status()

        assert status["criteria_detail"]["min_win_rate"] is False
        assert status["criteria_met"] is False


# ---------------------------------------------------------------------------
# T17: Time gap guard
# ---------------------------------------------------------------------------

class TestTimeGapGuard:
    def test_entry_within_4_hours_rejected(self):
        """Second entry on same symbol within 4 hours is rejected."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=1.5)

        # Immediate second entry — should be rejected by time gap
        svc.record_signal("OIL", "BUY", 65.0, 63.0, 69.0, "trending", 0.01, atr=1.5)

        assert len(svc._open_trades.get("OIL", [])) == 1

    def test_entry_after_4_hours_accepted(self):
        """Entry after 4+ hours on same symbol is accepted (if price gap ok)."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=1.5)

        # Move first trade's entry_time back 5 hours
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Now a second entry should be accepted (price gap = 5.0 > 1.5 ATR)
        svc.record_signal("OIL", "BUY", 65.0, 63.0, 69.0, "trending", 0.01, atr=1.5)

        assert len(svc._open_trades.get("OIL", [])) == 2


# ---------------------------------------------------------------------------
# T18: Price gap guard
# ---------------------------------------------------------------------------

class TestPriceGapGuard:
    def test_entry_too_close_in_price_rejected(self):
        """Entry within 1×ATR of an existing open entry is rejected."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=2.0)

        # Move time back to pass time guard
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Entry at 61.0 is only 1.0 away, ATR=2.0, so gap < 1×ATR → rejected
        svc.record_signal("OIL", "BUY", 61.0, 59.0, 65.0, "trending", 0.01, atr=2.0)

        assert len(svc._open_trades.get("OIL", [])) == 1

    def test_entry_far_enough_in_price_accepted(self):
        """Entry >= 1×ATR from all open entries is accepted."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=2.0)

        # Move time back to pass time guard
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Entry at 62.5 is 2.5 away, ATR=2.0, so gap > 1×ATR → accepted
        svc.record_signal("OIL", "BUY", 62.5, 60.5, 66.5, "trending", 0.01, atr=2.0)

        assert len(svc._open_trades.get("OIL", [])) == 2

    def test_no_atr_skips_price_gap_check(self):
        """When atr=0 (not provided), price gap guard is skipped."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=0.0)

        # Move time back
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Same price but atr=0 → price guard skipped → accepted
        svc.record_signal("OIL", "BUY", 60.1, 58.1, 64.1, "trending", 0.01, atr=0.0)

        assert len(svc._open_trades.get("OIL", [])) == 2


# ---------------------------------------------------------------------------
# T19: Concurrent trades resolve independently
# ---------------------------------------------------------------------------

class TestConcurrentResolution:
    def test_one_trade_resolves_others_stay_open(self):
        """When one concurrent trade hits TP, others remain open."""
        svc = PaperValidationService()

        # Trade 1: BUY at 60, TP at 63
        svc.record_signal("OIL", "BUY", 60.0, 57.0, 63.0, "trending", 0.01, atr=2.0)
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Trade 2: BUY at 65, TP at 68
        svc.record_signal("OIL", "BUY", 65.0, 62.0, 68.0, "trending", 0.01, atr=2.0)

        assert len(svc._open_trades.get("OIL", [])) == 2

        # Price hits Trade 1's TP but not Trade 2's
        resolved = svc.check_outcomes("OIL", 63.0)

        assert len(resolved) == 1
        assert resolved[0].entry_price == 60.0
        assert resolved[0].outcome == "win"
        # Trade 2 stays open
        assert len(svc._open_trades.get("OIL", [])) == 1
        assert svc._open_trades["OIL"][0].entry_price == 65.0

    def test_multiple_trades_resolve_same_tick(self):
        """Multiple trades can resolve on the same price check."""
        svc = PaperValidationService()

        # Trade 1: BUY at 60, TP at 63
        svc.record_signal("OIL", "BUY", 60.0, 57.0, 63.0, "trending", 0.01, atr=2.0)
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Trade 2: BUY at 65, TP at 68
        svc.record_signal("OIL", "BUY", 65.0, 62.0, 68.0, "trending", 0.01, atr=2.0)

        # Price hits both TPs
        resolved = svc.check_outcomes("OIL", 68.0)

        assert len(resolved) == 2
        assert all(r.outcome == "win" for r in resolved)
        assert len(svc._open_trades.get("OIL", [])) == 0


# ---------------------------------------------------------------------------
# T20: Open trades count sums all symbols
# ---------------------------------------------------------------------------

class TestOpenTradesCountMultiSymbol:
    def test_open_trades_count_across_symbols(self):
        """open_trades in status sums trades across all symbols."""
        svc = PaperValidationService()
        svc.record_signal("OIL", "BUY", 60.0, 58.0, 64.0, "trending", 0.01, atr=2.0)
        svc.record_signal("GOLD", "SELL", 1900.0, 1920.0, 1860.0, "ranging", 0.01, atr=20.0)

        # Add a second OIL trade (bypass time gap manually)
        svc._open_trades["OIL"][0].entry_time = (
            datetime.now(timezone.utc) - timedelta(hours=5)
        )
        svc.record_signal("OIL", "BUY", 65.0, 63.0, 69.0, "trending", 0.01, atr=2.0)

        status = svc.get_validation_status()
        assert status["open_trades"] == 3  # 2 OIL + 1 GOLD
