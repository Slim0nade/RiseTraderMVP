"""Unit tests for TieredPositionSizer — pure math, no mocks."""
import pytest
from src.trading.risk.tiered_position_sizer import TieredPositionSizer


class TestTierSelection:
    """Verify correct tier is selected based on confidence."""

    def test_95_plus_gets_20_pct(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.997, account_balance=430, symbol="CrudeOIL", atr=1.0)
        # 20% of 430 = $86, stop=2*1.0=2.0, contract=1000
        # raw_lots = 86 / (2.0 * 1000) = 0.043
        assert lots == 0.04

    def test_85_to_95_gets_15_pct(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.90, account_balance=430, symbol="CrudeOIL", atr=1.0)
        # 15% of 430 = $64.50, raw = 64.5 / (2.0 * 1000) = 0.03225
        assert lots == 0.03

    def test_70_to_85_gets_10_pct(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.75, account_balance=430, symbol="CrudeOIL", atr=1.0)
        # 10% of 430 = $43, raw = 43 / (2.0 * 1000) = 0.0215
        assert lots == 0.02

    def test_50_to_70_gets_5_pct(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.60, account_balance=430, symbol="CrudeOIL", atr=1.0)
        # 5% of 430 = $21.50, raw = 21.5 / (2.0 * 1000) = 0.01075
        assert lots == 0.01

    def test_below_50_returns_zero(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.40, account_balance=430, symbol="CrudeOIL", atr=1.0)
        assert lots == 0.0

    def test_exactly_50_returns_minimum(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.50, account_balance=430, symbol="CrudeOIL", atr=1.0)
        assert lots >= 0.01


