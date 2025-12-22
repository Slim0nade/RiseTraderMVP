"""
Portfolio state management for backtesting.

Tracks cash, positions, and P&L during backtest execution.
Provides mark-to-market valuation and position management.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID, uuid4


@dataclass
class Position:
    """
    Represents an open position in the backtest portfolio.

    Attributes:
        symbol: Trading symbol
        action: 'buy' (long) or 'sell' (short)
        entry_price: Price at entry
        quantity: Position size (lots/shares)
        entry_timestamp: Time of entry
        trade_id: UUID of the simulated trade record
        unrealized_pnl: Current mark-to-market P&L
    """

    symbol: str
    action: str  # 'buy' or 'sell'
    entry_price: Decimal
    quantity: Decimal
    entry_timestamp: datetime
    trade_id: UUID
    unrealized_pnl: Decimal = Decimal("0.0")

    def update_unrealized_pnl(self, current_price: Decimal) -> None:
        """
        Update unrealized P&L based on current market price.

        Args:
            current_price: Current market price
        """
        if self.action == "buy":
            # Long position: profit when price goes up
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            # Short position: profit when price goes down
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

    def to_dict(self) -> Dict:
        """Convert position to dictionary for JSONB storage."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "entry_price": str(self.entry_price),
            "quantity": str(self.quantity),
            "entry_timestamp": self.entry_timestamp.isoformat(),
            "trade_id": str(self.trade_id),
            "unrealized_pnl": str(self.unrealized_pnl),
        }


