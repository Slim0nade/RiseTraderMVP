"""
CFD Instrument Specifications for accurate backtesting.

Defines contract specifications, swap rates, spreads, and trading costs
for CFD instruments to ensure backtest accuracy matches live trading.

UPDATED: 2026-01-01 with ACTUAL Fortrade Canada specifications from MT4

Usage:
    specs = CFDSpecifications()
    crude_oil = specs.get_instrument("CrudeOIL")
    swap_cost = specs.calculate_overnight_swap("CrudeOIL", "buy", 1.0, 2)
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class SwapChargeDay(Enum):
    """Day when triple swap is charged (settlement for weekend)."""
    WEDNESDAY = 2  # Most common for forex/commodities
    FRIDAY = 4     # Some brokers use Friday


@dataclass
class InstrumentSpec:
    """
    CFD instrument specification.
    
    Attributes:
        symbol: Trading symbol (e.g., "CrudeOIL", "EURUSD")
        contract_size: Units per 1 lot (e.g., 1000 barrels for CL)
        pip_size: Minimum price movement (e.g., 0.001 for CL)
        pip_value_per_lot: Value of 1 pip move per lot in account currency
        spread_pips: Typical spread in pips/points
        swap_long_per_lot: Overnight swap for long positions (per lot per night)
        swap_short_per_lot: Overnight swap for short positions (per lot per night)
        swap_triple_day: Day when 3x swap is charged (for weekend settlement)
        commission_per_lot: Commission per lot (0 for most CFDs)
        min_lot_size: Minimum tradeable lot size
        lot_step: Lot size increment
        margin_pct: Required margin percentage
        trading_hours_start: Market open time (UTC)
        trading_hours_end: Market close time (UTC)
        rollover_time: Time when swap is applied (usually 22:00 UTC)
    """
    symbol: str
    contract_size: Decimal
    pip_size: Decimal
    pip_value_per_lot: Decimal
    spread_pips: Decimal
    swap_long_per_lot: Decimal  # Can be negative (cost) or positive (earn)
    swap_short_per_lot: Decimal  # Can be negative (cost) or positive (earn)
    swap_triple_day: SwapChargeDay = SwapChargeDay.WEDNESDAY
    commission_per_lot: Decimal = Decimal("0.0")
    min_lot_size: Decimal = Decimal("0.01")
    lot_step: Decimal = Decimal("0.01")
    margin_pct: Decimal = Decimal("5.0")  # 5% = 20:1 leverage
    trading_hours_start: time = time(0, 0)
    trading_hours_end: time = time(23, 59)
    rollover_time: time = time(22, 0)  # 22:00 UTC (5 PM EST)
    
    def calculate_pip_value(self, lot_size: Decimal, current_price: Decimal) -> Decimal:
        """Calculate pip value for a given lot size."""
        return self.pip_value_per_lot * lot_size
    
    def calculate_spread_cost(self, lot_size: Decimal) -> Decimal:
        """Calculate spread cost for entry/exit."""
        return self.spread_pips * self.pip_value_per_lot * lot_size
    
    def calculate_notional_value(self, lot_size: Decimal, price: Decimal) -> Decimal:
        """Calculate notional value of position."""
        return self.contract_size * lot_size * price


# Default instrument specifications
# UPDATED with ACTUAL Fortrade Canada specifications from MT4 (2026-01-01)
DEFAULT_INSTRUMENTS: Dict[str, InstrumentSpec] = {
    "CrudeOIL": InstrumentSpec(
        symbol="CrudeOIL",
        # From MT4 Contract Specification (2026-01-01):
        contract_size=Decimal("1000"),      # 1000 barrels per lot (ACTUAL)
        pip_size=Decimal("0.001"),          # Tick size = 0.001 (3 digits)
        pip_value_per_lot=Decimal("1.00"),  # Tick value = $1.00 per tick per lot
        spread_pips=Decimal("40"),          # 40 points spread (ACTUAL from MT4)
        # Swap rates - TBD: Need to get from MT4 Symbol Properties
        # These are ESTIMATED values - update with actual from MT4
        swap_long_per_lot=Decimal("-3.50"),   # Pay ~$3.50/lot/night for long (ESTIMATED)
        swap_short_per_lot=Decimal("-1.50"),  # Pay ~$1.50/lot/night for short (ESTIMATED)
        swap_triple_day=SwapChargeDay.WEDNESDAY,
        commission_per_lot=Decimal("0.0"),    # No commission (spread only)
        min_lot_size=Decimal("0.01"),
        margin_pct=Decimal("7.3"),            # 7.3% margin = ~13.7:1 leverage (ACTUAL)
        rollover_time=time(22, 0),            # 22:00 UTC (server time)
    ),
    "XAUUSD": InstrumentSpec(
        symbol="XAUUSD",
        contract_size=Decimal("100"),  # 100 oz per lot
        pip_size=Decimal("0.01"),
        pip_value_per_lot=Decimal("1.00"),
        spread_pips=Decimal("30.0"),   # ~$0.30 spread
        swap_long_per_lot=Decimal("-3.50"),
        swap_short_per_lot=Decimal("0.50"),  # Can earn on short gold
        commission_per_lot=Decimal("0.0"),
    ),
    "EURUSD": InstrumentSpec(
        symbol="EURUSD",
        contract_size=Decimal("100000"),  # 100,000 base currency
        pip_size=Decimal("0.0001"),
        pip_value_per_lot=Decimal("10.00"),  # $10 per pip per standard lot
        spread_pips=Decimal("1.2"),
        swap_long_per_lot=Decimal("-6.50"),  # Interest differential
        swap_short_per_lot=Decimal("3.20"),  # Can earn on short EUR
        commission_per_lot=Decimal("0.0"),
    ),
    "US500": InstrumentSpec(
        symbol="US500",
        contract_size=Decimal("1"),  # $1 per point
        pip_size=Decimal("0.1"),
        pip_value_per_lot=Decimal("0.10"),
        spread_pips=Decimal("5.0"),
        swap_long_per_lot=Decimal("-1.20"),
        swap_short_per_lot=Decimal("-0.80"),
        commission_per_lot=Decimal("0.0"),
    ),
}


class CFDSpecifications:
    """
    Manager for CFD instrument specifications.
    
    Provides methods to:
    - Get instrument specifications
    - Calculate swap/overnight costs
    - Calculate spread costs
    - Determine if swap should be charged
    """
    
    def __init__(self, custom_specs: Optional[Dict[str, InstrumentSpec]] = None):
        """
        Initialize with default or custom specifications.
        
        Args:
            custom_specs: Optional custom specifications to override defaults
        """
        self.instruments = DEFAULT_INSTRUMENTS.copy()
        if custom_specs:
            self.instruments.update(custom_specs)
    
    def get_instrument(self, symbol: str) -> Optional[InstrumentSpec]:
        """Get instrument specification by symbol."""
        return self.instruments.get(symbol)
    
    def add_instrument(self, spec: InstrumentSpec) -> None:
        """Add or update instrument specification."""
        self.instruments[spec.symbol] = spec
        logger.info("instrument_spec_added", symbol=spec.symbol)
    
    def calculate_overnight_swap(
        self,
        symbol: str,
        direction: str,  # 'buy' or 'sell'
        lot_size: Decimal,
        nights: int = 1,
        timestamp: Optional[datetime] = None,
    ) -> Decimal:
        """
        Calculate overnight swap cost.
        
        Args:
            symbol: Trading symbol
            direction: 'buy' (long) or 'sell' (short)
            lot_size: Position size in lots
            nights: Number of nights held
            timestamp: Optional timestamp to check for triple swap day
            
        Returns:
            Swap cost (negative = pay, positive = receive)
        """
        spec = self.get_instrument(symbol)
        if not spec:
            logger.warning("instrument_not_found_for_swap", symbol=symbol)
            return Decimal("0.0")
        
        # Get base swap rate
        if direction.lower() in ["buy", "long"]:
            swap_rate = spec.swap_long_per_lot
        else:
            swap_rate = spec.swap_short_per_lot
        
        # Calculate base swap
        base_swap = swap_rate * lot_size * nights
        
        # Check for triple swap day (Wednesday settlement for weekend)
        if timestamp:
            weekday = timestamp.weekday()
            if weekday == spec.swap_triple_day.value:
                # Triple swap on this day
                base_swap = base_swap * 3
                logger.debug(
                    "triple_swap_applied",
                    symbol=symbol,
                    weekday=weekday,
                    multiplier=3,
                )
        
        return base_swap
    
    def calculate_spread_cost(
        self,
        symbol: str,
        lot_size: Decimal,
    ) -> Decimal:
        """
        Calculate spread cost for entry.
        
        Note: Spread is paid on entry (built into execution price).
        
        Args:
            symbol: Trading symbol
            lot_size: Position size in lots
            
        Returns:
            Spread cost in account currency
        """
        spec = self.get_instrument(symbol)
        if not spec:
            return Decimal("0.0")
        
        return spec.calculate_spread_cost(lot_size)
    
    def should_charge_swap(
        self,
        entry_time: datetime,
        exit_time: datetime,
        rollover_time: time = time(22, 0),
    ) -> int:
        """
        Determine how many nights of swap should be charged.
        
        Swap is charged when position is held across rollover time (22:00 UTC).
        
        Args:
            entry_time: Position entry timestamp
            exit_time: Position exit timestamp
            rollover_time: Daily rollover time (default 22:00 UTC)
            
        Returns:
            Number of nights to charge swap
        """
        if entry_time.date() == exit_time.date():
            # Same day - check if crossed rollover
            entry_past_rollover = entry_time.time() >= rollover_time
            exit_past_rollover = exit_time.time() >= rollover_time
            
            if not entry_past_rollover and exit_past_rollover:
                return 1
            return 0
        
        # Multi-day position
        nights = 0
        current = entry_time
        
        while current.date() < exit_time.date():
            # Check if we'll cross rollover
            if current.time() < rollover_time:
                nights += 1
            
            # Move to next day
            current = datetime.combine(
                current.date(),
                time(0, 0)
            ) + timedelta(days=1)
        
        # Check final day
        if exit_time.time() >= rollover_time:
            nights += 1
        
        return nights
    
    def calculate_total_overnight_cost(
        self,
        symbol: str,
        direction: str,
        lot_size: Decimal,
        entry_time: datetime,
        exit_time: datetime,
    ) -> tuple[Decimal, int]:
        """
        Calculate total overnight swap cost for a trade.
        
        Accounts for:
        - Number of nights held
        - Triple swap on Wednesday
        
        Args:
            symbol: Trading symbol
            direction: 'buy' or 'sell'
            lot_size: Position size in lots
            entry_time: Entry timestamp
            exit_time: Exit timestamp
            
        Returns:
            Tuple of (total_swap_cost, nights_charged)
        """
        spec = self.get_instrument(symbol)
        if not spec:
            return Decimal("0.0"), 0
        
        # Get base swap rate
        if direction.lower() in ["buy", "long"]:
            swap_rate = spec.swap_long_per_lot
        else:
            swap_rate = spec.swap_short_per_lot
        
        # Calculate nights and any triple swap days
        total_swap = Decimal("0.0")
        nights = 0
        rollover_time = spec.rollover_time
        
        current = entry_time
        while current.date() <= exit_time.date():
            # Determine if this day's rollover is crossed
            day_rollover = datetime.combine(current.date(), rollover_time)
            
            if entry_time <= day_rollover < exit_time:
                # Position held across this rollover
                weekday = current.weekday()
                
                if weekday == spec.swap_triple_day.value:
                    # Triple swap day
                    total_swap += swap_rate * lot_size * 3
                    nights += 3  # Count as 3 nights for reporting
                else:
                    total_swap += swap_rate * lot_size
                    nights += 1
            
            # Move to next day
            current = datetime.combine(current.date(), time(0, 0)) + timedelta(days=1)
        
        return total_swap, nights


def get_default_spec(symbol: str) -> Optional[InstrumentSpec]:
    """Quick access to get default instrument specification."""
    return DEFAULT_INSTRUMENTS.get(symbol)


def create_custom_spec(
    symbol: str,
    swap_long: float,
    swap_short: float,
    spread_pips: float = 40.0,
    contract_size: float = 1000.0,
    pip_value: float = 1.0,
) -> InstrumentSpec:
    """
    Create a custom instrument specification.
    
    Useful for testing or when broker specs differ from defaults.
    
    Args:
        symbol: Trading symbol
        swap_long: Swap rate for long positions
        swap_short: Swap rate for short positions  
        spread_pips: Spread in pips
        contract_size: Contract size per lot
        pip_value: Pip value per lot
        
    Returns:
        InstrumentSpec instance
    """
    return InstrumentSpec(
        symbol=symbol,
        contract_size=Decimal(str(contract_size)),
        pip_size=Decimal("0.001"),
        pip_value_per_lot=Decimal(str(pip_value)),
        spread_pips=Decimal(str(spread_pips)),
        swap_long_per_lot=Decimal(str(swap_long)),
        swap_short_per_lot=Decimal(str(swap_short)),
    )
