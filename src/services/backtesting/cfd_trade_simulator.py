"""
Enhanced Trade Simulator with accurate CFD cost modeling.

Simulates order execution with:
- Realistic spread (not slippage)
- Overnight swap/rollover fees
- Triple swap on Wednesdays
- Proper lot size calculations

This replaces the basic TradeSimulator for CFD instruments.
"""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID, uuid4

import structlog

from .portfolio_state import PortfolioState
from .cfd_specifications import CFDSpecifications, InstrumentSpec, get_default_spec

logger = structlog.get_logger(__name__)


@dataclass
class CFDTradeResult:
    """
    Result of a simulated CFD trade execution.
    
    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        action: 'buy', 'sell', 'close_long', or 'close_short'
        entry_price: Execution price (after spread)
        quantity: Trade size in LOTS
        timestamp: Execution timestamp
        spread_cost: Cost of spread at entry
        commission: Commission paid (usually $0)
        net_capital_change: Change in cash balance
        success: Whether trade executed successfully
        error_message: Error message if failed
        contract_size: Contract size per lot
        notional_value: Total notional value of trade
    """
    trade_id: UUID
    symbol: str
    action: str
    entry_price: Decimal
    quantity: Decimal  # In LOTS
    timestamp: datetime
    spread_cost: Decimal
    commission: Decimal
    net_capital_change: Decimal
    success: bool
    error_message: Optional[str] = None
    contract_size: Decimal = Decimal("1000")
    notional_value: Decimal = Decimal("0")


