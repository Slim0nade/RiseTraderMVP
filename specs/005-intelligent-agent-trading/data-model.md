# Data Model: Intelligent Multi-Agent Trading System

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Created**: 2025-12-01 | **Phase**: Phase 1 - Design & Contracts

## Overview

This document defines the data entities, relationships, and validation rules for Feature 005. All entities are extracted from functional requirements in spec.md and mapped to database models, Pydantic schemas, and agent communication protocols.

**Storage Strategy**:
- **PostgreSQL**: Persistent entities (decision logs, training runs, configurations, allocations)
- **Redis**: Transient state (agent state, cached forecasts, pub/sub events)
- **MLflow**: RL model checkpoints and experiment metadata

## Entity Catalog

| Entity | Source FR | Storage | Lifecycle |
|--------|-----------|---------|-----------|
| Agent | FR-004, FR-005, FR-006, FR-007 | PostgreSQL + Redis | Long-lived (configuration) + Ephemeral (runtime state) |
| Trade Intent | FR-004 | PostgreSQL (audit) + Redis (event) | Created → Validated → Archived |
| Position Size | FR-005 | PostgreSQL (audit) + Redis (event) | Created → Approved → Executed |
| Stop Loss | FR-006 | PostgreSQL (audit) + Redis (event) | Created → Set → Adjusted → Closed |
| Take Profit | FR-007 | PostgreSQL (audit) + Redis (event) | Created → Set → Hit/Adjusted → Closed |
| Analyst Report | FR-001, FR-002, FR-003 | Redis (cache 5min) | Generated → Consumed → Expired |
| Debate Outcome | FR-008 | PostgreSQL (audit) | Created → Consumed → Archived |
| Decision Log | FR-004 through FR-011 | PostgreSQL (TimescaleDB) | Logged → Analyzed → Retained (90d) |
| RL Training Run | FR-012, FR-013, FR-014 | PostgreSQL + MLflow | Started → Completed/Failed → Archived |
| Model Configuration | FR-015, FR-016 | PostgreSQL | Created → Active → Deprecated |
| Portfolio Allocation | FR-018 | PostgreSQL | Created → Active → Adjusted |
| MCP Tool | FR-019 | PostgreSQL (registry) | Registered → Active → Versioned |
| Strategy Team | FR-018 | PostgreSQL | Created → Active → Modified |

## Core Entities

### 1. Agent

**Purpose**: Represents a single intelligent agent instance (e.g., Technical Analyst for Gold, Position Sizing for Crude Oil)

**Source**: FR-004 (Trade Decision), FR-005 (Position Sizing), FR-006 (Stop Loss), FR-007 (Take Profit)

**Schema**:
```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime
from uuid import UUID

class AgentConfig(BaseModel):
    """Agent configuration (PostgreSQL)"""
    agent_id: UUID = Field(default_factory=uuid4)
    agent_type: Literal[
        "technical_analyst", "fundamental_analyst", "sentiment_analyst",
        "bull_researcher", "bear_researcher",
        "trade_decision", "position_sizing", "stop_loss", "take_profit",
        "execution", "position_monitor", "risk_overseer",
        "portfolio_allocator"
    ]
    symbol: str | None = Field(None, description="Instrument symbol if agent is instrument-specific")
    strategy_team_id: UUID | None = Field(None, description="Strategy team this agent belongs to")

    # LLM Configuration (FR-021)
    llm_tier: Literal["quick_think", "deep_think"] = Field(
        default="quick_think",
        description="LLM tier for cost optimization"
    )
    llm_model: str = Field(
        default="ollama/qwen2.5:14b",
        description="Specific model identifier"
    )

    # Risk Limits
    max_position_size_pct: float = Field(default=2.0, ge=0.1, le=10.0)
    max_stop_distance_pct: float = Field(default=5.0, ge=0.5, le=20.0)

    # RL Configuration (FR-012)
    rl_enabled: bool = Field(default=False, description="Whether RL is enabled for this agent")
    rl_model_path: str | None = Field(None, description="Path to trained RL model checkpoint")
    rl_algorithm: Literal["ppo", "sac"] | None = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    is_active: bool = Field(default=True)

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "agent_type": "position_sizing",
                "symbol": "CrudeOIL",
                "strategy_team_id": "987fcdeb-51a2-43f8-b912-123456789abc",
                "llm_tier": "deep_think",
                "llm_model": "ollama/deepseek-r1:14b",
                "max_position_size_pct": 3.0,
                "rl_enabled": True,
                "rl_model_path": "mlflow://models/position_sizing_sac_crude/Production",
                "rl_algorithm": "sac"
            }
        }


class AgentState(BaseModel):
    """Agent runtime state (Redis)"""
    agent_id: UUID
    status: Literal["idle", "processing", "waiting", "error"]
    current_task: str | None = None
    last_heartbeat: datetime
    error_message: str | None = None
    metrics: dict = Field(default_factory=dict)  # Decision count, avg latency, etc.
```

**Relationships**:
- Belongs to one `StrategyTeam`
- Produces multiple `DecisionLog` entries
- May reference one `RLTrainingRun` (via rl_model_path)

**Validation Rules**:
- `agent_type` must match one of 12 defined types
- If `symbol` is set, agent is instrument-specific (e.g., Position Sizing for Gold)
- `llm_tier` determines model allocation per FR-021
- `max_position_size_pct` must not exceed portfolio allocation limit
- If `rl_enabled=True`, `rl_model_path` and `rl_algorithm` must be set

**State Transitions**:
```
idle → processing (event received)
processing → waiting (waiting for dependency)
processing → idle (decision complete)
processing → error (exception occurred)
error → idle (recovery)
```

---

### 2. Trade Intent

**Purpose**: Represents the decision to go LONG, SHORT, or NO_TRADE with conviction score

**Source**: FR-004 (Trade Decision Agent)

**Schema**:
```python
class TradeIntent(BaseModel):
    """Trade decision output (PostgreSQL audit + Redis event)"""
    decision_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str = Field(..., pattern=r"^[A-Z][a-zA-Z0-9]{1,19}$")
    timestamp: datetime

    # Decision
    direction: Literal["LONG", "SHORT", "NO_TRADE"]
    conviction: float = Field(..., ge=0.0, le=1.0, description="Confidence in decision (0-1)")

    # Inputs (from analyst reports)
    technical_report: dict  # TechnicalReport serialized
    fundamental_report: dict | None = None
    sentiment_report: dict | None = None
    debate_outcome: dict | None = None  # DebateOutcome serialized

    # Reasoning (FR-004)
    rationale: str = Field(..., min_length=50, description="Explanation of decision")
    key_factors: list[str] = Field(default_factory=list, description="Top 3-5 decision factors")

    # Metadata
    correlation_id: UUID = Field(
        ...,
        description="Links entire decision pipeline (analysis → debate → decision → execution)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "decision_id": "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f9a",
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "symbol": "CrudeOIL",
                "timestamp": "2025-12-01T10:30:00Z",
                "direction": "LONG",
                "conviction": 0.78,
                "rationale": "Strong bullish technical setup with RSI reversal from oversold, 200-day MA support at $72.50, and ML forecast showing 68% probability of upward move in next 4 hours. Fundamental support from OPEC+ production cut extension and rising geopolitical risk premium.",
                "key_factors": [
                    "RSI reversal from oversold (32 → 45)",
                    "ML forecast 68% up probability (4h)",
                    "Support at 200-day MA ($72.50)",
                    "OPEC+ production cut extension",
                    "Geopolitical risk premium rising"
                ],
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }
```