class PortfolioState:
    """
    Manages portfolio state during backtesting.

    Tracks cash balance, open positions, realized/unrealized P&L,
    and provides mark-to-market valuation.

    Attributes:
        initial_capital: Starting capital
        cash_balance: Current available cash
        positions: Dictionary of open positions by symbol
        realized_pnl: Cumulative P&L from closed trades
        max_leverage: Maximum allowed leverage (1.0 = no leverage)
        allow_short_selling: Whether short positions are allowed
    """

    def __init__(
        self,
        initial_capital: Decimal,
        max_leverage: Decimal = Decimal("1.0"),
        allow_short_selling: bool = False,
    ):
        """
        Initialize portfolio state.

        Args:
            initial_capital: Starting account balance
            max_leverage: Maximum leverage multiplier
            allow_short_selling: Whether to allow short positions
        """
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = Decimal("0.0")
        self.max_leverage = max_leverage
        self.allow_short_selling = allow_short_selling
        self._current_prices: Dict[str, Decimal] = {}

    def update_market_price(self, symbol: str, price: Decimal) -> None:
        """
        Update current market price for a symbol.

        Updates unrealized P&L for any open positions in this symbol.

        Args:
            symbol: Trading symbol
            price: Current market price
        """
        self._current_prices[symbol] = price

        # Update unrealized P&L for open position
        if symbol in self.positions:
            self.positions[symbol].update_unrealized_pnl(price)

    def get_unrealized_pnl(self) -> Decimal:
        """
        Get total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L
        """
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_total_value(self) -> Decimal:
        """
        Get total portfolio value (cash + unrealized position value).

        Returns:
            Total portfolio value
        """
        return self.cash_balance + self.get_unrealized_pnl()

    def get_buying_power(self) -> Decimal:
        """
        Calculate available buying power considering leverage.

        Returns:
            Available capital for new trades
        """
        total_value = self.get_total_value()
        max_buying_power = total_value * self.max_leverage

        # Calculate current exposure
        current_exposure = sum(
            abs(pos.entry_price * pos.quantity) for pos in self.positions.values()
        )

        # Available buying power is max minus current exposure
        return max_buying_power - current_exposure

    def can_open_position(
        self, symbol: str, action: str, price: Decimal, quantity: Decimal
    ) -> tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            symbol: Trading symbol
            action: 'buy' or 'sell'
            price: Entry price
            quantity: Position size

        Returns:
            Tuple of (can_open: bool, reason: str)
        """
        # Check if position already exists for symbol
        if symbol in self.positions:
            return False, f"Position already open for {symbol}"

        # Check short selling restriction
        if action == "sell" and not self.allow_short_selling:
            return False, "Short selling not allowed"

        # Calculate required capital
        required_capital = price * quantity

        # Check buying power
        buying_power = self.get_buying_power()
        if required_capital > buying_power:
            return (
                False,
                f"Insufficient buying power. Required: {required_capital}, Available: {buying_power}",
            )

        return True, "OK"

    def open_position(
        self,
        symbol: str,
        action: str,
        price: Decimal,
        quantity: Decimal,
        timestamp: datetime,
        trade_id: UUID,
    ) -> Position:
        """
        Open a new position.

        Args:
            symbol: Trading symbol
            action: 'buy' (long) or 'sell' (short)
            price: Entry price
            quantity: Position size
            timestamp: Entry timestamp
            trade_id: UUID of the simulated trade

        Returns:
            Created Position instance

        Raises:
            ValueError: If position cannot be opened
        """
        can_open, reason = self.can_open_position(symbol, action, price, quantity)
        if not can_open:
            raise ValueError(f"Cannot open position: {reason}")

        # Deduct capital from cash (for both long and short)
        required_capital = price * quantity
        self.cash_balance -= required_capital

        # Create and store position
        position = Position(
            symbol=symbol,
            action=action,
            entry_price=price,
            quantity=quantity,
            entry_timestamp=timestamp,
            trade_id=trade_id,
        )
        self.positions[symbol] = position

        # Initialize current price
        self._current_prices[symbol] = price

        return position

    def close_position(
        self, symbol: str, exit_price: Decimal
    ) -> tuple[Position, Decimal, Decimal]:
        """
        Close an open position.

        Args:
            symbol: Trading symbol
            exit_price: Exit price

        Returns:
            Tuple of (closed_position, gross_pnl, net_capital_change)

        Raises:
            ValueError: If no position exists for symbol
        """
        if symbol not in self.positions:
            raise ValueError(f"No open position for {symbol}")

        position = self.positions.pop(symbol)

        # Calculate gross P&L
        if position.action == "buy":
            gross_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - exit_price) * position.quantity

        # Return initial capital + P&L
        capital_return = position.entry_price * position.quantity + gross_pnl
        self.cash_balance += capital_return

        # Update realized P&L
        self.realized_pnl += gross_pnl

        # Remove from current prices
        if symbol in self._current_prices:
            del self._current_prices[symbol]

        return position, gross_pnl, capital_return

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get open position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position instance or None
        """
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """
        Check if position exists for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if position exists
        """
        return symbol in self.positions

    def get_all_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position instances
        """
        return list(self.positions.values())

    def get_snapshot(self, timestamp: datetime, backtest_run_id: UUID) -> Dict:
        """
        Get current portfolio snapshot for database persistence.

        Args:
            timestamp: Current timestamp
            backtest_run_id: Backtest run UUID

        Returns:
            Dictionary suitable for PortfolioSnapshot creation
        """
        unrealized_pnl = self.get_unrealized_pnl()
        total_value = self.get_total_value()
        buying_power = self.get_buying_power()

        return {
            "id": uuid4(),
            "backtest_run_id": backtest_run_id,
            "timestamp": timestamp,
            "cash_balance": self.cash_balance,
            "positions": [pos.to_dict() for pos in self.positions.values()],
            "total_value": total_value,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "buying_power": buying_power,
        }

    def get_performance_metrics(self) -> Dict:
        """
        Get current performance metrics.

        Returns:
            Dictionary with performance statistics
        """
        total_value = self.get_total_value()
        total_return = total_value - self.initial_capital
        total_return_pct = (total_return / self.initial_capital * 100) if self.initial_capital > 0 else Decimal("0.0")

        return {
            "initial_capital": float(self.initial_capital),
            "current_value": float(total_value),
            "cash_balance": float(self.cash_balance),
            "total_return": float(total_return),
            "total_return_pct": float(total_return_pct),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.get_unrealized_pnl()),
            "open_positions_count": len(self.positions),
            "buying_power": float(self.get_buying_power()),
        }

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.cash_balance = self.initial_capital
        self.positions.clear()
        self.realized_pnl = Decimal("0.0")
        self._current_prices.clear()
