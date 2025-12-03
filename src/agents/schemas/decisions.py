"""
Decision schemas for agent decision-making.
Used by Decision Layer agents (Position Sizing, Stop Loss, Take Profit, Entry Timing).
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


class TradeDirection(str, Enum):
    """Trade direction enum."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"  # No trade signal


class OrderType(str, Enum):
    """Order type enum."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class ConfidenceLevel(str, Enum):
    """Confidence level categorization."""

    VERY_LOW = "very_low"  # 0.0-0.2
    LOW = "low"  # 0.2-0.4
    MEDIUM = "medium"  # 0.4-0.6
    HIGH = "high"  # 0.6-0.8
    VERY_HIGH = "very_high"  # 0.8-1.0


class TradeIntent(BaseModel):
    """
    Trade intent decision from signal generation and analysis.

    Represents the initial trading signal with direction, confidence,
    and reasoning before position sizing and risk management.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "timeframe": "H4",
                "direction": "long",
                "confidence": 0.75,
                "entry_price_estimate": 2650.50,
                "reasoning": "Bullish divergence on RSI with support at 2650",
                "supporting_indicators": ["rsi_divergence", "support_level"],
                "analyst_consensus": 0.67
            }
        }
    )

    # Trade identification
    symbol: str = Field(
        ...,
        description="Trading symbol (e.g., 'Gold', 'CrudeOIL')"
    )

    timeframe: str = Field(
        ...,
        description="Chart timeframe (e.g., 'H1', 'H4', 'D1')"
    )

    # Trade signal
    direction: TradeDirection = Field(
        ...,
        description="Trade direction: long, short, or neutral"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Signal confidence score (0.0-1.0)"
    )

    confidence_level: Optional[ConfidenceLevel] = Field(
        None,
        description="Confidence level category"
    )

    # Entry information
    entry_price_estimate: Optional[float] = Field(
        None,
        gt=0,
        description="Estimated entry price"
    )

    entry_timing_preference: Optional[str] = Field(
        None,
        description="Entry timing preference (e.g., 'immediate', 'on_pullback', 'breakout')"
    )

    # Supporting analysis
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Agent's reasoning for this trade intent"
    )

    supporting_indicators: list[str] = Field(
        default_factory=list,
        description="List of indicators supporting this signal"
    )

    analyst_consensus: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Consensus score from analyst agents (0.0-1.0)"
    )

    # Metadata
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when intent was generated"
    )

    expires_at: Optional[datetime] = Field(
        None,
        description="Expiration timestamp for this signal"
    )

    @field_validator('confidence_level', mode='before')
    @classmethod
    def set_confidence_level(cls, v, info):
        """Auto-set confidence level based on confidence score."""
        if v is not None:
            return v

        confidence = info.data.get('confidence')
        if confidence is None:
            return None

        if confidence < 0.2:
            return ConfidenceLevel.VERY_LOW
        elif confidence < 0.4:
            return ConfidenceLevel.LOW
        elif confidence < 0.6:
            return ConfidenceLevel.MEDIUM
        elif confidence < 0.8:
            return ConfidenceLevel.HIGH
        else:
            return ConfidenceLevel.VERY_HIGH


