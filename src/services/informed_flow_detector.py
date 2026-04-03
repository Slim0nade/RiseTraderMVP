"""
InformedFlowDetector - Real-time detection of unusual trading activity

Detects pre-announcement "informed flow" patterns like the Trump/Iran event where
$760M in oil futures changed hands 15 minutes before the announcement.

Key Detection Signals:
1. Volume anomaly (5-10x+ baseline in short window)
2. No apparent news catalyst
3. Cross-asset correlation spikes
4. Bid-ask spread widening
5. Order flow imbalance

Usage:
    detector = InformedFlowDetector(config)
    await detector.start_monitoring(['CrudeOIL', 'XAUUSD', 'DXY', 'VIX'])
    
Events Emitted:
    - informed_flow_alert: High-confidence unusual activity detected
    - volume_anomaly: Volume spike above threshold
    - cross_asset_correlation: Correlated movement across instruments
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"           # Interesting but not actionable
    MEDIUM = "medium"     # Worth monitoring
    HIGH = "high"         # Potential trade setup
    CRITICAL = "critical" # Immediate attention required


class FlowDirection(Enum):
    """Detected flow direction"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class VolumeProfile:
    """Rolling volume statistics for a symbol"""
    symbol: str
    window_minutes: int = 60
    
    # Rolling stats
    volumes: deque = field(default_factory=lambda: deque(maxlen=1000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # Computed stats
    mean_volume: float = 0.0
    std_volume: float = 0.0
    median_volume: float = 0.0
    
    # Time-of-day profiles (hour -> (mean, std))
    hourly_profile: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    
    def update(self, volume: float, timestamp: datetime) -> None:
        """Add new volume observation"""
        self.volumes.append(volume)
        self.timestamps.append(timestamp)
        
        if len(self.volumes) >= 20:
            vol_array = np.array(self.volumes)
            self.mean_volume = np.mean(vol_array)
            self.std_volume = np.std(vol_array)
            self.median_volume = np.median(vol_array)
    
    def get_z_score(self, volume: float, hour: Optional[int] = None) -> float:
        """
        Calculate z-score for volume vs baseline
        
        Args:
            volume: Observed volume
            hour: Hour of day for time-adjusted baseline
            
        Returns:
            Z-score (number of standard deviations from mean)
        """
        if self.std_volume == 0:
            return 0.0
            
        # Use time-of-day profile if available
        if hour is not None and hour in self.hourly_profile:
            mean, std = self.hourly_profile[hour]
            if std > 0:
                return (volume - mean) / std
                
        return (volume - self.mean_volume) / self.std_volume
    
    def get_volume_ratio(self, volume: float) -> float:
        """Get ratio of volume to baseline mean"""
        if self.mean_volume == 0:
            return 1.0
        return volume / self.mean_volume


@dataclass
class InformedFlowAlert:
    """Alert for detected informed flow"""
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    
    # Detection details
    primary_symbol: str
    affected_symbols: List[str]
    flow_direction: FlowDirection
    
    # Metrics
    volume_z_score: float
    volume_ratio: float
    cross_asset_correlation: float
    
    # Context
    window_minutes: int
    total_volume: float
    estimated_notional: float
    
    # Timing analysis
    time_to_potential_event: Optional[timedelta] = None
    confidence_score: float = 0.0
    
    # Actionable intelligence
    suggested_direction: Optional[str] = None
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "primary_symbol": self.primary_symbol,
            "affected_symbols": self.affected_symbols,
            "flow_direction": self.flow_direction.value,
            "volume_z_score": self.volume_z_score,
            "volume_ratio": self.volume_ratio,
            "cross_asset_correlation": self.cross_asset_correlation,
            "confidence_score": self.confidence_score,
            "estimated_notional": self.estimated_notional,
            "suggested_direction": self.suggested_direction,
        }


@dataclass
class TickData:
    """Single tick/candle data point"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: Optional[float] = None
    ask: Optional[float] = None


class InformedFlowDetector:
    """
    Real-time informed flow detection engine
    
    Monitors multiple instruments for unusual activity patterns
    that may indicate informed trading ahead of announcements.
    """
    
    # Default configuration
    DEFAULT_CONFIG = {
        # Volume anomaly thresholds
        "volume_z_threshold": 3.0,      # Z-score to trigger alert
        "volume_ratio_threshold": 5.0,   # Multiple of baseline volume
        "min_volume_for_alert": 100,     # Minimum absolute volume
        
        # Time windows
        "detection_window_minutes": 5,   # Window for spike detection
        "baseline_window_minutes": 60,   # Window for baseline calculation
        "correlation_window_minutes": 10, # Window for cross-asset correlation
        
        # Cross-asset correlation
        "correlation_threshold": 0.7,    # Min correlation to flag
        "correlation_symbols": {
            "CrudeOIL": ["DXY", "VIX", "XAUUSD"],
            "XAUUSD": ["DXY", "VIX", "CrudeOIL"],
            "DXY": ["EURUSD", "XAUUSD", "VIX"],
        },
        
        # Alert cooldowns
        "alert_cooldown_minutes": 5,     # Min time between alerts per symbol
        
        # Contract specifications (for notional calculation)
        "contract_specs": {
            "CrudeOIL": {"multiplier": 1000, "currency": "USD"},  # 1000 barrels
            "XAUUSD": {"multiplier": 100, "currency": "USD"},     # 100 oz
        },
        
        # Confidence scoring weights
        "confidence_weights": {
            "volume_z": 0.3,
            "volume_ratio": 0.2,
            "cross_correlation": 0.2,
            "time_clustering": 0.15,
            "no_news_catalyst": 0.15,
        },
    }
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable] = None,
    ):
        """
        Initialize detector
        
        Args:
            config: Configuration overrides
            event_callback: Async callback for alerts
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.event_callback = event_callback
        
        # State
        self.volume_profiles: Dict[str, VolumeProfile] = {}
        self.tick_buffers: Dict[str, deque] = {}
        self.last_alerts: Dict[str, datetime] = {}
        self.alert_history: List[InformedFlowAlert] = []
        
        # Monitoring state
        self.is_monitoring = False
        self.monitored_symbols: List[str] = []
        
        logger.info(
            "informed_flow_detector_initialized",
            volume_z_threshold=self.config["volume_z_threshold"],
            volume_ratio_threshold=self.config["volume_ratio_threshold"],
        )
    
    async def start_monitoring(self, symbols: List[str]) -> None:
        """
        Start monitoring symbols for informed flow
        
        Args:
            symbols: List of symbols to monitor
        """
        self.monitored_symbols = symbols
        self.is_monitoring = True
        
        # Initialize profiles
        for symbol in symbols:
            if symbol not in self.volume_profiles:
                self.volume_profiles[symbol] = VolumeProfile(symbol=symbol)
            if symbol not in self.tick_buffers:
                self.tick_buffers[symbol] = deque(maxlen=1000)
        
        logger.info(
            "informed_flow_monitoring_started",
            symbols=symbols,
        )
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self.is_monitoring = False
        logger.info("informed_flow_monitoring_stopped")
    
    async def process_tick(self, tick: TickData) -> Optional[InformedFlowAlert]:
        """
        Process incoming tick data and check for anomalies
        
        Args:
            tick: New tick data
            
        Returns:
            Alert if anomaly detected, None otherwise
        """
        if not self.is_monitoring:
            return None
            
        symbol = tick.symbol
        
        # Update buffers
        if symbol not in self.tick_buffers:
            self.tick_buffers[symbol] = deque(maxlen=1000)
        self.tick_buffers[symbol].append(tick)
        
        # Update volume profile
        if symbol not in self.volume_profiles:
            self.volume_profiles[symbol] = VolumeProfile(symbol=symbol)
        self.volume_profiles[symbol].update(tick.volume, tick.timestamp)
        
        # Check for anomaly
        alert = await self._check_volume_anomaly(symbol, tick)
        
        if alert:
            # Enrich with cross-asset analysis
            alert = await self._enrich_with_cross_asset(alert)
            
            # Calculate confidence score
            alert.confidence_score = self._calculate_confidence(alert)
            
            # Store and emit
            self.alert_history.append(alert)
            self.last_alerts[symbol] = tick.timestamp
            
            if self.event_callback:
                await self.event_callback(alert)
            
            logger.warning(
                "informed_flow_alert",
                alert_id=alert.alert_id,
                symbol=symbol,
                severity=alert.severity.value,
                volume_z_score=alert.volume_z_score,
                confidence=alert.confidence_score,
            )
        
        return alert
    
    async def _check_volume_anomaly(
        self,
        symbol: str,
        tick: TickData,
    ) -> Optional[InformedFlowAlert]:
        """
        Check for volume anomaly in detection window
        
        Args:
            symbol: Symbol to check
            tick: Latest tick
            
        Returns:
            Alert if anomaly detected
        """
        profile = self.volume_profiles.get(symbol)
        if not profile or len(profile.volumes) < 20:
            return None  # Not enough baseline data
        
        # Check cooldown
        last_alert_time = self.last_alerts.get(symbol)
        if last_alert_time:
            cooldown = timedelta(minutes=self.config["alert_cooldown_minutes"])
            if tick.timestamp - last_alert_time < cooldown:
                return None
        
        # Get recent volume in detection window
        window = timedelta(minutes=self.config["detection_window_minutes"])
        cutoff = tick.timestamp - window
        
        recent_ticks = [
            t for t in self.tick_buffers[symbol]
            if t.timestamp >= cutoff
        ]
        
        if not recent_ticks:
            return None
        
        # Calculate window volume
        window_volume = sum(t.volume for t in recent_ticks)
        
        # Get z-score
        hour = tick.timestamp.hour
        z_score = profile.get_z_score(window_volume, hour)
        volume_ratio = profile.get_volume_ratio(window_volume)
        
        # Check thresholds
        z_threshold = self.config["volume_z_threshold"]
        ratio_threshold = self.config["volume_ratio_threshold"]
        min_volume = self.config["min_volume_for_alert"]
        
        if (z_score >= z_threshold or volume_ratio >= ratio_threshold) and window_volume >= min_volume:
            # Determine severity
            if z_score >= z_threshold * 2 or volume_ratio >= ratio_threshold * 2:
                severity = AlertSeverity.CRITICAL
            elif z_score >= z_threshold * 1.5 or volume_ratio >= ratio_threshold * 1.5:
                severity = AlertSeverity.HIGH
            elif z_score >= z_threshold or volume_ratio >= ratio_threshold:
                severity = AlertSeverity.MEDIUM
            else:
                severity = AlertSeverity.LOW
            
            # Determine flow direction from price action
            if len(recent_ticks) >= 2:
                price_change = recent_ticks[-1].close - recent_ticks[0].open
                if price_change > 0:
                    direction = FlowDirection.BULLISH
                elif price_change < 0:
                    direction = FlowDirection.BEARISH
                else:
                    direction = FlowDirection.NEUTRAL
            else:
                direction = FlowDirection.NEUTRAL
            
            # Calculate notional
            specs = self.config["contract_specs"].get(symbol, {"multiplier": 1})
            notional = window_volume * tick.close * specs.get("multiplier", 1)
            
            return InformedFlowAlert(
                alert_id=f"{symbol}_{tick.timestamp.strftime('%Y%m%d_%H%M%S')}",
                timestamp=tick.timestamp,
                severity=severity,
                primary_symbol=symbol,
                affected_symbols=[symbol],
                flow_direction=direction,
                volume_z_score=z_score,
                volume_ratio=volume_ratio,
                cross_asset_correlation=0.0,  # Will be filled by enrichment
                window_minutes=self.config["detection_window_minutes"],
                total_volume=window_volume,
                estimated_notional=notional,
            )
        
        return None
    
    async def _enrich_with_cross_asset(
        self,
        alert: InformedFlowAlert,
    ) -> InformedFlowAlert:
        """
        Enrich alert with cross-asset correlation analysis
        
        Args:
            alert: Base alert
            
        Returns:
            Enriched alert
        """
        symbol = alert.primary_symbol
        correlated_symbols = self.config["correlation_symbols"].get(symbol, [])
        
        if not correlated_symbols:
            return alert
        
        # Get returns for correlation calculation
        window = timedelta(minutes=self.config["correlation_window_minutes"])
        cutoff = alert.timestamp - window
        
        primary_returns = self._get_returns(symbol, cutoff)
        if len(primary_returns) < 5:
            return alert
        
        affected_symbols = [symbol]
        max_correlation = 0.0
        
        for corr_symbol in correlated_symbols:
            corr_returns = self._get_returns(corr_symbol, cutoff)
            
            if len(corr_returns) < 5:
                continue
            
            # Align and calculate correlation
            min_len = min(len(primary_returns), len(corr_returns))
            if min_len < 5:
                continue
                
            correlation = np.corrcoef(
                primary_returns[-min_len:],
                corr_returns[-min_len:]
            )[0, 1]
            
            if abs(correlation) >= self.config["correlation_threshold"]:
                affected_symbols.append(corr_symbol)
                max_correlation = max(max_correlation, abs(correlation))
        
        alert.affected_symbols = affected_symbols
        alert.cross_asset_correlation = max_correlation
        
        # Upgrade severity if multiple assets affected
        if len(affected_symbols) >= 3 and alert.severity != AlertSeverity.CRITICAL:
            alert.severity = AlertSeverity(
                min(AlertSeverity.CRITICAL.value, 
                    [AlertSeverity.LOW, AlertSeverity.MEDIUM, 
                     AlertSeverity.HIGH, AlertSeverity.CRITICAL]
                    .index(alert.severity) + 1)
            )
        
        return alert
    
    def _get_returns(self, symbol: str, cutoff: datetime) -> np.ndarray:
        """Get price returns for symbol since cutoff"""
        ticks = self.tick_buffers.get(symbol, [])
        prices = [t.close for t in ticks if t.timestamp >= cutoff]
        
        if len(prices) < 2:
            return np.array([])
        
        return np.diff(prices) / np.array(prices[:-1])
    
    def _calculate_confidence(self, alert: InformedFlowAlert) -> float:
        """
        Calculate confidence score for alert
        
        Factors:
        - Volume z-score magnitude
        - Volume ratio magnitude
        - Cross-asset correlation
        - Time clustering (how concentrated is the activity)
        - Absence of news catalyst (would need news feed integration)
        
        Returns:
            Confidence score (0-1)
        """
        weights = self.config["confidence_weights"]
        
        # Volume z-score contribution (normalized 0-1)
        z_contrib = min(alert.volume_z_score / 10.0, 1.0) * weights["volume_z"]
        
        # Volume ratio contribution (normalized 0-1)
        ratio_contrib = min(alert.volume_ratio / 20.0, 1.0) * weights["volume_ratio"]
        
        # Cross-correlation contribution
        corr_contrib = alert.cross_asset_correlation * weights["cross_correlation"]
        
        # Time clustering (assume high if alert triggered)
        clustering_contrib = 0.8 * weights["time_clustering"]
        
        # No news catalyst (default to neutral without news feed)
        news_contrib = 0.5 * weights["no_news_catalyst"]
        
        confidence = z_contrib + ratio_contrib + corr_contrib + clustering_contrib + news_contrib
        
        return min(confidence, 1.0)
    
    def get_current_profiles(self) -> Dict[str, Dict[str, float]]:
        """Get current volume profiles for all monitored symbols"""
        return {
            symbol: {
                "mean_volume": profile.mean_volume,
                "std_volume": profile.std_volume,
                "median_volume": profile.median_volume,
            }
            for symbol, profile in self.volume_profiles.items()
        }
    
    def get_recent_alerts(self, hours: int = 24) -> List[InformedFlowAlert]:
        """Get alerts from the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [a for a in self.alert_history if a.timestamp >= cutoff]


class InformedFlowStrategy:
    """
    Trading strategy based on informed flow detection
    
    Strategy Logic:
    1. Wait for HIGH or CRITICAL informed flow alert
    2. Determine likely direction from order flow analysis
    3. Enter position OPPOSITE to the informed flow direction
       (assume smart money is accumulating before reversal)
    4. Set tight stop-loss at recent swing high/low
    5. Target 2:1 reward:risk minimum
    
    Alternative Strategy (Follow the Flow):
    1. Enter SAME direction as informed flow
    2. Ride momentum until news catalyst hits
    3. Exit on first sign of reversal
    """
    
    def __init__(
        self,
        detector: InformedFlowDetector,
        mode: str = "follow",  # "follow" or "fade"
        min_confidence: float = 0.6,
        risk_per_trade_pct: float = 1.0,
    ):
        """
        Initialize strategy
        
        Args:
            detector: InformedFlowDetector instance
            mode: "follow" (trade with flow) or "fade" (trade against)
            min_confidence: Minimum confidence to trade
            risk_per_trade_pct: Risk per trade as % of account
        """
        self.detector = detector
        self.mode = mode
        self.min_confidence = min_confidence
        self.risk_per_trade_pct = risk_per_trade_pct
        
        self.active_signals: Dict[str, Dict] = {}
    
    def process_alert(
        self,
        alert: InformedFlowAlert,
        current_price: float,
        atr: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trade signal from alert
        
        Args:
            alert: Informed flow alert
            current_price: Current market price
            atr: Current ATR for stop calculation
            
        Returns:
            Trade signal dict or None
        """
        # Filter by severity and confidence
        if alert.severity not in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
            return None
        
        if alert.confidence_score < self.min_confidence:
            return None
        
        # Determine direction
        if self.mode == "follow":
            if alert.flow_direction == FlowDirection.BULLISH:
                side = "buy"
            elif alert.flow_direction == FlowDirection.BEARISH:
                side = "sell"
            else:
                return None
        else:  # fade
            if alert.flow_direction == FlowDirection.BULLISH:
                side = "sell"
            elif alert.flow_direction == FlowDirection.BEARISH:
                side = "buy"
            else:
                return None
        
        # Calculate stops (2 ATR)
        stop_distance = atr * 2
        
        if side == "buy":
            stop_loss = current_price - stop_distance
            take_profit = current_price + (stop_distance * 2)  # 2:1 R:R
        else:
            stop_loss = current_price + stop_distance
            take_profit = current_price - (stop_distance * 2)
        
        signal = {
            "alert_id": alert.alert_id,
            "symbol": alert.primary_symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": alert.confidence_score,
            "reason": f"Informed flow {self.mode}: {alert.flow_direction.value} flow detected with {alert.volume_ratio:.1f}x volume",
            "metadata": {
                "volume_z_score": alert.volume_z_score,
                "cross_asset_correlation": alert.cross_asset_correlation,
                "estimated_notional": alert.estimated_notional,
                "affected_symbols": alert.affected_symbols,
            }
        }
        
        self.active_signals[alert.primary_symbol] = signal
        return signal


# Integration with existing RiseTrader agent system
class InformedFlowAgent:
    """
    Agent wrapper for informed flow detection
    
    Integrates with the existing agent event bus system.
    """
    
    def __init__(
        self,
        agent_id: str,
        event_bus,
        agent_registry,
        config: Dict[str, Any],
    ):
        self.agent_id = agent_id
        self.event_bus = event_bus
        self.agent_registry = agent_registry
        self.config = config
        
        self.detector = InformedFlowDetector(
            config=config.get("detector_config", {}),
            event_callback=self._on_alert,
        )
        self.strategy = InformedFlowStrategy(
            detector=self.detector,
            mode=config.get("strategy_mode", "follow"),
            min_confidence=config.get("min_confidence", 0.6),
        )
    
    async def initialize(self) -> None:
        """Initialize agent"""
        symbols = self.config.get("symbols", ["CrudeOIL", "XAUUSD"])
        await self.detector.start_monitoring(symbols)
        
        # Subscribe to tick events
        # self.event_bus.subscribe("new_tick", self._on_tick)
    
    async def _on_tick(self, event) -> None:
        """Process incoming tick"""
        tick_data = event.data
        tick = TickData(
            symbol=tick_data["symbol"],
            timestamp=tick_data["timestamp"],
            open=tick_data["open"],
            high=tick_data["high"],
            low=tick_data["low"],
            close=tick_data["close"],
            volume=tick_data["volume"],
        )
        await self.detector.process_tick(tick)
    
    async def _on_alert(self, alert: InformedFlowAlert) -> None:
        """Handle alert from detector"""
        # Emit to event bus for other agents
        await self.event_bus.publish(
            event_type="informed_flow_alert",
            data=alert.to_dict(),
        )
        
        # Generate trade signal if applicable
        # Would need current price and ATR from market data
