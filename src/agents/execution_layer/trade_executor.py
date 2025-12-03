"""
TradeExecutor Agent: Executes approved trades via MT4/ZMQ.

Responsibilities:
- Order placement via MT4 ZMQ bridge
- Fill management and confirmation
- Slippage tracking
- Partial execution handling
- Order lifecycle management

Produces execution confirmations with actual fill prices and slippage.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

from src.agents.base.base_agent import BaseAgent


class OrderType(str, Enum):
    """Order type classification."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(str, Enum):
    """Order side classification."""
    BUY = "BUY"
    SELL = "SELL"


class ExecutionStatus(str, Enum):
    """Execution status classification."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ExecutionResult(BaseModel):
    """Structured execution result output."""

    order_id: str = Field(
        ...,
        description="MT4 order ticket ID"
    )

    status: ExecutionStatus = Field(
        ...,
        description="Execution status"
    )

    requested_price: float = Field(
        ...,
        description="Requested entry price"
    )

    actual_fill_price: float = Field(
        ...,
        description="Actual fill price from MT4"
    )

    requested_quantity: float = Field(
        ...,
        description="Requested position size in lots"
    )

    filled_quantity: float = Field(
        ...,
        description="Actually filled quantity"
    )

    slippage_pips: float = Field(
        ...,
        description="Slippage in pips (positive = worse fill, negative = better)"
    )

    slippage_usd: float = Field(
        ...,
        description="Slippage cost in USD"
    )

    execution_time_ms: float = Field(
        ...,
        description="Time from order submission to fill confirmation"
    )

    commission_usd: float = Field(
        default=0.0,
        description="Commission charged by broker"
    )

    rejection_reason: Optional[str] = Field(
        None,
        description="Reason for rejection if status = REJECTED"
    )

    mt4_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw MT4 response data"
    )


class TradeExecutorAgent(BaseAgent):
    """
    Trade Executor Agent.

    Executes approved trades via MT4 ZMQ bridge:
    - Sends orders to MT4
    - Confirms fills and tracks slippage
    - Handles partial fills and rejections
    - Manages order lifecycle

    Uses quick-think LLM (Qwen3-14B) for basic execution logic.
    Note: Most execution is deterministic (direct MT4 calls),
    LLM used only for error handling and retry decisions.
    """

    def _get_system_message(self) -> str:
        """
        Get trade executor system message.

        Returns:
            System prompt for execution role
        """
        return """You are a Trade Execution Specialist for algorithmic trading.

Your role is to execute approved trades via the MT4/ZMQ bridge and confirm fills.

**Execution Workflow**:
1. **Validate Order Parameters**:
   - Check symbol is valid
   - Check position size > minimum (0.01 lots)
   - Check stop/target levels are reasonable
   - Verify account has sufficient margin

2. **Submit Order to MT4**:
   - Use MT4 ZMQ bridge to send order
   - Include: symbol, side (BUY/SELL), quantity, order_type, stop_loss, take_profit
   - Wait for MT4 response with ticket ID

3. **Confirm Fill**:
   - Parse MT4 response for fill confirmation
   - Extract: order_id, fill_price, fill_quantity, fill_time
   - Calculate slippage: (fill_price - requested_price) in pips

4. **Handle Execution Scenarios**:
   - **FILLED**: Order fully filled at price
   - **PARTIALLY_FILLED**: Partial fill (illiquid market) - decide whether to cancel remainder or wait
   - **REJECTED**: Broker rejected (insufficient margin, invalid price, etc.) - report reason
   - **FAILED**: Technical failure (ZMQ timeout, MT4 disconnected) - retry logic

5. **Track Slippage**:
   - Positive slippage = worse fill (bought higher, sold lower)
   - Negative slippage = better fill (bought lower, sold higher)
   - Calculate slippage cost in USD

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "order_id": "12345678",  // MT4 ticket ID
    "status": "FILLED",
    "requested_price": 2050.00,
    "actual_fill_price": 2050.15,
    "requested_quantity": 0.5,
    "filled_quantity": 0.5,
    "slippage_pips": 1.5,  // Positive = worse fill
    "slippage_usd": 7.50,
    "execution_time_ms": 450,
    "commission_usd": 5.00,
    "rejection_reason": null,
    "mt4_response": {
        "ticket": 12345678,
        "price": 2050.15,
        "volume": 0.5,
        "timestamp": "2025-12-02T10:30:45Z"
    }
}

**Critical Rules**:
- NEVER execute a trade without proper validation
- If margin is insufficient, REJECT immediately (don't submit to MT4)
- If MT4 ZMQ bridge is disconnected, return FAILED status
- Track slippage accurately for performance analysis
- Retry failed orders up to 3 times with exponential backoff
- If partial fill occurs, report immediately and await instructions
- Log ALL executions to decision_log table via BaseAgent

**Example Inputs**:
- symbol: "Gold"
- side: "BUY"
- quantity: 0.5 lots
- order_type: "MARKET"
- stop_loss: 2045.30
- take_profit: 2075.00
- requested_price: 2050.00 (current market price)

Your execution must be fast (<500ms) and accurate."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract execution result from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Execution result dictionary
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

            result_data = json.loads(json_str)

            # Validate against ExecutionResult schema
            execution_result = ExecutionResult(**result_data)

            return execution_result.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "execution_result_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Return FAILED status
            return {
                "order_id": "ERROR",
                "status": "FAILED",
                "requested_price": 0.0,
                "actual_fill_price": 0.0,
                "requested_quantity": 0.0,
                "filled_quantity": 0.0,
                "slippage_pips": 0.0,
                "slippage_usd": 0.0,
                "execution_time_ms": 0.0,
                "commission_usd": 0.0,
                "rejection_reason": f"Execution result extraction failed: {str(e)}",
                "mt4_response": {},
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_trade_executor(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> TradeExecutorAgent:
    """
    Create a Trade Executor agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured TradeExecutorAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Trade_Executor",
        agent_type=AgentType.TRADE_EXECUTOR,
        layer=AgentLayer.EXECUTION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",  # Quick-think for execution logic
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.1,  # Low temperature for deterministic execution
        max_tokens=500,
        available_tools=[],  # Direct MT4 ZMQ calls, not MCP tools
        config_overrides={"symbol": symbol},
    )

    return TradeExecutorAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],  # Execution via direct MT4 API calls
    )