class CFDTradeSimulator:
    """
    Simulates CFD trade execution with realistic cost modeling.
    
    Key differences from basic TradeSimulator:
    - Uses spread instead of slippage
    - Calculates overnight swap fees
    - Supports triple swap on Wednesdays
    - Proper lot size handling
    
    Attributes:
        cfd_specs: CFD instrument specifications
        default_spread_pips: Fallback spread if instrument not found
    """
    
    def __init__(
        self,
        cfd_specs: Optional[CFDSpecifications] = None,
        default_spread_pips: Decimal = Decimal("40.0"),
    ):
        """
        Initialize CFD trade simulator.
        
        Args:
            cfd_specs: CFD specifications (uses defaults if None)
            default_spread_pips: Default spread if instrument not configured
        """
        self.cfd_specs = cfd_specs or CFDSpecifications()
        self.default_spread_pips = default_spread_pips
        
        logger.info("cfd_trade_simulator_initialized")
    
    def _get_spec(self, symbol: str) -> Optional[InstrumentSpec]:
        """Get instrument specification, with fallback."""
        spec = self.cfd_specs.get_instrument(symbol)
        if not spec:
            logger.warning(
                "instrument_spec_not_found_using_defaults",
                symbol=symbol,
            )
        return spec
    
    def _apply_spread(
        self,
        price: Decimal,
        action: str,
        spec: Optional[InstrumentSpec],
    ) -> Tuple[Decimal, Decimal]:
        """
        Apply spread to execution price.
        
        For CFDs, spread is the difference between bid and ask.
        - Buy orders execute at ASK (higher)
        - Sell orders execute at BID (lower)
        
        Args:
            price: Mid-market price
            action: 'buy' or 'sell'
            spec: Instrument specification
            
        Returns:
            Tuple of (execution_price, spread_cost_per_unit)
        """
        if spec:
            spread_pips = spec.spread_pips
            pip_size = spec.pip_size
        else:
            spread_pips = self.default_spread_pips
            pip_size = Decimal("0.001")
        
        half_spread = (spread_pips * pip_size) / 2
        
        if action in ["buy", "close_short"]:
            # Buy at ASK (mid + half spread)
            execution_price = price + half_spread
        else:
            # Sell at BID (mid - half spread)
            execution_price = price - half_spread
        
        spread_cost_per_unit = spread_pips * pip_size
        
        return execution_price, spread_cost_per_unit
    
    def _calculate_commission(
        self,
        lot_size: Decimal,
        spec: Optional[InstrumentSpec],
    ) -> Decimal:
        """Calculate commission for trade."""
        if spec:
            return spec.commission_per_lot * lot_size
        return Decimal("0.0")
    
    def execute_entry(
        self,
        portfolio: PortfolioState,
        symbol: str,
        action: str,
        price: Decimal,
        lot_size: Decimal,
        timestamp: datetime,
    ) -> CFDTradeResult:
        """
        Execute a CFD position entry.
        
        Args:
            portfolio: Portfolio state to modify
            symbol: Trading symbol
            action: 'buy' (long) or 'sell' (short)
            price: Mid-market price
            lot_size: Position size in LOTS
            timestamp: Execution timestamp
            
        Returns:
            CFDTradeResult with execution details
        """
        trade_id = uuid4()
        spec = self._get_spec(symbol)
        
        # Apply spread
        execution_price, spread_per_unit = self._apply_spread(price, action, spec)
        
        # Calculate contract size and notional
        contract_size = spec.contract_size if spec else Decimal("1000")
        quantity_units = lot_size * contract_size
        notional_value = execution_price * quantity_units
        
        # Calculate costs
        spread_cost = self.cfd_specs.calculate_spread_cost(symbol, lot_size) if spec else Decimal("0")
        commission = self._calculate_commission(lot_size, spec)
        total_cost = spread_cost + commission
        
        # Check if position can be opened
        can_open, reason = portfolio.can_open_position(
            symbol, action, execution_price, quantity_units
        )
        
        if not can_open:
            return CFDTradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=lot_size,
                timestamp=timestamp,
                spread_cost=Decimal("0"),
                commission=Decimal("0"),
                net_capital_change=Decimal("0"),
                success=False,
                error_message=reason,
                contract_size=contract_size,
                notional_value=notional_value,
            )
        
        try:
            # Open position in portfolio (using units, not lots)
            position = portfolio.open_position(
                symbol=symbol,
                action=action,
                price=execution_price,
                quantity=quantity_units,
                timestamp=timestamp,
                trade_id=trade_id,
            )
            
            # Deduct trading costs from cash
            portfolio.cash_balance -= total_cost
            
            # Net capital change
            net_capital_change = -(notional_value + total_cost)
            
            logger.info(
                "cfd_entry_executed",
                trade_id=str(trade_id),
                symbol=symbol,
                action=action,
                lot_size=float(lot_size),
                units=float(quantity_units),
                price=float(execution_price),
                spread_cost=float(spread_cost),
                commission=float(commission),
            )
            
            return CFDTradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=lot_size,
                timestamp=timestamp,
                spread_cost=spread_cost,
                commission=commission,
                net_capital_change=net_capital_change,
                success=True,
                contract_size=contract_size,
                notional_value=notional_value,
            )
            
        except Exception as e:
            return CFDTradeResult(
                trade_id=trade_id,
                symbol=symbol,
                action=action,
                entry_price=execution_price,
                quantity=lot_size,
                timestamp=timestamp,
                spread_cost=Decimal("0"),
                commission=Decimal("0"),
                net_capital_change=Decimal("0"),
                success=False,
                error_message=str(e),
                contract_size=contract_size,
                notional_value=notional_value,
            )
    
    def execute_exit(
        self,
        portfolio: PortfolioState,
        symbol: str,
        exit_price: Decimal,
        timestamp: datetime,
    ) -> Tuple[CFDTradeResult, Decimal, Decimal, Decimal]:
        """
        Execute a CFD position exit with swap calculation.
        
        Args:
            portfolio: Portfolio state to modify
            symbol: Trading symbol
            exit_price: Mid-market price
            timestamp: Exit timestamp
            
        Returns:
            Tuple of (CFDTradeResult, gross_pnl, swap_cost, net_pnl)
        """
        if not portfolio.has_position(symbol):
            raise ValueError(f"No open position for {symbol}")
        
        position = portfolio.get_position(symbol)
        spec = self._get_spec(symbol)
        
        # Determine exit action
        exit_action = "close_long" if position.action == "buy" else "close_short"
        reverse_action = "sell" if position.action == "buy" else "buy"
        
        # Apply spread for exit
        execution_price, _ = self._apply_spread(exit_price, reverse_action, spec)
        
        # Calculate lot size from units
        contract_size = spec.contract_size if spec else Decimal("1000")
        lot_size = position.quantity / contract_size
        
        # Calculate swap cost for overnight holding
        swap_cost, nights = self.cfd_specs.calculate_total_overnight_cost(
            symbol=symbol,
            direction=position.action,
            lot_size=lot_size,
            entry_time=position.entry_timestamp,
            exit_time=timestamp,
        )
        
        # Close position in portfolio
        closed_position, gross_pnl, capital_return = portfolio.close_position(
            symbol, execution_price
        )
        
        # Calculate commission for exit
        commission = self._calculate_commission(lot_size, spec)
        
        # Calculate spread cost for exit (not charged again - only on entry)
        # Actually for CFDs, spread is effectively charged on both entry and exit
        # because you buy at ask and sell at bid
        spread_cost = self.cfd_specs.calculate_spread_cost(symbol, lot_size) if spec else Decimal("0")
        
        # Total fees
        total_fees = commission + spread_cost + abs(swap_cost)
        
        # Deduct fees from cash
        portfolio.cash_balance -= total_fees
        
        # Net P&L after all costs
        net_pnl = gross_pnl - total_fees
        
        # Calculate notional
        notional_value = execution_price * position.quantity
        
        logger.info(
            "cfd_exit_executed",
            trade_id=str(closed_position.trade_id),
            symbol=symbol,
            action=exit_action,
            lot_size=float(lot_size),
            exit_price=float(execution_price),
            gross_pnl=float(gross_pnl),
            swap_cost=float(swap_cost),
            nights_held=nights,
            spread_cost=float(spread_cost),
            commission=float(commission),
            net_pnl=float(net_pnl),
        )
        
        return (
            CFDTradeResult(
                trade_id=closed_position.trade_id,
                symbol=symbol,
                action=exit_action,
                entry_price=execution_price,
                quantity=lot_size,
                timestamp=timestamp,
                spread_cost=spread_cost,
                commission=commission,
                net_capital_change=capital_return - total_fees,
                success=True,
                contract_size=contract_size,
                notional_value=notional_value,
            ),
            gross_pnl,
            swap_cost,
            net_pnl,
        )
    
    def to_simulated_trade_dict(
        self,
        result: CFDTradeResult,
        backtest_run_id: UUID,
        exit_timestamp: Optional[datetime] = None,
        exit_price: Optional[Decimal] = None,
        gross_pnl: Optional[Decimal] = None,
        net_pnl: Optional[Decimal] = None,
        swap_cost: Optional[Decimal] = None,
    ) -> dict:
        """
        Convert CFDTradeResult to SimulatedTrade database record.
        
        Args:
            result: CFDTradeResult from execution
            backtest_run_id: Backtest run UUID
            exit_timestamp: Exit timestamp (for closed trades)
            exit_price: Exit price (for closed trades)
            gross_pnl: Gross P&L (for closed trades)
            net_pnl: Net P&L after fees (for closed trades)
            swap_cost: Overnight swap cost
            
        Returns:
            Dictionary suitable for SimulatedTrade creation
        """
        # Total fees = spread + commission + swap
        total_fees = result.spread_cost + result.commission
        if swap_cost:
            total_fees += abs(swap_cost)
        
        trade_dict = {
            "id": result.trade_id,
            "backtest_run_id": backtest_run_id,
            "symbol": result.symbol,
            "action": result.action,
            "entry_timestamp": result.timestamp,
            "entry_price": result.entry_price,
            "quantity": result.quantity * result.contract_size,  # Store in units
            "fees_paid": total_fees,
            "slippage_applied": result.spread_cost,  # Use spread cost in slippage field
            "exit_timestamp": exit_timestamp,
            "exit_price": exit_price,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
        }
        
        # Calculate holding duration if trade is closed
        if exit_timestamp and result.timestamp:
            holding_duration = int((exit_timestamp - result.timestamp).total_seconds())
            trade_dict["holding_duration_seconds"] = holding_duration
        
        return trade_dict


# Factory function for easy creation
def create_cfd_simulator(
    custom_swap_long: Optional[float] = None,
    custom_swap_short: Optional[float] = None,
    custom_spread_pips: Optional[float] = None,
) -> CFDTradeSimulator:
    """
    Create a CFD simulator with optional custom parameters.
    
    Args:
        custom_swap_long: Override swap rate for long positions
        custom_swap_short: Override swap rate for short positions
        custom_spread_pips: Override spread in pips
        
    Returns:
        Configured CFDTradeSimulator
    """
    cfd_specs = CFDSpecifications()
    
    # If custom params provided, update CrudeOIL spec
    if any([custom_swap_long, custom_swap_short, custom_spread_pips]):
        from .cfd_specifications import create_custom_spec
        
        default_spec = get_default_spec("CrudeOIL")
        
        custom_spec = create_custom_spec(
            symbol="CrudeOIL",
            swap_long=custom_swap_long or float(default_spec.swap_long_per_lot),
            swap_short=custom_swap_short or float(default_spec.swap_short_per_lot),
            spread_pips=custom_spread_pips or float(default_spec.spread_pips),
        )
        cfd_specs.add_instrument(custom_spec)
    
    return CFDTradeSimulator(cfd_specs=cfd_specs)
