"""
TakeProfit Agent: Probabilistic take-profit targeting.

NOT a fixed risk-reward ratio. Considers:
- ML forecast probability distributions
- Key resistance/support levels
- Risk-reward vs. probability trade-offs
- Partial profit opportunities (scaling out)

Produces probabilistic targets with expected value optimization.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.agents.base.base_agent import BaseAgent
from src.agents.tools.mcp_tools import (
    get_tcn_forecast,
    get_xgboost_forecast,
    get_lstm_forecast,
    get_technical_indicators,
    get_market_data,
)


class PartialTarget(BaseModel):
    """Partial profit target structure."""

    target_price: float = Field(..., description="Price level for this target")
    close_percentage: int = Field(..., ge=0, le=100, description="% of position to close")
    estimated_probability: float = Field(..., ge=0.0, le=1.0, description="P(reach this target)")
    reasoning: str = Field(..., description="Why this partial target makes sense")


class TakeProfitDecision(BaseModel):
    """Structured take-profit decision output."""

    primary_target_price: float = Field(
        ...,
        description="Primary take-profit price level"
    )

    primary_target_pips: float = Field(
        ...,
        description="Distance to primary target in pips"
    )

    dynamic_risk_reward_ratio: float = Field(
        ...,
        gt=0.0,
        description="Dynamically calculated risk-reward ratio (NOT fixed!)"
    )

    estimated_reach_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated probability of reaching primary target"
    )

    expected_value: float = Field(
        ...,
        description="Expected value of this trade (probability * reward - probability * risk)"
    )

    partial_targets: List[PartialTarget] = Field(
        default_factory=list,
        description="Optional partial profit targets for scaling out"
    )

    nearest_resistance_level: float | None = Field(
        None,
        description="Nearest resistance/support level affecting target"
    )

    reasoning: str = Field(
        ...,
        description="Detailed explanation of target placement logic"
    )

    risk_factors: List[str] = Field(
        default_factory=list,
        description="Risk factors related to target placement"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this target placement (0.0-1.0)"
    )


class TakeProfitAgent(BaseAgent):
    """
    Take-Profit Agent.

    Probabilistically sets take-profit targets considering:
    - ML forecast probability distributions (not fixed RR)
    - Key market structure levels (resistance/support)
    - Expected value optimization
    - Partial profit opportunities

    Uses deep-think LLM (DeepSeek-R1-14B) for probability reasoning.
    """

    def _get_system_message(self) -> str:
        """
        Get take-profit system message.

        Returns:
            System prompt for take-profit targeting role
        """
        return """You are a Take-Profit Targeting Specialist for algorithmic trading.

Your role is to determine the OPTIMAL take-profit target(s) for each trade. You do NOT use fixed risk-reward ratios like "always 2:1 RR". Target placement must be based on PROBABILITY DISTRIBUTIONS and EXPECTED VALUE optimization.

**Available Tools**:
- get_tcn_forecast: Get ML forecast with probability distributions
- get_xgboost_forecast: Get XGBoost forecast
- get_lstm_forecast: Get LSTM forecast
- get_technical_indicators: Get resistance levels (for LONG) or support (for SHORT)
- get_market_data: Analyze price structure for key levels

**Target Placement Methodology**:

1. **Gather ML Forecast Probability Distributions**:
   - Get forecasts from multiple models (TCN, XGBoost, LSTM)
   - Identify probability mass concentration zones
   - Example: TCN shows 70% probability within 30 pips, 15% probability at 50+ pips

2. **Identify Key Market Structure Levels**:
   - For LONG trades: Find nearest resistance levels above entry
   - For SHORT trades: Find nearest support levels below entry
   - Consider: Recent swing highs/lows, round numbers, Fibonacci levels
   - Strong resistance can cap upside (reduce target)

3. **Calculate Expected Value for Different Targets**:
   - EV = (P_target * Reward) - (P_stop * Risk)
   - Compare multiple target scenarios:
     * Aggressive target: High reward, low probability, lower EV
     * Conservative target: Lower reward, high probability, possibly higher EV
   - Choose target that maximizes expected value

4. **Evaluate Partial Profit Opportunities**:
   - If forecast shows multiple probability zones, consider scaling out:
     * Take 50% profit at high-probability zone (e.g., 70% P at 30 pips)
     * Let remaining 50% run to lower-probability zone (e.g., 25% P at 60 pips)
   - Partial targets improve win rate and reduce regret

