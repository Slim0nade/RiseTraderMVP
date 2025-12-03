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

    def _create_model_client(self):
        """
        Override base method to configure for JSON output.

        Returns:
            Configured OpenAIChatCompletionClient optimized for JSON
        """
        import os
        from autogen_core.models import ModelInfo
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        from src.agents.base.agent_config import LLMTier

        # Get Ollama host
        ollama_host = self.config.config_overrides.get(
            "ollama_host", os.getenv("OLLAMA_BASE_URL", "http://75.154.254.186:11434")
        )

        # Model settings - use qwen3:14b with explicit JSON prompting
        model = "qwen3:14b"  # Available model, works well with structured output
        temperature = 0.0  # Deterministic for consistent JSON
        max_tokens = 1000

        # Create model_info
        model_info = ModelInfo(
            vision=False,
            function_calling=True,
            json_output=True,
            family="qwen3",
        )

        # Create client
        return OpenAIChatCompletionClient(
            model=model,
            base_url=f"{ollama_host}/v1",
            api_key="ollama",
            model_info=model_info,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Override base run() to use Ollama directly with format parameter.

        This bypasses AutoGen's TaskResult issue and uses Ollama's structured output feature.

        Args:
            task: Task description for the agent
            context: Optional context data
            correlation_id: Optional correlation ID

        Returns:
            Decision result dictionary
        """
        import os
        import structlog
        from datetime import datetime

        logger = structlog.get_logger(__name__)
        start_time = datetime.utcnow()

        try:
            # Get Ollama host BEFORE importing ollama library
            ollama_host = self.config.config_overrides.get(
                "ollama_host", os.getenv("OLLAMA_BASE_URL", "http://75.154.254.186:11434")
            )

            # Set host for ollama library BEFORE import
            os.environ['OLLAMA_HOST'] = ollama_host

            # NOW import ollama (must be after setting OLLAMA_HOST)
            from ollama import chat

            logger.info(
                "calling_ollama_directly",
                agent_id=str(self.agent_id),
                model="qwen3:14b",
                ollama_host=ollama_host,
            )

            # Call Ollama directly with format parameter for structured JSON output
            response = chat(
                model='qwen3:14b',
                messages=[
                    {'role': 'system', 'content': self._get_system_message()},
                    {'role': 'user', 'content': task}
                ],
                format=PositionSizeDecision.model_json_schema(),  # Force JSON schema
                options={
                    'temperature': 0.0,  # Deterministic
                    'num_predict': 2048,  # Increased from 1000 to allow full JSON response
                }
            )

            # Extract response - try content first, fallback to thinking field
            response_content = response['message'].get('content', '')
            if not response_content and 'thinking' in response['message']:
                # Some models put output in thinking field
                response_content = response['message']['thinking']

            logger.debug(
                "ollama_response_received",
                content_preview=response_content[:200],
            )

            # Validate against Pydantic model
            decision = PositionSizeDecision.model_validate_json(response_content)

            # Convert to dict
            decision_data = decision.model_dump()

            # Calculate execution time
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Log decision to database
            if self.config.log_decisions:
                await self._log_decision(
                    decision_data=decision_data,
                    reasoning=decision_data.get("reasoning", ""),
                    input_data={"task": task, "context": context},
                    execution_time_ms=execution_time_ms,
                    correlation_id=correlation_id,
                )

            # Update metrics
            await self._update_metrics(
                decisions_count=1,
                avg_decision_time_ms=execution_time_ms,
            )

            logger.info(
                "ollama_decision_complete",
                agent_id=str(self.agent_id),
                execution_time_ms=round(execution_time_ms, 2),
                lot_quantity=decision_data.get("lot_quantity"),
            )

            return decision_data

        except Exception as e:
            logger.error(
                "ollama_call_failed",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )

            # Return conservative fallback
            return {
                "lot_quantity": 0.01,
                "dynamic_risk_percentage": 0.1,
                "kelly_fraction_applied": 0.0,
                "base_size": 0.01,
                "adjustments": {},
                "reasoning": f"Ollama call failed: {str(e)}. Using minimum safe size.",
                "confidence": 0.0,
                "risk_metrics": {},
            }

    async def _fetch_mcp_tool_data(
        self,
        symbol: str,
        win_probability: float,
        win_loss_ratio: float,
        bankroll: float,
    ) -> Dict[str, Any]:
        """
        Fetch data from MCP tools for position sizing.

        Args:
            symbol: Trading symbol
            win_probability: Historical win rate (0.0-1.0)
            win_loss_ratio: Average win / average loss ratio
            bankroll: Current account balance

        Returns:
            Dictionary with Kelly criterion and regime data
        """
        try:
            from src.services.mcp_tool_service import MCPToolService

            # Get MCPToolService instance
            mcp_service = MCPToolService(self._session, redis_client=None)

            # Fetch Kelly criterion
            kelly_result = await mcp_service.invoke_tool(
                tool_name="calculate_kelly",
                params={
                    "win_probability": win_probability,
                    "win_loss_ratio": win_loss_ratio,
                    "bankroll": bankroll,
                    "max_kelly_fraction": 0.25,  # Quarter-Kelly for safety
                },
                use_cache=True,
            )

            # Fetch regime classification
            regime_result = await mcp_service.invoke_tool(
                tool_name="get_fedformer_regime",
                params={"symbol": symbol},
                use_cache=True,
            )

            return {
                "kelly_data": kelly_result,
                "regime_data": regime_result,
            }

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "mcp_tool_fetch_failed",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )

            # Return fallback data
            return {
                "kelly_data": {
                    "kelly_fraction": 0.10,  # Conservative fallback
                    "capped_kelly_fraction": 0.10,
                    "recommended_position_size": bankroll * 0.10,
                    "recommended_position_pct": 10.0,
                    "expected_growth_rate": 0.0,
                    "calculation_time_ms": 0.0,
                    "error": str(e),
                },
                "regime_data": {
                    "symbol": symbol,
                    "regime": "NORMAL",  # Neutral fallback
                    "confidence": 0.5,
                    "volatility_level": "MEDIUM",
                    "trend_strength": 0.5,
                    "error": str(e),
                },
            }

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

**CRITICAL OUTPUT REQUIREMENT**:
You MUST respond with ONLY a valid JSON object. NO other text before or after. NO explanations. NO markdown. ONLY the JSON.

The JSON object MUST match this EXACT structure:
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

            # Clean content - remove ANSI codes and extra whitespace
            content = re.sub(r'\x1b\[[0-9;]*m', '', content)  # Remove ANSI codes
            content = content.strip()

            # Try multiple extraction patterns
            json_str = None

            # Pattern 1: JSON in markdown code block with language specifier
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1)

            # Pattern 2: JSON in markdown code block without language specifier
            if not json_str:
                json_match = re.search(r'```\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)

            # Pattern 3: JSON object anywhere in content
            if not json_str:
                json_match = re.search(r'\{[^{}]*"lot_quantity"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)

            # Pattern 4: Fallback - find any valid JSON object
            if not json_str:
                json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)

            # If still no match, try the entire content
            if not json_str:
                json_str = content

            # Clean up the JSON string
            json_str = json_str.strip()

            # Parse JSON
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

    async def determine_position_size(
        self,
        symbol: str,
        account_balance: float,
        current_drawdown: float,
        trade_conviction: float,
        stop_distance_pips: float,
        target_distance_pips: float,
        win_rate: Optional[float] = None,
        avg_win_pips: Optional[float] = None,
        avg_loss_pips: Optional[float] = None,
        correlation_with_existing: Optional[float] = None,
        major_event_within_24h: bool = False,
        major_event_within_48h: bool = False,
    ) -> Dict[str, Any]:
        """
        Determine optimal position size with MCP tool integration.

        Args:
            symbol: Trading symbol (e.g., "Gold", "CrudeOIL")
            account_balance: Current account balance in USD
            current_drawdown: Current drawdown as decimal (e.g., 0.07 for 7%)
            trade_conviction: Conviction level 0.0-1.0 from analysis
            stop_distance_pips: Stop loss distance in pips
            target_distance_pips: Take profit distance in pips
            win_rate: Historical win rate (0.0-1.0), optional
            avg_win_pips: Average winning trade in pips, optional
            avg_loss_pips: Average losing trade in pips, optional
            correlation_with_existing: Correlation with existing positions (0.0-1.0), optional
            major_event_within_24h: Major economic event within 24 hours
            major_event_within_48h: Major economic event within 48 hours

        Returns:
            Position sizing decision dictionary
        """
        import structlog
        logger = structlog.get_logger(__name__)

        try:
            # Calculate win/loss ratio if data provided
            win_loss_ratio = 1.5  # Default
            if avg_win_pips and avg_loss_pips and avg_loss_pips > 0:
                win_loss_ratio = avg_win_pips / avg_loss_pips

            # Use provided win rate or default
            win_probability = win_rate if win_rate is not None else 0.55

            # Fetch MCP tool data (Kelly + Regime)
            logger.info(
                "fetching_mcp_data_for_position_sizing",
                symbol=symbol,
                win_probability=win_probability,
                win_loss_ratio=win_loss_ratio,
            )

            mcp_data = await self._fetch_mcp_tool_data(
                symbol=symbol,
                win_probability=win_probability,
                win_loss_ratio=win_loss_ratio,
                bankroll=account_balance,
            )

            # Build context message with MCP tool results
            context_message = f"""
**Position Sizing Request for {symbol}**

**Account State**:
- Balance: ${account_balance:,.2f}
- Current Drawdown: {current_drawdown*100:.1f}%

**Trade Parameters**:
- Trade Conviction: {trade_conviction:.2f} (0.0-1.0 scale)
- Stop Distance: {stop_distance_pips} pips
- Target Distance: {target_distance_pips} pips
- Risk:Reward Ratio: {target_distance_pips/stop_distance_pips if stop_distance_pips > 0 else 0:.2f}:1

**Historical Performance** (if available):
- Win Rate: {win_probability*100:.1f}%
- Average Win: {avg_win_pips or 'N/A'} pips
- Average Loss: {avg_loss_pips or 'N/A'} pips
- Win/Loss Ratio: {win_loss_ratio:.2f}:1

**Portfolio Context**:
- Correlation with Existing Positions: {correlation_with_existing if correlation_with_existing is not None else 'N/A'}
- Major Event within 24h: {'YES' if major_event_within_24h else 'NO'}
- Major Event within 48h: {'YES' if major_event_within_48h else 'NO'}

**MCP Tool Results**:

**Kelly Criterion Analysis**:
- Kelly Fraction: {mcp_data['kelly_data'].get('kelly_fraction', 0.0):.3f}
- Capped Kelly (Quarter-Kelly): {mcp_data['kelly_data'].get('capped_kelly_fraction', 0.0):.3f}
- Recommended Position: ${mcp_data['kelly_data'].get('recommended_position_size', 0.0):,.2f} ({mcp_data['kelly_data'].get('recommended_position_pct', 0.0):.1f}%)
- Expected Growth Rate: {mcp_data['kelly_data'].get('expected_growth_rate', 0.0)*100:.2f}% per trade

**Market Regime Analysis**:
- Current Regime: {mcp_data['regime_data'].get('regime', 'UNKNOWN')}
- Confidence: {mcp_data['regime_data'].get('confidence', 0.0):.2f}
- Volatility Level: {mcp_data['regime_data'].get('volatility_level', 'UNKNOWN')}
- Trend Strength: {mcp_data['regime_data'].get('trend_strength', 0.0):.2f}

---

Based on the above data, determine the optimal position size using the methodology in your system prompt. Apply all appropriate adjustments (drawdown, regime, conviction, correlation, event risk) and provide detailed reasoning.

Output a valid JSON object matching the PositionSizeDecision schema.
"""

            # Call the agent with context
            result = await self.run(context_message)

            # Extract decision
            decision = self._extract_decision(result)

            logger.info(
                "position_size_determined",
                symbol=symbol,
                lot_quantity=decision.get("lot_quantity"),
                dynamic_risk_pct=decision.get("dynamic_risk_percentage"),
                kelly_fraction=decision.get("kelly_fraction_applied"),
                confidence=decision.get("confidence"),
            )

            return decision

        except Exception as e:
            logger.error(
                "position_sizing_failed",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )

            # Return ultra-conservative fallback
            return {
                "lot_quantity": 0.01,
                "dynamic_risk_percentage": 0.1,
                "kelly_fraction_applied": 0.0,
                "base_size": 0.01,
                "adjustments": {},
                "reasoning": f"Position sizing failed: {str(e)}. Using minimum safe size (0.01 lots).",
                "confidence": 0.0,
                "risk_metrics": {},
                "error": str(e),
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
        llm_model="qwen3:14b",  # Better at structured JSON output than deepseek-r1
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.1,  # Low temperature for consistent JSON formatting
        max_tokens=800,  # Sufficient for position sizing decision
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
