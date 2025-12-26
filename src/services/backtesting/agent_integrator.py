"""
AgentIntegrator - Bridge between backtesting engine and LLM-powered trading agents.

Implements full_pipeline execution mode where trading decisions are made by
autonomous agents using Ollama LLMs instead of rule-based strategies.

Architecture:
- Receives market data from backtest engine
- Formats data for LLM agent consumption
- Invokes trading decision agent via MCP
- Converts agent decisions back to backtest actions
- Logs all agent decisions with context
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from autogen_core.models import SystemMessage, UserMessage
from pydantic import BaseModel, Field

from src.agents.providers.ollama_client import create_ollama_client
from src.agents.providers.openai_client import create_openai_client, create_gpt4o_client, create_gpt4o_mini_client
from src.agents.providers.anthropic_client import create_anthropic_client, create_claude_sonnet_client
from src.agents.schemas.trade_decision import TradeDirection, TradeIntent
from src.config.network_config import NetworkLocationManager
from src.database.models.simulated_trade import AgentDecisionLog
from src.services.backtesting.portfolio_state import PortfolioState

logger = structlog.get_logger(__name__)


class MarketContext(BaseModel):
    """Market data context provided to agent for decision making."""

    symbol: str
    timestamp: datetime
    current_price: Decimal

    # OHLCV data
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    # Recent price history (last N candles)
    price_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Technical indicators (if available)
    indicators: Dict[str, float] = Field(default_factory=dict)

    # Portfolio state
    cash_balance: Decimal
    current_positions: Dict[str, Any] = Field(default_factory=dict)
    unrealized_pnl: Decimal = Decimal("0")

    # Risk constraints
    max_position_size: Decimal
    allow_short: bool = False


class AgentDecision(BaseModel):
    """Structured decision from trading agent."""

    action: str  # 'buy', 'sell', 'close_long', 'close_short', 'hold'
    quantity: Optional[Decimal] = None
    conviction: float  # 0.0 to 1.0
    rationale: str
    key_factors: List[str]
    risk_assessment: str
    processing_time_ms: int
    model_used: str

    # Optional fields from TradeIntent
    expected_holding_period: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentIntegrator:
    """
    Integrates LLM-powered trading agents with backtesting engine.

    Responsibilities:
    - Format market data for agent consumption
    - Invoke trading decision agent
    - Convert TradeIntent to backtest actions
    - Log all agent decisions for analysis
    - Handle agent errors gracefully

    Performance Target:
    - <5s per decision (acceptable for backtest mode)
    - Batch decisions where possible
    """

    def __init__(
        self,
        backtest_run_id: UUID,
        backtest_repo,  # Add repository for real-time logging
        model: str = "qwen3:14b",
        ollama_base_url: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,  # Increased from 1000 to prevent truncation
        decision_threshold: float = 0.6,  # Min conviction to trade
    ):
        """
        Initialize AgentIntegrator.

        Args:
            backtest_run_id: UUID of current backtest run
            backtest_repo: BacktestRepository for saving decisions
            model: Ollama model to use for decisions
            ollama_base_url: Ollama server URL (auto-detects if None)
            temperature: LLM sampling temperature
            max_tokens: Max tokens for LLM response
            decision_threshold: Minimum conviction required to execute trade
        """
        self.backtest_run_id = backtest_run_id
        self.backtest_repo = backtest_repo
        self.model = model
        self.ollama_base_url = ollama_base_url  # Will be auto-detected in initialize()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.decision_threshold = decision_threshold

        # LLM client
        self.llm_client = None

        # Decision logging
        self.decision_logs: List[AgentDecisionLog] = []
        self.decision_count = 0

        logger.info(
            "agent_integrator_initialized",
            backtest_run_id=str(backtest_run_id),
            model=model,
            ollama_base_url=ollama_base_url or "auto-detect",
            decision_threshold=decision_threshold,
        )

    async def initialize(self):
        """Initialize LLM client connection based on model type."""
        try:
            # Detect model provider based on model name
            model_lower = self.model.lower()

            # OpenAI models (GPT)
            if model_lower.startswith('gpt-'):
                if 'gpt-4o-mini' in model_lower:
                    self.llm_client = create_gpt4o_mini_client()
                elif 'gpt-4o' in model_lower:
                    self.llm_client = create_gpt4o_client()
                else:
                    self.llm_client = create_openai_client(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                logger.info(
                    "agent_integrator_llm_connected",
                    provider="openai",
                    model=self.model,
                )

            # Anthropic models (Claude)
            elif 'claude' in model_lower:
                if 'sonnet' in model_lower:
                    self.llm_client = create_claude_sonnet_client()
                else:
                    self.llm_client = create_anthropic_client(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                logger.info(
                    "agent_integrator_llm_connected",
                    provider="anthropic",
                    model=self.model,
                )

            # Mistral proprietary API models
            elif model_lower.startswith('mistral-') and not ':' in model_lower:
                # Proprietary Mistral models (via API, not Ollama)
                # For now, route through OpenAI-compatible endpoint if available
                # TODO: Add dedicated Mistral API client if needed
                logger.warning(
                    "mistral_proprietary_api_not_yet_supported",
                    model=self.model,
                    fallback="Will attempt Ollama",
                )
                # Fall through to Ollama
                self._initialize_ollama_client()

            # Ollama models (local/open-source)
            else:
                self._initialize_ollama_client()

        except Exception as e:
            logger.error(
                "agent_integrator_llm_connection_failed",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    def _initialize_ollama_client(self):
        """Initialize Ollama client for local/open-source models."""
        # Get Ollama URL from NetworkLocationManager if not explicitly provided
        if self.ollama_base_url is None:
            network_manager = NetworkLocationManager()
            ollama_config = network_manager.get_ollama_config()
            self.ollama_base_url = ollama_config.base_url
            logger.debug(
                "using_network_location_manager_for_ollama",
                ollama_url=self.ollama_base_url,
                location=network_manager.location.value,
            )

        # Create client with network-aware URL
        self.llm_client = create_ollama_client(
            model=self.model,
            base_url=self.ollama_base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        logger.info(
            "agent_integrator_llm_connected",
            provider="ollama",
            model=self.model,
            base_url=self.ollama_base_url,
        )

    async def get_trading_decision(
        self,
        market_context: MarketContext,
    ) -> Optional[AgentDecision]:
        """
        Get trading decision from LLM agent.

        Args:
            market_context: Current market state and portfolio

        Returns:
            AgentDecision or None if no action recommended
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Build prompt for LLM
            prompt = self._build_decision_prompt(market_context)

            # Call LLM
            response = await self._call_llm(prompt)

            # Parse response to TradeIntent
            trade_intent = self._parse_trade_intent(response)

            # Convert TradeIntent to AgentDecision
            decision = self._convert_to_decision(
                trade_intent,
                market_context,
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )

            # Log decision
            await self._log_decision(decision, market_context, trade_intent)

            self.decision_count += 1

            logger.info(
                "agent_decision_generated",
                backtest_run_id=str(self.backtest_run_id),
                symbol=market_context.symbol,
                action=decision.action,
                conviction=decision.conviction,
                processing_time_ms=decision.processing_time_ms,
            )

            return decision

        except Exception as e:
            logger.error(
                "agent_decision_failed",
                backtest_run_id=str(self.backtest_run_id),
                symbol=market_context.symbol,
                error=str(e),
                exc_info=True,
            )

            # Return safe default (hold)
            return AgentDecision(
                action="hold",
                quantity=None,
                conviction=0.0,
                rationale=f"Error during decision: {str(e)}",
                key_factors=["error_fallback"],
                risk_assessment="Unable to assess - defaulting to hold",
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                model_used=self.model,
            )

    def _build_decision_prompt(self, context: MarketContext) -> str:
        """Build prompt for LLM trading decision."""

        # Format position info
        position_info = "No open positions"
        if context.current_positions:
            position_info = f"Current position: {context.current_positions}"

        # Format recent price action
        price_summary = f"Current: ${context.current_price}, Open: ${context.open}, High: ${context.high}, Low: ${context.low}"

        # Format indicators if available
        indicators_summary = "No indicators available"
        if context.indicators:
            indicators_summary = ", ".join([f"{k}={v:.2f}" for k, v in context.indicators.items()])

        prompt = f"""You are an expert trading agent analyzing {context.symbol}.

Current Market Data:
- Timestamp: {context.timestamp}
- Price: {price_summary}
- Volume: {context.volume:,}
- Technical Indicators: {indicators_summary}

Portfolio State:
- Cash Balance: ${context.cash_balance:,.2f}
- {position_info}
- Unrealized P&L: ${context.unrealized_pnl:,.2f}

Risk Constraints:
- Max Position Size: ${context.max_position_size:,.2f}
- Short Selling Allowed: {context.allow_short}

Task: Analyze the current market conditions and make a trading decision.

Respond in JSON format with:
{{
    "direction": "LONG" | "SHORT" | "NO_TRADE",
    "conviction": 0.0 to 1.0,
    "rationale": "detailed explanation (MINIMUM 100 characters - be thorough and specific)",
    "key_factors": ["factor1", "factor2", "factor3", "factor4"],
    "risk_assessment": "risk summary (MINIMUM 50 characters - explain specific risks)",
    "expected_holding_period": "optional: intraday, 1-3 days, etc",
    "timestamp": "{context.timestamp.isoformat()}"
}}

CRITICAL Requirements:
- MUST provide at least 3 key_factors (preferably 4-5)
- MUST write rationale with at least 100 characters
- MUST write risk_assessment with at least 50 characters
- Only recommend LONG if conviction >= {self.decision_threshold}
- Only recommend SHORT if conviction >= {self.decision_threshold} AND shorting is allowed
- Otherwise recommend NO_TRADE
- Be conservative with risk
- Provide specific, actionable rationale with market reasoning
"""

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt and return response."""

        if not self.llm_client:
            raise RuntimeError("LLM client not initialized - call initialize() first")

        try:
            # Use AutoGen's message objects
            messages = [
                SystemMessage(content="You are an expert trading analyst. Always respond in valid JSON format."),
                UserMessage(content=prompt, source="user")
            ]

            response = await self.llm_client.create(messages=messages)

            # Extract content from response
            if hasattr(response, 'choices') and len(response.choices) > 0:
                return response.choices[0].message.content
            elif hasattr(response, 'content'):
                return response.content
            else:
                raise ValueError(f"Unexpected response format: {response}")

        except Exception as e:
            logger.error(
                "llm_call_failed",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    def _parse_trade_intent(self, llm_response: str) -> TradeIntent:
        """Parse LLM response to TradeIntent schema."""
        import json

        try:
            # Extract JSON from response (handles markdown code blocks)
            response_text = llm_response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            data = json.loads(response_text)

            # Validate and create TradeIntent
            trade_intent = TradeIntent(
                direction=TradeDirection(data["direction"]),
                conviction=float(data["conviction"]),
                rationale=data["rationale"],
                key_factors=data["key_factors"],
                risk_assessment=data["risk_assessment"],
                expected_holding_period=data.get("expected_holding_period"),
                timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
                metadata=data.get("metadata", {}),
            )

            return trade_intent

        except Exception as e:
            logger.error(
                "trade_intent_parsing_failed",
                llm_response=llm_response[:500],  # Log first 500 chars
                error=str(e),
                exc_info=True,
            )

            # Return conservative default
            return TradeIntent(
                direction=TradeDirection.NO_TRADE,
                conviction=0.0,
                rationale="Failed to parse LLM response",
                key_factors=["parsing_error"],
                risk_assessment="Unable to assess - defaulting to no trade",
                timestamp=datetime.utcnow().isoformat(),
            )

    def _convert_to_decision(
        self,
        trade_intent: TradeIntent,
        market_context: MarketContext,
        processing_time_ms: int,
    ) -> AgentDecision:
        """Convert TradeIntent to AgentDecision with quantity."""

        # Determine action
        action = "hold"
        quantity = None

        if trade_intent.direction == TradeDirection.LONG and trade_intent.conviction >= self.decision_threshold:
            action = "buy"
            # Simple position sizing: use conviction to scale position
            max_qty_value = min(market_context.cash_balance, market_context.max_position_size)
            # Fix: Convert conviction to Decimal before multiplication
            quantity = (max_qty_value * Decimal(str(trade_intent.conviction))) / market_context.current_price

        elif trade_intent.direction == TradeDirection.SHORT and trade_intent.conviction >= self.decision_threshold:
            if market_context.allow_short:
                action = "sell"
                max_qty_value = market_context.max_position_size
                # Fix: Convert conviction to Decimal before multiplication
                quantity = (max_qty_value * Decimal(str(trade_intent.conviction))) / market_context.current_price
            else:
                logger.warning(
                    "short_trade_rejected",
                    reason="short_selling_disabled",
                    conviction=trade_intent.conviction,
                )

        # Check if we should close existing position
        if market_context.current_positions:
            existing_direction = market_context.current_positions.get("direction")
            if existing_direction == "long" and trade_intent.direction == TradeDirection.SHORT:
                action = "close_long"
                quantity = Decimal(str(market_context.current_positions.get("quantity", 0)))
            elif existing_direction == "short" and trade_intent.direction == TradeDirection.LONG:
                action = "close_short"
                quantity = Decimal(str(market_context.current_positions.get("quantity", 0)))

        return AgentDecision(
            action=action,
            quantity=quantity,
            conviction=trade_intent.conviction,
            rationale=trade_intent.rationale,
            key_factors=trade_intent.key_factors,
            risk_assessment=trade_intent.risk_assessment,
            processing_time_ms=processing_time_ms,
            model_used=self.model,
            expected_holding_period=trade_intent.expected_holding_period,
            metadata=trade_intent.metadata,
        )

    async def _log_decision(
        self,
        decision: AgentDecision,
        market_context: MarketContext,
        trade_intent: TradeIntent,
    ):
        """Log agent decision to database immediately."""

        decision_log = AgentDecisionLog(
            id=uuid4(),
            backtest_run_id=self.backtest_run_id,
            timestamp=market_context.timestamp,
            agent_identifier=f"trading_agent_{self.model}",
            decision_type="trade",
            input_data={
                "symbol": market_context.symbol,
                "current_price": float(market_context.current_price),
                "cash_balance": float(market_context.cash_balance),
                "indicators": market_context.indicators,
                "positions": market_context.current_positions,
            },
            output_decision={
                "action": decision.action,
                "quantity": float(decision.quantity) if decision.quantity else None,
                "conviction": decision.conviction,
                "direction": trade_intent.direction.value,
                "rationale": decision.rationale,
                "key_factors": decision.key_factors,
            },
            processing_time_ms=decision.processing_time_ms,
            execution_outcome=None,  # Will be updated after execution
            correlation_id=uuid4(),
        )

        # Save to database IMMEDIATELY (real-time logging)
        try:
            await self.backtest_repo.create_agent_decision_log(decision_log)
            logger.debug(
                "agent_decision_saved_to_db",
                decision_id=str(decision_log.id),
                backtest_run_id=str(self.backtest_run_id),
            )
        except Exception as e:
            logger.error(
                "failed_to_save_decision_log",
                error=str(e),
                decision_id=str(decision_log.id),
                exc_info=True,
            )
            # Continue even if save fails - don't break the backtest

        # Also keep in memory for backward compatibility
        self.decision_logs.append(decision_log)

    def get_decision_logs(self) -> List[AgentDecisionLog]:
        """Get all decision logs for this backtest run."""
        return self.decision_logs.copy()

    async def shutdown(self):
        """Cleanup resources."""
        logger.info(
            "agent_integrator_shutdown",
            backtest_run_id=str(self.backtest_run_id),
            total_decisions=self.decision_count,
        )
