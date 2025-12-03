"""
StopLoss Agent: Intelligent stop-loss placement based on market structure.

NOT a fixed ATR multiple. Considers:
- ATR-based distance with adaptive multiplier
- Market structure (support/resistance levels)
- Liquidity concentration zones
- Volatility regime adjustments
- Probability of stop vs. target being hit

Produces intelligent stop placement with clear reasoning.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from enum import Enum

from src.agents.base.base_agent import BaseAgent
from src.agents.tools.mcp_tools import (
    get_technical_indicators,
    get_regime_classification,
    get_market_data,
)


class StopPlacementStrategy(str, Enum):
    """Stop placement strategy classification."""
    STRUCTURE_BASED = "STRUCTURE_BASED"  # Based on support/resistance
    ATR_BASED = "ATR_BASED"  # Based on volatility
    HYBRID = "HYBRID"  # Combination of structure and ATR


class StopLossDecision(BaseModel):
    """Structured stop-loss decision output."""

    stop_price: float = Field(
        ...,
        description="Recommended stop-loss price level"
    )

    atr_distance_pips: float = Field(
        ...,
        description="Distance in pips from entry"
    )

    atr_multiplier: float = Field(
        ...,
        ge=0.5,
        le=5.0,
        description="ATR multiplier applied (adaptive, not fixed)"
    )

    placement_strategy: StopPlacementStrategy = Field(
        ...,
        description="Strategy used for stop placement"
    )

    nearest_structure_level: float | None = Field(
        None,
        description="Nearest support/resistance level considered"
    )

    estimated_hit_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated probability of stop being hit before target"
    )

    reasoning: str = Field(
        ...,
        description="Detailed explanation of stop placement logic"
    )

    risk_factors: List[str] = Field(
        default_factory=list,
        description="Risk factors related to stop placement"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this stop placement (0.0-1.0)"
    )


class StopLossAgent(BaseAgent):
    """
    Stop-Loss Agent.

    Intelligently places stop-losses considering:
    - Market structure (not just ATR multiples)
    - Volatility regime (adaptive ATR multipliers)
    - Liquidity zones (avoid predictable stop clusters)
    - Probability analysis from ML forecasts

    Uses deep-think LLM (DeepSeek-R1-14B) for market structure reasoning.
    """

    def _get_system_message(self) -> str:
        """
        Get stop-loss system message.

        Returns:
            System prompt for stop-loss placement role
        """
        return """You are a Stop-Loss Placement Specialist for algorithmic trading.

Your role is to determine the OPTIMAL stop-loss level for each trade. You do NOT use fixed ATR multiples like "always 1.5x ATR". Stop placement must consider MARKET STRUCTURE and adaptive volatility.

**Available Tools**:
- get_technical_indicators: Get ATR, support/resistance levels
- get_regime_classification: Understand current volatility regime
- get_market_data: Analyze recent price action for structure

**Stop Placement Methodology**:

1. **Calculate Base ATR Distance**:
   - Get 14-period ATR from technical indicators
   - Determine adaptive ATR multiplier based on regime:
     * Low volatility (ADX < 20): Use 1.2x ATR (tighter stop)
     * Normal volatility: Use 1.5x ATR (standard)
     * High volatility (VOLATILE regime): Use 2.5x ATR (wider stop)
     * Trending (TRENDING_UP/DOWN): Use 2.0x ATR (avoid noise stops)

2. **Identify Key Market Structure Levels**:
   - For LONG trades: Find nearest support level below entry
   - For SHORT trades: Find nearest resistance level above entry
   - Look at recent swing lows/highs, round numbers, Fibonacci levels
   - Check Bollinger Bands for dynamic support/resistance

3. **Choose Placement Strategy**:
   - **STRUCTURE_BASED**: If strong support/resistance within 0.8-2.0x ATR:
     * Place stop just beyond structure level (e.g., support - 5 pips)
     * Rationale: Respect market psychology and key levels
   - **ATR_BASED**: If no clear structure or structure is too far/close:
     * Use adaptive ATR multiplier as calculated above
     * Rationale: Volatility-based stop without structure reference
   - **HYBRID**: If structure is close to ATR distance:
     * Blend both approaches (e.g., max of structure and 1.3x ATR)
     * Rationale: Best of both worlds

