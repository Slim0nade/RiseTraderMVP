"""
AgentIntegrator - Bridge between backtesting engine and LLM-powered trading agents.

Implements full_pipeline execution mode where trading decisions are made by
autonomous agents using Ollama LLMs instead of rule-based strategies.

ENHANCED: Now supports full portfolio awareness and multi-position management.

Architecture:
- Receives market data from backtest engine
- Formats data for LLM agent consumption (including ALL positions)
- Invokes trading decision agent via MCP
- Converts agent decisions back to backtest actions
- Supports scale-in/pyramid trading
- Logs all agent decisions with context
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
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
from src.services.backtesting.backtest_events import (
    BacktestEvent,
    BacktestEventType,
    get_event_broadcaster,
)

logger = structlog.get_logger(__name__)


class MarketContext(BaseModel):
    """
    Market data context provided to agent for decision making.
    
    ENHANCED: Now includes full portfolio state across all symbols.
    """

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

    # ENHANCED: Full portfolio state
    cash_balance: Decimal
    buying_power: Decimal = Decimal("0")
    
    # All positions across all symbols
    portfolio_positions: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Summary by symbol
    symbols_summary: Dict[str, Any] = Field(default_factory=dict)
    
    # Aggregated metrics
    total_position_count: int = 0
    total_exposure: Decimal = Decimal("0")
    exposure_pct: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    total_portfolio_value: Decimal = Decimal("0")
    
    # Current symbol positions (convenience)
    current_symbol_positions: List[Dict[str, Any]] = Field(default_factory=list)
    current_symbol_net_direction: str = "flat"
    current_symbol_net_quantity: Decimal = Decimal("0")

    # Risk constraints
    max_position_size: Decimal
    allow_short: bool = False
    
    # DEPRECATED: Keep for backward compatibility
    current_positions: Dict[str, Any] = Field(default_factory=dict)
    unrealized_pnl: Decimal = Decimal("0")


class AgentDecision(BaseModel):
    """
    Structured decision from trading agent.
    
    ENHANCED: Now supports scale_in action for adding to existing positions.
    """

    action: str  # 'buy', 'sell', 'scale_in', 'close_long', 'close_short', 'close_all', 'hold'
    quantity: Optional[Decimal] = None
    conviction: float  # 0.0 to 1.0
    rationale: str
    key_factors: List[str]
    risk_assessment: str
    processing_time_ms: int
    model_used: str
    
    # NEW: Target position for partial closes
    target_position_id: Optional[str] = None

    # Optional fields from TradeIntent
    expected_holding_period: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentIntegrator:
    """
    Integrates LLM-powered trading agents with backtesting engine.

    ENHANCED: Full portfolio awareness for better decision making.

    Responsibilities:
    - Format market data for agent consumption (ALL positions visible)
    - Invoke trading decision agent
    - Convert TradeIntent to backtest actions
    - Support scale-in/pyramid trading
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
                logger.warning(
                    "mistral_proprietary_api_not_yet_supported",
                    model=self.model,
                    fallback="Will attempt Ollama",
                )
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
        if self.ollama_base_url is None:
            network_manager = NetworkLocationManager()
            ollama_config = network_manager.get_ollama_config()
            self.ollama_base_url = ollama_config.base_url
            logger.debug(
                "using_network_location_manager_for_ollama",
                ollama_url=self.ollama_base_url,
                location=network_manager.location.value,
            )

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
            # DEBUG: Log market context before building prompt
            logger.debug(
                "agent_decision_context",
                symbol=market_context.symbol,
                current_price=float(market_context.current_price),
                total_positions=market_context.total_position_count,
                current_symbol_positions_count=len(market_context.current_symbol_positions),
                current_symbol_positions_detail=[
                    {
                        "direction": p["direction"],
                        "qty": p["quantity"],
                        "entry": p["entry_price"],
                    }
                    for p in market_context.current_symbol_positions
                ] if market_context.current_symbol_positions else "NONE",
            )

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
                total_positions=market_context.total_position_count,
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

    async def should_exit_position(
        self,
        position: 'Position',  # Forward reference
        current_price: Decimal,
        indicators: Dict[str, float],
        timestamp: datetime,
    ) -> Tuple[str, Optional[Decimal], str]:
        """
        Ask agent if a specific position should be exited.

        Args:
            position: The open position to evaluate
            current_price: Current market price
            indicators: Current technical indicators
            timestamp: Current time

        Returns:
            Tuple of (action, quantity, rationale)
            - action: "hold" | "close" | "partial_close"
            - quantity: Amount to close (None for hold, full qty for close, partial for partial_close)
            - rationale: Agent's reasoning
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Build exit evaluation prompt
            prompt = self._build_exit_prompt(position, current_price, indicators, timestamp)

            # Call LLM
            response = await self._call_llm(prompt)

            # Parse exit decision
            action, quantity, rationale = self._parse_exit_response(response, position)

            logger.info(
                "agent_exit_decision",
                position_id=str(position.position_id),
                symbol=position.symbol,
                action=action,
                quantity=float(quantity) if quantity else None,
                entry_price=float(position.entry_price),
                current_price=float(current_price),
                unrealized_pnl=float(position.unrealized_pnl),
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )

            return action, quantity, rationale

        except Exception as e:
            logger.error(
                "agent_exit_decision_failed",
                position_id=str(position.position_id),
                error=str(e),
                exc_info=True,
            )
            # Safe default: hold position
            return "hold", None, f"Error evaluating exit: {str(e)}"

    def _build_exit_prompt(
        self,
        position: 'Position',
        current_price: Decimal,
        indicators: Dict[str, float],
        timestamp: datetime,
    ) -> str:
        """Build prompt for exit decision evaluation."""

        # Calculate position metrics
        pnl = position.unrealized_pnl
        pnl_pct = (pnl / (position.entry_price * position.quantity)) * 100 if position.quantity > 0 else 0
        holding_hours = (timestamp - position.entry_timestamp).total_seconds() / 3600

        # Position direction
        direction = "LONG" if position.action == "buy" else "SHORT"

        prompt = f"""You are managing an open {direction} position. Evaluate whether to exit or continue holding.

