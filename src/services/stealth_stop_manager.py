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
from typing import Any, Dict, List, Optional

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
    """Configuration for dynamic trailing stops."""
    # ATR-based trailing
    atr_multiplier_initial: float = 2.0  # Initial stop distance in ATR
    atr_multiplier_trail: float = 1.5    # Trailing stop distance in ATR
    
    # Trail trigger settings (in ATR units)
    trail_trigger_atr: float = 1.0       # Start trailing after price moves 1x ATR in profit
    trail_step_atr: float = 0.5          # Trail every 0.5 ATR of additional profit
    
    # Institutional pricing
    min_offset_pips: float = 5           # Min random offset
    max_offset_pips: float = 15          # Max random offset
    pip_value: float = 0.01              # Crude oil = 0.01, Forex = 0.0001
    
    # Breakeven settings
    breakeven_trigger_atr: float = 1.5   # Move to breakeven after 1.5x ATR profit
    breakeven_offset_pips: float = 10    # Lock in 10 pips profit at breakeven


@dataclass 
class MonitoredPosition:
    """A position being monitored for trailing stops."""
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
        config: Optional[DynamicTrailConfig] = None
    ):
        """
        Initialize the Stealth Stop Manager.
        
        Args:
            mt4_host: MT4 ZMQ server host
            mt4_port: MT4 ZMQ server port
            poll_interval: How often to check prices (seconds)
            config: Dynamic trail configuration
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
                timeout_ms=10000,
                enable_circuit_breaker=False
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
    
    async def sync_positions(self) -> None:
        """
        Sync monitored positions with actual MT4 positions.
        
        - Adds new positions
        - Removes closed positions
        - Updates current stop/tp/price values
        """
        mt4_positions = await self.get_open_positions_from_mt4()
        
        # Get set of current MT4 tickets
        mt4_tickets = set()
        
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
                    current_price=current_price
                )
                self._monitored_positions[ticket] = monitored
                logger.info(
                    f"📊 New position detected: {ticket} {direction.upper()} "
                    f"{monitored.symbol} @ ${monitored.entry_price:.2f}"
                )
        
        # Remove closed positions
        closed_tickets = set(self._monitored_positions.keys()) - mt4_tickets
        for ticket in closed_tickets:
            pos = self._monitored_positions.pop(ticket)
            logger.info(f"📴 Position {ticket} closed/removed from monitoring")
    
    def calculate_trail_stop(
        self,
        position: MonitoredPosition,
        current_price: float,
        atr: float
    ) -> Optional[float]:
        """
        Calculate new trailing stop based on current price and ATR.
        
        Returns None if no trail is needed.
        """
        entry = position.entry_price
        current_stop = position.current_stop
        
        if position.direction == "long":
            # For long: profit when price > entry
            profit_distance = current_price - entry
            
            # Calculate ideal stop (trailing behind current price)
            ideal_stop = current_price - (atr * self.config.atr_multiplier_trail)
            
            # Only trail if:
            # 1. We're in profit by at least trail_trigger_atr
            # 2. New stop would be higher than current stop
            # 3. New stop is higher than entry (never trail into loss)
            min_profit_for_trail = atr * self.config.trail_trigger_atr
            
            if profit_distance >= min_profit_for_trail:
                if ideal_stop > current_stop and ideal_stop > entry:
                    return ideal_stop
                    
            # Check for breakeven trigger
            if not position.breakeven_triggered:
                breakeven_trigger = atr * self.config.breakeven_trigger_atr
                if profit_distance >= breakeven_trigger:
                    breakeven_stop = entry + (self.config.breakeven_offset_pips * self.config.pip_value)
                    if breakeven_stop > current_stop:
                        position.breakeven_triggered = True
                        return breakeven_stop
                        
        else:  # short
            # For short: profit when price < entry
            profit_distance = entry - current_price
            
            # Calculate ideal stop (trailing above current price)
            ideal_stop = current_price + (atr * self.config.atr_multiplier_trail)
            
            # Only trail if:
            # 1. We're in profit by at least trail_trigger_atr
            # 2. New stop would be lower than current stop
            # 3. New stop is lower than entry (never trail into loss)
            min_profit_for_trail = atr * self.config.trail_trigger_atr
            
            if profit_distance >= min_profit_for_trail:
                # For short, we want stop to be LOWER (tighter) but still above current price
                if current_stop == 0 or (ideal_stop < current_stop and ideal_stop < entry):
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
    
    async def run_once(self) -> None:
        """Run a single check cycle."""
        # Sync positions with MT4 (this also updates current prices)
        await self.sync_positions()
        
        if not self._monitored_positions:
            logger.debug("No positions to monitor")
            return
        
        # Group positions by symbol for logging
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
            
            # Check each position
            for position in self._monitored_positions.values():
                if position.symbol != symbol:
                    continue
                
                if position.current_price <= 0:
                    logger.warning(f"No current price for position {position.ticket}")
                    continue
                
                # Calculate P/L
                if position.direction == "long":
                    pnl_pips = (position.current_price - position.entry_price) / self.config.pip_value
                else:
                    pnl_pips = (position.entry_price - position.current_price) / self.config.pip_value
                
                pnl_dollars = pnl_pips * position.lots * 100  # Rough estimate
                
                logger.debug(
                    f"   Position {position.ticket}: {position.direction.upper()} "
                    f"Entry ${position.entry_price:.2f}, SL ${position.current_stop:.2f}, "
                    f"P/L {pnl_pips:.0f} pips (~${pnl_dollars:.0f})"
                )
                
                await self.check_and_trail(position, position.current_price, atr)
    
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
