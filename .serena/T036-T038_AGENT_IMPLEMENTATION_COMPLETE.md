# Agent Implementation Complete: T036-T038

**Date**: 2025-12-02
**Session**: Continuation from Feature 005 Session Final Summary
**Status**: ✅ Core Agents Implemented

---

## 📦 Files Created (8 total)

### Analysis Layer (3 agents)
```
src/agents/analysis/
├── __init__.py
├── technical_analyst.py      [TechnicalAnalystAgent]
├── fundamental_analyst.py    [FundamentalAnalystAgent]
└── sentiment_analyst.py      [SentimentAnalystAgent]
```

### Decision Layer (3 agents)
```
src/agents/decision/
├── __init__.py
├── position_sizing_agent.py   [PositionSizingAgent]
├── stop_loss_agent.py         [StopLossAgent]
└── take_profit_agent.py       [TakeProfitAgent]
```

---

## ✅ Analysis Layer Agents

### 1. TechnicalAnalystAgent
**LLM Tier**: Quick-think (Qwen3-14B)
**Purpose**: Technical analysis using ML forecasts and indicators

**Tools Available**:
- `get_tcn_forecast` - TCN model predictions with confidence
- `get_xgboost_forecast` - Fast XGBoost forecasts
- `get_lstm_forecast` - LSTM sequential predictions
- `get_regime_classification` - Market regime detection
- `get_technical_indicators` - RSI, MACD, BB, ATR, ADX
- `get_market_data` - OHLCV historical data
- `get_forecast_accuracy` - Model performance metrics

**Output**: `TechnicalReport`
```python
{
    "directional_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence": 0.85,
    "current_price": 2050.00,
    "support_levels": [2045, 2040],
    "resistance_levels": [2055, 2060],
    "model_agreement": 0.75,  # 3/4 models agree
    "regime": "TRENDING_UP",
    "key_indicators": {"rsi": 62, "macd_signal": "BULLISH", "atr": 25, "adx": 28},
    "forecast_summary": "ML models show 70% upside probability to $2060",
    "risk_factors": ["RSI approaching overbought", "Resistance at $2055"]
}
```

---

### 2. FundamentalAnalystAgent
**LLM Tier**: Quick-think (Qwen3-14B)
**Purpose**: Macro and fundamental context analysis

**Tools Available**: None yet (future: economic calendar, correlation APIs)

**Output**: `FundamentalReport`
```python
{
    "macro_sentiment": "RISK_OFF",
    "macro_context": "USD weakness driving Gold demand, geopolitical tensions elevated",
    "upcoming_events": [
        {
            "event_name": "FOMC Meeting",
            "event_time": "2025-12-15T14:00:00Z",
            "importance": "HIGH",
            "expected_impact": "Potential USD volatility"
        }
    ],
    "correlation_insights": {
        "usd_strength": "Strong inverse correlation with Gold",
        "equity_correlation": "Low correlation with S&P 500"
    },
    "fundamental_drivers": [
        "USD weakness driving Gold higher",
        "Inflation expectations rising"
    ],
    "risk_factors": ["FOMC meeting in 2 days could reverse USD trend"],
    "confidence": 0.70
}
```

---

### 3. SentimentAnalystAgent
**LLM Tier**: Quick-think (Qwen3-14B)
**Purpose**: Sentiment and positioning analysis

**Tools Available**: None yet (future: COT data, retail sentiment APIs)

**Output**: `SentimentReport`
```python
{
    "crowd_sentiment": "EXTREMELY_BULLISH",
    "crowd_metrics": {
        "retail_long_percent": 85,
        "fear_greed_index": 75
    },
    "smart_money_flow": "DISTRIBUTING",
    "sentiment_divergence": True,  # Crowd vs. smart money mismatch
    "contrarian_signal": True,     # Extreme sentiment = potential reversal
    "order_flow_insights": {
        "large_buy_orders": "Concentrated above current price",
        "institutional_flow": "Net selling over last 3 sessions"
    },
    "sentiment_summary": "Retail 85% long while institutions reduce positions - bearish divergence",
    "risk_factors": ["Crowded long positioning vulnerable to squeeze"],
    "confidence": 0.75
}
```

