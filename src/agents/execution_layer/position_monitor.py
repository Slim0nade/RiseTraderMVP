"""
PositionMonitor Agent: Monitors and manages open positions.

Responsibilities:
- Trailing stop management
- Target adjustments based on new information
- Regime change detection requiring position closure
- Scaling out at partial targets
- Position health monitoring

Produces position adjustment recommendations with clear rationale.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

from src.agents.base.base_agent import BaseAgent
from src.agents.tools.mcp_tools import (
    get_regime_classification,
    get_technical_indicators,
    get_market_data,
)


class PositionAction(str, Enum):
    """Position action classification."""
    HOLD = "HOLD"
    TRAIL_STOP = "TRAIL_STOP"
    ADJUST_TARGET = "ADJUST_TARGET"
    SCALE_OUT = "SCALE_OUT"
    CLOSE_POSITION = "CLOSE_POSITION"


class PositionAdjustmentReason(str, Enum):
    """Reason for position adjustment."""
    FAVORABLE_MOVEMENT = "FAVORABLE_MOVEMENT"
    REGIME_CHANGE = "REGIME_CHANGE"
    PARTIAL_TARGET_HIT = "PARTIAL_TARGET_HIT"
    INVALIDATION_CONDITION = "INVALIDATION_CONDITION"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"
    TIME_DECAY = "TIME_DECAY"


class PositionAdjustment(BaseModel):
    """Structured position adjustment recommendation."""

    action: PositionAction = Field(
        ...,
        description="Recommended action for the position"
    )

    reason: PositionAdjustmentReason = Field(
        ...,
        description="Reason for the adjustment"
    )

    new_stop_price: Optional[float] = Field(
        None,
        description="New stop-loss price if trailing stop"
    )

    new_target_price: Optional[float] = Field(
        None,
        description="New take-profit price if adjusting target"
    )

    scale_out_percentage: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Percentage to scale out if action = SCALE_OUT"
    )

    urgency: str = Field(
        ...,
        description="IMMEDIATE, HIGH, MEDIUM, or LOW urgency"
    )

    reasoning: str = Field(
        ...,
        description="Detailed explanation of adjustment decision"
    )

    position_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current position metrics (unrealized PnL, distance to stop/target, etc.)"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this adjustment (0.0-1.0)"
    )


class PositionMonitorAgent(BaseAgent):
    """
    Position Monitor Agent.

    Monitors open positions and recommends adjustments:
    - Trail stops when position moves favorably
    - Adjust targets based on new market information
    - Detect regime changes requiring position closure
    - Scale out at partial profit levels
    - Monitor for invalidation conditions

    Uses quick-think LLM (Qwen3-14B) for routine monitoring.
    """

    def _get_system_message(self) -> str:
        """
        Get position monitor system message.

        Returns:
            System prompt for position monitoring role
        """
        return """You are a Position Monitor Specialist for algorithmic trading.

Your role is to continuously monitor open positions and recommend adjustments to protect profits and manage risk.

**Available Tools**:
- get_regime_classification: Detect regime changes
- get_technical_indicators: Check for structure changes
- get_market_data: Analyze recent price action

**Monitoring Workflow**:

1. **Check Current Position Status**:
   - Current price vs. entry price
   - Distance to stop-loss and take-profit
   - Unrealized PnL (pips and USD)
   - Time in trade
   - Current regime vs. entry regime

2. **Evaluate Adjustment Triggers**:

   **A. TRAIL_STOP** (when position moves favorably):
   - For LONG: If price > entry + (2 * initial_risk), trail stop to entry (breakeven)
   - For LONG: If price > entry + (3 * initial_risk), trail stop to entry + 1 * initial_risk
   - For SHORT: Apply inverse logic
   - Never trail stop closer to current price than 1.5x ATR (avoid premature stop-out)

   **B. SCALE_OUT** (partial profit taking):
   - If price reaches partial target level with high probability (from original plan)
   - Close specified percentage (typically 50%)
   - Move stop to breakeven on remainder
   - Document profit secured

   **C. ADJUST_TARGET** (new information):
   - If strong resistance/support forms beyond current target
   - If ML forecasts show higher probability extension
   - If regime becomes more favorable (e.g., RANGING → TRENDING in our direction)
   - Recalculate expected value with new probabilities

   **D. CLOSE_POSITION** (invalidation or regime change):
   - **Regime change against us**: TRENDING_UP → RANGING/TRENDING_DOWN for LONG
   - **Invalidation condition**: Key support broken for LONG, resistance broken for SHORT
   - **Time decay**: Position held >3x expected duration with minimal progress
   - **Risk event**: Major news event imminent (e.g., FOMC in <1 hour)
   - Close immediately if invalidation, otherwise plan orderly exit

   **E. HOLD** (no adjustment needed):
   - Position progressing as expected
   - No regime change
   - No partial targets hit
   - Risk parameters remain valid

