"""
StopLoss Agent: Intelligent stop-loss placement based on market structure.

NOT a fixed ATR multiple approach. Considers:
- ATR-based baseline calculation
- Market structure (support/resistance levels)
- Volatility regime adjustment (1.0-3.0 multiplier)
- Liquidity cluster avoidance
- ML forecast uncertainty and probability analysis

Produces structural stop placement with documented reasoning.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from src.agents.base.base_agent import BaseAgent


class StopPlacementType(str, Enum):
    """Stop placement methodology classification."""

    STRUCTURE = "structure"  # Based on support/resistance
    ATR = "atr"  # Pure ATR multiple
    HYBRID = "hybrid"  # Combination of structure + ATR


class StopLossDecision(BaseModel):
    """Structured stop-loss decision output."""

    stop_price: float = Field(
        ...,
        gt=0.0,
        description="Recommended stop loss price level"
    )

    stop_distance_pips: float = Field(
        ...,
        gt=0.0,
        description="Distance from entry in pips"
    )

    placement_type: StopPlacementType = Field(
        ...,
        description="Stop placement methodology used"
    )

    atr_baseline_pips: float = Field(
        ...,
        gt=0.0,
        description="ATR baseline value in pips"
    )

    atr_multiplier: float = Field(
        ...,
        ge=1.0,
        le=3.0,
        description="ATR multiplier applied (1.0-3.0 based on regime)"
    )

    structure_level: Optional[float] = Field(
        None,
        description="Key structure level used (support/resistance price)"
    )

    structure_type: Optional[str] = Field(
        None,
        description="Type of structure level (e.g., 'swing_low', 'support', 'fib_level')"
    )

    liquidity_cluster_distance: Optional[float] = Field(
        None,
        description="Distance from nearest liquidity cluster in pips"
    )

    adjustments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Adjustment factors applied (regime, structure_buffer, liquidity_offset, etc.)"
    )

    stop_hit_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated probability of stop being hit (0.0-1.0)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed explanation of stop placement decision"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this stop placement (0.0-1.0)"
    )

    should_trail: bool = Field(
        default=False,
        description="Whether stop should trail price"
    )

    trailing_distance_pips: Optional[float] = Field(
        None,
        description="Trailing distance in pips if should_trail=True"
    )


class StopLossAgent(BaseAgent):
    """
    Stop Loss Agent.

    Intelligently determines stop-loss placement based on:
    - ATR-based baseline (volatility-adjusted)
    - Market structure (support/resistance, swing points)
    - Volatility regime (adjusts ATR multiplier 1.0-3.0)
    - Liquidity clusters (avoids predictable stop zones)
    - ML forecast uncertainty (probability of stop hit)

    Uses deep-think LLM for complex reasoning about risk placement.
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
            "ollama_host", os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
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
        Override base run() to use OpenAI, Anthropic, or Ollama with JSON mode.

        This bypasses AutoGen issues and uses LLM's reliable structured output.
        Set LLM_PROVIDER env var to:
        - 'openai' (default) - GPT-4o-mini
        - 'anthropic' - Claude Sonnet 4.5
        - 'ollama' - Local models (mistral:7b-instruct, qwen3:14b)

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

        # Get LLM provider from environment (default: ollama)
        llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

        try:
            if llm_provider == "ollama":
                # Use local Ollama model with INSTRUCTOR for guaranteed JSON schema
                from src.agents.providers.instructor_client import InstructorOllamaClient

                ollama_host = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")

                # Default to mistral:7b-instruct (best speed + JSON reliability)
                model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")

                # Timeout configuration
                timeout = float(os.getenv("OLLAMA_TIMEOUT", "60.0"))
                max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

                logger.info(
                    "calling_ollama_with_instructor",
                    agent_id=str(self.agent_id),
                    agent_type="stop_loss",
                    model=model,
                    ollama_host=ollama_host,
                )

                # Create Instructor client
                instructor_client = InstructorOllamaClient(
                    model=model,
                    base_url=ollama_host,
                    mode="JSON",
                    default_max_retries=max_retries,
                    default_timeout=timeout,
                )

                # Get GUARANTEED valid response using Pydantic schema
                decision = instructor_client.get_structured_response(
                    response_model=StopLossDecision,
                    system_prompt=self._get_system_message_ollama(),
                    user_prompt=task,
                    temperature=0.0,
                )

                logger.info(
                    "instructor_response_validated",
                    agent_id=str(self.agent_id),
                    stop_price=decision.stop_price,
                    placement_type=decision.placement_type,
                )

                # Convert validated Pydantic model to dict
                decision_data = decision.model_dump()

            elif llm_provider == "anthropic":
                # Use Anthropic Claude
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                client = anthropic.Anthropic(api_key=api_key)

                logger.info(
                    "calling_anthropic",
                    agent_id=str(self.agent_id),
                    model="claude-sonnet-4-5-20250929",
                )

                # Call Anthropic
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2000,
                    temperature=0.0,
                    system=[
                        {
                            "type": "text",
                            "text": self._get_system_message()
                        }
                    ],
                    messages=[
                        {"role": "user", "content": task}
                    ]
                )

                # Extract JSON content
                response_content = response.content[0].text

                # Strip markdown code blocks if present
                import re
                if response_content.startswith("```"):
                    response_content = re.sub(r'^```(?:json)?\s*\n?', '', response_content)
                    response_content = re.sub(r'\n?```\s*$', '', response_content)

                # Validate against schema
                decision = StopLossDecision.model_validate_json(response_content)
                decision_data = decision.model_dump()

            else:
                # Use OpenAI (default)
                from openai import OpenAI

                api_key = os.getenv("OPENAI_API_KEY")
                client = OpenAI(api_key=api_key)

                # Allow model selection via environment variable
                model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

                logger.info(
                    "calling_openai",
                    agent_id=str(self.agent_id),
                    model=model,
                )

                # Call OpenAI with JSON mode
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self._get_system_message()},
                        {"role": "user", "content": task}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=2000,
                )

                # Extract JSON content
                response_content = response.choices[0].message.content

                # Validate against schema
                decision = StopLossDecision.model_validate_json(response_content)
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
                f"{llm_provider}_decision_complete",
                agent_id=str(self.agent_id),
                execution_time_ms=round(execution_time_ms, 2),
                stop_price=decision_data.get("stop_price"),
                placement_type=decision_data.get("placement_type"),
            )

            return decision_data

        except Exception as e:
            logger.error(
                f"{llm_provider}_call_failed",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )

            # Return conservative fallback
            return {
                "stop_price": 0.0,
                "stop_distance_pips": 100.0,  # Conservative wide stop
                "placement_type": "atr",
                "atr_baseline_pips": 100.0,
                "atr_multiplier": 2.0,
                "structure_level": None,
                "structure_type": None,
                "liquidity_cluster_distance": None,
                "adjustments": {},
                "stop_hit_probability": 0.5,
                "reasoning": f"{llm_provider.upper()} call failed: {str(e)}. Using conservative ATR-based stop.",
                "confidence": 0.0,
                "should_trail": False,
                "trailing_distance_pips": None,
            }

    async def _fetch_mcp_tool_data(
        self,
        symbol: str,
        current_price: float,
        direction: str,
    ) -> Dict[str, Any]:
        """
        Fetch data from MCP tools for stop-loss placement.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            direction: Trade direction ("long" or "short")

        Returns:
            Dictionary with support/resistance, regime, and ATR data
        """
        try:
            from src.services.mcp_tool_service import MCPToolService

            # Get MCPToolService instance
            mcp_service = MCPToolService(self._session, redis_client=None)

            # Fetch support/resistance levels
            sr_result = await mcp_service.invoke_tool(
                tool_name="get_support_resistance",
                params={"symbol": symbol, "current_price": current_price},
                use_cache=True,
            )

            # Fetch regime classification
            regime_result = await mcp_service.invoke_tool(
                tool_name="get_fedformer_regime",
                params={"symbol": symbol},
                use_cache=True,
            )

            # Fetch liquidity clusters
            liquidity_result = await mcp_service.invoke_tool(
                tool_name="detect_liquidity_clusters",
                params={"symbol": symbol, "direction": direction},
                use_cache=True,
            )

            return {
                "support_resistance_data": sr_result,
                "regime_data": regime_result,
                "liquidity_data": liquidity_result,
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
                "support_resistance_data": {
                    "support_levels": [],
                    "resistance_levels": [],
                    "nearest_support": None,
                    "nearest_resistance": None,
                    "error": str(e),
                },
                "regime_data": {
                    "symbol": symbol,
                    "regime": "NORMAL",
                    "confidence": 0.5,
                    "volatility_level": "MEDIUM",
                    "error": str(e),
                },
                "liquidity_data": {
                    "clusters": [],
                    "nearest_cluster": None,
                    "error": str(e),
                },
            }

    def _get_system_message_ollama(self) -> str:
        """
        Get simplified system message for Ollama models.
        """
        return """You MUST return ONLY valid JSON with these EXACT field names.

REQUIRED FIELDS:
- stop_price (number)
- stop_distance_pips (number)
- placement_type (string: "structure", "atr", or "hybrid")
- atr_baseline_pips (number)
- atr_multiplier (number 1.0-3.0)
- structure_level (number or null)
- structure_type (string or null)
- liquidity_cluster_distance (number or null)
- adjustments (object)
- stop_hit_probability (number 0-1)
- reasoning (string)
- confidence (number 0-1)
- should_trail (boolean)
- trailing_distance_pips (number or null)

Example output:
{
    "stop_price": 2640.50,
    "stop_distance_pips": 105.0,
    "placement_type": "hybrid",
    "atr_baseline_pips": 80.0,
    "atr_multiplier": 1.5,
    "structure_level": 2638.00,
    "structure_type": "swing_low",
    "liquidity_cluster_distance": 15.0,
    "adjustments": {
        "regime_multiplier": 1.5,
        "structure_buffer_pips": 10.0,
        "liquidity_offset_pips": 5.0
    },
    "stop_hit_probability": 0.25,
    "reasoning": "Stop placed below swing low with ATR buffer, avoiding liquidity cluster",
    "confidence": 0.85,
    "should_trail": false,
    "trailing_distance_pips": null
}

Methodology:
1. Calculate ATR baseline
2. Adjust ATR multiplier based on regime (volatile=3.0, normal=1.5, calm=1.0)
3. Identify key structure levels (support for longs, resistance for shorts)
4. Position stop beyond structure with buffer
5. Check for liquidity clusters and offset if needed
6. Estimate stop hit probability from ML forecast uncertainty"""

    def _get_system_message(self) -> str:
        """
        Get stop-loss system message.

        Returns:
            System prompt for stop-loss placement role
        """
        return """OUTPUT ONLY VALID JSON. NO TEXT. NO EXPLANATIONS. NO MARKDOWN. ONLY JSON.

You determine stop-loss placement for algorithmic trading. Use market structure + ATR, NOT fixed multiples.

Response format (MUST be valid JSON):
{
    "stop_price": 2640.50,
    "stop_distance_pips": 105.0,
    "placement_type": "hybrid",
    "atr_baseline_pips": 80.0,
    "atr_multiplier": 1.5,
    "structure_level": 2638.00,
    "structure_type": "swing_low",
    "liquidity_cluster_distance": 15.0,
    "adjustments": {
        "regime_multiplier": 1.5,
        "structure_buffer_pips": 10.0,
        "liquidity_offset_pips": 5.0
    },
    "stop_hit_probability": 0.25,
    "reasoning": "Brief explanation",
    "confidence": 0.85,
    "should_trail": false,
    "trailing_distance_pips": null
}

Rules:
- PREFER structure-based stops (support/resistance) over pure ATR
- Use ATR multiplier 1.0-3.0 based on volatility regime
- Position stop beyond key structure levels with buffer
- Avoid predictable liquidity clusters (round numbers, obvious levels)
- Estimate stop hit probability from ML forecast uncertainty
- placement_type: "structure" if >70% structure-based, "atr" if pure ATR, "hybrid" otherwise

OUTPUT ONLY THE JSON OBJECT. START WITH { and END WITH }. NO OTHER TEXT."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract stop-loss decision from result.

        Args:
            result: Result dict or AutoGen result

        Returns:
            Stop loss decision dictionary
        """
        try:
            # If result is already a dict, return it directly
            if isinstance(result, dict):
                return result

            # Otherwise parse from response
            import json
            import re

            content = str(result)
            content = re.sub(r'\x1b\[[0-9;]*m', '', content).strip()

            # Try to extract JSON
            json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                decision_data = json.loads(json_str)
                decision = StopLossDecision(**decision_data)
                return decision.model_dump()

            raise ValueError("Could not extract JSON from response")

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "stop_loss_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return conservative fallback
            return {
                "stop_price": 0.0,
                "stop_distance_pips": 100.0,
                "placement_type": "atr",
                "atr_baseline_pips": 100.0,
                "atr_multiplier": 2.0,
                "structure_level": None,
                "structure_type": None,
                "liquidity_cluster_distance": None,
                "adjustments": {},
                "stop_hit_probability": 0.5,
                "reasoning": f"Extraction failed: {str(e)}. Using conservative ATR stop.",
                "confidence": 0.0,
                "should_trail": False,
                "trailing_distance_pips": None,
            }

    async def determine_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        direction: str,  # "long" or "short"
        atr_value: float,
        position_size_lots: float,
        account_balance: float,
        max_risk_percentage: float = 2.0,
        ml_forecast_std: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Determine optimal stop-loss placement with MCP tool integration.

        Args:
            symbol: Trading symbol
            entry_price: Entry price level
            direction: Trade direction ("long" or "short")
            atr_value: Current ATR value in pips
            position_size_lots: Position size in lots (for risk calculation)
            account_balance: Current account balance
            max_risk_percentage: Maximum risk as percentage of balance
            ml_forecast_std: Optional ML forecast standard deviation (for probability)

        Returns:
            Stop loss decision dictionary
        """
        import structlog
        logger = structlog.get_logger(__name__)

        try:
            # Fetch MCP tool data (S/R, Regime, Liquidity)
            logger.info(
                "fetching_mcp_data_for_stop_loss",
                symbol=symbol,
                entry_price=entry_price,
                direction=direction,
            )

            mcp_data = await self._fetch_mcp_tool_data(
                symbol=symbol,
                current_price=entry_price,
                direction=direction,
            )

            # Build context message
            context_message = f"""
