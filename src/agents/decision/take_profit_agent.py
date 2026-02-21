"""
TakeProfit Agent: Probabilistic take-profit targeting based on ML forecasts.

NOT a fixed risk-reward ratio approach. Considers:
- ML forecast probability distributions (p50, p75, p90 quantiles)
- Market structure (resistance levels, key barriers)
- Partial profit opportunities (up to 3 targets)
- Expected value calculation (probability-weighted profits)
- Dynamic risk-reward validation (>= 1.5 minimum)

Produces intelligent profit targets with documented reasoning.
"""

from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from src.agents.base.base_agent import BaseAgent


class PartialTarget(BaseModel):
    """Single take-profit target with partial close percentage."""
    
    target_price: float = Field(
        ...,
        gt=0.0,
        description="Target price level"
    )
    
    target_distance_pips: float = Field(
        ...,
        gt=0.0,
        description="Distance from entry in pips"
    )
    
    close_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of position to close at this target (0-100)"
    )
    
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of reaching this target (0.0-1.0)"
    )
    
    quantile_source: Optional[str] = Field(
        None,
        description="ML forecast quantile (e.g., 'p50', 'p75', 'p90')"
    )
    
    structure_level: Optional[float] = Field(
        None,
        description="Resistance level used (if structure-based)"
    )


class TakeProfitDecision(BaseModel):
    """Structured take-profit decision output."""
    
    targets: List[PartialTarget] = Field(
        ...,
        min_items=1,
        max_items=3,
        description="List of take-profit targets (1-3 targets)"
    )
    
    primary_target_price: float = Field(
        ...,
        gt=0.0,
        description="Primary/final take-profit price"
    )
    
    primary_target_distance_pips: float = Field(
        ...,
        gt=0.0,
        description="Primary target distance from entry in pips"
    )
    
    risk_reward_ratio: float = Field(
        ...,
        ge=0.0,
        description="Overall risk-reward ratio"
    )
    
    expected_value_usd: float = Field(
        ...,
        description="Expected value in USD (probability-weighted profit)"
    )
    
    expected_value_improvement_pct: float = Field(
        ...,
        description="EV improvement vs fixed 2:1 ratio (%)"
    )
    
    ml_forecast_quantiles: Dict[str, float] = Field(
        default_factory=dict,
        description="ML forecast quantiles used (p50, p75, p90)"
    )
    
    structure_resistance_levels: List[float] = Field(
        default_factory=list,
        description="Resistance levels considered"
    )
    
    reasoning: str = Field(
        ...,
        description="Detailed explanation of target placement"
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this targeting decision (0.0-1.0)"
    )
    
    use_trailing: bool = Field(
        default=False,
        description="Whether to use trailing take-profit"
    )


