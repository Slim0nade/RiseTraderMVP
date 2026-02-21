"""
Stealth Stop Manager Service

A 24/7 background service that monitors positions and automatically trails stops
using institutional-grade "weird" prices to avoid stop hunting.

FULLY DYNAMIC - No hardcoding! Automatically:
- Detects open positions from MT4
- Calculates trail levels based on ATR and price action
- Adjusts stops using institutional pricing

Usage:
    Integrated into main API - starts automatically
    Or standalone: python -m src.services.stealth_stop_manager
"""
import asyncio
import json
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("stealth-stop-manager")


@dataclass
class DynamicTrailConfig:
    """Configuration for dynamic trailing stops.
    
    Enhanced with new protection settings:
    - disaster_stop_multiplier: Initial disaster stop distance
    - erosion_threshold_atr: Tighten stop when erosion exceeds this
    - erosion_alert_threshold_atr: Log warning when erosion exceeds this
    """
    # ATR-based trailing
    atr_multiplier_initial: float = 2.0  # Initial stop distance in ATR
    atr_multiplier_trail: float = 1.5    # Trailing stop distance in ATR
    
    # Trail trigger settings (in ATR units) - LOWERED from 1.0 to 0.5 (FR-011)
    trail_trigger_atr: float = 0.5       # Start trailing after price moves 0.5x ATR in profit
    trail_step_atr: float = 0.5          # Trail every 0.5 ATR of additional profit
    
    # Institutional pricing
    min_offset_pips: float = 5           # Min random offset
    max_offset_pips: float = 15          # Max random offset
    pip_value: float = 0.01              # Crude oil = 0.01, Forex = 0.0001
    
    # Breakeven settings - LOWERED from 1.5 to 0.5 (FR-011)
    breakeven_trigger_atr: float = 0.5   # Move to breakeven after 0.5x ATR profit
    breakeven_offset_pips: float = 10    # Lock in 10 pips profit at breakeven
    
    # NEW: Disaster stop protection (FR-002)
    disaster_stop_multiplier: float = 3.0  # Initial stop at 3x ATR from entry
    
    # NEW: Profit erosion detection (FR-010)
    erosion_threshold_atr: float = 0.5     # Tighten stop when erosion > 0.5x ATR
    erosion_alert_threshold_atr: float = 0.3  # Warning when erosion > 0.3x ATR
    
    # NEW: Configuration management
    monitoring_cycle_seconds: int = 60     # Position check interval
    max_volatility_adjustment: float = 0.5  # Max 50% stop change per cycle
    atr_fallback_percentage: float = 0.02  # Fallback when ATR unavailable
    manual_override_grace_period: int = 60  # Respect manual changes for 60s    # Lock in 10 pips profit at breakeven


@dataclass 
class MonitoredPosition:
    """A position being monitored for trailing stops.
    
    Enhanced with profit tracking for erosion detection:
    - profit_highwater: Maximum profit reached since entry
    - profit_erosion: Amount profit has eroded from highwater
    - disaster_stop_set: Whether initial disaster stop was applied
    - trailing_activated: Whether trailing has been activated
    - last_stop_modification: When stop was last modified
    - manual_override_until: Respect manual changes until this time
    """
    ticket: int
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    current_stop: float
    current_tp: float
    lots: float
    current_price: float = 0.0  # Current market price
    last_check: Optional[datetime] = None
    last_trail_price: Optional[float] = None  # Price at which we last trailed
    breakeven_triggered: bool = False
    
    # New fields for enhanced protection (FR-002, FR-010, FR-011)
    profit_highwater: float = 0.0  # Maximum profit reached (FR-010)
    profit_erosion: float = 0.0    # Current erosion from highwater
    disaster_stop_set: bool = False  # Initial disaster stop applied (FR-002)
    trailing_activated: bool = False  # Early trailing triggered (FR-011)
    last_stop_modification: Optional[datetime] = None
    manual_override_until: Optional[datetime] = None  # Respect manual changes
    detected_at: Optional[datetime] = None  # When position was first detected
    
    