**Stop Loss Placement Request for {symbol}**

**Trade Details**:
- Entry Price: {entry_price:.2f}
- Direction: {direction.upper()}
- Position Size: {position_size_lots} lots
- Account Balance: ${account_balance:,.2f}
- Max Risk: {max_risk_percentage:.1f}%

**Volatility Analysis**:
- Current ATR: {atr_value:.1f} pips

**MCP Tool Results**:

**Support/Resistance Analysis**:
- Nearest Support: {mcp_data['support_resistance_data'].get('nearest_support', 'N/A')}
- Nearest Resistance: {mcp_data['support_resistance_data'].get('nearest_resistance', 'N/A')}
- Key Levels: {mcp_data['support_resistance_data'].get('support_levels', []) if direction == 'long' else mcp_data['support_resistance_data'].get('resistance_levels', [])}

**Market Regime Analysis**:
- Current Regime: {mcp_data['regime_data'].get('regime', 'UNKNOWN')}
- Volatility Level: {mcp_data['regime_data'].get('volatility_level', 'UNKNOWN')}
- Regime Confidence: {mcp_data['regime_data'].get('confidence', 0.0):.2f}

**Liquidity Cluster Analysis**:
- Nearest Cluster: {mcp_data['liquidity_data'].get('nearest_cluster', 'N/A')}
- Clusters to Avoid: {mcp_data['liquidity_data'].get('clusters', [])}