class TakeProfitAgent(BaseAgent):
    """
    Take Profit Agent.
    
    Intelligently determines take-profit targets based on:
    - ML forecast probability distributions (quantiles)
    - Market structure (resistance levels)
    - Partial profit opportunities (3 targets)
    - Expected value optimization
    - Dynamic risk-reward validation
    
    Uses deep-think LLM for complex probability reasoning.
    """

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Override base run() to use OpenAI, Anthropic, or Ollama with JSON mode.
        """
        import os
        import structlog
        from datetime import datetime

        logger = structlog.get_logger(__name__)
        start_time = datetime.utcnow()

        llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

        try:
            if llm_provider == "ollama":
                from src.agents.providers.instructor_client import InstructorOllamaClient

                ollama_host = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
                model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
                timeout = float(os.getenv("OLLAMA_TIMEOUT", "60.0"))
                max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

                logger.info(
                    "calling_ollama_with_instructor",
                    agent_id=str(self.agent_id),
                    agent_type="take_profit",
                    model=model,
                )

                instructor_client = InstructorOllamaClient(
                    model=model,
                    base_url=ollama_host,
                    mode="JSON",
                    default_max_retries=max_retries,
                    default_timeout=timeout,
                )

                decision = instructor_client.get_structured_response(
                    response_model=TakeProfitDecision,
                    system_prompt=self._get_system_message_ollama(),
                    user_prompt=task,
                    temperature=0.0,
                )

                logger.info(
                    "instructor_response_validated",
                    agent_id=str(self.agent_id),
                    primary_target=decision.primary_target_price,
                    num_targets=len(decision.targets),
                )

                decision_data = decision.model_dump()

            elif llm_provider == "anthropic":
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                client = anthropic.Anthropic(api_key=api_key)

                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2000,
                    temperature=0.0,
                    system=[{"type": "text", "text": self._get_system_message()}],
                    messages=[{"role": "user", "content": task}]
                )

                response_content = response.content[0].text
                
                import re
                if response_content.startswith("```"):
                    response_content = re.sub(r'^```(?:json)?\s*\n?', '', response_content)
                    response_content = re.sub(r'\n?```\s*$', '', response_content)

                decision = TakeProfitDecision.model_validate_json(response_content)
                decision_data = decision.model_dump()

            else:
                from openai import OpenAI

                api_key = os.getenv("OPENAI_API_KEY")
                client = OpenAI(api_key=api_key)
                model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

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

                response_content = response.choices[0].message.content
                decision = TakeProfitDecision.model_validate_json(response_content)
                decision_data = decision.model_dump()

            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            if self.config.log_decisions:
                await self._log_decision(
                    decision_data=decision_data,
                    reasoning=decision_data.get("reasoning", ""),
                    input_data={"task": task, "context": context},
                    execution_time_ms=execution_time_ms,
                    correlation_id=correlation_id,
                )

            await self._update_metrics(
                decisions_count=1,
                avg_decision_time_ms=execution_time_ms,
            )

            logger.info(
                f"{llm_provider}_decision_complete",
                agent_id=str(self.agent_id),
                execution_time_ms=round(execution_time_ms, 2),
                primary_target=decision_data.get("primary_target_price"),
                expected_value=decision_data.get("expected_value_usd"),
            )

            return decision_data

        except Exception as e:
            logger.error(
                f"{llm_provider}_call_failed",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )

            # Conservative fallback: single target at 2:1
            return {
                "targets": [{
                    "target_price": 0.0,
                    "target_distance_pips": 200.0,
                    "close_percentage": 100.0,
                    "probability": 0.5,
                    "quantile_source": None,
                    "structure_level": None,
                }],
                "primary_target_price": 0.0,
                "primary_target_distance_pips": 200.0,
                "risk_reward_ratio": 2.0,
                "expected_value_usd": 0.0,
                "expected_value_improvement_pct": 0.0,
                "ml_forecast_quantiles": {},
                "structure_resistance_levels": [],
                "reasoning": f"{llm_provider.upper()} call failed: {str(e)}. Using conservative 2:1 fixed ratio.",
                "confidence": 0.0,
                "use_trailing": False,
            }

    def _get_system_message_ollama(self) -> str:
        """Get simplified system message for Ollama models."""
        return """You MUST return ONLY valid JSON with these EXACT field names.

REQUIRED FIELDS:
- targets (array of 1-3 objects, each with: target_price, target_distance_pips, close_percentage, probability, quantile_source, structure_level)
- primary_target_price (number, MUST BE > 0)
- primary_target_distance_pips (number, MUST BE > 0)
- risk_reward_ratio (number)
- expected_value_usd (number)
- expected_value_improvement_pct (number, can be negative)
- ml_forecast_quantiles (object with p50, p75, p90 - all numbers, no nulls)
- structure_resistance_levels (array of numbers)
- reasoning (string)
- confidence (number 0-1)
- use_trailing (boolean)

CRITICAL RULES:
1. LONG trades: target_price MUST BE > entry_price (targets are ABOVE entry)
2. SHORT trades: target_price MUST BE < entry_price (targets are BELOW entry)
3. ALL target_price values MUST BE > 0 (never use 0.0)
4. ml_forecast_quantiles MUST have numeric values for p50, p75, p90 (no nulls)

