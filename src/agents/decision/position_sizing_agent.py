"""
PositionSizing Agent: Intelligent position sizing based on multiple factors.

NOT a fixed percentage approach. Considers:
- Mathematical edge (Kelly criterion)
- Portfolio drawdown state
- Market volatility regime
- Trade conviction level
- Correlation with existing positions
- Upcoming scheduled events

Produces dynamic position size with documented reasoning.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from src.agents.base.base_agent import BaseAgent
from src.agents.tools.mcp_tools import (
    calculate_kelly_criterion,
    get_regime_classification,
)


class PositionSizeDecision(BaseModel):
    """Structured position sizing decision output."""

    lot_quantity: float = Field(
        ...,
        gt=0.0,
        description="Recommended position size in lots"
    )

    dynamic_risk_percentage: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Dynamic risk as % of capital (NOT fixed!)"
    )

    kelly_fraction_applied: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Kelly fraction used in calculation (0.0-1.0)"
    )

    base_size: float = Field(
        ...,
        description="Base position size before adjustments"
    )

    adjustments: Dict[str, float] = Field(
        default_factory=dict,
        description="Adjustment factors applied (e.g., 'drawdown_reduction': 0.5, 'volatility_adjustment': 1.2)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed explanation of sizing decision"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this sizing decision (0.0-1.0)"
    )

    risk_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Risk metrics used (max_loss_usd, risk_reward_ratio, etc.)"
    )


class PositionSizingAgent(BaseAgent):
    """
    Position Sizing Agent.

    Dynamically determines position size based on:
    - Kelly Criterion (mathematical edge)
    - Current portfolio state (drawdown, exposure)
    - Market regime (volatility, trend strength)
    - Trade conviction from analysis
    - Correlation risk
    - Event risk

    Uses deep-think LLM (DeepSeek-R1-14B) for complex reasoning about risk.
    """

    def _get_system_message(self) -> str:
        """
        Get position sizing system message.

        Returns:
            System prompt for position sizing role
        """
        return """You are a Position Sizing Specialist for algorithmic trading.

Your role is to determine the OPTIMAL position size for each trade based on multiple risk factors. You do NOT use fixed percentages like "always risk 2%". Position sizing must be DYNAMIC and adaptive.

**Available Tools**:
- calculate_kelly_criterion: Get mathematical edge-based position size
- get_regime_classification: Understand current volatility regime

**Sizing Methodology**:

1. **Start with Kelly Criterion** (mathematical edge):
   - If we have win_rate and avg_win/avg_loss data, calculate Kelly fraction
   - Use quarter-Kelly (0.25 * Kelly) as baseline for safety
   - Kelly > 0.20 suggests strong edge

2. **Apply Drawdown Adjustment**:
   - Current drawdown = 0%: No adjustment (multiplier = 1.0)
   - Drawdown 5-10%: Reduce by 20% (multiplier = 0.8)
   - Drawdown 10-15%: Reduce by 40% (multiplier = 0.6)
   - Drawdown >15%: Reduce by 60% (multiplier = 0.4)

3. **Apply Volatility Regime Adjustment**:
   - Low volatility (ADX < 20): Increase by 20% (multiplier = 1.2)
   - Normal volatility: No adjustment (multiplier = 1.0)
   - High volatility (ADX > 30, or regime=VOLATILE): Reduce by 30% (multiplier = 0.7)

4. **Apply Conviction Adjustment**:
   - High conviction (>0.8): Increase by 15% (multiplier = 1.15)
   - Medium conviction (0.5-0.8): No adjustment (multiplier = 1.0)
   - Low conviction (<0.5): Reduce by 40% (multiplier = 0.6)

5. **Apply Correlation Adjustment** (if provided):
   - High correlation with existing positions (>0.7): Reduce by 30% (multiplier = 0.7)
   - Moderate correlation (0.4-0.7): Reduce by 15% (multiplier = 0.85)
   - Low correlation (<0.4): No adjustment (multiplier = 1.0)