---

## ✅ Decision Layer Agents

### 4. PositionSizingAgent
**LLM Tier**: Deep-think (DeepSeek-R1-14B)
**Purpose**: Dynamic position sizing (NOT fixed percentage!)

**Tools Available**:
- `calculate_kelly_criterion` - Mathematical edge calculation
- `get_regime_classification` - Volatility regime for adjustment

**Methodology**:
1. Start with Kelly Criterion (mathematical edge)
2. Apply drawdown adjustment (0-60% reduction based on DD)
3. Apply volatility regime adjustment (VOLATILE = 30% reduction)
4. Apply conviction adjustment (high conviction = 15% boost)
5. Apply correlation adjustment (high correlation = 30% reduction)
6. Apply event risk adjustment (major event <24h = 40% reduction)

**Output**: `PositionSizeDecision`
```python
{
    "lot_quantity": 0.5,
    "dynamic_risk_percentage": 1.2,  # Actual risk % (not fixed!)
    "kelly_fraction_applied": 0.15,
    "base_size": 2.0,
    "adjustments": {
        "drawdown_reduction": 0.8,      # 20% reduction for 5% DD
        "volatility_adjustment": 0.7,   # 30% reduction for VOLATILE regime
        "conviction_boost": 1.15,       # 15% increase for 0.85 conviction
        "correlation_reduction": 0.85,  # 15% reduction for 0.5 correlation
        "event_risk_reduction": 1.0     # No event risk
    },
    "reasoning": "Kelly 0.15 → drawdown reduction → volatility reduction → conviction boost → final 0.5 lots",
    "confidence": 0.85,
    "risk_metrics": {"max_loss_usd": 500, "risk_reward_ratio": 2.5}
}
```

---

### 5. StopLossAgent
**LLM Tier**: Deep-think (DeepSeek-R1-14B)
**Purpose**: Intelligent stop placement (NOT fixed ATR multiple!)

**Tools Available**:
- `get_technical_indicators` - ATR and indicators
- `get_regime_classification` - Regime for adaptive ATR multipliers
- `get_market_data` - Price structure analysis

**Methodology**:
1. Calculate base ATR distance with adaptive multiplier:
   - Low volatility: 1.2x ATR
   - Normal: 1.5x ATR
   - High volatility: 2.5x ATR
   - Trending: 2.0x ATR
2. Identify nearest support/resistance
3. Choose strategy:
   - **STRUCTURE_BASED**: Place beyond structure level
   - **ATR_BASED**: Use adaptive ATR multiplier
   - **HYBRID**: Blend both approaches
4. Avoid liquidity traps (round numbers, common ATR multiples)

**Output**: `StopLossDecision`
```python
{
    "stop_price": 2045.30,
    "atr_distance_pips": 55,
    "atr_multiplier": 2.2,  # Adaptive, not fixed!
    "placement_strategy": "HYBRID",
    "nearest_structure_level": 2048.00,
    "estimated_hit_probability": 0.25,
    "reasoning": "Support at $2048, ATR 25 pips. HYBRID: respected support while ensuring stop beyond noise.",
    "risk_factors": ["Support only tested twice", "Liquidity cluster at $2045"],
    "confidence": 0.80
}
```

---

### 6. TakeProfitAgent
**LLM Tier**: Deep-think (DeepSeek-R1-14B)
**Purpose**: Probabilistic targeting (NOT fixed risk-reward!)

**Tools Available**:
- `get_tcn_forecast` - Probability distributions
- `get_xgboost_forecast` - Additional forecasts
- `get_lstm_forecast` - Sequential predictions
- `get_technical_indicators` - Resistance levels
- `get_market_data` - Price structure

**Methodology**:
1. Gather ML forecast probability distributions
2. Identify key resistance/support levels
3. Calculate expected value for different targets:
   - EV = (P_target × Reward) - (P_stop × Risk)