POSITION DETAILS:
- Symbol: {position.symbol}
- Direction: {direction}
- Entry Price: ${position.entry_price:.2f}
- Current Price: ${current_price:.2f}
- Quantity: {position.quantity:.2f}
- Unrealized P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)
- Held for: {holding_hours:.1f} hours
- Position ID: {position.position_id}

TECHNICAL INDICATORS:
"""
        for key, value in indicators.items():
            prompt += f"- {key}: {value:.2f}\n"

        prompt += f"""
EXIT OPTIONS:
1. HOLD - Keep position open, conditions still favorable
2. CLOSE - Exit entire position (take profit or cut loss)
3. PARTIAL_CLOSE - Close 50% to lock in some gains while keeping exposure

DECISION CRITERIA:
- Is the original trade thesis still valid?
- Has momentum shifted against the position?
- Is P&L at a reasonable profit target or stop loss level?
- Are technical indicators showing reversal signals?

Respond in JSON format:
{{
    "action": "hold" | "close" | "partial_close",
    "rationale": "Detailed explanation of your decision",
    "confidence": 0.0 to 1.0,
    "key_factors": ["factor1", "factor2", "factor3"]
}}
"""
        return prompt

    def _parse_exit_response(
        self,
        llm_response: str,
        position: 'Position',
    ) -> Tuple[str, Optional[Decimal], str]:
        """
        Parse LLM exit decision response.

        Returns:
            Tuple of (action, quantity, rationale)
        """
        import json

        try:
            # Extract JSON
            response_text = llm_response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            data = json.loads(response_text)

            action = data.get("action", "hold").lower()
            rationale = data.get("rationale", "No rationale provided")

            # Determine quantity based on action
            quantity = None
            if action == "close":
                quantity = position.quantity  # Close full position
            elif action == "partial_close":
                quantity = position.quantity * Decimal("0.5")  # Close 50%
            # "hold" keeps quantity as None

            return action, quantity, rationale

        except Exception as e:
            logger.warning(
                "exit_response_parsing_failed",
                llm_response=llm_response[:500],
                error=str(e),
            )
            # Safe default
            return "hold", None, f"Failed to parse response: {str(e)}"

    def _build_decision_prompt(self, context: MarketContext) -> str:
        """
        Build prompt for LLM trading decision.

        ENHANCED: Now includes full portfolio state for informed decisions.
        """

        # Format current symbol positions
        current_symbol_info = "No positions in this symbol"
        if context.current_symbol_positions:
            positions_str = []
            for pos in context.current_symbol_positions:
                positions_str.append(
                    f"  - {pos['direction'].upper()} {pos['quantity']:.2f} @ ${pos['entry_price']:.2f} "
                    f"(P&L: ${pos['unrealized_pnl']:.2f})"
                )
            current_symbol_info = f"Positions in {context.symbol}:\n" + "\n".join(positions_str)
            current_symbol_info += f"\n  Net: {context.current_symbol_net_direction.upper()} {float(context.current_symbol_net_quantity):.2f}"

        # Format all portfolio positions
        portfolio_info = "No open positions in portfolio"
        if context.portfolio_positions:
            by_symbol = {}
            for pos in context.portfolio_positions:
                sym = pos['symbol']
                if sym not in by_symbol:
                    by_symbol[sym] = []
                by_symbol[sym].append(pos)
            
            portfolio_lines = []
            for sym, positions in by_symbol.items():
                total_qty = sum(p['quantity'] for p in positions)
                total_pnl = sum(p['unrealized_pnl'] for p in positions)
                direction = "LONG" if positions[0]['direction'] == 'long' else "SHORT"
                portfolio_lines.append(f"  {sym}: {direction} {total_qty:.2f} units (P&L: ${total_pnl:.2f})")
            
            portfolio_info = "Portfolio Positions:\n" + "\n".join(portfolio_lines)

        # Format price action
        price_summary = f"Current: ${context.current_price}, Open: ${context.open}, High: ${context.high}, Low: ${context.low}"

        # Format indicators
        indicators_summary = "No indicators available"
        if context.indicators:
            indicators_summary = ", ".join([f"{k}={v:.2f}" for k, v in context.indicators.items()])

        prompt = f"""You are an expert trading agent analyzing {context.symbol}.