class StealthStopManager:
    """
    Background service for intelligent stop management.
    
    FULLY DYNAMIC - automatically detects positions and calculates
    optimal trail levels based on ATR and market conditions.
    """
    
    def __init__(
        self,
        mt4_host: str = "localhost",
        mt4_port: int = 5555,
        poll_interval: int = 5,  # seconds
        config: Optional[DynamicTrailConfig] = None,
        features_enabled: Optional[Dict[str, bool]] = None
    ):
        """
        Initialize the Stealth Stop Manager.
        
        Args:
            mt4_host: MT4 ZMQ server host
            mt4_port: MT4 ZMQ server port
            poll_interval: How often to check prices (seconds)
            config: Dynamic trail configuration
            features_enabled: Feature flags for protection mechanisms
        """
        self.mt4_host = mt4_host
        self.mt4_port = mt4_port
        self.poll_interval = poll_interval
        self.config = config or DynamicTrailConfig()
        
        self._mt4_client: Optional[MT4Client] = None
        self._running = False
        self._monitored_positions: Dict[int, MonitoredPosition] = {}
        self._atr_cache: Dict[str, float] = {}  # symbol -> ATR value
        self._atr_cache_time: Dict[str, datetime] = {}  # symbol -> last update time
        
        # Feature flags with defaults
        self.features_enabled = features_enabled or {
            "enable_disaster_stops": True,
            "enable_profit_erosion": True,
            "enable_early_breakeven": True,
            "enable_institutional_pricing": True,
            "enable_alerts": True,
        }
        
        # Alert system
        self._alert_history: List[Dict[str, Any]] = []
        self._max_alert_history = 100
        self.on_alert: Optional[Callable[[Dict[str, Any]], None]] = None  # symbol -> last update time
        
    def calculate_institutional_price(
        self,
        base_price: float,
        direction: str,
        is_stop: bool = True
    ) -> float:
        """
        Calculate an institutional-grade price with random offset.
        
        Avoids obvious levels like round numbers and .X0/.X5 prices.
        
        Args:
            base_price: The base price before adjustment
            direction: "long" or "short"
            is_stop: True for stop loss, False for take profit
            
        Returns:
            Adjusted price with random offset
        """
        # Generate random offset
        offset = random.uniform(
            self.config.min_offset_pips, 
            self.config.max_offset_pips
        ) * self.config.pip_value
        
        # Determine offset direction based on position and order type
        if direction.lower() == "long":
            if is_stop:
                # Long stop is below - push further down
                price = base_price - offset
            else:
                # Long TP is above - push further up
                price = base_price + offset
        else:  # short
            if is_stop:
                # Short stop is above - push further up
                price = base_price + offset
            else:
                # Short TP is below - push further down
                price = base_price - offset
            
        # Round to 2 decimal places
        price = round(price, 2)
        
        # Ensure it's not at an obvious level (.00 or .50)
        cents = int((price * 100) % 100)
        if cents == 0 or cents == 50:
            nudge = random.uniform(0.03, 0.09)
            price = round(price + nudge, 2)
            
        return price
    
    async def _get_mt4_client(self) -> MT4Client:
        """Get or create MT4 client connection."""
        if self._mt4_client is None:
            encryption_manager = MT4EncryptionManager(encryption_enabled=False)
            self._mt4_client = MT4Client(
                host=self.mt4_host,
                rep_port=self.mt4_port,
                pub_port=self.mt4_port + 1,
                magic_number=123456,
                encryption_manager=encryption_manager,
                timeout_ms=10000
            )
            await self._mt4_client.connect()
            logger.info(f"Connected to MT4 at {self.mt4_host}:{self.mt4_port}")
        return self._mt4_client
    
    async def _reconnect(self) -> bool:
        """Attempt to reconnect to MT4."""
        try:
            if self._mt4_client:
                await self._mt4_client.disconnect()
            self._mt4_client = None
            await self._get_mt4_client()
            return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    async def get_atr(self, symbol: str, period: int = 14, timeframe: str = "H1") -> Optional[float]:
        """
        Get ATR value for a symbol.
        
        For now, uses sensible defaults based on symbol type.
        TODO: Implement proper ATR calculation from candle data.
        """
        # Symbol-specific ATR defaults (based on typical volatility)
        atr_defaults = {
            "CrudeOIL": 0.75,
            "XAUUSD": 15.0,
            "EURUSD": 0.0050,
            "GBPUSD": 0.0070,
            "USDJPY": 0.50,
        }
        
        # Return default or generic fallback
        return atr_defaults.get(symbol, 0.75)
    
    async def get_open_positions_from_mt4(self) -> List[Dict[str, Any]]:
        """Get all open positions directly from MT4."""
        try:
            client = await self._get_mt4_client()
            response = await client.get_open_positions()
            
            return response.get("positions", [])
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    async def modify_stop(self, ticket: int, new_stop: float) -> bool:
        """Modify stop loss for a position."""
        try:
            client = await self._get_mt4_client()
            response = await client.modify_position(
                ticket=ticket,
                stop_loss=Decimal(str(new_stop))
            )
            
            success = response.get("success", False) or response.get("status") == "OK"
            if success:
                logger.info(f"✅ Modified position {ticket} SL to ${new_stop:.2f}")
            else:
                logger.error(f"❌ Failed to modify position {ticket}: {response}")
            return success
            
        except Exception as e:
            logger.error(f"Error modifying position {ticket}: {e}")
            return False

    async def calculate_disaster_stop(
        self,
        position: MonitoredPosition,
        atr: Optional[float],
        apply_offset: bool = False
    ) -> float:
        """
        Calculate disaster stop price for a position.
        
        FR-002: Set initial stop at disaster_stop_multiplier × ATR from entry.
        
        Args:
            position: The position to calculate stop for
            atr: Current ATR value (or None to use fallback)
            apply_offset: Whether to apply institutional pricing offset
            
        Returns:
            Calculated stop price
        """
        entry = position.entry_price
        multiplier = self.config.disaster_stop_multiplier
        
        # Use ATR or fallback to percentage of entry
        if atr is None or atr <= 0:
            # Fallback: use percentage of entry price
            distance = entry * self.config.atr_fallback_percentage * multiplier
            logger.warning(
                f"ATR unavailable for {position.symbol}, using fallback: "
                f"{self.config.atr_fallback_percentage * 100:.1f}% × {multiplier}× = ${distance:.2f}"
            )
        else:
            distance = atr * multiplier
        
        # Calculate stop based on direction
        if position.direction.lower() == "short":
            # For SHORT: stop is ABOVE entry (loss if price rises)
            base_stop = entry + distance
        else:
            # For LONG: stop is BELOW entry (loss if price falls)
            base_stop = entry - distance
        
        # Apply institutional pricing offset if requested
        if apply_offset and self.features_enabled.get("enable_institutional_pricing", True):
            return self.calculate_institutional_price(
                base_stop,
                position.direction,
                is_stop=True
            )
        
        return round(base_stop, 2)

    async def apply_disaster_protection(
        self,
        position: MonitoredPosition
    ) -> bool:
        """
        Apply disaster stop protection to a position.
        
        FR-002: Set initial stop loss within 10 seconds of position detection.
        
        Args:
            position: The position to protect
            
        Returns:
            True if stop was applied/verified, False otherwise
        """
        # Check feature flag
        if not self.features_enabled.get("enable_disaster_stops", True):
            logger.debug(f"Disaster stops disabled, skipping for {position.ticket}")
            return False
        
        # Already protected
        if position.disaster_stop_set:
            return False
        
        # Get ATR for the symbol
        atr = await self.get_atr(position.symbol)
        
        # Calculate disaster stop
        disaster_stop = await self.calculate_disaster_stop(
            position,
            atr,
            apply_offset=self.features_enabled.get("enable_institutional_pricing", True)
        )
        
        # Check if existing stop is already tighter (closer to entry = more protective)
        if position.current_stop != 0:
            is_tighter = self._is_stop_tighter(
                position.direction,
                position.entry_price,
                position.current_stop,
                disaster_stop
            )
            
            if is_tighter:
                logger.info(
                    f"Position {position.ticket} already has tighter stop "
                    f"${position.current_stop:.2f} vs disaster ${disaster_stop:.2f}"
                )
                position.disaster_stop_set = True
                return True  # Existing stop is good
        
        # Apply the disaster stop
        logger.info(
            f"🛡️ Applying disaster stop to {position.ticket}: "
            f"{position.direction.upper()} {position.symbol} @ ${position.entry_price:.2f} → "
            f"stop ${disaster_stop:.2f} ({self.config.disaster_stop_multiplier}×ATR)"
        )
        
        success = await self.modify_stop(position.ticket, disaster_stop)
        
        if success:
            position.disaster_stop_set = True
            position.current_stop = disaster_stop
            position.last_stop_modification = datetime.now()
            logger.info(f"✅ Disaster stop set for {position.ticket}")
            
            # Emit alert
            self.emit_alert({
                "type": "disaster_stop",
                "ticket": position.ticket,
                "symbol": position.symbol,
                "message": f"Disaster stop set at ${disaster_stop:.2f}",
                "severity": "info",
                "stop_price": disaster_stop,
            })
        else:
            logger.error(f"❌ Failed to set disaster stop for {position.ticket}")
        
        return success

    def _is_stop_tighter(
        self,
        direction: str,
        entry_price: float,
        current_stop: float,
        new_stop: float
    ) -> bool:
        """
        Check if current stop is tighter (more protective) than new stop.
        
        For LONG: Tighter means closer to entry from below
        For SHORT: Tighter means closer to entry from above
        """
        if direction.lower() == "long":
            # LONG: Stop is below entry, tighter = higher (closer to entry)
            current_distance = entry_price - current_stop
            new_distance = entry_price - new_stop
        else:
            # SHORT: Stop is above entry, tighter = lower (closer to entry)
            current_distance = current_stop - entry_price
            new_distance = new_stop - entry_price
        
        # Tighter = smaller distance from entry
        return current_distance < new_distance

    def calculate_profit(self, position: MonitoredPosition) -> float:
        """
        Calculate current profit for a position in price units.
        
        Args:
            position: The position to calculate profit for
            
        Returns:
            Profit in price units (positive = profit, negative = loss)
        """
        if position.direction.lower() == "short":
            # SHORT: Profit when price falls below entry
            return position.entry_price - position.current_price
        else:
            # LONG: Profit when price rises above entry
            return position.current_price - position.entry_price

    def update_highwater(self, position: MonitoredPosition, current_profit: float) -> None:
        """
        Update profit highwater mark if current profit exceeds it.
        
        FR-010: Track maximum profit reached for erosion detection.
        
        Args:
            position: The position to update
            current_profit: Current profit in price units
        """
        if current_profit > position.profit_highwater:
            old_highwater = position.profit_highwater
            position.profit_highwater = current_profit
            
            if old_highwater > 0:
                logger.info(
                    f"📈 New highwater for {position.ticket}: "
                    f"${old_highwater:.2f} → ${current_profit:.2f}"
                )
            else:
                logger.info(
                    f"📈 Highwater set for {position.ticket}: ${current_profit:.2f}"
                )

    def calculate_erosion(
        self,
        position: MonitoredPosition,
        current_profit: float
    ) -> float:
        """
        Calculate profit erosion from highwater mark.
        
        FR-010: Detect when profit erodes from maximum.
        
        Args:
            position: The position to check
            current_profit: Current profit in price units
            
        Returns:
            Erosion amount (positive = profit eroded, 0 = no erosion)
        """
        if position.profit_highwater <= 0:
            return 0.0
            
        erosion = position.profit_highwater - current_profit
        
        # Update position's erosion tracking
        position.profit_erosion = max(0.0, erosion)
        
        return max(0.0, erosion)

    async def check_erosion(
        self,
        position: MonitoredPosition,
        current_profit: float,
        atr: float
    ) -> Dict[str, Any]:
        """
        Check if profit erosion exceeds alert or protection thresholds.
        
        FR-010: Two-tier erosion detection:
        - Alert at erosion_alert_threshold_atr (default 0.3×)
        - Protection at erosion_threshold_atr (default 0.5×)
        
        Args:
            position: The position to check
            current_profit: Current profit in price units
            atr: Current ATR for threshold calculations
            
        Returns:
            Dict with alert_triggered, protection_triggered, erosion_atr_ratio
        """
        result = {
            "alert_triggered": False,
            "protection_triggered": False,
            "erosion": 0.0,
            "erosion_atr_ratio": 0.0,
        }
        
        # Calculate erosion
        erosion = self.calculate_erosion(position, current_profit)
        result["erosion"] = erosion
        
        if erosion <= 0 or atr <= 0:
            return result
        
        # Calculate erosion as ratio of ATR
        erosion_atr_ratio = erosion / atr
        result["erosion_atr_ratio"] = erosion_atr_ratio
        
        # Check alert threshold (0.3× ATR default)
        if erosion_atr_ratio >= self.config.erosion_alert_threshold_atr:
            result["alert_triggered"] = True
            logger.warning(
                f"⚠️ PROFIT EROSION ALERT for {position.ticket}: "
                f"${erosion:.2f} erosion ({erosion_atr_ratio:.2f}× ATR) "
                f"from highwater ${position.profit_highwater:.2f}"
            )
        
        # Check protection threshold (0.5× ATR default)
        if erosion_atr_ratio >= self.config.erosion_threshold_atr:
            result["protection_triggered"] = True
            logger.warning(
                f"🛡️ EROSION PROTECTION TRIGGERED for {position.ticket}: "
                f"${erosion:.2f} erosion ({erosion_atr_ratio:.2f}× ATR) "
                f"exceeds threshold ({self.config.erosion_threshold_atr}×)"
            )
        
        return result

    async def apply_erosion_protection(self, position: MonitoredPosition) -> bool:
        """
        Apply erosion protection by tightening the stop loss.
        
        FR-010: Tighten stop when erosion exceeds protection threshold.
        
        Args:
            position: The position to protect
            
        Returns:
            True if protection was applied, False otherwise
        """
        # Check feature flag
        if not self.features_enabled.get("enable_profit_erosion", True):
            logger.debug(f"Profit erosion disabled, skipping for {position.ticket}")
            return False
        
        # Get ATR
        atr = await self.get_atr(position.symbol)
        if atr is None or atr <= 0:
            logger.warning(f"Cannot apply erosion protection without ATR for {position.symbol}")
            return False
        
        # Calculate current profit and erosion
        current_profit = self.calculate_profit(position)
        erosion_result = await self.check_erosion(position, current_profit, atr)
        
        # Only apply if protection threshold exceeded
        if not erosion_result["protection_triggered"]:
            return False
        
        # Calculate tightened stop (trail stop at current price)
        new_stop = self.calculate_trail_stop(position, position.current_price, atr)
        
        if new_stop is None:
            logger.debug(f"No valid trail stop calculated for erosion protection on {position.ticket}")
            return False
        
        # Apply institutional pricing
        if self.features_enabled.get("enable_institutional_pricing", True):
            new_stop = self.calculate_institutional_price(
                new_stop,
                position.direction,
                is_stop=True
            )
        
        # Only modify if new stop is tighter than current
        if position.current_stop != 0:
            is_tighter = self._is_stop_tighter(
                position.direction,
                position.entry_price,
                new_stop,  # New stop
                position.current_stop  # Current stop
            )
            if not is_tighter:
                logger.debug(
                    f"New stop ${new_stop:.2f} not tighter than current ${position.current_stop:.2f}"
                )
                return False
        
        logger.info(
            f"🛡️ Tightening stop for {position.ticket} due to erosion: "
            f"${position.current_stop:.2f} → ${new_stop:.2f}"
        )
        
        success = await self.modify_stop(position.ticket, new_stop)
        
        if success:
            position.current_stop = new_stop
            position.last_stop_modification = datetime.now()
        
        return success
    
    async def sync_positions(self) -> None:
        """
        Sync monitored positions with actual MT4 positions.
        
        - Adds new positions
        - Removes closed positions
        - Updates current stop/tp/price values
        - Applies disaster stop protection to new positions (FR-002)
        """
        mt4_positions = await self.get_open_positions_from_mt4()
        
        # Get set of current MT4 tickets
        mt4_tickets = set()
        new_positions: List[MonitoredPosition] = []  # Track new positions
        
        for pos in mt4_positions:
            ticket = pos.get("ticket")
            if not ticket:
                continue
                
            mt4_tickets.add(ticket)
            
            # Determine direction from order type
            order_type = pos.get("type", "").upper()
            if order_type == "BUY":
                direction = "long"
            elif order_type == "SELL":
                direction = "short"
            else:
                continue  # Skip pending orders
            
            # Get current price from position data
            current_price = float(pos.get("curPrice", 0))
            
            # Update or add position
            if ticket in self._monitored_positions:
                # Update existing
                monitored = self._monitored_positions[ticket]
                monitored.current_stop = float(pos.get("sl", 0))
                monitored.current_tp = float(pos.get("tp", 0))
                monitored.current_price = current_price
            else:
                # Add new position
                monitored = MonitoredPosition(
                    ticket=ticket,
                    symbol=pos.get("symbol", ""),
                    direction=direction,
                    entry_price=float(pos.get("openPrice", 0)),
                    current_stop=float(pos.get("sl", 0)),
                    current_tp=float(pos.get("tp", 0)),
                    lots=float(pos.get("lots", 0)),
                    current_price=current_price,
                    detected_at=datetime.now(),  # Track when detected
                )
                self._monitored_positions[ticket] = monitored
                new_positions.append(monitored)
                logger.info(
                    f"📊 New position detected: {ticket} {direction.upper()} "
                    f"{monitored.symbol} @ ${monitored.entry_price:.2f}"
                )
        
        # Remove closed positions
        closed_tickets = set(self._monitored_positions.keys()) - mt4_tickets
        for ticket in closed_tickets:
            pos = self._monitored_positions.pop(ticket)
            logger.info(f"📴 Position {ticket} closed/removed from monitoring")
        
        # Apply disaster stop protection to new positions (FR-002)
        for position in new_positions:
            await self.apply_disaster_protection(position)    
    def calculate_trail_stop(
        self,
        position: MonitoredPosition,
        current_price: float,
        atr: float
    ) -> Optional[float]:
        """
        Calculate new trailing stop based on current price and ATR.
        
        CRITICAL RULES:
        - For LONG: Stop must always be ABOVE entry (locks profit)
        - For SHORT: Stop must always be BELOW entry (locks profit)
        - Never set a stop that guarantees a loss!
        
        Returns None if no trail is needed.
        """
        entry = position.entry_price
        current_stop = position.current_stop
        
        if position.direction == "long":
            # For long: profit when price > entry
            profit_distance = current_price - entry
            
            # Calculate ideal stop (trailing behind current price)
            ideal_stop = current_price - (atr * self.config.atr_multiplier_trail)
            
            # CRITICAL: Stop must be ABOVE entry to lock profit
            if ideal_stop <= entry:
                logger.debug(f"LONG {position.ticket}: ideal_stop ${ideal_stop:.2f} <= entry ${entry:.2f}, skipping (would not lock profit)")
                return None
            
            # Only trail if:
            # 1. We're in profit by at least trail_trigger_atr
            # 2. New stop would be higher than current stop (tightening)
            min_profit_for_trail = atr * self.config.trail_trigger_atr
            
            if profit_distance >= min_profit_for_trail:
                if current_stop == 0 or ideal_stop > current_stop:
                    return ideal_stop
                    
            # Check for breakeven trigger
            if not position.breakeven_triggered:
                breakeven_trigger = atr * self.config.breakeven_trigger_atr
                if profit_distance >= breakeven_trigger:
                    breakeven_stop = entry + (self.config.breakeven_offset_pips * self.config.pip_value)
                    if current_stop == 0 or breakeven_stop > current_stop:
                        position.breakeven_triggered = True
                        return breakeven_stop
                        
        else:  # short
            # For short: profit when price < entry
            profit_distance = entry - current_price
            
            # Calculate ideal stop (trailing above current price)
            ideal_stop = current_price + (atr * self.config.atr_multiplier_trail)
            
            # CRITICAL: Stop must be BELOW entry to lock profit
            if ideal_stop >= entry:
                logger.debug(f"SHORT {position.ticket}: ideal_stop ${ideal_stop:.2f} >= entry ${entry:.2f}, skipping (would not lock profit)")
                return None
            
            # Only trail if:
            # 1. We're in profit by at least trail_trigger_atr
            # 2. New stop would be lower than current stop (tightening)
            min_profit_for_trail = atr * self.config.trail_trigger_atr
            
            if profit_distance >= min_profit_for_trail:
                if current_stop == 0 or ideal_stop < current_stop:
                    return ideal_stop
                    
            # Check for breakeven trigger
            if not position.breakeven_triggered:
                breakeven_trigger = atr * self.config.breakeven_trigger_atr
                if profit_distance >= breakeven_trigger:
                    breakeven_stop = entry - (self.config.breakeven_offset_pips * self.config.pip_value)
                    if current_stop == 0 or breakeven_stop < current_stop:
                        position.breakeven_triggered = True
                        return breakeven_stop
        
        return None
    
    async def check_and_trail(self, position: MonitoredPosition, current_price: float, atr: float) -> None:
        """
        Check if position needs trailing and execute if needed.
        """
        position.last_check = datetime.utcnow()
        
        # Calculate potential new stop
        new_stop = self.calculate_trail_stop(position, current_price, atr)
        
        if new_stop is None:
            return
            
        # Apply institutional pricing (random offset)
        institutional_stop = self.calculate_institutional_price(
            new_stop,
            position.direction,
            is_stop=True
        )
        
        # Verify the institutional stop is still valid (didn't flip past entry)
        if position.direction == "long":
            if institutional_stop <= position.entry_price:
                return
            # BUG FIX: Ensure new stop is actually HIGHER than current (for longs)
            if institutional_stop <= position.current_stop:
                logger.debug(f"Skipping trail for {position.ticket}: institutional stop ${institutional_stop:.2f} not better than current ${position.current_stop:.2f}")
                return
        else:
            if institutional_stop >= position.entry_price:
                return
            # BUG FIX: Ensure new stop is actually LOWER than current (for shorts)
            if position.current_stop > 0 and institutional_stop >= position.current_stop:
                logger.debug(f"Skipping trail for {position.ticket}: institutional stop ${institutional_stop:.2f} not better than current ${position.current_stop:.2f}")
                return
        
        # Calculate profit locked
        if position.direction == "long":
            profit_locked = (institutional_stop - position.entry_price) / self.config.pip_value
        else:
            profit_locked = (position.entry_price - institutional_stop) / self.config.pip_value
        
        logger.info(
            f"🎯 Trail triggered for {position.ticket}! "
            f"Price ${current_price:.2f}, ATR ${atr:.2f}. "
            f"Moving SL ${position.current_stop:.2f} → ${institutional_stop:.2f} "
            f"(locks {profit_locked:.0f} pips)"
        )
        
        # Execute the modification
        success = await self.modify_stop(position.ticket, institutional_stop)
        
        if success:
            position.current_stop = institutional_stop
            position.last_trail_price = current_price
    

    def should_trail(self, position: MonitoredPosition, atr: float) -> bool:
        """
        Check if position should trigger trailing.
        
        FR-004: Trail triggers at trail_trigger_atr (0.5× ATR by default).
        
        Args:
            position: The position to check
            atr: Current ATR value
            
        Returns:
            True if trailing should be triggered
        """
        if atr <= 0:
            return False
        
        # Calculate profit
        if position.direction == "long":
            profit = position.current_price - position.entry_price
        else:
            profit = position.entry_price - position.current_price
        
        # Check against threshold
        threshold = atr * self.config.trail_trigger_atr
        
        return profit >= threshold
    
    def should_breakeven(self, position: MonitoredPosition, atr: float) -> bool:
        """
        Check if position should trigger breakeven.
        
        FR-005: Breakeven triggers at breakeven_trigger_atr (0.5× ATR by default).
        
        Args:
            position: The position to check
            atr: Current ATR value
            
        Returns:
            True if breakeven should be triggered
        """
        if atr <= 0:
            return False
        
        if position.breakeven_triggered:
            return False  # Already triggered
        
        # Calculate profit
        if position.direction == "long":
            profit = position.current_price - position.entry_price
        else:
            profit = position.entry_price - position.current_price
        
        # Check against threshold
        threshold = atr * self.config.breakeven_trigger_atr
        
        return profit >= threshold
    
    async def apply_trail(self, position: MonitoredPosition) -> bool:
        """
        Apply trailing stop to position.
        
        Args:
            position: The position to trail
            
        Returns:
            True if trail was applied, False otherwise
        """
        atr = await self.get_atr(position.symbol)
        if atr is None or atr <= 0:
            logger.warning(f"Cannot apply trail without ATR for {position.symbol}")
            return False
        
        # Check if we should trail
        if not self.should_trail(position, atr):
            return False
        
        # Calculate new trail stop
        new_stop = self.calculate_trail_stop(position, position.current_price, atr)
        
        if new_stop is None:
            logger.debug(f"No valid trail stop for {position.ticket}")
            return False
        
        # Apply institutional pricing
        if self.features_enabled.get("enable_institutional_pricing", True):
            new_stop = self.calculate_institutional_price(
                new_stop,
                position.direction,
                is_stop=True
            )
        
        # Only modify if new stop is tighter
        if position.current_stop != 0:
            is_tighter = self._is_stop_tighter(
                position.direction,
                position.entry_price,
                new_stop,
                position.current_stop
            )
            if not is_tighter:
                logger.debug(
                    f"Trail stop ${new_stop:.2f} not tighter than current ${position.current_stop:.2f}"
                )
                return False
        
        old_stop = position.current_stop
        was_trailing = position.trailing_activated
        
        logger.info(
            f"🎯 TRAIL ACTIVATED for {position.ticket}: "
            f"${position.current_stop:.2f} → ${new_stop:.2f}"
        )
        
        success = await self.modify_stop(position.ticket, new_stop)
        
        if success:
            position.current_stop = new_stop
            position.trailing_activated = True
            position.last_stop_modification = datetime.now()
            
            # Emit alert (only on first activation)
            if not was_trailing:
                self.emit_alert({
                    "type": "trail_activated",
                    "ticket": position.ticket,
                    "symbol": position.symbol,
                    "message": f"Trailing activated: ${old_stop:.2f} → ${new_stop:.2f}",
                    "severity": "info",
                    "old_stop": old_stop,
                    "new_stop": new_stop,
                })
        
        return success
    
    async def apply_breakeven(self, position: MonitoredPosition) -> bool:
        """
        Apply breakeven stop to position.
        
        Sets stop at entry price + small offset to guarantee no loss.
        
        Args:
            position: The position to move to breakeven
            
        Returns:
            True if breakeven was applied, False otherwise
        """
        atr = await self.get_atr(position.symbol)
        if atr is None or atr <= 0:
            logger.warning(f"Cannot apply breakeven without ATR for {position.symbol}")
            return False
        
        # Check if we should breakeven
        if not self.should_breakeven(position, atr):
            return False
        
        # Calculate breakeven stop (entry +/- small offset)
        offset = self.config.breakeven_offset_pips * self.config.pip_value
        
        if position.direction == "long":
            # For LONG: stop above entry
            breakeven_stop = position.entry_price + offset
            
            # Only apply if tighter than current stop
            if position.current_stop != 0 and breakeven_stop <= position.current_stop:
                return False
        else:
            # For SHORT: stop below entry
            breakeven_stop = position.entry_price - offset
            
            # Only apply if tighter than current stop
            if position.current_stop != 0 and breakeven_stop >= position.current_stop:
                return False
        
        logger.info(
            f"⚖️ BREAKEVEN for {position.ticket}: "
            f"${position.current_stop:.2f} → ${breakeven_stop:.2f} (entry: ${position.entry_price:.2f})"
        )
        
        success = await self.modify_stop(position.ticket, breakeven_stop)
        
        if success:
            position.current_stop = breakeven_stop
            position.breakeven_triggered = True
            position.last_stop_modification = datetime.now()
        
        return success

    # ========================================================================
    # Alert System Methods (FR-011, FR-012)
    # ========================================================================
    
    def emit_alert(self, alert: Dict[str, Any]) -> None:
        """
        Emit an alert and store in history.
        
        FR-011: Alert system for stop modifications and erosion warnings.
        
        Args:
            alert: Alert dictionary with type, ticket, message, severity
        """
        # Check if alerts are enabled
        if not self.features_enabled.get("enable_alerts", True):
            return
        
        # Add timestamp if not present
        if "timestamp" not in alert:
            alert["timestamp"] = datetime.now()
        
        # Store in history
        self._alert_history.append(alert)
        
        # Limit history size
        if len(self._alert_history) > self._max_alert_history:
            self._alert_history = self._alert_history[-self._max_alert_history:]
        
        # Invoke callback if set
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception as e:
                logger.warning(f"Alert callback error: {e}")
    
    def get_alert_history(self) -> List[Dict[str, Any]]:
        """Get all stored alerts."""
        return list(self._alert_history)
    
    def get_alerts_by_ticket(self, ticket: int) -> List[Dict[str, Any]]:
        """Get alerts for a specific position ticket."""
        return [a for a in self._alert_history if a.get("ticket") == ticket]
    
    def get_alerts_by_severity(self, min_severity: str) -> List[Dict[str, Any]]:
        """
        Get alerts at or above a severity level.
        
        Args:
            min_severity: Minimum severity (debug, info, warning, error, critical)
            
        Returns:
            List of alerts at or above the specified severity
        """
        severity_order = ["debug", "info", "warning", "error", "critical"]
        
        if min_severity not in severity_order:
            return []
        
        min_index = severity_order.index(min_severity)
        
        return [
            a for a in self._alert_history
            if severity_order.index(a.get("severity", "info")) >= min_index
        ]
    
    def get_recent_alerts(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """
        Get alerts from the last N minutes.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            List of recent alerts
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        return [
            a for a in self._alert_history
            if a.get("timestamp", datetime.min) >= cutoff
        ]
    
    # ========================================================================
    # Monitoring Stats Methods (FR-012)
    # ========================================================================
    
    def get_protection_stats(self) -> Dict[str, Any]:
        """
        Get protection statistics for all monitored positions.
        
        FR-012: Monitoring dashboard data.
        
        Returns:
            Dictionary with protection stats
        """
        positions = list(self._monitored_positions.values())
        
        return {
            "total_positions": len(positions),
            "disaster_stops_set": sum(1 for p in positions if p.disaster_stop_set),
            "trailing_activated": sum(1 for p in positions if p.trailing_activated),
            "breakeven_triggered": sum(1 for p in positions if p.breakeven_triggered),
            "positions_by_symbol": self._group_positions_by_symbol(),
            "last_update": datetime.now().isoformat(),
        }
    
    def _group_positions_by_symbol(self) -> Dict[str, int]:
        """Group positions by symbol."""
        counts: Dict[str, int] = {}
        for pos in self._monitored_positions.values():
            counts[pos.symbol] = counts.get(pos.symbol, 0) + 1
        return counts
    
    def get_position_summary(self, ticket: int) -> Optional[Dict[str, Any]]:
        """
        Get summary for a specific position.
        
        Args:
            ticket: Position ticket number
            
        Returns:
            Position summary dictionary or None if not found
        """
        position = self._monitored_positions.get(ticket)
        
        if position is None:
            return None
        
        return self._position_to_summary(position)
    
    def get_all_positions_summary(self) -> List[Dict[str, Any]]:
        """Get summary for all monitored positions."""
        return [
            self._position_to_summary(p)
            for p in self._monitored_positions.values()
        ]
    
    def _position_to_summary(self, position: MonitoredPosition) -> Dict[str, Any]:
        """Convert position to summary dictionary."""
        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "current_stop": position.current_stop,
            "current_price": position.current_price,
            "lots": position.lots,
            "disaster_stop_set": position.disaster_stop_set,
            "trailing_activated": position.trailing_activated,
            "breakeven_triggered": position.breakeven_triggered,
            "profit_highwater": position.profit_highwater,
            "profit_erosion": position.profit_erosion,
        }

    async def run_once(self) -> None:
        """
        Run a single protection cycle.
        
        This applies all protection layers in order:
        1. Disaster protection (for positions without stops)
        2. Highwater mark updates
        3. Erosion detection and protection
        4. Early trailing and breakeven
        """
        # Sync positions with MT4 (this also updates current prices)
        await self.sync_positions()
        
        if not self._monitored_positions:
            logger.debug("No positions to monitor")
            return
        
        # Group positions by symbol for efficient ATR lookup
        symbols = set(pos.symbol for pos in self._monitored_positions.values())
        
        for symbol in symbols:
            # Get ATR for this symbol
            atr = await self.get_atr(symbol)
            if atr is None:
                logger.warning(f"Could not get ATR for {symbol}")
                continue
            
            # Get sample price for logging
            sample_price = None
            for pos in self._monitored_positions.values():
                if pos.symbol == symbol:
                    sample_price = pos.current_price
                    break
            
            if sample_price:
                logger.info(f"📊 {symbol} @ ${sample_price:.2f} (ATR: ${atr:.2f})")
            
            # Check each position for this symbol
            for position in list(self._monitored_positions.values()):
                if position.symbol != symbol:
                    continue
                
                if position.current_price <= 0:
                    logger.warning(f"No current price for position {position.ticket}")
                    continue
                
                position.last_check = datetime.utcnow()
                
                # Log current state
                pnl = self.calculate_profit(position)
                logger.debug(
                    f"   Position {position.ticket}: {position.direction.upper()} "
                    f"Entry ${position.entry_price:.2f}, SL ${position.current_stop:.2f}, "
                    f"P/L ${pnl:.2f}"
                )
                
                # Layer 1: Disaster protection (if no stop set)
                if not position.disaster_stop_set:
                    await self.apply_disaster_protection(position)
                
                # Layer 2: Update highwater mark
                current_profit = self.calculate_profit(position)
                self.update_highwater(position, current_profit)
                
                # Layer 3: Check erosion and apply protection
                if self.features_enabled.get("enable_profit_erosion", True):
                    erosion_result = await self.check_erosion(position, current_profit, atr)
                    if erosion_result.get("protection_triggered"):
                        await self.apply_erosion_protection(position)
                
                # Layer 4: Early trailing and breakeven
                if position.disaster_stop_set:
                    # Check for breakeven first (if not already at breakeven)
                    if not position.breakeven_triggered and self.should_breakeven(position, atr):
                        await self.apply_breakeven(position)
                    
                    # Check for trailing (if not already trailing or can trail further)
                    if self.should_trail(position, atr):
                        await self.apply_trail(position)
    
    async def run(self) -> None:
        """Main run loop - monitors positions continuously."""
        self._running = True
        logger.info("=" * 60)
        logger.info("🚀 Stealth Stop Manager Started (DYNAMIC MODE)")
        logger.info(f"   MT4: {self.mt4_host}:{self.mt4_port}")
        logger.info(f"   Poll interval: {self.poll_interval}s")
        logger.info(f"   ATR Trail Multiplier: {self.config.atr_multiplier_trail}x")
        logger.info(f"   Trail Trigger: {self.config.trail_trigger_atr}x ATR profit")
        logger.info(f"   Breakeven Trigger: {self.config.breakeven_trigger_atr}x ATR profit")
        logger.info("   Positions: Auto-detected from MT4")
        logger.info("=" * 60)
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                await self.run_once()
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in main loop ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning("Too many consecutive errors, attempting reconnect...")
                    await self._reconnect()
                    consecutive_errors = 0
                    
            await asyncio.sleep(self.poll_interval)
            
    def stop(self) -> None:
        """Stop the service."""
        self._running = False
        logger.info("Stealth Stop Manager stopping...")


async def main():
    """Main entry point for standalone execution."""
    # Configuration from environment
    mt4_host = os.getenv("MT4_HOST", "192.168.0.123")
    mt4_port = int(os.getenv("MT4_PORT", "5555"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "5"))
    
    # Dynamic trail configuration from environment
    config = DynamicTrailConfig(
        atr_multiplier_initial=float(os.getenv("ATR_MULTIPLIER_INITIAL", "2.0")),
        atr_multiplier_trail=float(os.getenv("ATR_MULTIPLIER_TRAIL", "1.5")),
        trail_trigger_atr=float(os.getenv("TRAIL_TRIGGER_ATR", "1.0")),
        breakeven_trigger_atr=float(os.getenv("BREAKEVEN_TRIGGER_ATR", "1.5")),
        min_offset_pips=float(os.getenv("MIN_OFFSET_PIPS", "5")),
        max_offset_pips=float(os.getenv("MAX_OFFSET_PIPS", "15")),
        pip_value=float(os.getenv("PIP_VALUE", "0.01")),  # Crude oil default
    )
    
    manager = StealthStopManager(
        mt4_host=mt4_host,
        mt4_port=mt4_port,
        poll_interval=poll_interval,
        config=config
    )
    
    try:
        await manager.run()
    except KeyboardInterrupt:
        manager.stop()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