**Relationships**:
- Created by `Agent` (trade_decision type)
- References `AnalystReport` (technical, fundamental, sentiment)
- References `DebateOutcome`
- Triggers `PositionSize` calculation
- Logged in `DecisionLog`

**Validation Rules**:
- `conviction >= 0.6` required for LONG/SHORT (configurable threshold)
- `rationale` must be substantive (min 50 chars)
- `key_factors` should list 3-5 specific reasons
- Must include `technical_report` (mandatory per FR-001)
- If `direction != NO_TRADE`, must have `debate_outcome` (FR-008)

**State Transitions**:
```
Created → Validated (RiskManagerAgent checks) → Approved/Rejected
Approved → PositionSized → Executed
Rejected → Archived
```

---

### 3. Position Size

**Purpose**: Dynamic position size calculation based on Kelly criterion, regime, conviction, and correlation

**Source**: FR-005 (Position Sizing Agent)

**Schema**:
```python
class PositionSize(BaseModel):
    """Position sizing decision (PostgreSQL audit + Redis event)"""
    sizing_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # Input Context
    trade_intent_id: UUID  # References TradeIntent
    allocated_capital: float = Field(..., gt=0, description="Capital allocated to this strategy (from Portfolio Allocation)")
    current_equity: float = Field(..., gt=0)
    open_positions_count: int = Field(..., ge=0)

    # Sizing Calculation (FR-005)
    kelly_fraction: float = Field(..., ge=0.0, le=1.0, description="Kelly criterion output")
    regime_adjustment: float = Field(..., ge=0.5, le=1.5, description="Regime-based multiplier")
    conviction_adjustment: float = Field(..., ge=0.5, le=1.5, description="Conviction-based multiplier")
    correlation_adjustment: float = Field(..., ge=0.5, le=1.5, description="Correlation penalty")

    # Final Output
    position_size_usd: float = Field(..., gt=0)
    position_size_pct: float = Field(..., gt=0, le=10.0, description="% of allocated capital")
    lot_size: float = Field(..., gt=0, description="Broker lot size")

    # Reasoning
    rationale: str
    risk_metrics: dict = Field(
        default_factory=dict,
        description="Additional risk metrics (var, volatility, correlation matrix)"
    )

    # Metadata
    correlation_id: UUID

    class Config:
        json_schema_extra = {
            "example": {
                "sizing_id": "b9c8d7e6-f5a4-3b2c-1d0e-9f8e7d6c5b4a",
                "agent_id": "987e6543-b21a-98d7-c654-321098765432",
                "symbol": "CrudeOIL",
                "timestamp": "2025-12-01T10:30:05Z",
                "trade_intent_id": "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f9a",
                "allocated_capital": 40000.0,
                "current_equity": 100000.0,
                "open_positions_count": 1,
                "kelly_fraction": 0.15,
                "regime_adjustment": 1.2,
                "conviction_adjustment": 1.1,
                "correlation_adjustment": 0.9,
                "position_size_usd": 7128.0,
                "position_size_pct": 17.82,
                "lot_size": 0.95,
                "rationale": "Kelly suggests 15% base sizing. Trending regime (+20% boost). High conviction 0.78 (+10% boost). Negative correlation with existing Gold position (-10% penalty). Final size: 17.82% of allocated $40K = $7,128.",
                "risk_metrics": {
                    "var_95": 850.0,
                    "volatility_30d": 0.025,
                    "correlation_gold": -0.32
                },
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }
```

**Relationships**:
- Created by `Agent` (position_sizing type)
- References `TradeIntent`
- References `PortfolioAllocation` (allocated_capital)
- Triggers `StopLoss` and `TakeProfit` calculations
- Logged in `DecisionLog`

**Validation Rules**:
- `position_size_pct` must not exceed `Agent.max_position_size_pct`
- `position_size_usd` must not exceed `allocated_capital * max_position_size_pct / 100`
- All adjustment factors (regime, conviction, correlation) must be in [0.5, 1.5]
- `kelly_fraction` must be in [0, 1]
- Must validate against Risk Overseer limits before execution

**Constraints** (from FR-005):
- Max 3% per position (configurable per agent)
- Position size based on allocated capital, NOT total account balance
- Must account for existing positions (correlation adjustment)

---

### 4. Stop Loss

**Purpose**: Intelligent stop-loss placement using market structure, ATR, and probability analysis

**Source**: FR-006 (Stop Loss Agent)

**Schema**:
```python
class StopLoss(BaseModel):
    """Stop-loss decision (PostgreSQL audit + Redis event)"""
    stop_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # Input Context
    trade_intent_id: UUID
    position_size_id: UUID
    entry_price: float = Field(..., gt=0)
    direction: Literal["LONG", "SHORT"]

    # Stop Calculation (FR-006)
    stop_price: float = Field(..., gt=0)
    stop_distance_pct: float = Field(..., gt=0, le=20.0)
    atr_multiplier: float = Field(..., ge=1.0, le=3.0, description="ATR-based distance")

    # Market Structure Context
    nearest_support: float | None = Field(None, description="Nearest support level (for LONG)")
    nearest_resistance: float | None = Field(None, description="Nearest resistance level (for SHORT)")
    structure_type: Literal["swing_low", "swing_high", "pivot", "liquidity_cluster", "atr_based"] | None = None

    # Probability Analysis
    stop_hit_probability: float = Field(..., ge=0.0, le=1.0, description="ML-estimated probability of stop being hit")

    # Trailing Configuration
    is_trailing: bool = Field(default=False)
    trailing_offset_pct: float | None = Field(None, ge=0.5, le=10.0)

    # Reasoning
    rationale: str

    # Metadata
    correlation_id: UUID

    class Config:
        json_schema_extra = {
            "example": {
                "stop_id": "c5d4e3f2-a1b0-9c8d-7e6f-5a4b3c2d1e0f",
                "agent_id": "321a4567-e89b-12d3-a456-426614174111",
                "symbol": "CrudeOIL",
                "timestamp": "2025-12-01T10:30:07Z",
                "trade_intent_id": "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f9a",
                "position_size_id": "b9c8d7e6-f5a4-3b2c-1d0e-9f8e7d6c5b4a",
                "entry_price": 75.20,
                "direction": "LONG",
                "stop_price": 73.15,
                "stop_distance_pct": 2.73,
                "atr_multiplier": 1.8,
                "nearest_support": 73.10,
                "structure_type": "swing_low",
                "stop_hit_probability": 0.22,
                "is_trailing": True,
                "trailing_offset_pct": 1.5,
                "rationale": "Swing low at $73.10 from 4h chart provides strong structural support. Stop placed at $73.15 (5 pips below) equals 2.73% distance, within 1.8x ATR (14-period = $1.14). ML probability of stop hit: 22% (low risk). Trailing stop enabled with 1.5% offset.",
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }
```

**Relationships**:
- Created by `Agent` (stop_loss type)
- References `TradeIntent` and `PositionSize`
- May be adjusted by `PositionMonitorAgent` (trailing stops)
- Logged in `DecisionLog`

**Validation Rules**:
- `stop_distance_pct` must not exceed `Agent.max_stop_distance_pct`
- For LONG: `stop_price < entry_price`
- For SHORT: `stop_price > entry_price`
- `atr_multiplier` typically in [1.0, 3.0] (configurable)
- If `is_trailing=True`, must have `trailing_offset_pct`
- `stop_hit_probability < 0.5` preferred (low risk of premature stop-out)

**Constraints** (from FR-006):
- Prefer structural levels (swing lows/highs) over arbitrary ATR distances
- Stop must provide favorable risk/reward ratio (validated by Risk Overseer)
- Must account for bid-ask spread and slippage

