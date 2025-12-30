"""
Unit tests for TradeSimulator.

Tests slippage calculation, commission fees, trade execution,
and conversion to database records.
"""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.services.backtesting.portfolio_state import PortfolioState
from src.services.backtesting.trade_simulator import TradeSimulator, TradeResult


class TestTradeSimulator:
    """Test TradeSimulator class."""

    def test_initialization(self):
        """Test simulator initializes with correct fee structure."""
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.002"),
            commission_pct=Decimal("0.001"),
            commission_fixed=Decimal("5.00")
        )

        assert simulator.slippage_pct == Decimal("0.002")
        assert simulator.commission_pct == Decimal("0.001")
        assert simulator.commission_fixed == Decimal("5.00")

    def test_default_initialization(self):
        """Test simulator uses correct defaults."""
        simulator = TradeSimulator()

        assert simulator.slippage_pct == Decimal("0.001")  # 0.1%
        assert simulator.commission_pct == Decimal("0.0005")  # 0.05%
        assert simulator.commission_fixed == Decimal("0.0")

    def test_slippage_on_buy_order(self):
        """Test that buy orders get worse fill (higher price)."""
        simulator = TradeSimulator(slippage_pct=Decimal("0.001"))

        execution_price, slippage = simulator._apply_slippage(
            price=Decimal("100.00"),
            action="buy"
        )

        # Buy should execute at higher price (worse for us)
        assert execution_price == Decimal("100.10")  # 100 + (100 * 0.001)
        assert slippage == Decimal("0.10")

    def test_slippage_on_sell_order(self):
        """Test that sell orders get worse fill (lower price)."""
        simulator = TradeSimulator(slippage_pct=Decimal("0.001"))

        execution_price, slippage = simulator._apply_slippage(
            price=Decimal("100.00"),
            action="sell"
        )

        # Sell should execute at lower price (worse for us)
        assert execution_price == Decimal("99.90")  # 100 - (100 * 0.001)
        assert slippage == Decimal("-0.10")  # Negative for sell

    def test_commission_calculation(self):
        """Test commission is calculated correctly."""
        simulator = TradeSimulator(
            commission_pct=Decimal("0.001"),  # 0.1%
            commission_fixed=Decimal("5.00")
        )

        notional_value = Decimal("10000.00")
        fees = simulator._calculate_fees(notional_value)

        # Fees should be (10000 * 0.001) + 5.00 = 15.00
        assert fees == Decimal("15.00")

    def test_execute_entry_success(self):
        """Test successful entry execution."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0")
        )

        result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now()
        )

        assert result.success is True
        assert result.error_message is None
        assert result.symbol == "EURUSD"
        assert result.action == "buy"

        # Execution price should include slippage
        # 1.1000 + (1.1000 * 0.001) = 1.1011
        assert result.entry_price == Decimal("1.1011")

        # Fees should be (1.1011 * 1000 * 0.0005) = 0.55055, rounded to 0.55
        assert abs(result.fees_paid - Decimal("0.55")) < Decimal("0.01")

        # Position should be created in portfolio
        assert portfolio.has_position("EURUSD")

    def test_execute_entry_insufficient_funds(self):
        """Test entry execution fails with insufficient funds."""
        portfolio = PortfolioState(initial_capital=Decimal("1000.00"))
        simulator = TradeSimulator()

        result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="BTCUSD",
            action="buy",
            price=Decimal("50000.00"),
            quantity=Decimal("1.0"),  # Would cost 50000+
            timestamp=datetime.now()
        )

        assert result.success is False
        assert "Insufficient buying power" in result.error_message
        assert not portfolio.has_position("BTCUSD")

    def test_execute_entry_duplicate_position(self):
        """Test entry execution fails for duplicate position."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator()

        # Open first position
        result1 = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now()
        )
        assert result1.success is True

        # Try to open duplicate
        result2 = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1050"),
            quantity=Decimal("500"),
            timestamp=datetime.now()
        )

        assert result2.success is False
        assert "already open" in result2.error_message.lower()

    def test_execute_entry_short_not_allowed(self):
        """Test entry execution fails when short selling not allowed."""
        portfolio = PortfolioState(
            initial_capital=Decimal("10000.00"),
            allow_short_selling=False
        )
        simulator = TradeSimulator()

        result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="BTCUSD",
            action="sell",  # Short position
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now()
        )

        assert result.success is False
        assert "Short selling not allowed" in result.error_message

    def test_execute_exit_long_with_profit(self):
        """Test exit execution for profitable long position."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0")
        )

        # Open position
        entry_result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now()
        )

        # Exit at higher price
        exit_result, gross_pnl, net_pnl = simulator.execute_exit(
            portfolio=portfolio,
            symbol="EURUSD",
            exit_price=Decimal("1.1500"),
            timestamp=datetime.now()
        )

        assert exit_result.success is True
        assert gross_pnl > 0  # Should be profitable
        assert net_pnl < gross_pnl  # Net should be less due to fees

        # Position should be closed
        assert not portfolio.has_position("EURUSD")

    def test_execute_exit_short_with_profit(self):
        """Test exit execution for profitable short position."""
        portfolio = PortfolioState(
            initial_capital=Decimal("100000.00"),
            allow_short_selling=True
        )
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0")
        )

        # Open short position
        simulator.execute_entry(
            portfolio=portfolio,
            symbol="BTCUSD",
            action="sell",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now()
        )

        # Exit at lower price (profit for short)
        exit_result, gross_pnl, net_pnl = simulator.execute_exit(
            portfolio=portfolio,
            symbol="BTCUSD",
            exit_price=Decimal("45000.00"),
            timestamp=datetime.now()
        )

        assert exit_result.success is True
        assert gross_pnl > 0  # Short profits when price drops

    def test_execute_exit_nonexistent_position(self):
        """Test exit execution fails for nonexistent position."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator()

        with pytest.raises(ValueError, match="No open position"):
            simulator.execute_exit(
                portfolio=portfolio,
                symbol="EURUSD",
                exit_price=Decimal("1.1500"),
                timestamp=datetime.now()
            )

    def test_fees_reduce_capital(self):
        """Test that fees are properly deducted from cash."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.001"),  # 0.1% commission
            commission_fixed=Decimal("10.00")
        )

        initial_cash = portfolio.cash_balance

        # Execute entry
        result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now()
        )

        # Cash should be reduced by: (price * quantity) + fees
        expected_reduction = result.entry_price * result.quantity + result.fees_paid
        actual_reduction = initial_cash - portfolio.cash_balance

        # Allow small rounding difference
        assert abs(expected_reduction - actual_reduction) < Decimal("0.01")

    def test_to_simulated_trade_dict_entry(self):
        """Test conversion of entry TradeResult to database dict."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator()
        backtest_run_id = uuid4()

        result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now(),
            decision_context={"agent": "TestAgent", "signal": "buy"}
        )

        trade_dict = simulator.to_simulated_trade_dict(
            result=result,
            backtest_run_id=backtest_run_id,
            decision_context={"agent": "TestAgent", "signal": "buy"}
        )

        assert trade_dict["backtest_run_id"] == backtest_run_id
        assert trade_dict["symbol"] == "EURUSD"
        assert trade_dict["action"] == "buy"
        assert trade_dict["entry_price"] == result.entry_price
        assert trade_dict["quantity"] == result.quantity
        assert trade_dict["fees_paid"] == result.fees_paid
        assert trade_dict["decision_context"]["agent"] == "TestAgent"

    def test_to_simulated_trade_dict_closed(self):
        """Test conversion of closed trade to database dict."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator()
        backtest_run_id = uuid4()

        # Entry
        entry_time = datetime.now()
        entry_result = simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=entry_time
        )

        # Exit
        exit_time = entry_time + timedelta(hours=2)
        exit_result, gross_pnl, net_pnl = simulator.execute_exit(
            portfolio=portfolio,
            symbol="EURUSD",
            exit_price=Decimal("1.1500"),
            timestamp=exit_time
        )

        trade_dict = simulator.to_simulated_trade_dict(
            result=entry_result,
            backtest_run_id=backtest_run_id,
            exit_timestamp=exit_time,
            exit_price=Decimal("1.1500"),
            gross_pnl=gross_pnl,
            net_pnl=net_pnl
        )

        assert trade_dict["exit_timestamp"] == exit_time
        assert trade_dict["exit_price"] == Decimal("1.1500")
        assert trade_dict["gross_pnl"] == gross_pnl
        assert trade_dict["net_pnl"] == net_pnl
        assert "holding_duration_seconds" in trade_dict
        assert trade_dict["holding_duration_seconds"] == 7200  # 2 hours

    def test_validate_trade_params_valid(self):
        """Test validation passes for valid trade parameters."""
        simulator = TradeSimulator()

        is_valid, message = simulator.validate_trade_params(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000")
        )

        assert is_valid is True
        assert message == "OK"

    def test_validate_trade_params_invalid_symbol(self):
        """Test validation fails for empty symbol."""
        simulator = TradeSimulator()

        is_valid, message = simulator.validate_trade_params(
            symbol="",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000")
        )

        assert is_valid is False
        assert "Symbol cannot be empty" in message

    def test_validate_trade_params_invalid_action(self):
        """Test validation fails for invalid action."""
        simulator = TradeSimulator()

        is_valid, message = simulator.validate_trade_params(
            symbol="EURUSD",
            action="invalid_action",
            price=Decimal("1.1000"),
            quantity=Decimal("1000")
        )

        assert is_valid is False
        assert "Invalid action" in message

    def test_validate_trade_params_invalid_price(self):
        """Test validation fails for zero/negative price."""
        simulator = TradeSimulator()

        is_valid, message = simulator.validate_trade_params(
            symbol="EURUSD",
            action="buy",
            price=Decimal("0.00"),
            quantity=Decimal("1000")
        )

        assert is_valid is False
        assert "Price must be positive" in message

    def test_validate_trade_params_invalid_quantity(self):
        """Test validation fails for zero/negative quantity."""
        simulator = TradeSimulator()

        is_valid, message = simulator.validate_trade_params(
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("-100")
        )

        assert is_valid is False
        assert "Quantity must be positive" in message


from datetime import timedelta

class TestTradeSimulatorRealism:
    """Test realistic trading scenarios."""

    def test_round_trip_trade_loses_fees(self):
        """Test that a round trip at same price loses money due to fees."""
        portfolio = PortfolioState(initial_capital=Decimal("10000.00"))
        simulator = TradeSimulator(
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.001"),
            commission_fixed=Decimal("5.00")
        )

        initial_value = portfolio.get_total_value()

        # Buy
        simulator.execute_entry(
            portfolio=portfolio,
            symbol="EURUSD",
            action="buy",
            price=Decimal("1.1000"),
            quantity=Decimal("1000"),
            timestamp=datetime.now()
        )

        # Sell at same quote price (but slippage applies)
        simulator.execute_exit(
            portfolio=portfolio,
            symbol="EURUSD",
            exit_price=Decimal("1.1000"),
            timestamp=datetime.now()
        )

        final_value = portfolio.get_total_value()

        # Should lose money due to slippage and commissions
        assert final_value < initial_value
        assert portfolio.realized_pnl < 0