4. Evaluate partial profit opportunities:
   - Take 50% at high-probability zone (70% P)
   - Let 50% run to extension (40% P)
5. Maximize expected value, not risk-reward ratio

**Output**: `TakeProfitDecision`
```python
{
    "primary_target_price": 2075.00,
    "primary_target_pips": 50,
    "dynamic_risk_reward_ratio": 1.8,  # 50 pips / 28 pips
    "estimated_reach_probability": 0.65,
    "expected_value": 22.5,  # (0.65 * 50) - (0.35 * 28)
    "partial_targets": [
        {
            "target_price": 2065.00,
            "close_percentage": 50,
            "estimated_probability": 0.75,
            "reasoning": "75% probability within 30 pips - lock in half"
        },
        {
            "target_price": 2075.00,
            "close_percentage": 50,
            "estimated_probability": 0.65,
            "reasoning": "Let remainder run to resistance"
        }
    ],
    "nearest_resistance_level": 2078.00,
    "reasoning": "EV maximized at $22.5 with partials vs. $18 full exit early",
    "risk_factors": ["Resistance at $2078 may cap upside"],
    "confidence": 0.70
}
```

---

## 🎯 Key Design Principles

### 1. NO FIXED RULES
- Position sizing: Dynamic based on Kelly, drawdown, volatility, conviction
- Stop-loss: Adaptive ATR multipliers based on regime + structure
- Take-profit: Probability-driven, expected value optimized

### 2. Deep-Think vs. Quick-Think
- **Analysis agents** (Technical, Fundamental, Sentiment): Quick-think (Qwen3-14B)
  - Routine data gathering and summarization
  - Fast inference (<2s)
- **Decision agents** (Position Sizing, Stop-Loss, Take-Profit): Deep-think (DeepSeek-R1-14B)
  - Complex reasoning about risk and probability
  - Deeper inference (~10s)

### 3. Structured Outputs
- All agents return Pydantic-validated schemas
- Extraction failures handled with conservative fallbacks
- Clear reasoning documentation in all decisions

### 4. Tool Integration
- Analysis agents: Access to MCP tools (ML forecasts, indicators, regime detection)
- Decision agents: Access to calculation tools (Kelly, regime classification)

---

## 🧪 Usage Example

```python
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.analysis import create_technical_analyst
from src.agents.decision import (
    create_position_sizing_agent,
    create_stop_loss_agent,
    create_take_profit_agent,
)

# Create analysis agent
technical_analyst = create_technical_analyst(
    agent_id=uuid4(),
    session=session,  # AsyncSession
    symbol="Gold",
    strategy_team_id=None,
)

# Run technical analysis
technical_report = await technical_analyst.run(
    task="Analyze Gold technical conditions for 4H swing trade",
    context={"timeframe": "4H", "horizon": "2-5 days"},
)

print(f"Bias: {technical_report['directional_bias']}")
print(f"Confidence: {technical_report['confidence']}")
print(f"Regime: {technical_report['regime']}")

# Create decision agents
position_sizer = create_position_sizing_agent(
    agent_id=uuid4(),
    session=session,
    symbol="Gold",
)

stop_loss_agent = create_stop_loss_agent(
    agent_id=uuid4(),
    session=session,
    symbol="Gold",
)

take_profit_agent = create_take_profit_agent(
    agent_id=uuid4(),
    session=session,
    symbol="Gold",
)

# Get position size recommendation
position_decision = await position_sizer.run(
    task="Determine position size for Gold long trade",
    context={
        "account_balance": 50000,
        "current_drawdown": 0.07,  # 7% drawdown
        "trade_conviction": 0.85,
        "win_rate": 0.60,
        "avg_win": 125,
        "avg_loss": 50,
        "market_regime": "VOLATILE",
        "correlation_with_existing": 0.5,
    },
)

print(f"Position size: {position_decision['lot_quantity']} lots")
print(f"Risk: {position_decision['dynamic_risk_percentage']}%")
print(f"Reasoning: {position_decision['reasoning']}")

# Get stop-loss recommendation
stop_decision = await stop_loss_agent.run(
    task="Determine stop-loss for Gold long trade at $2050",
    context={
        "entry_price": 2050.00,
        "direction": "LONG",
        "timeframe": "4H",
        "recent_swing_low": 2048.00,
    },
)

print(f"Stop price: ${stop_decision['stop_price']}")
print(f"Strategy: {stop_decision['placement_strategy']}")

# Get take-profit recommendation
tp_decision = await take_profit_agent.run(
    task="Determine take-profit for Gold long trade",
    context={
        "entry_price": 2050.00,
        "stop_price": stop_decision['stop_price'],
        "direction": "LONG",
        "timeframe": "4H",
    },
)

print(f"Target: ${tp_decision['primary_target_price']}")
print(f"Risk-reward: {tp_decision['dynamic_risk_reward_ratio']:.2f}:1")
print(f"Probability: {tp_decision['estimated_reach_probability']:.1%}")
print(f"Expected value: ${tp_decision['expected_value']:.2f}")
```