=== MARKET DATA ===
Timestamp: {context.timestamp}
Price: {price_summary}
Volume: {context.volume:,}
Technical Indicators: {indicators_summary}

=== PORTFOLIO STATE ===
Cash Balance: ${context.cash_balance:,.2f}
Buying Power: ${context.buying_power:,.2f}
Total Portfolio Value: ${context.total_portfolio_value:,.2f}
Portfolio Exposure: {float(context.exposure_pct):.1f}%
Total Unrealized P&L: ${context.total_unrealized_pnl:,.2f}
Realized P&L: ${context.realized_pnl:,.2f}
Open Positions: {context.total_position_count}

{portfolio_info}

=== CURRENT SYMBOL ({context.symbol}) ===
{current_symbol_info}

=== RISK CONSTRAINTS ===
Max Position Size: ${context.max_position_size:,.2f}
Short Selling Allowed: {context.allow_short}

=== TASK ===
Analyze the market and portfolio state, then make a trading decision.

Available Actions:
- "LONG": Open a new long position (or add to existing longs)
- "SHORT": Open a new short position (or add to existing shorts) - only if allowed
- "CLOSE": Close ALL positions in {context.symbol}
- "NO_TRADE": Hold current positions, take no action

Respond in JSON format:
{{
    "direction": "LONG" | "SHORT" | "CLOSE" | "NO_TRADE",
    "conviction": 0.0 to 1.0,
    "rationale": "detailed explanation (MINIMUM 100 characters)",
    "key_factors": ["factor1", "factor2", "factor3"],
    "risk_assessment": "risk summary (MINIMUM 50 characters)",
    "expected_holding_period": "optional: intraday, 1-3 days, etc",
    "timestamp": "{context.timestamp.isoformat()}"
}}