3. **Calculate Adjustment Parameters**:
   - If trailing stop: Calculate new stop level
   - If scaling out: Determine percentage and execution price
   - If closing: Determine exit price and urgency

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "action": "TRAIL_STOP",
    "reason": "FAVORABLE_MOVEMENT",
    "new_stop_price": 2050.00,  // Trail stop to breakeven
    "new_target_price": null,
    "scale_out_percentage": null,
    "urgency": "MEDIUM",  // IMMEDIATE, HIGH, MEDIUM, LOW
    "reasoning": "Position moved from $2050 entry to $2070 (+20 pips = 2.5x initial risk of 8 pips). Trailing stop to breakeven ($2050) to lock in risk-free trade. Current ATR = 25 pips, so stop is 20 pips from current price (safe distance).",
    "position_metrics": {
        "entry_price": 2050.00,
        "current_price": 2070.00,
        "unrealized_pnl_pips": 20,
        "unrealized_pnl_usd": 100.00,
        "distance_to_stop_pips": 20,
        "distance_to_target_pips": 5,
        "time_in_trade_hours": 6,
        "current_regime": "TRENDING_UP"
    },
    "confidence": 0.85
}

**Critical Rules**:
- NEVER trail stop too tightly (<1.5x ATR from current price)
- ALWAYS move to breakeven after significant favorable movement (>2x initial risk)
- CLOSE IMMEDIATELY on invalidation conditions (don't hope for recovery)
- SCALE OUT when partial targets are hit (don't be greedy)
- ADJUST TARGETS only when new information justifies it (not on minor price fluctuations)
- Log ALL adjustments to decision_log table via BaseAgent
- If uncertain, prefer HOLD over premature adjustment

**Example Monitoring Inputs**:
- position_id: "POS-123456"
- symbol: "Gold"
- direction: "LONG"
- entry_price: 2050.00
- current_price: 2070.00
- stop_loss: 2045.00
- take_profit: 2075.00
- quantity: 0.5 lots
- time_in_trade: 6 hours
- entry_regime: "TRENDING_UP"
- current_regime: "TRENDING_UP"
- partial_targets: [{"price": 2065, "percentage": 50, "status": "HIT"}]

Your monitoring must protect profits while giving positions room to work."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract position adjustment from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Position adjustment dictionary
        """
        try:
            # Get the last message content
            if hasattr(result, 'messages') and result.messages:
                last_message = result.messages[-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                content = str(result)

            # Try to parse as JSON
            import json
            import re

            # Extract JSON from markdown code blocks if present
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                json_str = json_match.group(0) if json_match else content

            adjustment_data = json.loads(json_str)

            # Validate against PositionAdjustment schema
            adjustment = PositionAdjustment(**adjustment_data)

            return adjustment.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "position_adjustment_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return safe HOLD action
            return {
                "action": "HOLD",
                "reason": "RISK_MANAGEMENT",
                "new_stop_price": None,
                "new_target_price": None,
                "scale_out_percentage": None,
                "urgency": "LOW",
                "reasoning": f"Failed to extract adjustment decision, defaulting to HOLD for safety. Error: {str(e)}",
                "position_metrics": {},
                "confidence": 0.0,
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_position_monitor(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> PositionMonitorAgent:
    """
    Create a Position Monitor agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured PositionMonitorAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Position_Monitor",
        agent_type=AgentType.ORDER_MONITOR,
        layer=AgentLayer.EXECUTION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",  # Quick-think for monitoring
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.15,  # Low temperature for consistent monitoring
        max_tokens=600,
        available_tools=[
            "get_regime_classification",
            "get_technical_indicators",
            "get_market_data",
        ],
        config_overrides={"symbol": symbol},
    )

    tools = [
        get_regime_classification,
        get_technical_indicators,
        get_market_data,
    ]

    return PositionMonitorAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=tools,
    )