Example LONG trade (entry 2650.00):
{
    "targets": [
        {
            "target_price": 2670.00,
            "target_distance_pips": 50.0,
            "close_percentage": 33.0,
            "probability": 0.75,
            "quantile_source": "p50",
            "structure_level": 2668.00
        },
        {
            "target_price": 2685.00,
            "target_distance_pips": 85.0,
            "close_percentage": 33.0,
            "probability": 0.50,
            "quantile_source": "p75",
            "structure_level": 2680.00
        },
        {
            "target_price": 2700.00,
            "target_distance_pips": 100.0,
            "close_percentage": 34.0,
            "probability": 0.30,
            "quantile_source": "p90",
            "structure_level": null
        }
    ],
    "primary_target_price": 2700.00,
    "primary_target_distance_pips": 100.0,
    "risk_reward_ratio": 2.5,
    "expected_value_usd": 450.00,
    "expected_value_improvement_pct": 18.5,
    "ml_forecast_quantiles": {
        "p50": 2670.00,
        "p75": 2685.00,
        "p90": 2700.00
    },
    "structure_resistance_levels": [2668.00, 2680.00, 2700.00],
    "reasoning": "Three partial targets based on ML quantiles and resistance levels",
    "confidence": 0.80,
    "use_trailing": false
}

Example SHORT trade (entry 2650.00):
{
    "targets": [
        {
            "target_price": 2620.00,
            "target_distance_pips": 30.0,
            "close_percentage": 33.0,
            "probability": 0.75,
            "quantile_source": "p50",
            "structure_level": 2625.00
        },
        {
            "target_price": 2595.00,
            "target_distance_pips": 55.0,
            "close_percentage": 33.0,
            "probability": 0.50,
            "quantile_source": "p75",
            "structure_level": 2600.00
        },
        {
            "target_price": 2570.00,
            "target_distance_pips": 80.0,
            "close_percentage": 34.0,
            "probability": 0.30,
            "quantile_source": "p90",
            "structure_level": 2570.00
        }
    ],
    "primary_target_price": 2570.00,
    "primary_target_distance_pips": 80.0,
    "risk_reward_ratio": 2.0,
    "expected_value_usd": 350.00,
    "expected_value_improvement_pct": 15.0,
    "ml_forecast_quantiles": {
        "p50": 2620.00,
        "p75": 2595.00,
        "p90": 2570.00
    },
    "structure_resistance_levels": [2625.00, 2600.00, 2570.00],
    "reasoning": "Three partial targets for SHORT trade positioned at support levels",
    "confidence": 0.75,
    "use_trailing": false
}

Methodology:
1. Extract ML forecast quantiles (p50, p75, p90) - ensure ALL are valid numbers
2. For LONG: targets > entry, for SHORT: targets < entry
3. Create 1-3 targets (preferably 3 for partial profits)
4. Distribute position size across targets (e.g., 33%, 33%, 34%)
5. Calculate probability-weighted expected value
6. Compare to fixed 2:1 ratio baseline
7. Ensure risk-reward ratio >= 1.5
8. NEVER use 0.0 for any price field"""

    def _get_system_message(self) -> str:
        """Get take-profit system message."""
        return """OUTPUT ONLY VALID JSON. NO TEXT. NO MARKDOWN. ONLY JSON.

You determine take-profit targets for algorithmic trading. Use ML forecasts + structure, NOT fixed ratios.

CRITICAL RULES:
1. LONG trades: target_price MUST BE > entry_price (targets are ABOVE entry)
2. SHORT trades: target_price MUST BE < entry_price (targets are BELOW entry)
3. ALL target_price values MUST BE > 0 (never use 0.0)
4. ml_forecast_quantiles MUST have numeric values for p50, p75, p90 (no nulls)

Rules:
- Use ML forecast quantiles (p50, p75, p90) as primary guidance
- Position targets before resistance levels (LONG) or support levels (SHORT)
- Create 1-3 partial targets (preferably 3)
- Calculate expected value (sum of probability-weighted profits)
- Ensure risk-reward ratio >= 1.5
- Compare EV to fixed 2:1 baseline and report improvement %