CRITICAL Requirements:
- Consider EXISTING positions before recommending new trades
- If already LONG with good conviction, you may add to position (scale in)
- If exposure is high (>80%), be more conservative
- Only recommend action if conviction >= {self.decision_threshold}
- MUST provide at least 3 key_factors
- Be specific about WHY given current portfolio state
"""

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt and return response."""

        if not self.llm_client:
            raise RuntimeError("LLM client not initialized - call initialize() first")

        try:
            messages = [
                SystemMessage(content="You are an expert trading analyst. Always respond in valid JSON format."),
                UserMessage(content=prompt, source="user")
            ]

            response = await self.llm_client.create(messages=messages)

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
            response_text = llm_response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            data = json.loads(response_text)

            # Handle CLOSE as a special direction
            direction_str = data["direction"]
            if direction_str == "CLOSE":
                # Map to NO_TRADE but flag in metadata for special handling
                trade_intent = TradeIntent(
                    direction=TradeDirection.NO_TRADE,
                    conviction=float(data["conviction"]),
                    rationale=data["rationale"],
                    key_factors=data["key_factors"],
                    risk_assessment=data["risk_assessment"],
                    expected_holding_period=data.get("expected_holding_period"),
                    timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
                    metadata={"close_positions": True},
                )
            else:
                trade_intent = TradeIntent(
                    direction=TradeDirection(direction_str),
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
                llm_response=llm_response[:500],
                error=str(e),
                exc_info=True,
            )

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
        """
        Convert TradeIntent to AgentDecision with quantity.
        
        ENHANCED: Now supports scale-in and doesn't block buys when positions exist.
        """

        action = "hold"
        quantity = None

        # Check for explicit close request
        if trade_intent.metadata.get("close_positions"):
            if market_context.current_symbol_positions:
                action = "close_all"
                # Sum all quantities to close
                total_qty = sum(
                    Decimal(str(p['quantity'])) 
                    for p in market_context.current_symbol_positions
                )
                quantity = total_qty
            else:
                action = "hold"  # Nothing to close

        # Handle LONG direction
        elif trade_intent.direction == TradeDirection.LONG and trade_intent.conviction >= self.decision_threshold:
            # Check if we have existing SHORT positions - need to close first
            if market_context.current_symbol_net_direction == "short":
                action = "close_all"  # Close shorts before going long
                quantity = market_context.current_symbol_net_quantity
            else:
                # Either no position or already long - can open/add
                action = "buy"
                # Calculate quantity based on available buying power
                available = min(market_context.buying_power, market_context.max_position_size)
                if available > 0:
                    quantity = (available * Decimal(str(trade_intent.conviction))) / market_context.current_price
                else:
                    action = "hold"
                    logger.warning(
                        "insufficient_buying_power_for_long",
                        buying_power=float(market_context.buying_power),
                        max_position_size=float(market_context.max_position_size),
                    )

        # Handle SHORT direction
        elif trade_intent.direction == TradeDirection.SHORT and trade_intent.conviction >= self.decision_threshold:
            if not market_context.allow_short:
                logger.warning(
                    "short_trade_rejected",
                    reason="short_selling_disabled",
                    conviction=trade_intent.conviction,
                )
                action = "hold"
            elif market_context.current_symbol_net_direction == "long":
                # Close longs before going short
                action = "close_all"
                quantity = market_context.current_symbol_net_quantity
            else:
                # Either no position or already short - can open/add
                action = "sell"
                available = min(market_context.buying_power, market_context.max_position_size)
                if available > 0:
                    quantity = (available * Decimal(str(trade_intent.conviction))) / market_context.current_price
                else:
                    action = "hold"

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
                "buying_power": float(market_context.buying_power),
                "indicators": market_context.indicators,
                # ENHANCED: Full portfolio context
                "total_position_count": market_context.total_position_count,
                "exposure_pct": float(market_context.exposure_pct),
                "total_unrealized_pnl": float(market_context.total_unrealized_pnl),
                "current_symbol_positions": market_context.current_symbol_positions,
                "current_symbol_net_direction": market_context.current_symbol_net_direction,
                "model_used": self.model,
                "max_position_size": float(market_context.max_position_size),
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
            execution_outcome=None,
            correlation_id=uuid4(),
        )

        try:
            await self.backtest_repo.create_agent_decision_log(decision_log)
            logger.debug(
                "agent_decision_saved_to_db",
                decision_id=str(decision_log.id),
                backtest_run_id=str(self.backtest_run_id),
            )

            # Broadcast to WebSocket
            try:
                broadcaster = get_event_broadcaster()
                event = BacktestEvent(
                    event_type=BacktestEventType.AGENT_DECISION,
                    run_id=self.backtest_run_id,
                    timestamp=decision_log.timestamp,
                    data={
                        "symbol": market_context.symbol,
                        "price": float(market_context.current_price),
                        "action": decision.action,
                        "quantity": float(decision.quantity or 0),
                        "conviction": float(decision.conviction),
                        "direction": trade_intent.direction.value,
                        "agent_thought": decision.rationale[:500],
                        "key_factors": decision.key_factors[:3] if decision.key_factors else [],
                        "timestamp": decision_log.timestamp.isoformat(),
                        "processing_time_ms": decision.processing_time_ms,
                        "total_positions": market_context.total_position_count,
                        "exposure_pct": float(market_context.exposure_pct),
                    },
                )
                await broadcaster.broadcast(event)
            except Exception as broadcast_error:
                logger.warning(
                    "agent_decision_broadcast_failed",
                    error=str(broadcast_error),
                    decision_id=str(decision_log.id),
                )

        except Exception as e:
            logger.error(
                "failed_to_save_decision_log",
                error=str(e),
                decision_id=str(decision_log.id),
                exc_info=True,
            )

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