class TestExistingLotsCap:
    """Verify pyramiding respects max total lots."""

    def test_existing_lots_reduces_capacity(self):
        sizer = TieredPositionSizer()
        # With 0.05 existing, max remaining = 0.05
        lots = sizer.calculate_lot_size(
            confidence=0.997, account_balance=430, symbol="CrudeOIL", atr=1.0,
            existing_lots=0.05,
        )
        assert lots <= 0.05

    def test_at_max_returns_zero(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(
            confidence=0.997, account_balance=430, symbol="CrudeOIL", atr=1.0,
            existing_lots=0.10,
        )
        assert lots == 0.0

    def test_near_max_gets_minimum(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(
            confidence=0.997, account_balance=430, symbol="CrudeOIL", atr=1.0,
            existing_lots=0.09,
        )
        assert round(lots, 2) == 0.01


class TestMarginValidation:
    """Verify margin level floor enforcement."""

    def test_sufficient_margin_passes(self):
        sizer = TieredPositionSizer()
        valid, level = sizer.validate_margin_level(
            lots=0.01, symbol="CrudeOIL", equity=430.0, current_margin=40.0,
        )
        assert valid is True
        assert level > 200.0

    def test_insufficient_margin_rejects(self):
        sizer = TieredPositionSizer()
        # equity=50, current_margin=40, new_margin~40 → total=80, level=62.5%
        valid, level = sizer.validate_margin_level(
            lots=0.01, symbol="CrudeOIL", equity=50.0, current_margin=40.0,
        )
        assert valid is False
        assert level < 200.0

    def test_zero_margin_passes(self):
        sizer = TieredPositionSizer()
        valid, level = sizer.validate_margin_level(
            lots=0.01, symbol="CrudeOIL", equity=430.0, current_margin=0.0,
        )
        assert valid is True


class TestDailyLossHalt:
    """Verify daily loss limit halts trading."""

    def test_within_limit(self):
        sizer = TieredPositionSizer()
        assert sizer.check_daily_loss_halt(daily_pnl=-10.0, account_balance=430.0) is False

    def test_at_limit(self):
        sizer = TieredPositionSizer()
        # 5% of 430 = 21.50
        assert sizer.check_daily_loss_halt(daily_pnl=-21.50, account_balance=430.0) is True

    def test_beyond_limit(self):
        sizer = TieredPositionSizer()
        assert sizer.check_daily_loss_halt(daily_pnl=-30.0, account_balance=430.0) is True

    def test_positive_pnl(self):
        sizer = TieredPositionSizer()
        assert sizer.check_daily_loss_halt(daily_pnl=50.0, account_balance=430.0) is False


class TestEdgeCases:
    """Edge cases."""

    def test_zero_balance(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.99, account_balance=0, symbol="CrudeOIL", atr=1.0)
        assert lots == 0.0

    def test_negative_balance(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.99, account_balance=-100, symbol="CrudeOIL", atr=1.0)
        assert lots == 0.0

    def test_unknown_symbol_uses_defaults(self):
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(confidence=0.80, account_balance=430, symbol="UNKNOWN", atr=1.0)
        assert lots >= 0.01

    def test_minimum_lot_floor_normal_atr(self):
        sizer = TieredPositionSizer()
        # Moderate high ATR but account still large enough: $5000, ATR=2.0
        # min_lot_risk = 4.0 × 1000 × 0.01 = $40 → 0.8% of $5000 < 5% → no protection
        # 5% of $5000 = $250, raw = 250 / (4.0 × 1000) = 0.0625 → floored at 0.01 (nope, 0.06)
        # Actually raw=0.06 so lots=0.06, not floored
        # Use very low confidence (5% tier): $5000 × 0.05 = $250, raw = 250/(4×1000)=0.0625 → 0.06
        # Better: use balance=430, ATR=2.0 → min_lot_risk=$40, risk=9.3%>5%, max_stop=(0.05×430)/10=$2.15
        # 0.9×2.0=$1.80; $2.15>$1.80 → tightened, returns 0.01
        # For a true "floor at 0.01" case we need the raw lot to be < 0.01 without triggering protection
        # e.g. balance=100, ATR=0.5: min_lot_risk=1.0×1000×0.01=$10, risk=10% >5%
        # max_stop=0.05×100/10=$0.50, 0.9×0.50=$0.45, $0.50>=$0.45 → tightened, returns 0.01
        lots = sizer.calculate_lot_size(confidence=0.60, account_balance=100, symbol="CrudeOIL", atr=0.5)
        assert lots == 0.01
        assert sizer._last_adjusted_stop is not None  # stop was tightened to fit 5% cap

    def test_extreme_atr_refuses_trade(self):
        sizer = TieredPositionSizer()
        # ATR=100 with $430 account: even at minimum lot the stop would need to be
        # $2.15 which is < 0.9×100=$90 ATR floor → trade refused entirely
        lots = sizer.calculate_lot_size(confidence=0.60, account_balance=430, symbol="CrudeOIL", atr=100.0)
        assert lots == 0.0
        assert sizer._last_adjusted_stop is None


class TestSmallAccountProtection:
    """
    Verify structural over-leverage guard for small accounts.

    Problem: at $293 balance with CrudeOIL ATR=$1.50 the minimum lot (0.01)
    already risks $30 — 10.2% of account — so the 2% and 5% tiers are
    meaningless.  The sizer must either tighten the stop or refuse the trade.

    Math reference (CrudeOIL, contract_size=1000, MIN_LOTS=0.01):
      min_lot_risk   = stop_distance × 1000 × 0.01
      actual_risk_pct = min_lot_risk / account_balance
      max_stop       = (0.05 × balance) / (1000 × 0.01)   # 5% cap
      tighten if: max_stop >= 0.9 × ATR
      skip if:    max_stop < 0.9 × ATR
    """

    def test_293_atr150_returns_min_lot_with_adjusted_stop(self):
        """
        $293 balance, ATR=$1.50 → 0.01 lots with stop tightened to $1.465.

        min_lot_risk = 3.00 × 1000 × 0.01 = $30 → 10.24% > 5%
        max_stop     = (0.05 × 293) / (1000 × 0.01) = $1.465
        0.9 × ATR    = 0.9 × 1.50 = $1.35
        $1.465 >= $1.35 → tighten, return 0.01
        """
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(
            confidence=0.75, account_balance=293.0, symbol="CrudeOIL", atr=1.50
        )
        assert lots == 0.01
        assert sizer._last_adjusted_stop is not None
        assert abs(sizer._last_adjusted_stop - 1.465) < 0.001

    def test_293_atr350_returns_zero_account_too_small(self):
        """
        $293 balance, ATR=$3.50 → 0.0 lots (trade skipped, stop too tight).

        min_lot_risk = 7.00 × 1000 × 0.01 = $70 → 23.9% > 5%
        max_stop     = $1.465
        0.9 × ATR    = 0.9 × 3.50 = $3.15
        $1.465 < $3.15 → stop below safe floor, skip trade
        """
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(
            confidence=0.75, account_balance=293.0, symbol="CrudeOIL", atr=3.50
        )
        assert lots == 0.0
        assert sizer._last_adjusted_stop is None

    def test_600_atr150_no_stop_adjustment(self):
        """
        $600 balance, ATR=$1.50 → normal lot size, no stop adjustment.

        min_lot_risk = $30 → 5.0% of $600 — exactly at the 5% threshold.
        At the boundary the risk is not > 5%, so the small-account branch is
        not triggered and _last_adjusted_stop stays None.

        ($600 is the break-even balance for CrudeOIL at ATR=$1.50:
         requires balance >= 2 × ATR × 1000 × 0.01 / 0.05 = $600)
        """
        sizer = TieredPositionSizer()
        lots = sizer.calculate_lot_size(
            confidence=0.75, account_balance=600.0, symbol="CrudeOIL", atr=1.50
        )
        # 10% of $600 = $60, raw = 60 / (3.0 × 1000) = 0.02
        assert lots == 0.02
        assert sizer._last_adjusted_stop is None

    def test_last_adjusted_stop_reset_on_each_call(self):
        """
        _last_adjusted_stop is always reset to None at the start of each call,
        so stale state from a prior trade cannot bleed into the next trade.
        """
        sizer = TieredPositionSizer()

        # First call — triggers adjustment (small account, moderate ATR)
        lots1 = sizer.calculate_lot_size(
            confidence=0.75, account_balance=293.0, symbol="CrudeOIL", atr=1.50
        )
        assert lots1 == 0.01
        assert sizer._last_adjusted_stop is not None  # set after first call

        # Second call — well-capitalised account, no adjustment needed
        lots2 = sizer.calculate_lot_size(
            confidence=0.75, account_balance=600.0, symbol="CrudeOIL", atr=1.50
        )
        assert lots2 == 0.02
        # Must be cleared even though the first call had set it
        assert sizer._last_adjusted_stop is None