---

### 5. Take Profit

**Purpose**: Probabilistic take-profit targets based on ML forecast distributions

**Source**: FR-007 (Take Profit Agent)

**Schema**:
```python
class TakeProfit(BaseModel):
    """Take-profit decision (PostgreSQL audit + Redis event)"""
    tp_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # Input Context
    trade_intent_id: UUID
    position_size_id: UUID
    stop_loss_id: UUID
    entry_price: float = Field(..., gt=0)
    direction: Literal["LONG", "SHORT"]

    # Target Calculation (FR-007)
    targets: list[dict] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Up to 3 partial targets with probabilities"
    )
    # Each target: {"price": float, "size_pct": float, "probability": float, "rationale": str}

    # Risk/Reward
    risk_reward_ratio: float = Field(..., ge=1.0, description="Reward/Risk ratio")
    expected_value: float = Field(..., description="Probability-weighted expected profit")

    # ML Forecast Context
    forecast_horizon: Literal["1h", "4h", "1d"]
    forecast_distribution: dict = Field(
        default_factory=dict,
        description="ML forecast percentiles (p25, p50, p75, p90)"
    )

    # Reasoning
    rationale: str

    # Metadata
    correlation_id: UUID

    class Config:
        json_schema_extra = {
            "example": {
                "tp_id": "f1e2d3c4-b5a6-9780-1234-567890abcdef",
                "agent_id": "456b7890-c12d-34e5-f678-901234567abc",
                "symbol": "CrudeOIL",
                "timestamp": "2025-12-01T10:30:09Z",
                "trade_intent_id": "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f9a",
                "position_size_id": "b9c8d7e6-f5a4-3b2c-1d0e-9f8e7d6c5b4a",
                "stop_loss_id": "c5d4e3f2-a1b0-9c8d-7e6f-5a4b3c2d1e0f",
                "entry_price": 75.20,
                "direction": "LONG",
                "targets": [
                    {
                        "price": 76.50,
                        "size_pct": 50.0,
                        "probability": 0.65,
                        "rationale": "ML p50 target at $76.50 (65% probability). Take 50% profit at 1.73% gain."
                    },
                    {
                        "price": 77.80,
                        "size_pct": 30.0,
                        "probability": 0.35,
                        "rationale": "ML p75 target at $77.80 (35% probability). Take 30% profit at 3.46% gain."
                    },
                    {
                        "price": 79.50,
                        "size_pct": 20.0,
                        "probability": 0.15,
                        "rationale": "ML p90 target at $79.50 (15% probability). Final 20% at 5.72% gain."
                    }
                ],
                "risk_reward_ratio": 2.1,
                "expected_value": 245.80,
                "forecast_horizon": "4h",
                "forecast_distribution": {
                    "p25": 74.80,
                    "p50": 76.50,
                    "p75": 77.80,
                    "p90": 79.50
                },
                "rationale": "Using 4h ML forecast distribution. Three partial targets aligned with p50, p75, p90. Risk/reward 2.1:1. Expected value: $245.80 (probability-weighted).",
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }
```

**Relationships**:
- Created by `Agent` (take_profit type)
- References `TradeIntent`, `PositionSize`, `StopLoss`
- May be adjusted by `PositionMonitorAgent` (target adjustments)
- Logged in `DecisionLog`

**Validation Rules**:
- Sum of `targets[].size_pct` must equal 100.0
- For LONG: all `targets[].price > entry_price`
- For SHORT: all `targets[].price < entry_price`
- `targets` must be sorted by ascending price (LONG) or descending (SHORT)
- Each `targets[].probability` must be in [0, 1]
- `risk_reward_ratio >= 1.5` preferred (configurable minimum)