class PositionSize(BaseModel):
    """
    Position sizing decision from Position Sizing Agent.

    Determines optimal position size based on risk parameters,
    account balance, and confidence level.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "position_size_lots": 0.75,
                "position_size_units": 75,
                "risk_amount_usd": 1000.0,
                "risk_percentage": 1.0,
                "reasoning": "1% risk with 2:1 reward ratio"
            }
        }
    )

    # Position details
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    position_size_lots: float = Field(
        ...,
        gt=0,
        description="Position size in lots (e.g., 0.1, 0.5, 1.0)"
    )

    position_size_units: Optional[int] = Field(
        None,
        gt=0,
        description="Position size in units (contracts/shares)"
    )

    # Risk calculation
    risk_amount_usd: float = Field(
        ...,
        gt=0,
        description="Risk amount in USD for this trade"
    )

    risk_percentage: float = Field(
        ...,
        gt=0,
        le=100,
        description="Risk as percentage of account balance"
    )

    account_balance_usd: Optional[float] = Field(
        None,
        gt=0,
        description="Account balance at time of calculation"
    )

    # Reward calculation
    expected_reward_usd: Optional[float] = Field(
        None,
        description="Expected reward in USD"
    )

    reward_risk_ratio: Optional[float] = Field(
        None,
        ge=0,
        description="Reward-to-risk ratio (e.g., 2.0 for 2:1)"
    )

    # Reasoning
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Agent's reasoning for this position size"
    )

    # Metadata
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when calculated"
    )

    model_version: Optional[str] = Field(
        None,
        description="RL model version if RL-enabled"
    )


class StopLoss(BaseModel):
    """
    Stop loss decision from Stop Loss Agent.

    Determines optimal stop loss placement based on technical levels,
    volatility, and risk tolerance.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "stop_loss_price": 2640.00,
                "stop_loss_type": "stop",
                "distance_pips": 105,
                "reasoning": "Below recent swing low with ATR buffer"
            }
        }
    )

    # Stop loss details
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    stop_loss_price: float = Field(
        ...,
        gt=0,
        description="Stop loss price level"
    )

    stop_loss_type: OrderType = Field(
        default=OrderType.STOP,
        description="Stop order type"
    )

    # Distance metrics
    distance_pips: Optional[float] = Field(
        None,
        gt=0,
        description="Distance from entry in pips"
    )

    distance_percentage: Optional[float] = Field(
        None,
        gt=0,
        description="Distance from entry as percentage"
    )

    # Supporting analysis
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Agent's reasoning for this stop loss level"
    )

    technical_level: Optional[str] = Field(
        None,
        description="Technical level used (e.g., 'swing_low', 'support', 'atr_multiple')"
    )

    volatility_adjustment: Optional[float] = Field(
        None,
        description="ATR or volatility adjustment applied"
    )

    # Metadata
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when calculated"
    )

    should_trail: bool = Field(
        default=False,
        description="Whether stop loss should trail price"
    )

    trailing_distance_pips: Optional[float] = Field(
        None,
        gt=0,
        description="Trailing distance in pips if should_trail=True"
    )


class TakeProfit(BaseModel):
    """
    Take profit decision from Take Profit Agent.

    Determines optimal profit target(s) based on technical levels,
    risk-reward ratio, and market structure.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "take_profit_price": 2680.00,
                "take_profit_type": "limit",
                "distance_pips": 295,
                "reward_risk_ratio": 2.81,
                "reasoning": "Target at resistance with 2.8:1 RR"
            }
        }
    )

    # Take profit details
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    take_profit_price: float = Field(
        ...,
        gt=0,
        description="Take profit price level"
    )

    take_profit_type: OrderType = Field(
        default=OrderType.LIMIT,
        description="Take profit order type"
    )

    # Distance metrics
    distance_pips: Optional[float] = Field(
        None,
        gt=0,
        description="Distance from entry in pips"
    )

    distance_percentage: Optional[float] = Field(
        None,
        gt=0,
        description="Distance from entry as percentage"
    )

    reward_risk_ratio: Optional[float] = Field(
        None,
        gt=0,
        description="Reward-to-risk ratio achieved"
    )

    # Multiple targets support
    partial_close_percentage: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Percentage of position to close at this level (for partial profits)"
    )

    is_final_target: bool = Field(
        default=True,
        description="Whether this is the final take profit target"
    )

    # Supporting analysis
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Agent's reasoning for this take profit level"
    )

    technical_level: Optional[str] = Field(
        None,
        description="Technical level used (e.g., 'resistance', 'fibonacci', 'measured_move')"
    )

    # Metadata
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when calculated"
    )


class EntryTiming(BaseModel):
    """
    Entry timing decision from Entry Timing Agent.

    Determines optimal entry timing and conditions for trade execution.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "entry_action": "execute_now",
                "entry_price_target": 2650.50,
                "entry_conditions_met": True,
                "reasoning": "Pullback to support complete, momentum turning bullish"
            }
        }
    )

    # Timing decision
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    entry_action: str = Field(
        ...,
        description="Entry action: execute_now, wait_for_pullback, wait_for_breakout, cancel"
    )

    entry_price_target: Optional[float] = Field(
        None,
        gt=0,
        description="Target entry price if waiting"
    )

    entry_order_type: OrderType = Field(
        default=OrderType.MARKET,
        description="Recommended order type"
    )

    # Conditions
    entry_conditions_met: bool = Field(
        ...,
        description="Whether all entry conditions are satisfied"
    )

    pending_conditions: list[str] = Field(
        default_factory=list,
        description="List of conditions not yet met"
    )

    # Timing window
    execute_before: Optional[datetime] = Field(
        None,
        description="Execute before this timestamp (signal expiration)"
    )

    patience_score: Optional[float] = Field(
        None,
        ge=0,
        le=1.0,
        description="Patience score: 0=execute now, 1=wait for optimal setup"
    )

    # Reasoning
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Agent's reasoning for this timing decision"
    )

    # Metadata
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when calculated"
    )