**ML Forecast Uncertainty**:
- Standard Deviation: {ml_forecast_std if ml_forecast_std else 'N/A'} pips

---

Based on the above data, determine the optimal stop-loss placement using intelligent structure-based methodology:

1. Calculate ATR baseline
2. Adjust ATR multiplier based on volatility regime (1.0-3.0)
3. Identify key structure level (support for longs, resistance for shorts)
4. Position stop beyond structure with buffer
5. Check liquidity clusters and offset if needed
6. Estimate stop hit probability

Aim for 70%+ structure-based placement. Output valid JSON matching StopLossDecision schema.
"""

            # Call the agent with context
            result = await self.run(context_message)

            # Extract decision
            decision = self._extract_decision(result)

            logger.info(
                "stop_loss_determined",
                symbol=symbol,
                stop_price=decision.get("stop_price"),
                stop_distance_pips=decision.get("stop_distance_pips"),
                placement_type=decision.get("placement_type"),
                confidence=decision.get("confidence"),
            )

            return decision

        except Exception as e:
            logger.error(
                "stop_loss_placement_failed",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )

            # Return ultra-conservative fallback
            return {
                "stop_price": 0.0,
                "stop_distance_pips": atr_value * 2.0,  # 2x ATR fallback
                "placement_type": "atr",
                "atr_baseline_pips": atr_value,
                "atr_multiplier": 2.0,
                "structure_level": None,
                "structure_type": None,
                "liquidity_cluster_distance": None,
                "adjustments": {},
                "stop_hit_probability": 0.5,
                "reasoning": f"Stop loss placement failed: {str(e)}. Using conservative 2x ATR stop.",
                "confidence": 0.0,
                "should_trail": False,
                "trailing_distance_pips": None,
                "error": str(e),
            }


# Factory function
def create_stop_loss_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> StopLossAgent:
    """
    Create a Stop Loss agent instance.

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
        name=f"{symbol}_Stop_Loss_Agent",
        agent_type=AgentType.STOP_LOSS,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.1,
        max_tokens=800,
        available_tools=[],
        config_overrides={"symbol": symbol},
    )

    return StopLossAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],
    )
