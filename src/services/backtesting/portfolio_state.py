"""
Portfolio state management for backtesting.

Tracks cash, positions, and P&L during backtest execution.
Provides mark-to-market valuation and position management.

ENHANCED: Now supports multiple positions per symbol for:
- Pyramiding / scaling into positions
- Dollar-cost averaging
- Independent position management with stop losses
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
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
        position_id: Unique identifier for this specific position
        stop_loss: Optional stop loss price
        take_profit: Optional take profit price
        trailing_stop_pct: Optional trailing stop percentage
        peak_price: Highest price since entry (for trailing stops on longs)
        trough_price: Lowest price since entry (for trailing stops on shorts)
    """

    symbol: str
    action: str  # 'buy' or 'sell'
    entry_price: Decimal
    quantity: Decimal
    entry_timestamp: datetime
    trade_id: UUID
    unrealized_pnl: Decimal = Decimal("0.0")
    position_id: UUID = field(default_factory=uuid4)
    
    # Exit management
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    trailing_stop_pct: Optional[Decimal] = None
    peak_price: Optional[Decimal] = None
    trough_price: Optional[Decimal] = None

    def update_unrealized_pnl(self, current_price: Decimal) -> None:
        """
        Update unrealized P&L based on current market price.
        Also updates peak/trough for trailing stops.

        Args:
            current_price: Current market price
        """
        if self.action == "buy":
            # Long position: profit when price goes up
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
            # Update peak for trailing stop
            if self.peak_price is None or current_price > self.peak_price:
                self.peak_price = current_price
        else:
            # Short position: profit when price goes down
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
            # Update trough for trailing stop
            if self.trough_price is None or current_price < self.trough_price:
                self.trough_price = current_price

    def get_trailing_stop_price(self) -> Optional[Decimal]:
        """Calculate current trailing stop price if enabled."""
        if self.trailing_stop_pct is None:
            return None
        
        if self.action == "buy" and self.peak_price:
            # Long: stop is X% below peak
            return self.peak_price * (1 - self.trailing_stop_pct)
        elif self.action == "sell" and self.trough_price:
            # Short: stop is X% above trough
            return self.trough_price * (1 + self.trailing_stop_pct)
        
        return None

    def should_exit(self, current_price: Decimal) -> Tuple[bool, str]:
        """
        Check if position should be exited based on exit rules.
        
        Returns:
            Tuple of (should_exit, reason)
        """
        if self.action == "buy":
            # Long position exits
            if self.stop_loss and current_price <= self.stop_loss:
                return True, "stop_loss"
            if self.take_profit and current_price >= self.take_profit:
                return True, "take_profit"
            trailing_stop = self.get_trailing_stop_price()
            if trailing_stop and current_price <= trailing_stop:
                return True, "trailing_stop"
        else:
            # Short position exits
            if self.stop_loss and current_price >= self.stop_loss:
                return True, "stop_loss"
            if self.take_profit and current_price <= self.take_profit:
                return True, "take_profit"
            trailing_stop = self.get_trailing_stop_price()
            if trailing_stop and current_price >= trailing_stop:
                return True, "trailing_stop"
        
        return False, ""

    def to_dict(self) -> Dict:
        """Convert position to dictionary for JSONB storage."""
        return {
            "position_id": str(self.position_id),
            "symbol": self.symbol,
            "action": self.action,
            "entry_price": str(self.entry_price),
            "quantity": str(self.quantity),
            "entry_timestamp": self.entry_timestamp.isoformat(),
            "trade_id": str(self.trade_id),
            "unrealized_pnl": str(self.unrealized_pnl),
            "stop_loss": str(self.stop_loss) if self.stop_loss else None,
            "take_profit": str(self.take_profit) if self.take_profit else None,
            "trailing_stop_pct": str(self.trailing_stop_pct) if self.trailing_stop_pct else None,
        }