OUTPUT ONLY THE JSON OBJECT. START WITH { and END WITH }. NO OTHER TEXT."""

    async def determine_take_profit(
        self,
        symbol: str,
        entry_price: float,
        direction: str,
        stop_distance_pips: float,
        position_size_lots: float,
        pip_value: float = 10.0,
        ml_forecast_quantiles: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Determine optimal take-profit targets with MCP tool integration.
        """
        import structlog
        logger = structlog.get_logger(__name__)

        try:
            logger.info(
                "determining_take_profit",
                symbol=symbol,
                entry_price=entry_price,
                direction=direction,
            )

            # Build context message
            context_message = f"""
**Take-Profit Targeting Request for {symbol}**

**Trade Details**:
- Entry Price: {entry_price:.2f}
- Direction: {direction.upper()}
- Stop Distance: {stop_distance_pips:.1f} pips
- Position Size: {position_size_lots} lots
- Pip Value: ${pip_value}/pip

**ML Forecast Quantiles**:
- p50 (50% probability): {ml_forecast_quantiles.get('p50', 'N/A') if ml_forecast_quantiles else 'N/A'}
- p75 (75% probability): {ml_forecast_quantiles.get('p75', 'N/A') if ml_forecast_quantiles else 'N/A'}
- p90 (90% probability): {ml_forecast_quantiles.get('p90', 'N/A') if ml_forecast_quantiles else 'N/A'}

Determine optimal take-profit targets using probabilistic methodology:

1. Extract ML forecast quantiles as primary targets
2. Create 1-3 partial targets (preferably 3)
3. Distribute position: Target 1 (33%), Target 2 (33%), Target 3 (34%)
4. Calculate expected value (sum of probability × profit for each target)
5. Compare to fixed 2:1 baseline
6. Ensure risk-reward >= 1.5

Output valid JSON matching TakeProfitDecision schema.
"""

            result = await self.run(context_message)
            
            logger.info(
                "take_profit_determined",
                symbol=symbol,
                num_targets=len(result.get("targets", [])),
                expected_value=result.get("expected_value_usd"),
                ev_improvement=result.get("expected_value_improvement_pct"),
            )

            return result

        except Exception as e:
            logger.error(
                "take_profit_placement_failed",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )

            # Fallback: single target at 2:1
            fixed_target_pips = stop_distance_pips * 2.0
            return {
                "targets": [{
                    "target_price": entry_price + (fixed_target_pips * 0.0001 if direction == "long" else -fixed_target_pips * 0.0001),
                    "target_distance_pips": fixed_target_pips,
                    "close_percentage": 100.0,
                    "probability": 0.5,
                    "quantile_source": None,
                    "structure_level": None,
                }],
                "primary_target_price": entry_price + (fixed_target_pips * 0.0001 if direction == "long" else -fixed_target_pips * 0.0001),
                "primary_target_distance_pips": fixed_target_pips,
                "risk_reward_ratio": 2.0,
                "expected_value_usd": 0.0,
                "expected_value_improvement_pct": 0.0,
                "ml_forecast_quantiles": {},
                "structure_resistance_levels": [],
                "reasoning": f"Take-profit failed: {str(e)}. Using conservative 2:1 fixed ratio.",
                "confidence": 0.0,
                "use_trailing": False,
                "error": str(e),
            }

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract take-profit decision from result.

        Args:
            result: Result from run() method OR dict (from Ollama direct integration)

        Returns:
            Take-profit decision dictionary
        """
        try:
            # If result is already a dict (from run() override), return it directly
            if isinstance(result, dict):
                return result

            # Otherwise, assume it's a string and parse as JSON
            import json
            if isinstance(result, str):
                return json.loads(result)

            # Fallback: return result as-is
            return result

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "decision_extraction_failed",
                error=str(e),
                result_type=type(result).__name__,
            )

            # Conservative fallback
            return {
                "targets": [{
                    "target_price": 0.0,
                    "target_distance_pips": 200.0,
                    "close_percentage": 100.0,
                    "probability": 0.5,
                    "quantile_source": None,
                    "structure_level": None,
                }],
                "primary_target_price": 0.0,
                "primary_target_distance_pips": 200.0,
                "risk_reward_ratio": 2.0,
                "expected_value_usd": 0.0,
                "expected_value_improvement_pct": 0.0,
                "ml_forecast_quantiles": {},
                "structure_resistance_levels": [],
                "reasoning": f"Decision extraction failed: {str(e)}",
                "confidence": 0.0,
                "use_trailing": False,
            }


# Factory function
def create_take_profit_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> TakeProfitAgent:
    """Create a Take Profit agent instance."""
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Take_Profit_Agent",
        agent_type=AgentType.TAKE_PROFIT,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="mistral:7b-instruct",
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.0,
        max_tokens=1000,
        available_tools=[],
        config_overrides={"symbol": symbol},
    )

    return TakeProfitAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],
    )