---

## 📊 Architecture Summary

```
User Request
    ↓
TechnicalAnalyst (quick-think) → TechnicalReport
FundamentalAnalyst (quick-think) → FundamentalReport
SentimentAnalyst (quick-think) → SentimentReport
    ↓
[Debate Layer - to be implemented]
    ↓
PositionSizingAgent (deep-think) → PositionSizeDecision
StopLossAgent (deep-think) → StopLossDecision
TakeProfitAgent (deep-think) → TakeProfitDecision
    ↓
[Execution Layer - to be implemented]
```

---

## ✅ What's Complete

1. ✅ All 6 core agent implementations
2. ✅ Pydantic schemas for structured outputs
3. ✅ Factory functions for easy instantiation
4. ✅ Tool integration (MCP tools wired to agents)
5. ✅ Comprehensive system prompts with methodologies
6. ✅ Error handling with conservative fallbacks
7. ✅ LLM tier selection (quick-think vs. deep-think)
8. ✅ Decision logging via BaseAgent

---

## 🚧 What's Pending

### Immediate Next Steps:
1. **Execution Layer Stub Agents** (basic scaffolding):
   - `TradeExecutorAgent` (executes via MT4/ZMQ)
   - `PositionMonitorAgent` (trails stops, manages positions)

2. **Service Layer** (T044-T046):
   - `AgentService` - High-level agent orchestration
   - Agent lifecycle management (create, start, stop, health check)

3. **API Endpoints** (T047-T050):
   - `POST /api/v1/agents/analysis/run` - Run analysis team
   - `POST /api/v1/agents/decision/run` - Run decision agents
   - `GET /api/v1/agents/health` - Agent health status
   - `GET /api/v1/agents/registry/stats` - Registry statistics

4. **Integration Testing**:
   - Test full pipeline: Analysis → Decision
   - Test with real Ollama models (need to pull models first)
   - Test MCP tool integration with Feature 003 ML API

### Medium Priority:
5. **Debate Layer Implementation** (bull/bear researcher agents)
6. **Concrete tool endpoints** in ML service (if not already present)
7. **Economic calendar integration** for FundamentalAnalyst
8. **Sentiment data integration** for SentimentAnalyst

---

## 🎉 Achievement Summary

**Files Created**: 8 (6 agents + 2 `__init__.py`)
**Lines of Code**: ~2,000
**Schemas Defined**: 9 (TechnicalReport, FundamentalReport, SentimentReport, PositionSizeDecision, StopLossDecision, TakeProfitDecision, + supporting schemas)
**MCP Tools Integrated**: 8 (forecasts, regime, Kelly, indicators, market data)
**System Prompts**: 6 comprehensive prompts with methodologies

**Key Innovation**: NO FIXED RULES - all decisions are dynamic, data-driven, and adaptive to market conditions.

---

*Generated by Claude Code - Feature 005 Agent Implementation Session*
*Next: Execution layer stubs + Service layer + API endpoints*