class PortfolioState:
    """
    Manages portfolio state during backtesting.

    Tracks cash balance, open positions, realized/unrealized P&L,
    and provides mark-to-market valuation.

    ENHANCED: Now supports multiple positions per symbol.

    Attributes:
        initial_capital: Starting capital
        cash_balance: Current available cash
        positions: Dictionary mapping symbol -> list of Position objects
        realized_pnl: Cumulative P&L from closed trades
        max_leverage: Maximum allowed leverage (1.0 = no leverage)
        allow_short_selling: Whether short positions are allowed
        max_positions_per_symbol: Maximum concurrent positions per symbol (0 = unlimited)
    """

    def __init__(
        self,
        initial_capital: Decimal,
        max_leverage: Decimal = Decimal("1.0"),
        allow_short_selling: bool = False,
        max_positions_per_symbol: int = 0,  # 0 = unlimited
    ):
        """
        Initialize portfolio state.

        Args:
            initial_capital: Starting account balance
            max_leverage: Maximum leverage multiplier
            allow_short_selling: Whether to allow short positions
            max_positions_per_symbol: Max positions per symbol (0 = unlimited)
        """
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        # CHANGED: Now maps symbol -> list of positions
        self.positions: Dict[str, List[Position]] = {}
        self.realized_pnl = Decimal("0.0")
        self.max_leverage = max_leverage
        self.allow_short_selling = allow_short_selling
        self.max_positions_per_symbol = max_positions_per_symbol
        self._current_prices: Dict[str, Decimal] = {}

    def update_market_price(self, symbol: str, price: Decimal) -> None:
        """
        Update current market price for a symbol.

        Updates unrealized P&L for ALL open positions in this symbol.

        Args:
            symbol: Trading symbol
            price: Current market price
        """
        self._current_prices[symbol] = price

        # Update unrealized P&L for ALL positions in this symbol
        if symbol in self.positions:
            for position in self.positions[symbol]:
                position.update_unrealized_pnl(price)

    def get_unrealized_pnl(self) -> Decimal:
        """
        Get total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L
        """
        total = Decimal("0.0")
        for position_list in self.positions.values():
            for pos in position_list:
                total += pos.unrealized_pnl
        return total

    def get_unrealized_pnl_for_symbol(self, symbol: str) -> Decimal:
        """
        Get unrealized P&L for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Total unrealized P&L for the symbol
        """
        if symbol not in self.positions:
            return Decimal("0.0")
        return sum(pos.unrealized_pnl for pos in self.positions[symbol])

    def get_total_value(self) -> Decimal:
        """
        Get total portfolio value (cash + position market values).

        The total value includes:
        - Cash balance (reduced when positions opened)
        - Market value of all open positions (quantity * current_price)

        Returns:
            Total portfolio value
        """
        positions_market_value = Decimal("0.0")
        for symbol, position_list in self.positions.items():
            current_price = self._current_prices.get(symbol)
            if current_price is None:
                # Fallback to entry price if no current price
                for pos in position_list:
                    positions_market_value += pos.quantity * pos.entry_price
            else:
                for pos in position_list:
                    positions_market_value += pos.quantity * current_price
        return self.cash_balance + positions_market_value

    def get_total_exposure(self) -> Decimal:
        """
        Get total portfolio exposure (sum of all position values at entry).

        Returns:
            Total exposure in currency
        """
        total = Decimal("0.0")
        for position_list in self.positions.values():
            for pos in position_list:
                total += abs(pos.entry_price * pos.quantity)
        return total

    def get_exposure_pct(self) -> Decimal:
        """
        Get portfolio exposure as percentage of initial capital.

        Returns:
            Exposure percentage (0-100+)
        """
        if self.initial_capital == 0:
            return Decimal("0.0")
        return (self.get_total_exposure() / self.initial_capital) * 100

    def get_buying_power(self) -> Decimal:
        """
        Calculate available buying power considering leverage.

        Returns:
            Available capital for new trades
        """
        total_value = self.get_total_value()
        max_buying_power = total_value * self.max_leverage
        current_exposure = self.get_total_exposure()
        return max(Decimal("0.0"), max_buying_power - current_exposure)

    def get_position_count(self, symbol: Optional[str] = None) -> int:
        """
        Get count of open positions.

        Args:
            symbol: If provided, count only positions for this symbol

        Returns:
            Number of open positions
        """
        if symbol:
            return len(self.positions.get(symbol, []))
        return sum(len(pos_list) for pos_list in self.positions.values())

    def can_open_position(
        self, symbol: str, action: str, price: Decimal, quantity: Decimal
    ) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        ENHANCED: Now allows multiple positions per symbol.

        Args:
            symbol: Trading symbol
            action: 'buy' or 'sell'
            price: Entry price
            quantity: Position size

        Returns:
            Tuple of (can_open: bool, reason: str)
        """
        # Check max positions per symbol limit
        if self.max_positions_per_symbol > 0:
            current_count = self.get_position_count(symbol)
            if current_count >= self.max_positions_per_symbol:
                return False, f"Max positions ({self.max_positions_per_symbol}) reached for {symbol}"

        # Check for conflicting direction (optional - can be disabled)
        # For now, we allow both long and short positions simultaneously
        # Uncomment below to prevent hedging:
        # existing_positions = self.positions.get(symbol, [])
        # if existing_positions:
        #     existing_action = existing_positions[0].action
        #     if existing_action != action:
        #         return False, f"Cannot open {action} position while {existing_action} position exists"

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
                f"Insufficient buying power. Required: {required_capital:.2f}, Available: {buying_power:.2f}",
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
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        trailing_stop_pct: Optional[Decimal] = None,
    ) -> Position:
        """
        Open a new position.

        ENHANCED: Can now open multiple positions per symbol.

        Args:
            symbol: Trading symbol
            action: 'buy' (long) or 'sell' (short)
            price: Entry price
            quantity: Position size
            timestamp: Entry timestamp
            trade_id: UUID of the simulated trade
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            trailing_stop_pct: Optional trailing stop percentage (e.g., 0.02 = 2%)

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

        # Create position with exit management
        position = Position(
            symbol=symbol,
            action=action,
            entry_price=price,
            quantity=quantity,
            entry_timestamp=timestamp,
            trade_id=trade_id,
            position_id=uuid4(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct,
            peak_price=price if action == "buy" else None,
            trough_price=price if action == "sell" else None,
        )

        # Add to positions list for this symbol
        if symbol not in self.positions:
            self.positions[symbol] = []
        self.positions[symbol].append(position)

        # Initialize/update current price
        self._current_prices[symbol] = price

        return position

    def close_position(
        self, symbol: str, exit_price: Decimal, position_id: Optional[UUID] = None
    ) -> Tuple[Position, Decimal, Decimal]:
        """
        Close an open position.

        ENHANCED: Can close specific position by ID or oldest position (FIFO).

        Args:
            symbol: Trading symbol
            exit_price: Exit price
            position_id: Optional specific position to close (FIFO if not provided)

        Returns:
            Tuple of (closed_position, gross_pnl, net_capital_change)

        Raises:
            ValueError: If no position exists for symbol
        """
        if symbol not in self.positions or not self.positions[symbol]:
            raise ValueError(f"No open position for {symbol}")

        # Find the position to close
        position = None
        position_index = -1

        if position_id:
            # Find specific position by ID
            for i, pos in enumerate(self.positions[symbol]):
                if pos.position_id == position_id:
                    position = pos
                    position_index = i
                    break
            if position is None:
                raise ValueError(f"Position {position_id} not found for {symbol}")
        else:
            # FIFO: Close oldest position
            position = self.positions[symbol][0]
            position_index = 0

        # Remove from list
        self.positions[symbol].pop(position_index)

        # Clean up empty symbol entry
        if not self.positions[symbol]:
            del self.positions[symbol]

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

        # Don't remove from current prices - other positions might exist
        # Only remove if no positions left for this symbol
        if symbol not in self.positions and symbol in self._current_prices:
            del self._current_prices[symbol]

        return position, gross_pnl, capital_return

    def close_all_positions_for_symbol(
        self, symbol: str, exit_price: Decimal
    ) -> List[Tuple[Position, Decimal, Decimal]]:
        """
        Close all positions for a symbol.

        Args:
            symbol: Trading symbol
            exit_price: Exit price for all positions

        Returns:
            List of (closed_position, gross_pnl, net_capital_change) tuples
        """
        results = []
        while symbol in self.positions and self.positions[symbol]:
            result = self.close_position(symbol, exit_price)
            results.append(result)
        return results

    def get_position(self, symbol: str, position_id: Optional[UUID] = None) -> Optional[Position]:
        """
        Get open position for a symbol.

        Args:
            symbol: Trading symbol
            position_id: Optional specific position ID

        Returns:
            Position instance or None
        """
        if symbol not in self.positions or not self.positions[symbol]:
            return None

        if position_id:
            for pos in self.positions[symbol]:
                if pos.position_id == position_id:
                    return pos
            return None

        # Return first position if no ID specified
        return self.positions[symbol][0]

    def get_positions_for_symbol(self, symbol: str) -> List[Position]:
        """
        Get all open positions for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            List of Position instances (empty list if none)
        """
        return self.positions.get(symbol, []).copy()

    def has_position(self, symbol: str) -> bool:
        """
        Check if any position exists for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if at least one position exists
        """
        return symbol in self.positions and len(self.positions[symbol]) > 0

    def get_all_positions(self) -> List[Position]:
        """
        Get all open positions across all symbols.

        Returns:
            List of Position instances
        """
        all_positions = []
        for position_list in self.positions.values():
            all_positions.extend(position_list)
        return all_positions

    def get_net_position(self, symbol: str) -> Tuple[str, Decimal]:
        """
        Get net position direction and quantity for a symbol.

        Useful when you have both long and short positions.

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (direction: 'long'/'short'/'flat', net_quantity)
        """
        if symbol not in self.positions:
            return "flat", Decimal("0.0")

        long_qty = Decimal("0.0")
        short_qty = Decimal("0.0")

        for pos in self.positions[symbol]:
            if pos.action == "buy":
                long_qty += pos.quantity
            else:
                short_qty += pos.quantity

        net = long_qty - short_qty
        if net > 0:
            return "long", net
        elif net < 0:
            return "short", abs(net)
        else:
            return "flat", Decimal("0.0")

    def check_exit_signals(self, symbol: str, current_price: Decimal) -> List[Tuple[Position, str]]:
        """
        Check all positions for a symbol for exit signals.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            List of (position, exit_reason) tuples for positions that should exit
        """
        exits = []
        for pos in self.positions.get(symbol, []):
            should_exit, reason = pos.should_exit(current_price)
            if should_exit:
                exits.append((pos, reason))
        return exits

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

        # Flatten all positions for storage
        all_positions = []
        for position_list in self.positions.values():
            for pos in position_list:
                all_positions.append(pos.to_dict())

        return {
            "id": uuid4(),
            "backtest_run_id": backtest_run_id,
            "timestamp": timestamp,
            "cash_balance": self.cash_balance,
            "positions": all_positions,
            "total_value": total_value,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "buying_power": buying_power,
        }

    def get_full_portfolio_context(self) -> Dict:
        """
        Get complete portfolio state for agent decision making.

        Returns comprehensive view including all positions across all symbols.

        Returns:
            Dictionary with full portfolio state
        """
        all_positions = []
        symbols_summary = {}

        for symbol, position_list in self.positions.items():
            symbol_long_qty = Decimal("0.0")
            symbol_short_qty = Decimal("0.0")
            symbol_unrealized = Decimal("0.0")

            for pos in position_list:
                all_positions.append({
                    "position_id": str(pos.position_id),
                    "symbol": pos.symbol,
                    "direction": "long" if pos.action == "buy" else "short",
                    "quantity": float(pos.quantity),
                    "entry_price": float(pos.entry_price),
                    "entry_timestamp": pos.entry_timestamp.isoformat(),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                    "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                    "take_profit": float(pos.take_profit) if pos.take_profit else None,
                })

                if pos.action == "buy":
                    symbol_long_qty += pos.quantity
                else:
                    symbol_short_qty += pos.quantity
                symbol_unrealized += pos.unrealized_pnl

            net_direction, net_qty = self.get_net_position(symbol)
            symbols_summary[symbol] = {
                "position_count": len(position_list),
                "long_quantity": float(symbol_long_qty),
                "short_quantity": float(symbol_short_qty),
                "net_direction": net_direction,
                "net_quantity": float(net_qty),
                "unrealized_pnl": float(symbol_unrealized),
            }

        return {
            "positions": all_positions,
            "symbols_summary": symbols_summary,
            "total_position_count": len(all_positions),
            "total_exposure": float(self.get_total_exposure()),
            "exposure_pct": float(self.get_exposure_pct()),
            "buying_power": float(self.get_buying_power()),
            "cash_balance": float(self.cash_balance),
            "total_unrealized_pnl": float(self.get_unrealized_pnl()),
            "realized_pnl": float(self.realized_pnl),
            "total_value": float(self.get_total_value()),
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
            "open_positions_count": self.get_position_count(),
            "buying_power": float(self.get_buying_power()),
            "exposure_pct": float(self.get_exposure_pct()),
        }

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.cash_balance = self.initial_capital
        self.positions.clear()
        self.realized_pnl = Decimal("0.0")
        self._current_prices.clear()