**Constraints** (from FR-007):
- Targets derived from ML forecast percentiles (p50, p75, p90)
- Must support partial position closures (or fallback to single target if broker doesn't support)
- Expected value calculation: sum(target_profit * probability) for all targets

---

### 6. Analyst Report

**Purpose**: Structured output from Analysis Layer agents (Technical, Fundamental, Sentiment)

**Source**: FR-001 (Technical), FR-002 (Fundamental), FR-003 (Sentiment)

**Schema**:
```python
class TechnicalReport(BaseModel):
    """Technical analysis report (Redis cache, 5min TTL)"""
    report_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # ML Forecasts (FR-001)
    ml_forecasts: dict = Field(
        ...,
        description="ML model predictions (TCN, TFT, FEDformer)"
    )
    # Example: {"tcn_1h": {"direction": "UP", "prob": 0.68, "magnitude": 1.2}, ...}

    # Technical Indicators
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    support_levels: list[float] = Field(default_factory=list, max_length=3)
    resistance_levels: list[float] = Field(default_factory=list, max_length=3)
    key_indicators: dict = Field(
        default_factory=dict,
        description="RSI, MACD, moving averages, etc."
    )

    # Summary
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=100, max_length=500)

    # Metadata
    correlation_id: UUID


class FundamentalReport(BaseModel):
    """Fundamental analysis report (Redis cache, 5min TTL)"""
    report_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # Economic Events (FR-002)
    upcoming_events: list[dict] = Field(
        default_factory=list,
        description="High-impact economic events in next 24h"
    )
    # Example: {"event": "OPEC+ Meeting", "impact": "HIGH", "time": "2025-12-02T14:00:00Z"}

    # Correlations
    correlation_analysis: dict = Field(
        default_factory=dict,
        description="Correlations with DXY, interest rates, etc."
    )

    # Summary
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=100, max_length=500)

    # Metadata
    correlation_id: UUID


class SentimentReport(BaseModel):
    """Sentiment analysis report (Redis cache, 5min TTL)"""
    report_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    symbol: str
    timestamp: datetime

    # Positioning Data (FR-003)
    cot_data: dict | None = Field(
        None,
        description="Commitment of Traders report data"
    )
    retail_sentiment: dict | None = Field(
        None,
        description="Retail trader positioning"
    )

    # Summary
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=100, max_length=500)
    contrarian_signal: bool = Field(
        default=False,
        description="True if extreme sentiment suggests contrarian trade"
    )

    # Metadata
    correlation_id: UUID
```

**Relationships**:
- Created by `Agent` (technical_analyst, fundamental_analyst, sentiment_analyst types)
- Consumed by `TradeDecisionAgent`
- Cached in Redis with 5-minute TTL
- NOT persisted to PostgreSQL (transient analysis)

**Validation Rules**:
- `confidence` must be in [0, 1]
- `summary` must be substantive (100-500 chars)
- Technical report MUST include `ml_forecasts` (FR-001)
- All reports must have consistent `correlation_id` for same signal

**Cache Strategy**:
- Redis key: `report:{report_type}:{symbol}:{timestamp_5min_bucket}`
- TTL: 5 minutes
- Invalidation: On new tick if price moves > 0.5%

---

### 7. Debate Outcome

**Purpose**: Result of adversarial debate between Bull and Bear Researcher agents

**Source**: FR-008 (Debate Layer)

**Schema**:
```python
class DebateOutcome(BaseModel):
    """Debate layer output (PostgreSQL audit)"""
    debate_id: UUID = Field(default_factory=uuid4)
    bull_agent_id: UUID
    bear_agent_id: UUID
    symbol: str
    timestamp: datetime

    # Arguments
    bull_case: str = Field(..., min_length=200, description="Bull argument with evidence")
    bear_case: str = Field(..., min_length=200, description="Bear argument with rebuttals")

    # Strength Scores (FR-008)
    bull_strength: float = Field(..., ge=0.0, le=1.0, description="Strength of bull case")
    bear_strength: float = Field(..., ge=0.0, le=1.0, description="Strength of bear case")

    # Synthesis
    consensus: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in consensus")
    synthesis: str = Field(
        ...,
        min_length=100,
        description="Integration of both perspectives"
    )

    # Risk Warnings
    risk_warnings: list[str] = Field(
        default_factory=list,
        description="Key risks identified by either side"
    )

    # Metadata
    correlation_id: UUID
    debate_duration_ms: int = Field(..., ge=0, description="Time taken for debate")

    class Config:
        json_schema_extra = {
            "example": {
                "debate_id": "9a8b7c6d-5e4f-3210-9876-543210fedcba",
                "bull_agent_id": "bull-123",
                "bear_agent_id": "bear-456",
                "symbol": "CrudeOIL",
                "timestamp": "2025-12-01T10:30:03Z",
                "bull_case": "Strong technical setup: RSI reversal from oversold, 200-day MA support at $72.50, ML forecast 68% up probability. Fundamental tailwinds: OPEC+ production cut extension, rising geopolitical risk premium (Middle East tensions), inventory drawdowns exceeding expectations (-4.2M barrels vs -2.5M est). Sentiment: Commercial hedgers reducing shorts (-15% week-over-week in COT), institutional buying detected.",
                "bear_case": "Counterarguments: RSI reversal occurred in context of 6-week downtrend (lower highs pattern). 200-day MA tested 3 times in 10 days (weakening support). ML forecast uncertainty band wide (±3.2%), reducing conviction. Fundamentals: Demand concerns from China PMI miss (48.2 vs 49.5), US rate hikes still priced in (bearish for commodities). Sentiment: Retail traders 72% long (contrarian bearish), open interest declining (weak conviction).",
                "bull_strength": 0.72,
                "bear_strength": 0.58,
                "consensus": "BULLISH",
                "confidence": 0.64,
                "synthesis": "Bull case prevails with modest edge. Technical setup favors upside, but bear warnings on weakening support and demand concerns warrant cautious position sizing. Recommend LONG with reduced size and tight stop below 200-day MA.",
                "risk_warnings": [
                    "200-day MA support tested multiple times (weakening)",
                    "China demand concerns (PMI miss)",
                    "Wide ML forecast uncertainty (±3.2%)",
                    "Retail sentiment extremely bullish (contrarian risk)"
                ],
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "debate_duration_ms": 2450
            }
        }
```

**Relationships**:
- Created by two `Agent` instances (bull_researcher, bear_researcher types)
- Consumed by `TradeDecisionAgent`
- Persisted to PostgreSQL (audit trail)

**Validation Rules**:
- Both `bull_case` and `bear_case` must be substantive (min 200 chars)
- `bull_strength` and `bear_strength` must be in [0, 1]
- `consensus` typically aligns with stronger case (bull_strength > bear_strength → BULLISH)
- `risk_warnings` should list 3-5 key risks identified
- `debate_duration_ms` should be < 5000ms (5s target per FR performance goals)

**Usage** (from FR-008):
- Debate triggered for all non-NO_TRADE signals
- Produces stress-tested trade ideas
- Risk warnings used by Risk Overseer Agent

---

### 8. Decision Log

**Purpose**: Comprehensive audit trail for all agent decisions with full context

**Source**: All decision-making agents (FR-004 through FR-011)

**Schema**:
```python
class DecisionLog(BaseModel):
    """Agent decision audit log (PostgreSQL TimescaleDB)"""
    log_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime  # TimescaleDB partition key
    agent_id: UUID
    agent_type: str
    symbol: str | None = None

    # Decision Details
    decision_type: Literal[
        "trade_intent", "position_size", "stop_loss", "take_profit",
        "trade_execution", "position_adjustment", "risk_check"
    ]
    decision: str = Field(..., description="The actual decision made")
    confidence: float | None = Field(None, ge=0.0, le=1.0)

    # Full Context (FR-004 audit requirement)
    inputs: dict = Field(
        ...,
        description="All inputs to the decision (market data, forecasts, reports)"
    )
    rationale: str = Field(..., min_length=50, description="Explanation of decision")

    # Outcome Tracking
    outcome: Literal["success", "failure", "partial", "pending"] | None = None
    pnl: float | None = Field(None, description="P&L if applicable")
    outcome_notes: str | None = None

    # Performance Metadata
    decision_latency_ms: int = Field(..., ge=0, description="Time taken to make decision")
    llm_calls: int = Field(default=0, ge=0, description="Number of LLM API calls")
    llm_cost_usd: float = Field(default=0.0, ge=0.0, description="LLM cost for this decision")
    mcp_tool_calls: int = Field(default=0, ge=0, description="Number of MCP tool calls")

    # Correlation
    correlation_id: UUID = Field(
        ...,
        description="Links entire decision pipeline"
    )
    parent_decision_id: UUID | None = Field(
        None,
        description="Parent decision if this is a follow-up (e.g., position_size follows trade_intent)"
    )

    # Metadata
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "1a2b3c4d-5e6f-7890-abcd-ef1234567890",
                "timestamp": "2025-12-01T10:30:00Z",
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "agent_type": "trade_decision",
                "symbol": "CrudeOIL",
                "decision_type": "trade_intent",
                "decision": "LONG",
                "confidence": 0.78,
                "inputs": {
                    "current_price": 75.20,
                    "technical_report": {...},
                    "fundamental_report": {...},
                    "sentiment_report": {...},
                    "debate_outcome": {...}
                },
                "rationale": "Strong bullish technical setup with RSI reversal...",
                "outcome": "success",
                "pnl": 420.50,
                "outcome_notes": "Trade executed at 75.22, first target hit at 76.50, profit $420.50",
                "decision_latency_ms": 1850,
                "llm_calls": 3,
                "llm_cost_usd": 0.0042,
                "mcp_tool_calls": 5,
                "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "parent_decision_id": None,
                "created_at": "2025-12-01T10:30:00Z"
            }
        }
```

**Database Schema** (TimescaleDB):
```sql
CREATE TABLE decision_log (
    log_id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    agent_id UUID NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),

    decision_type VARCHAR(50) NOT NULL,
    decision VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,4),

    inputs JSONB NOT NULL,
    rationale TEXT NOT NULL,

    outcome VARCHAR(20),
    pnl DECIMAL(15,2),
    outcome_notes TEXT,

    decision_latency_ms INTEGER NOT NULL,
    llm_calls INTEGER DEFAULT 0,
    llm_cost_usd DECIMAL(10,6) DEFAULT 0.0,
    mcp_tool_calls INTEGER DEFAULT 0,

    correlation_id UUID NOT NULL,
    parent_decision_id UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (timestamp, agent_id, log_id)
);

-- TimescaleDB hypertable for partitioning
SELECT create_hypertable('decision_log', 'timestamp');

-- Indexes
CREATE INDEX idx_decision_log_agent_id ON decision_log (agent_id, timestamp DESC);
CREATE INDEX idx_decision_log_symbol ON decision_log (symbol, timestamp DESC);
CREATE INDEX idx_decision_log_correlation ON decision_log (correlation_id);
CREATE INDEX idx_decision_log_outcome ON decision_log (outcome, timestamp DESC);

-- Retention policy (90 days per research.md)
SELECT add_retention_policy('decision_log', INTERVAL '90 days');

-- Continuous aggregates for analytics
CREATE MATERIALIZED VIEW decision_log_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    agent_id,
    agent_type,
    symbol,
    decision_type,
    COUNT(*) AS decision_count,
    AVG(confidence) AS avg_confidence,
    AVG(decision_latency_ms) AS avg_latency_ms,
    SUM(llm_cost_usd) AS total_llm_cost,
    COUNT(CASE WHEN outcome = 'success' THEN 1 END) AS success_count,
    SUM(pnl) AS total_pnl
FROM decision_log
GROUP BY hour, agent_id, agent_type, symbol, decision_type;
```

**Relationships**:
- Created by all decision-making `Agent` instances
- References parent decisions via `parent_decision_id`
- Grouped by `correlation_id` for pipeline analysis

**Validation Rules**:
- `rationale` must be substantive (min 50 chars)
- `decision_latency_ms` should be < 5000ms for INTRADAY (performance target)
- `inputs` must be complete JSONB for full auditability
- If `pnl` is set, `outcome` must be success/failure/partial

**Query Patterns**:
```sql
-- Find all decisions for a correlation_id (full pipeline)
SELECT * FROM decision_log WHERE correlation_id = 'a1b2c3d4...' ORDER BY timestamp;

-- Agent performance analysis
SELECT agent_id, agent_type,
       COUNT(*) AS decisions,
       AVG(decision_latency_ms) AS avg_latency,
       COUNT(CASE WHEN outcome = 'success' THEN 1 END)::float / COUNT(*) AS success_rate,
       SUM(pnl) AS total_pnl
FROM decision_log
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY agent_id, agent_type;

-- Cost analysis
SELECT agent_type, symbol,
       SUM(llm_cost_usd) AS total_llm_cost,
       AVG(llm_calls) AS avg_llm_calls,
       AVG(mcp_tool_calls) AS avg_mcp_calls
FROM decision_log
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY agent_type, symbol;
```

---

### 9. RL Training Run

**Purpose**: Metadata and results for offline RL training runs

**Source**: FR-012 (Backtesting Environment), FR-013 (RL Training), FR-014 (Walk-Forward Validation)

**Schema**:
```python
class RLTrainingRun(BaseModel):
    """RL training run metadata (PostgreSQL + MLflow)"""
    run_id: UUID = Field(default_factory=uuid4)
    agent_type: Literal["position_sizing", "stop_loss", "take_profit", "trade_decision"]
    symbol: str
    algorithm: Literal["ppo", "sac"]

    # Training Configuration
    hyperparameters: dict = Field(
        ...,
        description="RL hyperparameters (learning_rate, gamma, etc.)"
    )
    # Example: {"learning_rate": 0.0003, "gamma": 0.99, "batch_size": 256, ...}

    training_data_range: dict = Field(
        ...,
        description="Start and end dates for training data"
    )
    # Example: {"start_date": "2023-01-01", "end_date": "2023-12-31"}

    validation_strategy: Literal["walk_forward", "rolling_window", "expanding_window"]
    validation_config: dict = Field(
        default_factory=dict,
        description="Validation configuration (train_days, test_days, step_days)"
    )

    # Training Execution
    started_at: datetime
    completed_at: datetime | None = None
    status: Literal["running", "completed", "failed", "cancelled"]

    # Results
    total_timesteps: int = Field(default=0, ge=0)
    training_duration_seconds: float = Field(default=0.0, ge=0.0)

    final_metrics: dict = Field(
        default_factory=dict,
        description="Final training metrics"
    )
    # Example: {
    #   "mean_reward": 0.042,
    #   "std_reward": 0.018,
    #   "sharpe_ratio": 1.85,
    #   "max_drawdown": 0.12,
    #   "win_rate": 0.68
    # }

    validation_metrics: dict = Field(
        default_factory=dict,
        description="Walk-forward validation results"
    )
    # Example: {
    #   "oos_sharpe": 1.62,  # Out-of-sample Sharpe
    #   "oos_max_drawdown": 0.15,
    #   "oos_win_rate": 0.64,
    #   "overfitting_score": 0.88  # train_sharpe / oos_sharpe
    # }

    # MLflow Integration
    mlflow_run_id: str | None = None
    mlflow_experiment_id: str | None = None
    model_checkpoint_uri: str | None = Field(
        None,
        description="MLflow model URI (e.g., mlflow://models/position_sizing_sac_crude/Production)"
    )

    # Deployment
    is_deployed: bool = Field(default=False)
    deployed_at: datetime | None = None
    deployment_stage: Literal["None", "Staging", "Production"] = Field(default="None")

    # Error Tracking
    error_message: str | None = None

    # Metadata
    created_by: str = Field(default="system")
    notes: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "7890abcd-ef12-3456-7890-abcdef123456",
                "agent_type": "position_sizing",
                "symbol": "CrudeOIL",
                "algorithm": "sac",
                "hyperparameters": {
                    "learning_rate": 0.0003,
                    "gamma": 0.99,
                    "batch_size": 256,
                    "buffer_size": 1000000,
                    "tau": 0.005,
                    "train_freq": 1,
                    "gradient_steps": 1
                },
                "training_data_range": {
                    "start_date": "2023-01-01",
                    "end_date": "2024-12-31"
                },
                "validation_strategy": "walk_forward",
                "validation_config": {
                    "train_days": 252,
                    "test_days": 63,
                    "step_days": 21
                },
                "started_at": "2025-12-01T08:00:00Z",
                "completed_at": "2025-12-01T12:45:30Z",
                "status": "completed",
                "total_timesteps": 500000,
                "training_duration_seconds": 17130.5,
                "final_metrics": {
                    "mean_reward": 0.042,
                    "std_reward": 0.018,
                    "sharpe_ratio": 1.85,
                    "max_drawdown": 0.12,
                    "win_rate": 0.68
                },
                "validation_metrics": {
                    "oos_sharpe": 1.62,
                    "oos_max_drawdown": 0.15,
                    "oos_win_rate": 0.64,
                    "overfitting_score": 0.88
                },
                "mlflow_run_id": "abc123def456",
                "mlflow_experiment_id": "exp-001",
                "model_checkpoint_uri": "mlflow://models/position_sizing_sac_crude/Production",
                "is_deployed": True,
                "deployed_at": "2025-12-01T13:00:00Z",
                "deployment_stage": "Production"
            }
        }
```

**Relationships**:
- One-to-many with `ModelConfiguration` (A/B testing)
- Referenced by `Agent.rl_model_path`
- Linked to MLflow experiment runs

**Validation Rules**:
- If `status = "completed"`, must have `completed_at`, `final_metrics`, `validation_metrics`
- If `is_deployed = True`, must have `model_checkpoint_uri` and `deployment_stage != "None"`
- `training_duration_seconds` should match `completed_at - started_at`
- Validation metrics should include out-of-sample (OOS) performance
- `overfitting_score` close to 1.0 indicates good generalization

**Walk-Forward Validation** (from FR-014):
```python
# Example validation_config
{
    "train_days": 252,   # Train on 1 year
    "test_days": 63,     # Test on 3 months
    "step_days": 21,     # Roll forward by 1 month
    "anchored": False    # False = rolling window, True = expanding window
}

# Walk-forward windows:
# Window 1: Train[2023-01-01 to 2023-12-31], Test[2024-01-01 to 2024-03-31]
# Window 2: Train[2023-02-01 to 2024-01-31], Test[2024-02-01 to 2024-04-30]
# Window 3: Train[2023-03-01 to 2024-02-28], Test[2024-03-01 to 2024-05-31]
# ...
```

---

### 10. Model Configuration

**Purpose**: A/B testing configurations for multi-model experiments

**Source**: FR-015 (A/B Testing Infrastructure), FR-016 (Multi-Model Testing)

**Schema**:
```python
class ModelConfiguration(BaseModel):
    """A/B test configuration (PostgreSQL)"""
    config_id: UUID = Field(default_factory=uuid4)
    experiment_name: str = Field(..., min_length=5, max_length=100)

    # Model Assignments
    agent_type: Literal["position_sizing", "stop_loss", "take_profit", "trade_decision"]
    symbol: str

    variant_name: Literal["A", "B", "C", "control"] = Field(
        ...,
        description="Variant identifier for A/B/C testing"
    )

    # Model Details
    model_source: Literal["rl_trained", "rule_based", "hybrid"]
    rl_training_run_id: UUID | None = Field(
        None,
        description="References RLTrainingRun if model_source = 'rl_trained'"
    )
    rule_based_config: dict | None = Field(
        None,
        description="Configuration for rule-based fallback"
    )

    # Traffic Allocation (FR-016)
    traffic_percentage: float = Field(..., ge=0.0, le=100.0, description="% of trades using this variant")
    is_active: bool = Field(default=True)

    # Experiment Metadata
    experiment_start_date: datetime
    experiment_end_date: datetime | None = None
    min_sample_size: int = Field(default=100, ge=10, description="Minimum trades before stat significance")

    # Results Tracking
    trades_executed: int = Field(default=0, ge=0)
    performance_metrics: dict = Field(
        default_factory=dict,
        description="Performance metrics for this variant"
    )
    # Example: {"sharpe": 1.45, "win_rate": 0.62, "avg_pnl": 125.30, "max_dd": 0.18}

    statistical_significance: dict = Field(
        default_factory=dict,
        description="Statistical test results vs control"
    )
    # Example: {"p_value": 0.023, "t_statistic": 2.45, "significantly_better": True}

    # Winner Selection
    is_winner: bool = Field(default=False)
    promoted_at: datetime | None = None

    # Metadata
    created_at: datetime
    created_by: str = Field(default="system")
    notes: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "config_id": "fedcba09-8765-4321-0fed-cba987654321",
                "experiment_name": "position_sizing_sac_vs_kelly_crude",
                "agent_type": "position_sizing",
                "symbol": "CrudeOIL",
                "variant_name": "A",
                "model_source": "rl_trained",
                "rl_training_run_id": "7890abcd-ef12-3456-7890-abcdef123456",
                "traffic_percentage": 50.0,
                "is_active": True,
                "experiment_start_date": "2025-12-01T00:00:00Z",
                "min_sample_size": 200,
                "trades_executed": 245,
                "performance_metrics": {
                    "sharpe": 1.68,
                    "win_rate": 0.67,
                    "avg_pnl": 142.80,
                    "max_dd": 0.14
                },
                "statistical_significance": {
                    "p_value": 0.018,
                    "t_statistic": 2.62,
                    "significantly_better": True
                },
                "is_winner": False,
                "created_at": "2025-12-01T00:00:00Z",
                "notes": "Testing SAC-trained position sizing vs Kelly criterion baseline"
            }
        }
```

**Relationships**:
- References `RLTrainingRun` (if model_source = "rl_trained")
- One experiment has 2-4 `ModelConfiguration` instances (variants A, B, C, control)
- Used by `Agent` to select active configuration

**Validation Rules**:
- Sum of `traffic_percentage` across all variants in same experiment must equal 100.0
- If `is_winner = True`, must have `promoted_at` timestamp
- `trades_executed >= min_sample_size` required before declaring winner
- Statistical significance: `p_value < 0.05` preferred for "significantly_better"
- Only one variant per experiment can have `is_winner = True`

**A/B Testing Workflow** (from FR-016):
```python
# 1. Create experiment with variants
control = ModelConfiguration(
    variant_name="control",
    model_source="rule_based",
    traffic_percentage=50.0
)
variant_a = ModelConfiguration(
    variant_name="A",
    model_source="rl_trained",
    rl_training_run_id=rl_run.run_id,
    traffic_percentage=50.0
)

# 2. Execute trades using traffic allocation
if random.random() < 0.5:  # 50% traffic
    agent.use_configuration(control)
else:
    agent.use_configuration(variant_a)

# 3. Track results
variant_a.trades_executed += 1
variant_a.performance_metrics["sharpe"] = calculate_sharpe(variant_a_trades)

# 4. Statistical testing (after min_sample_size reached)
if variant_a.trades_executed >= variant_a.min_sample_size:
    p_value, t_stat = ttest_ind(variant_a_returns, control_returns)
    variant_a.statistical_significance = {
        "p_value": p_value,
        "t_statistic": t_stat,
        "significantly_better": p_value < 0.05 and mean(variant_a_returns) > mean(control_returns)
    }

# 5. Promote winner
if variant_a.statistical_significance["significantly_better"]:
    variant_a.is_winner = True
    variant_a.promoted_at = datetime.now()
    # Update agent to use variant A permanently
```

---

### 11. Portfolio Allocation

**Purpose**: Capital allocation across multiple trading strategies/instruments

**Source**: FR-018 (Portfolio Allocation Architecture)

**Schema**:
```python
class PortfolioAllocation(BaseModel):
    """Portfolio allocation configuration (PostgreSQL)"""
    allocation_id: UUID = Field(default_factory=uuid4)

    # Allocation Configuration
    allocation_type: Literal["static", "dynamic"] = Field(
        default="static",
        description="Static (manual) or dynamic (Portfolio Allocator Agent)"
    )

    allocations: list[dict] = Field(
        ...,
        min_length=1,
        description="List of strategy allocations"
    )
    # Each allocation: {
    #   "strategy_team_id": UUID,
    #   "symbol": str,
    #   "allocated_capital_usd": float,
    #   "allocated_percentage": float
    # }

    total_capital_usd: float = Field(..., gt=0, description="Total portfolio capital")
    reserve_capital_usd: float = Field(..., ge=0, description="Reserve (unallocated) capital")
    reserve_percentage: float = Field(..., ge=0.0, le=50.0, description="% held in reserve")

    # Rebalancing (for dynamic allocation)
    rebalance_frequency: Literal["daily", "weekly", "monthly", "manual"] | None = None
    last_rebalanced_at: datetime | None = None
    next_rebalance_at: datetime | None = None

    # Validity Period
    effective_from: datetime
    effective_until: datetime | None = Field(
        None,
        description="None = indefinite, or set expiry for dynamic rebalancing"
    )
    is_active: bool = Field(default=True)

    # Metadata
    created_at: datetime
    created_by: str = Field(default="system")
    notes: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "allocation_id": "1234abcd-5678-90ef-1234-567890abcdef",
                "allocation_type": "static",
                "allocations": [
                    {
                        "strategy_team_id": "team-gold-001",
                        "symbol": "Gold",
                        "allocated_capital_usd": 40000.0,
                        "allocated_percentage": 40.0
                    },
                    {
                        "strategy_team_id": "team-crude-001",
                        "symbol": "CrudeOIL",
                        "allocated_capital_usd": 40000.0,
                        "allocated_percentage": 40.0
                    }
                ],
                "total_capital_usd": 100000.0,
                "reserve_capital_usd": 20000.0,
                "reserve_percentage": 20.0,
                "rebalance_frequency": None,
                "effective_from": "2025-12-01T00:00:00Z",
                "is_active": True,
                "notes": "Initial deployment: 40% Gold, 40% Crude Oil, 20% reserve"
            }
        }
```

**Relationships**:
- One-to-many with `StrategyTeam`
- Referenced by `PositionSizingAgent` to determine `allocated_capital`
- May be managed by `PortfolioAllocatorAgent` (if allocation_type = "dynamic")

**Validation Rules**:
- Sum of `allocations[].allocated_percentage` + `reserve_percentage` must equal 100.0
- Sum of `allocations[].allocated_capital_usd` + `reserve_capital_usd` must equal `total_capital_usd`
- Each `allocations[].allocated_percentage` must be in [0, 100]
- If `allocation_type = "dynamic"`, must have `rebalance_frequency` set
- Only one `PortfolioAllocation` can have `is_active = True` at a time

**Constraints** (from FR-018):
- Position sizing agents MUST operate within their `allocated_capital`, NOT total account balance
- Reserve capital provides buffer for drawdowns and prevents over-allocation
- Minimum reserve: 10% recommended

**Dynamic Rebalancing** (optional FR-018):
```python
# Portfolio Allocator Agent adjusts allocations based on:
# 1. Strategy performance (Sharpe ratios)
# 2. Drawdown levels
# 3. Correlation changes
# 4. Risk-parity principles

# Example rebalancing logic
if strategy_gold_sharpe > strategy_crude_sharpe * 1.2:
    # Increase Gold allocation by 5%, decrease Crude by 5%
    new_allocation = PortfolioAllocation(
        allocation_type="dynamic",
        allocations=[
            {"symbol": "Gold", "allocated_percentage": 45.0},
            {"symbol": "CrudeOIL", "allocated_percentage": 35.0}
        ],
        reserve_percentage=20.0,
        rebalance_frequency="weekly"
    )
```

---

### 12. MCP Tool

**Purpose**: Registry of MCP tools available to agents (ML forecasts, calculations, market structure)

**Source**: FR-019 (MCP Integration Protocol)

**Schema**:
```python
class MCPTool(BaseModel):
    """MCP tool registry (PostgreSQL)"""
    tool_id: UUID = Field(default_factory=uuid4)
    tool_name: str = Field(..., pattern=r"^[a-z_][a-z0-9_]*$", description="Snake_case tool name")
    tool_category: Literal["ml_forecast", "calculation", "market_structure", "data_retrieval"]

    # Tool Specification
    description: str = Field(..., min_length=20, max_length=500)
    input_schema: dict = Field(
        ...,
        description="Pydantic-compatible JSON schema for inputs"
    )
    output_schema: dict = Field(
        ...,
        description="Pydantic-compatible JSON schema for outputs"
    )

    # Implementation
    implementation_module: str = Field(
        ...,
        description="Python module path (e.g., src.ml.tools.forecasting_tools)"
    )
    implementation_function: str = Field(
        ...,
        description="Function name (e.g., get_tcn_forecast)"
    )

    # Performance Configuration (from research.md)
    cache_enabled: bool = Field(default=True, description="Enable Redis caching")
    cache_ttl_seconds: int = Field(default=300, ge=0, description="Cache TTL (5min default)")
    timeout_ms: int = Field(default=100, ge=10, le=5000, description="Timeout (100ms default)")
    circuit_breaker_enabled: bool = Field(default=True)
    circuit_breaker_threshold: int = Field(default=5, ge=1, description="Failures before opening")

    # Versioning
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="Semantic version (e.g., 1.0.0)")
    is_active: bool = Field(default=True)
    deprecated_at: datetime | None = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str = Field(default="system")

    class Config:
        json_schema_extra = {
            "example": {
                "tool_id": "tool-tcn-forecast-001",
                "tool_name": "get_tcn_forecast",
                "tool_category": "ml_forecast",
                "description": "Get TCN model forecast with confidence scores and uncertainty quantification",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "horizon": {"type": "string", "enum": ["1h", "4h", "1d"]},
                        "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                        "include_uncertainty": {"type": "boolean"}
                    },
                    "required": ["symbol", "horizon"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "predictions": {"type": "array", "items": {"type": "number"}},
                        "confidence_scores": {"type": "array", "items": {"type": "number"}},
                        "direction_prob": {"type": "number"},
                        "inference_time_ms": {"type": "number"}
                    },
                    "required": ["symbol", "predictions", "confidence_scores"]
                },
                "implementation_module": "src.ml.tools.forecasting_tools",
                "implementation_function": "get_tcn_forecast",
                "cache_enabled": True,
                "cache_ttl_seconds": 300,
                "timeout_ms": 100,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "version": "1.0.0",
                "is_active": True,
                "created_at": "2025-12-01T00:00:00Z"
            }
        }
```

**Relationships**:
- Used by all `Agent` types via MCP client
- Version history tracked for backward compatibility

**Validation Rules**:
- `tool_name` must be unique per version
- `input_schema` and `output_schema` must be valid JSON Schema
- `timeout_ms` should be < 100ms for p95 target (FR performance goals)
- If `deprecated_at` is set, `is_active` must be False

**MCP Tool Categories** (from FR-019):

1. **ML Forecasts**:
   - `get_tcn_forecast` - TCN model predictions
   - `get_tft_prediction` - TFT model predictions
   - `get_fedformer_regime` - Regime classification

2. **Calculations**:
   - `calculate_kelly` - Kelly criterion position sizing
   - `calculate_atr` - Average True Range

3. **Market Structure**:
   - `get_support_resistance` - Support/resistance levels
   - `detect_liquidity_clusters` - Liquidity zones

4. **Data Retrieval**:
   - `get_economic_events` - Economic calendar
   - `get_cot_data` - Commitment of Traders positioning

**Usage Example**:
```python
# Agent calls MCP tool
from src.agents.tools.mcp_client import MCPClient

mcp_client = MCPClient()

# Call with circuit breaker and caching
result = await mcp_client.call_tool(
    tool_name="get_tcn_forecast",
    inputs={
        "symbol": "CrudeOIL",
        "horizon": "4h",
        "confidence_threshold": 0.7,
        "include_uncertainty": True
    }
)

# Result cached in Redis with 5min TTL
# If tool fails 5 times, circuit breaker opens for 60s
```

---

### 13. Strategy Team

**Purpose**: Group of agents dedicated to a specific instrument/strategy

**Source**: FR-018 (Portfolio Allocation Architecture)

**Schema**:
```python
class StrategyTeam(BaseModel):
    """Strategy team configuration (PostgreSQL)"""
    team_id: UUID = Field(default_factory=uuid4)
    team_name: str = Field(..., min_length=5, max_length=100)
    symbol: str = Field(..., description="Trading instrument (e.g., Gold, CrudeOIL)")
    strategy_type: Literal["INTRADAY", "SWING", "POSITION"] = Field(
        default="SWING",
        description="Trading timeframe"
    )

    # Agent Assignments
    agent_assignments: dict = Field(
        ...,
        description="Map of agent roles to agent_ids"
    )
    # Example: {
    #   "technical_analyst": "agent-123",
    #   "fundamental_analyst": "agent-456",
    #   "sentiment_analyst": "agent-789",
    #   "bull_researcher": "agent-abc",
    #   "bear_researcher": "agent-def",
    #   "trade_decision": "agent-ghi",
    #   "position_sizing": "agent-jkl",
    #   "stop_loss": "agent-mno",
    #   "take_profit": "agent-pqr",
    #   "execution": "agent-stu",
    #   "position_monitor": "agent-vwx",
    #   "risk_overseer": "agent-yz0"
    # }

    # Team Status
    is_active: bool = Field(default=True)
    enabled_layers: list[Literal["analysis", "debate", "decision", "execution", "supervisory"]] = Field(
        default_factory=lambda: ["analysis", "debate", "decision", "execution", "supervisory"],
        description="Which agent layers are enabled"
    )

    # Performance Tracking
    total_trades: int = Field(default=0, ge=0)
    total_pnl: float = Field(default=0.0)
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = Field(None, ge=0.0, le=1.0)

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str = Field(default="system")
    notes: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "team_id": "team-crude-001",
                "team_name": "Crude Oil Swing Strategy",
                "symbol": "CrudeOIL",
                "strategy_type": "SWING",
                "agent_assignments": {
                    "technical_analyst": "agent-tech-crude-001",
                    "fundamental_analyst": "agent-fund-crude-001",
                    "sentiment_analyst": "agent-sent-crude-001",
                    "bull_researcher": "agent-bull-crude-001",
                    "bear_researcher": "agent-bear-crude-001",
                    "trade_decision": "agent-decision-crude-001",
                    "position_sizing": "agent-size-crude-001",
                    "stop_loss": "agent-stop-crude-001",
                    "take_profit": "agent-tp-crude-001",
                    "execution": "agent-exec-crude-001",
                    "position_monitor": "agent-monitor-crude-001",
                    "risk_overseer": "agent-risk-crude-001"
                },
                "is_active": True,
                "enabled_layers": ["analysis", "debate", "decision", "execution", "supervisory"],
                "total_trades": 142,
                "total_pnl": 12450.80,
                "sharpe_ratio": 1.68,
                "max_drawdown": 0.14,
                "win_rate": 0.67,
                "created_at": "2025-12-01T00:00:00Z"
            }
        }
```

**Relationships**:
- Has many `Agent` instances (12 agents per team)
- References `PortfolioAllocation` (receives capital allocation)
- Produces `DecisionLog` entries (aggregated from all team agents)

**Validation Rules**:
- `agent_assignments` must include all 12 required agent roles (or subset if layers disabled)
- Each agent_id in `agent_assignments` must reference a valid `Agent`
- All assigned agents must have `symbol` matching the team's `symbol`
- If `is_active = False`, all team agents should be inactive

**Multi-Instrument Support** (from FR-018 clarification):
```python
# Initial deployment: 2 strategy teams
team_gold = StrategyTeam(
    team_name="Gold Swing Strategy",
    symbol="Gold",
    strategy_type="SWING"
)

team_crude = StrategyTeam(
    team_name="Crude Oil Swing Strategy",
    symbol="CrudeOIL",
    strategy_type="SWING"
)

# Portfolio allocation
allocation = PortfolioAllocation(
    total_capital_usd=100000.0,
    allocations=[
        {"strategy_team_id": team_gold.team_id, "allocated_capital_usd": 40000.0},
        {"strategy_team_id": team_crude.team_id, "allocated_capital_usd": 40000.0}
    ],
    reserve_capital_usd=20000.0
)
```

---

## Entity Relationships Diagram

```
┌─────────────────────┐
│ Portfolio Allocation│
│  - allocations[]    │
│  - total_capital    │
└──────────┬──────────┘
           │ 1:N
           ▼
┌─────────────────────┐         ┌──────────────────┐
│   Strategy Team     │ 1:N     │      Agent       │
│  - symbol           │────────▶│  - agent_type    │
│  - agent_assignments│         │  - rl_model_path │
└─────────────────────┘         └────────┬─────────┘
                                         │ N:1
                                         ▼
                                ┌──────────────────┐
                                │ RL Training Run  │
                                │  - algorithm     │
                                │  - final_metrics │
                                └────────┬─────────┘
                                         │ 1:N
                                         ▼
                                ┌──────────────────┐
                                │Model Configuration│
                                │  - variant_name  │
                                │  - traffic_pct   │
                                └──────────────────┘

Decision Pipeline Flow:
┌──────────────────┐
│ Analyst Reports  │──┐
│  - Technical     │  │
│  - Fundamental   │  ├──▶┌──────────────┐
│  - Sentiment     │  │   │ Trade Intent │
└──────────────────┘  │   │  - direction │
                      │   │  - conviction│
┌──────────────────┐  │   └──────┬───────┘
│ Debate Outcome   │──┘          │
│  - bull_case     │             ▼
│  - bear_case     │      ┌──────────────┐
│  - synthesis     │      │Position Size │
└──────────────────┘      │  - kelly     │
                          │  - lot_size  │
                          └──────┬───────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
         ┌──────────────┐               ┌──────────────┐
         │  Stop Loss   │               │ Take Profit  │
         │  - stop_price│               │  - targets[] │
         └──────┬───────┘               └──────┬───────┘
                │                              │
                └────────────┬─────────────────┘
                             ▼
                    ┌──────────────────┐
                    │  Decision Log    │
                    │  - inputs        │
                    │  - rationale     │
                    │  - outcome       │
                    │  - pnl           │
                    └──────────────────┘

MCP Tools:
┌──────────────────┐
│    MCP Tool      │──┐
│  - tool_name     │  │
│  - input_schema  │  ├──▶ Called by all Agents
│  - output_schema │  │
│  - cache_ttl     │  │
└──────────────────┘──┘
```

## Indexes and Performance Optimization

### TimescaleDB Indexes (decision_log)
```sql
-- Core query patterns
CREATE INDEX idx_decision_log_agent_id ON decision_log (agent_id, timestamp DESC);
CREATE INDEX idx_decision_log_symbol ON decision_log (symbol, timestamp DESC);
CREATE INDEX idx_decision_log_correlation ON decision_log (correlation_id);
CREATE INDEX idx_decision_log_type_outcome ON decision_log (decision_type, outcome, timestamp DESC);

-- Gin index for JSONB queries
CREATE INDEX idx_decision_log_inputs ON decision_log USING gin (inputs);

-- Performance monitoring
CREATE INDEX idx_decision_log_latency ON decision_log (decision_latency_ms DESC)
WHERE decision_latency_ms > 1000; -- Partial index for slow decisions
```

### PostgreSQL Indexes (other tables)
```sql
-- Agent lookups
CREATE UNIQUE INDEX idx_agent_id ON agents (agent_id);
CREATE INDEX idx_agent_symbol_type ON agents (symbol, agent_type) WHERE is_active = true;

-- Strategy team performance queries
CREATE INDEX idx_strategy_team_symbol ON strategy_teams (symbol, is_active);

-- Portfolio allocation active lookup
CREATE UNIQUE INDEX idx_portfolio_allocation_active ON portfolio_allocations (is_active)
WHERE is_active = true; -- Only one active allocation

-- RL training run queries
CREATE INDEX idx_rl_run_agent_symbol ON rl_training_runs (agent_type, symbol, status);
CREATE INDEX idx_rl_run_deployed ON rl_training_runs (is_deployed, deployment_stage);

-- Model configuration experiments
CREATE INDEX idx_model_config_experiment ON model_configurations (experiment_name, is_active);
CREATE INDEX idx_model_config_winner ON model_configurations (is_winner, promoted_at DESC);

-- MCP tool lookups
CREATE UNIQUE INDEX idx_mcp_tool_name_version ON mcp_tools (tool_name, version);
CREATE INDEX idx_mcp_tool_active ON mcp_tools (tool_category, is_active);
```

## Validation Summary

All entities comply with:
- ✅ **Pydantic v2 schemas** for runtime validation
- ✅ **PostgreSQL constraints** for data integrity
- ✅ **TimescaleDB partitioning** for time-series data (decision_log)
- ✅ **Redis caching** for transient data (analyst reports, agent state)
- ✅ **MLflow integration** for RL model versioning
- ✅ **Structured audit trail** via decision_log with 90-day retention

## Next Steps

With the data model defined, the next phase is:
1. **Generate API contracts** (contracts/mcp-tools.yaml, contracts/agent-events.yaml)
2. **Create quickstart.md** for running the agent system
3. **Proceed to Phase 2**: Task breakdown via `/speckit.tasks`