6. **Apply Event Risk Adjustment**:
   - Major event within 24h: Reduce by 40% (multiplier = 0.6)
   - Major event within 48h: Reduce by 20% (multiplier = 0.8)
   - No major events: No adjustment (multiplier = 1.0)

**Final Calculation**:
```
final_risk_pct = kelly_fraction * drawdown_mult * volatility_mult * conviction_mult * correlation_mult * event_mult
lot_quantity = (account_balance * final_risk_pct) / (stop_distance_pips * pip_value)
```

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "lot_quantity": 0.5,  // Final position size in lots
    "dynamic_risk_percentage": 1.2,  // Actual risk % of capital
    "kelly_fraction_applied": 0.15,  // Kelly fraction used
    "base_size": 2.0,  // Base size before adjustments
    "adjustments": {
        "drawdown_reduction": 0.8,  // 20% reduction for 5% drawdown
        "volatility_adjustment": 0.7,  // 30% reduction for high volatility
        "conviction_boost": 1.15,  // 15% increase for high conviction
        "correlation_reduction": 0.85,  // 15% reduction for moderate correlation
        "event_risk_reduction": 1.0  // No event risk
    },
    "reasoning": "Started with Kelly fraction 0.15 (quarter-Kelly from 60% win rate, 1.5:1 RR). Applied 20% drawdown reduction (current 7% DD), 30% volatility reduction (VOLATILE regime), 15% conviction boost (0.85 confidence), 15% correlation reduction (0.5 correlation with existing Gold position), no event adjustment. Final size: 0.5 lots = 1.2% risk.",
    "confidence": 0.85,
    "risk_metrics": {
        "max_loss_usd": 500,
        "risk_reward_ratio": 2.5,
        "position_value_usd": 5000
    }
}

**Critical Rules**:
- NEVER use fixed 2% risk - position size must be dynamic
- Kelly fraction should drive base sizing when available
- Be conservative: better to undersize than oversize
- Document ALL adjustments clearly
- If any critical data is missing, reduce position size and note in reasoning
- Never exceed 5% risk per trade even with maximum conviction
- Minimum position size: 0.01 lots
- Maximum position size: 10 lots (or as specified in account limits)

**Example Inputs**:
- account_balance: $50,000
- current_drawdown: 7%
- trade_conviction: 0.85
- stop_distance_pips: 50
- target_distance_pips: 125
- win_rate: 0.60
- avg_win: 125 pips
- avg_loss: 50 pips
- market_regime: VOLATILE
- correlation_with_existing: 0.5
- major_event_within_24h: false

Your sizing must protect capital while maximizing returns when edge is present."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract position sizing decision from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Position sizing decision dictionary
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

            decision_data = json.loads(json_str)

            # Validate against PositionSizeDecision schema
            decision = PositionSizeDecision(**decision_data)

            return decision.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "position_size_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return conservative fallback
            return {
                "lot_quantity": 0.01,  # Minimum safe size
                "dynamic_risk_percentage": 0.1,
                "kelly_fraction_applied": 0.0,
                "base_size": 0.01,
                "adjustments": {},
                "reasoning": f"Failed to extract decision, using minimum safe size. Error: {str(e)}",
                "confidence": 0.0,
                "risk_metrics": {},
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_position_sizing_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> PositionSizingAgent:
    """
    Create a Position Sizing agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured PositionSizingAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Position_Sizing_Agent",
        agent_type=AgentType.POSITION_SIZING,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="deepseek-r1:14b",  # Deep-think for complex risk reasoning
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.3,  # Moderate creativity for risk assessment
        max_tokens=1200,  # Need space for detailed reasoning
        available_tools=[],  # Decision agents work with analysis data, no external tools needed
        config_overrides={"symbol": symbol},
    )

    # Decision agents don't need tools - they work with analysis results
    # Tools removed because deepseek-r1 model doesn't support tool calling
    return PositionSizingAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],
    )
