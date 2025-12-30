"""
Unit tests for PortfolioState.

Tests portfolio state management, position tracking, P&L calculations,
and buying power with leverage.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import given, strategies as st

from src.services.backtesting.portfolio_state import PortfolioState, Position


class TestPortfolioState:
    """Test PortfolioState class."""

    def test_initial_state(self):
        """Test portfolio initialization with correct initial values."""
        initial_capital = Decimal("10000.00")
        portfolio = PortfolioState(initial_capital=initial_capital)

        assert portfolio.initial_capital == initial_capital
        assert portfolio.cash_balance == initial_capital
        assert portfolio.realized_pnl == Decimal("0.0")
        assert len(portfolio.positions) == 0
        assert portfolio.get_total_value() == initial_capital

    def test_open_long_position(self):
        """Test opening a long position reduces cash and creates position."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        position = portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Check cash was debited
        assert portfolio.cash_balance == Decimal("10000.00") - (Decimal("1.1000") * Decimal("1000"))
        assert portfolio.cash_balance == Decimal("8900.00")

        # Check position was created
        assert position.symbol == "EURUSD"
        assert position.action == "buy"
        assert position.entry_price == Decimal("1.1000")
        assert position.quantity == Decimal("1000")

        # Check position is tracked
        assert portfolio.has_position("EURUSD")
        assert portfolio.get_position("EURUSD") == position

    def test_open_short_position_when_allowed(self):
        """Test opening a short position when short selling is allowed."""
        portfolio = PortfolioState(
            initial_capital=Decimal("10000.00"),
            allow_short_selling=True
        )

        position = portfolio.open_position(
            symbol="BTCUSD",
            action="sell",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        assert position.action == "sell"
        assert portfolio.has_position("BTCUSD")

    def test_open_short_position_when_not_allowed(self):
        """Test that opening a short position fails when not allowed."""
        portfolio = PortfolioState(
            initial_capital=Decimal("10000.00"),
            allow_short_selling=False
        )

        with pytest.raises(ValueError, match="Short selling not allowed"):
            portfolio.open_position(
                symbol="BTCUSD",
                action="sell",
                price=Decimal("50000.00"),
                quantity=Decimal("0.1"),
                timestamp=datetime.now(),
                trade_id=uuid4(),
            )

    def test_cannot_open_duplicate_position(self):
        """Test that opening a duplicate position for same symbol fails."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Open first position
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Try to open another position for same symbol
        with pytest.raises(ValueError, match="Position already open"):
            portfolio.open_position(
                symbol="EURUSD",
                action="buy",
                price=Decimal("1.1050"),
                quantity=Decimal("500"),
                timestamp=datetime.now(),
                trade_id=uuid4(),
            )

    def test_insufficient_buying_power(self):
        """Test that opening position with insufficient funds fails."""
        portfolio = PortfolioState(initial_capital=Decimal("1000.00"))

        with pytest.raises(ValueError, match="Insufficient buying power"):
            portfolio.open_position(
                symbol="BTCUSD",
                action="buy",
                price=Decimal("50000.00"),
                quantity=Decimal("1.0"),  # Would cost 50000, but only have 1000
                timestamp=datetime.now(),
                trade_id=uuid4(),
            )

    def test_close_long_position_with_profit(self):
        """Test closing a long position with profit."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Open position
        trade_id = uuid4()
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=trade_id,
        )

        initial_cash = portfolio.cash_balance

        # Close position at higher price (profit)
        position, gross_pnl, capital_return = portfolio.close_position(
            symbol="EURUSD",
            exit_price=Decimal("1.1500"),
        )

        # Gross P&L should be (1.1500 - 1.1000) * 1000 = 500
        assert gross_pnl == Decimal("500.00")

        # Cash should increase by initial investment + profit
        expected_cash = initial_cash + Decimal("1.1000") * Decimal("1000") + gross_pnl
        assert portfolio.cash_balance == expected_cash

        # Realized P&L should be updated
        assert portfolio.realized_pnl == Decimal("500.00")

        # Position should be removed
        assert not portfolio.has_position("EURUSD")

    def test_close_long_position_with_loss(self):
        """Test closing a long position with loss."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Open position
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Close position at lower price (loss)
        position, gross_pnl, capital_return = portfolio.close_position(
            symbol="EURUSD",
            exit_price=Decimal("1.0500"),
        )

        # Gross P&L should be (1.0500 - 1.1000) * 1000 = -500
        assert gross_pnl == Decimal("-500.00")
        assert portfolio.realized_pnl == Decimal("-500.00")

    def test_close_short_position_with_profit(self):
        """Test closing a short position with profit (price goes down)."""
        portfolio = PortfolioState(
            initial_capital=Decimal("10000.00"),
            allow_short_selling=True
        )

        # Open short position
        portfolio.open_position(
            symbol="BTCUSD",
            action="sell",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Close at lower price (profit for short)
        position, gross_pnl, capital_return = portfolio.close_position(
            symbol="BTCUSD",
            exit_price=Decimal("45000.00"),
        )

        # Gross P&L should be (50000 - 45000) * 0.1 = 500
        assert gross_pnl == Decimal("500.00")
        assert portfolio.realized_pnl == Decimal("500.00")

    def test_close_nonexistent_position_fails(self):
        """Test that closing a position that doesn't exist fails."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        with pytest.raises(ValueError, match="No open position"):
            portfolio.close_position(
                symbol="EURUSD",
                exit_price=Decimal("1.1500"),
            )

    def test_update_market_price_and_unrealized_pnl(self):
        """Test updating market price updates unrealized P&L."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Open position
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Update market price (profit)
        portfolio.update_market_price("EURUSD", Decimal("1.1200"))

        unrealized_pnl = portfolio.get_unrealized_pnl()
        assert unrealized_pnl == Decimal("200.00")  # (1.1200 - 1.1000) * 1000

        # Total value should include unrealized P&L
        total_value = portfolio.get_total_value()
        assert total_value == portfolio.cash_balance + unrealized_pnl

    def test_buying_power_with_leverage(self):
        """Test buying power calculation with leverage."""
        portfolio = PortfolioState(
            initial_capital=Decimal("10000.00"),
            max_leverage=Decimal("2.0")  # 2x leverage
        )

        # With no positions, buying power is total_value * leverage
        buying_power = portfolio.get_buying_power()
        assert buying_power == Decimal("20000.00")  # 10000 * 2.0

        # Open position
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        # Buying power should decrease by position notional value
        buying_power_after = portfolio.get_buying_power()
        assert buying_power_after == Decimal("20000.00") - Decimal("1100.00")
        assert buying_power_after == Decimal("18900.00")

    def test_performance_metrics(self):
        """Test get_performance_metrics returns correct values."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Open and close a profitable trade
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )
        portfolio.close_position("EURUSD", Decimal("1.1500"))

        metrics = portfolio.get_performance_metrics()

        assert metrics["initial_capital"] == 10000.00
        assert metrics["realized_pnl"] == 500.00
        assert metrics["total_return"] == 500.00
        assert metrics["total_return_pct"] == 5.0  # 500/10000 * 100
        assert metrics["open_positions_count"] == 0

    def test_portfolio_snapshot(self):
        """Test get_snapshot returns correct data structure."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        backtest_run_id = uuid4()
        timestamp = datetime.now()

        # Open position
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=timestamp,
            trade_id=uuid4(),
        )

        snapshot = portfolio.get_snapshot(timestamp, backtest_run_id)

        assert snapshot["backtest_run_id"] == backtest_run_id
        assert snapshot["timestamp"] == timestamp
        assert snapshot["cash_balance"] == Decimal("8900.00")
        assert len(snapshot["positions"]) == 1
        assert snapshot["positions"][0]["symbol"] == "EURUSD"

    def test_reset(self):
        """Test reset returns portfolio to initial state."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))

        # Make some changes
        portfolio.open_position(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )
        portfolio.close_position("EURUSD", Decimal("1.1500"))

        # Reset
        portfolio.reset()

        assert portfolio.cash_balance == Decimal("10000.00")
        assert len(portfolio.positions) == 0
        assert portfolio.realized_pnl == Decimal("0.0")