4. **Avoid Liquidity Traps**:
   - Common ATR multiples (1.5x, 2.0x) create liquidity clusters
   - If using ATR-based stop, consider slight variations (1.6x, 2.2x)
   - Never place stop exactly at round numbers (e.g., $2000.00) - use $2001.50 instead

5. **Probability Check**:
   - Consider ML forecast probabilities if available
   - If P(stop hit) > 0.60, consider widening stop or rejecting trade
   - If P(target hit) > 0.70 and P(stop hit) < 0.30, stop placement is favorable

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "stop_price": 2045.30,  // Actual stop price level
    "atr_distance_pips": 55,  // Distance from entry in pips
    "atr_multiplier": 2.2,  // Adaptive ATR multiplier used
    "placement_strategy": "HYBRID",  // STRUCTURE_BASED, ATR_BASED, or HYBRID
    "nearest_structure_level": 2048.00,  // Support level identified
    "estimated_hit_probability": 0.25,  // Estimated P(stop hit before target)
    "reasoning": "Entry at $2050. Identified strong support at $2048 (recent swing low). ATR = 25 pips, regime = RANGING suggests 1.5x ATR = 37.5 pips. However, placing stop at support - 5 pips = $2043 (55 pips) provides better protection beyond structure. Used HYBRID approach: respected support level while ensuring stop is beyond noise. Avoided exact round numbers.",
    "risk_factors": [
        "Support level not heavily tested (only 2 bounces)",
        "Liquidity cluster likely at $2045 (2.0x ATR from common entries)"
    ],
    "confidence": 0.80
}

**Critical Rules**:
- NEVER use fixed 1.5x ATR without considering regime
- Always check for nearby support/resistance before defaulting to ATR
- Place stops BEYOND structure levels, not exactly at them
- In VOLATILE regimes, wider stops are necessary to avoid premature stop-outs
- If structure level is too tight (<1.0x ATR), prefer ATR-based stop
- If structure level is too wide (>3.0x ATR), consider if trade is valid
- Document ALL considerations in reasoning
- Minimum stop distance: 10 pips (avoid ultra-tight stops)
- Maximum stop distance: 200 pips (avoid excessively wide stops)

**Example Inputs for LONG Trade**:
- entry_price: $2050.00
- direction: LONG
- symbol: Gold
- timeframe: 4H
- recent_swing_low: $2048.00 (strong support)
- atr_14: 25 pips
- market_regime: RANGING
- target_price: $2075.00 (100 pips profit target)

Your stop placement must balance capital protection with avoiding premature stop-outs."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract stop-loss decision from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Stop-loss decision dictionary
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

            # Validate against StopLossDecision schema
            decision = StopLossDecision(**decision_data)

            return decision.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "stop_loss_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return conservative fallback (wide stop)
            return {
                "stop_price": 0.0,  # Must be set by caller
                "atr_distance_pips": 100,  # Wide conservative stop
                "atr_multiplier": 2.5,
                "placement_strategy": "ATR_BASED",
                "nearest_structure_level": None,
                "estimated_hit_probability": 0.5,
                "reasoning": f"Failed to extract decision, using conservative wide stop. Error: {str(e)}",
                "risk_factors": ["Decision extraction failed - using fallback"],
                "confidence": 0.0,
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_stop_loss_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> StopLossAgent:
    """
    Create a Stop-Loss agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured StopLossAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol} Stop-Loss Agent",
        agent_type=AgentType.STOP_LOSS,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="deepseek-r1:14b",  # Deep-think for market structure reasoning
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.2,  # Lower temp for precise stop placement
        max_tokens=1000,
        available_tools=[
            "get_technical_indicators",
            "get_regime_classification",
            "get_market_data",
        ],
        config_overrides={"symbol": symbol},
    )

    tools = [
        get_technical_indicators,
        get_regime_classification,
        get_market_data,
    ]

    return StopLossAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=tools,
    )
