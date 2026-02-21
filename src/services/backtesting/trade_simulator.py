"""
Trade execution simulation with realistic market impact modeling.

Simulates order execution with slippage, commissions, and market impact
during backtesting.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from .portfolio_state import PortfolioState


@dataclass
class TradeResult:
    """
    Result of a simulated trade execution.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        action: 'buy', 'sell', 'close_long', or 'close_short'
        entry_price: Actual execution price (after slippage)
        quantity: Trade size
        timestamp: Execution timestamp
        fees_paid: Total fees (commission + slippage cost)
        slippage_applied: Actual slippage amount
        net_capital_change: Change in cash balance
        success: Whether trade executed successfully
        error_message: Error message if failed
    """

    trade_id: UUID
    symbol: str
    action: str
    entry_price: Decimal
    quantity: Decimal
    timestamp: datetime
    fees_paid: Decimal
    slippage_applied: Decimal
    net_capital_change: Decimal
    success: bool
    error_message: Optional[str] = None


class TradeSimulator:
    """
    Simulates trade execution with realistic market impact.

    Models slippage, commissions, and validates trades against portfolio state.
    Produces SimulatedTrade records for database persistence.

    Attributes:
        slippage_pct: Slippage percentage (e.g., 0.001 = 0.1%)
        commission_pct: Commission percentage (e.g., 0.0005 = 0.05%)
        commission_fixed: Fixed commission per trade
    """

    def __init__(
        self,
        slippage_pct: Decimal = Decimal("0.001"),
        commission_pct: Decimal = Decimal("0.0005"),
        commission_fixed: Decimal = Decimal("0.0"),
    ):
        """
        Initialize trade simulator with fee structure.

        Args:
            slippage_pct: Slippage percentage (default 0.1%)
            commission_pct: Commission percentage (default 0.05%)
            commission_fixed: Fixed commission per trade
        """
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct
        self.commission_fixed = commission_fixed

    def _apply_slippage(self, price: Decimal, action: str) -> tuple[Decimal, Decimal]:
        """
        Apply slippage to execution price.

        Buy orders get worse fill (higher price), sell orders get worse fill (lower price).

        Args:
            price: Quoted market price
            action: 'buy' or 'sell'

        Returns:
            Tuple of (execution_price, slippage_amount)
        """
        slippage_amount = price * self.slippage_pct

        if action in ["buy", "close_short"]:
            # Buying: price goes up (worse for us)
            execution_price = price + slippage_amount
        else:
            # Selling: price goes down (worse for us)
            execution_price = price - slippage_amount
            slippage_amount = -slippage_amount  # Track as negative for sells

        return execution_price, slippage_amount

    def _calculate_fees(self, notional_value: Decimal) -> Decimal:
        """
        Calculate total trading fees (commission + fixed).

        Args:
            notional_value: Trade value (price * quantity)

        Returns:
            Total fees
        """
        commission = notional_value * self.commission_pct
        return commission + self.commission_fixed

    def execute_entry(
        self,
        portfolio: PortfolioState,
        symbol: str,
        action: str,
        price: Decimal,
        quantity: Decimal,
        timestamp: datetime,
        decision_context: Optional[dict] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> TradeResult:
        """
        Execute a position entry (open new position).

        Args:
            portfolio: Portfolio state to modify
            symbol: Trading symbol
            action: 'buy' (long) or 'sell' (short)
            price: Market price (before slippage)
            quantity: Position size
            timestamp: Execution timestamp
            decision_context: Optional agent decision context (for full mode)
            stop_loss: Optional stop loss price for the position
            take_profit: Optional take profit price for the position

        Returns:
            TradeResult with execution details
        """
        trade_id = uuid4()

        # Apply slippage to get actual execution price
        execution_price, slippage = self._apply_slippage(price, action)

        # Calculate fees
        notional_value = execution_price * quantity
        fees = self._calculate_fees(notional_value)

        # Check if position can be opened
        can_open, reason = portfolio.can_open_position(
            symbol, action, execution_price, quantity
        )

        if not can_open:
            return TradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=quantity,
                timestamp=timestamp,
                fees_paid=Decimal("0.0"),
                slippage_applied=slippage,
                net_capital_change=Decimal("0.0"),
                success=False,
                error_message=reason,
            )

        try:
            # Open position in portfolio with SL/TP
            position = portfolio.open_position(
                symbol=symbol,
                action=action,
                price=execution_price,
                quantity=quantity,
                timestamp=timestamp,
                trade_id=trade_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            # Deduct fees from cash
            portfolio.cash_balance -= fees

            # Calculate net capital change (negative for entries)
            net_capital_change = -(notional_value + fees)

            return TradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=quantity,
                timestamp=timestamp,
                fees_paid=fees,
                slippage_applied=slippage,
                net_capital_change=net_capital_change,
                success=True,
                error_message=None,
            )

        except Exception as e:
            return TradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=quantity,
                timestamp=timestamp,
                fees_paid=Decimal("0.0"),
                slippage_applied=slippage,
                net_capital_change=Decimal("0.0"),
                success=False,
                error_message=str(e),
            )

    def execute_exit(
        self,
        portfolio: PortfolioState,
        symbol: str,
        exit_price: Decimal,
        timestamp: datetime,
        position_id: Optional[UUID] = None,
    ) -> tuple[TradeResult, Decimal, Decimal]:
        """
        Execute a position exit (close existing position).

        Args:
            portfolio: Portfolio state to modify
            symbol: Trading symbol
            exit_price: Market price (before slippage)
            timestamp: Exit timestamp
            position_id: Optional specific position to close (FIFO if not provided)

        Returns:
            Tuple of (TradeResult, gross_pnl, net_pnl)

        Raises:
            ValueError: If no position exists for symbol
        """
        if not portfolio.has_position(symbol):
            raise ValueError(f"No open position for {symbol}")

        position = portfolio.get_position(symbol, position_id)

        # Determine exit action (opposite of entry)
        exit_action = "close_long" if position.action == "buy" else "close_short"

        # Apply slippage (exit is opposite direction)
        reverse_action = "sell" if position.action == "buy" else "buy"
        execution_price, slippage = self._apply_slippage(exit_price, reverse_action)

        # Calculate fees
        notional_value = execution_price * position.quantity
        fees = self._calculate_fees(notional_value)

        # Close position in portfolio
        closed_position, gross_pnl, capital_return = portfolio.close_position(
            symbol, execution_price, position_id
        )

        # Deduct fees from cash
        portfolio.cash_balance -= fees

        # Calculate net P&L (after fees)
        net_pnl = gross_pnl - fees

        # Net capital change (positive for exits with profit)
        net_capital_change = capital_return - fees

        return (
            TradeResult(
                trade_id=closed_position.trade_id,
                symbol=symbol,
                action=exit_action,
                entry_price=execution_price,
                quantity=position.quantity,
                timestamp=timestamp,
                fees_paid=fees,
                slippage_applied=slippage,
                net_capital_change=net_capital_change,
                success=True,
                error_message=None,
            ),
            gross_pnl,
            net_pnl,
        )

    def to_simulated_trade_dict(
        self,
        result: TradeResult,
        backtest_run_id: UUID,
        decision_context: Optional[dict] = None,
        exit_timestamp: Optional[datetime] = None,
        exit_price: Optional[Decimal] = None,
        gross_pnl: Optional[Decimal] = None,
        net_pnl: Optional[Decimal] = None,
    ) -> dict:
        """
        Convert TradeResult to SimulatedTrade database record.

        Args:
            result: TradeResult from execution
            backtest_run_id: Backtest run UUID
            decision_context: Optional agent decision context
            exit_timestamp: Exit timestamp (for closed trades)
            exit_price: Exit price (for closed trades)
            gross_pnl: Gross P&L (for closed trades)
            net_pnl: Net P&L after fees (for closed trades)

        Returns:
            Dictionary suitable for SimulatedTrade creation
        """
        trade_dict = {
            "id": result.trade_id,
            "backtest_run_id": backtest_run_id,
            "symbol": result.symbol,
            "action": result.action,
            "entry_timestamp": result.timestamp,
            "entry_price": result.entry_price,
            "quantity": result.quantity,
            "fees_paid": result.fees_paid,
            "slippage_applied": result.slippage_applied,
            "exit_timestamp": exit_timestamp,
            "exit_price": exit_price,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "decision_context": decision_context,
        }

        # Calculate holding duration if trade is closed
        if exit_timestamp and result.timestamp:
            holding_duration = int((exit_timestamp - result.timestamp).total_seconds())
            trade_dict["holding_duration_seconds"] = holding_duration

        return trade_dict

    def validate_trade_params(
        self, symbol: str, action: str, price: Decimal, quantity: Decimal
    ) -> tuple[bool, str]:
        """
        Validate trade parameters before execution.

        Args:
            symbol: Trading symbol
            action: Trade action
            price: Price
            quantity: Quantity

        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if not symbol or not symbol.strip():
            return False, "Symbol cannot be empty"

        if action not in ["buy", "sell", "close_long", "close_short"]:
            return False, f"Invalid action: {action}"

        if price <= 0:
            return False, f"Price must be positive, got {price}"

        if quantity <= 0:
            return False, f"Quantity must be positive, got {quantity}"

        return True, "OK"