class TestPortfolioStatePropertyBased:
    """Property-based tests for PortfolioState using Hypothesis."""

    @given(
        initial_capital=st.decimals(
            min_value=Decimal("1000.00"),
            max_value=Decimal("1000000.00"),
            places=2
        )
    )
    def test_total_value_never_negative(self, initial_capital):
        """Property: Total portfolio value should never go negative."""
        portfolio = PortfolioState(initial_capital=initial_capital)
        assert portfolio.get_total_value() >= 0

    @given(
        price=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("10000.00"),
            places=2
        ),
        quantity=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("100.00"),
            places=2
        )
    )
    def test_deterministic_pnl_calculation(self, price, quantity):
        """Property: P&L calculation should be deterministic and reversible."""
        portfolio = PortfolioState(initial_capital=Decimal("1000000.00"))

        # Open position
        trade_id = uuid4()
        portfolio.open_position(
            symbol="TEST",
            action="buy",
            price=price,
            quantity=quantity,
            timestamp=datetime.now(),
            trade_id=trade_id,
        )

        # Close at same price (breakeven)
        _, gross_pnl, _ = portfolio.close_position("TEST", price)

        # P&L should be exactly zero for breakeven trade
        assert gross_pnl == Decimal("0.00")

    @given(
        entry_price=st.decimals(
            min_value=Decimal("1.00"),
            max_value=Decimal("100.00"),
            places=2
        ),
        exit_price=st.decimals(
            min_value=Decimal("1.00"),
            max_value=Decimal("100.00"),
            places=2
        )
    )
    def test_long_position_pnl_formula(self, entry_price, exit_price):
        """Property: Long position P&L = (exit - entry) * quantity."""
        portfolio = PortfolioState(initial_capital=Decimal("1000000.00"))
        quantity = Decimal("100.00")

        portfolio.open_position(
            symbol="TEST",
            action="buy",
            price=entry_price,
            quantity=quantity,
            timestamp=datetime.now(),
            trade_id=uuid4(),
        )

        _, gross_pnl, _ = portfolio.close_position("TEST", exit_price)

        expected_pnl = (exit_price - entry_price) * quantity
        assert gross_pnl == expected_pnl