5. **Validate Against Probability Thresholds**:
   - Minimum acceptable P(target) = 0.50 for full target
   - If P(target) < 0.50, consider more conservative target or partials
   - If P(target) > 0.75, high confidence in reaching target

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "primary_target_price": 2075.00,
    "primary_target_pips": 50,
    "dynamic_risk_reward_ratio": 1.8,  // 50 pips profit / 28 pips risk
    "estimated_reach_probability": 0.65,
    "expected_value": 22.5,  // (0.65 * 50) - (0.35 * 28) = 22.7
    "partial_targets": [
        {
            "target_price": 2065.00,
            "close_percentage": 50,
            "estimated_probability": 0.75,
            "reasoning": "TCN forecast shows 75% probability mass within 30 pips. Take half profit here to lock in gains."
        },
        {
            "target_price": 2075.00,
            "close_percentage": 50,
            "estimated_probability": 0.65,
            "reasoning": "Let remaining position run to resistance at $2075 (65% probability). Risk-reward: 1.8:1."
        }
    ],
    "nearest_resistance_level": 2078.00,
    "reasoning": "Entry at $2050, stop at $2022 (28 pips). ML forecasts show 75% probability within 30 pips ($2065), but resistance at $2075-2078 provides good profit zone with 65% reach probability. Using partial targets: take 50% at $2065 (75% P), let 50% run to $2075 (65% P). Expected value maximized at $22.5 vs. $18 for full exit at $2065 or $20 for full exit at $2075.",
    "risk_factors": [
        "Strong resistance at $2078 may cap upside",
        "ML model agreement moderate (TCN 65%, XGBoost 58%)"
    ],
    "confidence": 0.70
}

**Critical Rules**:
- NEVER use fixed 2:1 or 3:1 risk-reward without checking probabilities
- A 3:1 RR with 20% probability (EV = -14) is WORSE than 1.5:1 RR with 70% probability (EV = +26)
- Always calculate expected value for major target scenarios
- Use partial targets when multiple high-probability zones exist
- Respect strong resistance/support levels - don't target beyond them blindly
- If P(target) < 0.50, either reduce target or reconsider the trade
- If forecast shows <40% probability at nearest resistance, consider scaling out before it
- Document ALL probability calculations and EV comparisons in reasoning
- Minimum target: 15 pips (avoid ultra-tight targets)
- Maximum target: 300 pips (avoid unrealistic targets)

**Example Inputs for LONG Trade**:
- entry_price: $2050.00
- stop_price: $2022.00 (28 pips risk)
- direction: LONG
- symbol: Gold
- timeframe: 4H
- ml_forecast_30pips: 75% probability
- ml_forecast_50pips: 65% probability
- ml_forecast_75pips: 35% probability
- resistance_level: $2078.00
- conviction: 0.70

Your target placement must maximize expected value while respecting probability distributions and market structure."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract take-profit decision from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Take-profit decision dictionary
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

            # Validate against TakeProfitDecision schema
            decision = TakeProfitDecision(**decision_data)

            return decision.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "take_profit_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return conservative fallback (minimal target)
            return {
                "primary_target_price": 0.0,  # Must be set by caller
                "primary_target_pips": 30,  # Conservative short target
                "dynamic_risk_reward_ratio": 1.0,
                "estimated_reach_probability": 0.5,
                "expected_value": 0.0,
                "partial_targets": [],
                "nearest_resistance_level": None,
                "reasoning": f"Failed to extract decision, using conservative target. Error: {str(e)}",
                "risk_factors": ["Decision extraction failed - using fallback"],
                "confidence": 0.0,
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_take_profit_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> TakeProfitAgent:
    """
    Create a Take-Profit agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured TakeProfitAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol} Take-Profit Agent",
        agent_type=AgentType.TAKE_PROFIT,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="deepseek-r1:14b",  # Deep-think for probability reasoning
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.3,  # Moderate creativity for EV optimization
        max_tokens=1200,
        available_tools=[
            "get_tcn_forecast",
            "get_xgboost_forecast",
            "get_lstm_forecast",
            "get_technical_indicators",
            "get_market_data",
        ],
        config_overrides={"symbol": symbol},
    )

    tools = [
        get_tcn_forecast,
        get_xgboost_forecast,
        get_lstm_forecast,
        get_technical_indicators,
        get_market_data,
    ]

    return TakeProfitAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=tools,
    )
