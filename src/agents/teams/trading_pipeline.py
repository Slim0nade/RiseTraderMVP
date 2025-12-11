"""
Trading Pipeline: Orchestrates multi-stage decision workflow.

Phase 6 Full Pipeline (2025-12-07):
1. Analysis Team → Multi-analyst market analysis
2. Debate Team → Bull/Bear adversarial reasoning
3. Decision Agent → Trade intent decision
4. Position Sizing → Calculate lot size with Kelly Criterion
5. Stop-Loss Placement → ATR-based protective stops
6. Take-Profit Targets → Risk-reward optimized targets
7. Risk Debate Team → 3-way adversarial position sizing validation (optional)
8. Fund Manager → Final APPROVE/MODIFY/REJECT gate
9. Execution Agent → Order placement (if approved)

Can be implemented as Swarm (with handoffs) or as sequential team calls.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import structlog

from src.agents.teams.analysis_team import create_analysis_team
from src.agents.teams.debate_team import create_debate_team
from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.decision.trade_decision_agent import TradeDecisionAgent
from src.agents.decision.position_sizing_agent import PositionSizingAgent
from src.agents.decision.stop_loss_agent import StopLossAgent
from src.agents.decision.take_profit_agent import TakeProfitAgent
from src.agents.decision.fund_manager_agent import FundManagerAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.approval import PortfolioLimits, ApprovalDecision

logger = structlog.get_logger(__name__)


async def run_trading_pipeline(
    symbol: str,
    task: str = "Analyze current market and recommend trade",
    account_balance: float = 100000.0,
    current_portfolio: Optional[Dict[str, Any]] = None,
    enable_risk_debate: bool = True,
    enable_fund_manager: bool = True,
) -> Dict[str, Any]:
    """
    Execute full Phase 6 trading decision pipeline with adversarial safety gates.

    Workflow (Enhanced Phase 6):
    1. Analysis team produces market assessment
    2. Debate team provides bull/bear perspectives
    3. Trade Decision Agent synthesizes into TradeIntent
    4. Position Sizing Agent calculates lot size
    5. Stop-Loss Agent places protective stop
    6. Take-Profit Agent sets profit targets
    7. (Optional) Risk Debate Team validates position sizing
    8. (Optional) Fund Manager approves/modifies/rejects trade
    9. Return final trading decision with all justifications

    Args:
        symbol: Trading symbol
        task: Task description for analysis team
        account_balance: Current account balance for position sizing
        current_portfolio: Current portfolio state for fund manager
        enable_risk_debate: Whether to run risk debate team (default: True)
        enable_fund_manager: Whether to run fund manager approval (default: True)

    Returns:
        Dictionary with complete pipeline results including:
        - analysis_messages: List of analysis team outputs
        - debate_messages: List of debate team outputs
        - trade_intent: Final trade direction and conviction
        - position_size: Calculated position size
        - stop_loss: Stop-loss placement
        - take_profit: Take-profit targets
        - risk_debate_outcome: (if enabled) Risk debate results
        - fund_manager_approval: (if enabled) Final approval decision
        - final_decision: EXECUTE | MODIFY | REJECT
        - recommendation: Human-readable summary

    Example:
        >>> result = await run_trading_pipeline(
        ...     symbol="CrudeOIL",
        ...     account_balance=100000.0,
        ...     enable_risk_debate=True,
        ...     enable_fund_manager=True
        ... )
        >>> print(result['final_decision'])  # EXECUTE, MODIFY, or REJECT
        >>> print(result['fund_manager_approval']['decision'])  # APPROVE/MODIFY/REJECT
    """

    pipeline_start_time = datetime.utcnow()
    logger.info(
        "trading_pipeline_started",
        symbol=symbol,
        enable_risk_debate=enable_risk_debate,
        enable_fund_manager=enable_fund_manager
    )

    # Initialize current portfolio if not provided
    if current_portfolio is None:
        current_portfolio = {
            "open_positions": [],
            "total_exposure_percent": 0.0,
            "current_drawdown_percent": 0.0,
            "available_capital": account_balance
        }

    # Step 1: Run analysis team
    analysis_team = create_analysis_team(symbol)
    analysis_result = await analysis_team.run(task=task)

    # Extract summary from analysis messages
    analysis_summary = _extract_summary(analysis_result.messages)

    logger.info("analysis_complete", symbol=symbol, message_count=len(analysis_result.messages))

    # Step 2: Run debate team with analysis context
    debate_team = create_debate_team(
        symbol=symbol,
        analysis_summary=analysis_summary,
    )

    debate_task = f"Debate whether to go LONG or SHORT on {symbol} based on the analysis"
    debate_result = await debate_team.run(task=debate_task)

    logger.info("debate_complete", symbol=symbol, message_count=len(debate_result.messages))

    # Step 3: Trade Decision Agent - synthesize debate into TradeIntent
    # TODO: Implement TradeDecisionAgent integration with debate outcome
    # For now, extract basic trade direction from debate conclusion
    trade_intent = _extract_trade_intent_from_debate(debate_result.messages, symbol)

    logger.info(
        "trade_intent_generated",
        symbol=symbol,
        direction=trade_intent.get("direction"),
        conviction=trade_intent.get("conviction")
    )

    # Step 4: Position Sizing Agent
    position_sizing_config = AgentConfig(
        agent_type=AgentType.POSITION_SIZER,
        layer=AgentLayer.DECISION,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="mistral:7b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    position_sizing_agent = PositionSizingAgent(position_sizing_config)

    position_size = await position_sizing_agent.calculate_position_size(
        trade_intent=trade_intent,
        account_balance=account_balance,
        symbol=symbol
    )

    logger.info(
        "position_size_calculated",
        symbol=symbol,
        lot_size=position_size.position_size_lots,
        risk_percent=position_size.risk_percentage
    )

    # Step 5: Stop-Loss Agent
    stop_loss_config = AgentConfig(
        agent_type=AgentType.RISK_CONTROLLER,
        layer=AgentLayer.DECISION,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="mistral:7b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    stop_loss_agent = StopLossAgent(stop_loss_config)

    stop_loss = await stop_loss_agent.place_stop_loss(
        trade_intent=trade_intent,
        position_size=position_size,
        symbol=symbol
    )

    logger.info(
        "stop_loss_placed",
        symbol=symbol,
        stop_price=stop_loss.stop_loss_price,
        distance_pips=stop_loss.distance_pips
    )

    # Step 6: Take-Profit Agent
    take_profit_config = AgentConfig(
        agent_type=AgentType.PROFIT_OPTIMIZER,
        layer=AgentLayer.DECISION,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="mistral:7b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    take_profit_agent = TakeProfitAgent(take_profit_config)

    take_profit = await take_profit_agent.set_take_profit(
        trade_intent=trade_intent,
        position_size=position_size,
        stop_loss=stop_loss,
        symbol=symbol
    )

    logger.info(
        "take_profit_set",
        symbol=symbol,
        tp_price=take_profit.take_profit_price,
        rr_ratio=take_profit.reward_risk_ratio
    )

    # Step 7: Risk Debate Team (optional but recommended)
    risk_debate_outcome = None
    if enable_risk_debate:
        risk_debate_team = RiskDebateTeam(llm_tier=LLMTier.DEEP_THINK)

        trade_context = {
            "conviction": trade_intent.get("conviction", 0.5),
            "regime": "unknown",  # TODO: Extract from analysis
            "correlation_count": len(current_portfolio.get("open_positions", [])),
            "current_drawdown_percent": current_portfolio.get("current_drawdown_percent", 0.0),
            "account_balance": account_balance,
            "event_risk": False  # TODO: Extract from fundamental analysis
        }

        risk_debate_outcome = await risk_debate_team.run_risk_debate(
            position_size=position_size,
            trade_context=trade_context,
            symbol=symbol
        )

        logger.info(
            "risk_debate_complete",
            symbol=symbol,
            consensus_adjustment=risk_debate_outcome.consensus_adjustment,
            final_lot_size=risk_debate_outcome.final_position_size,
            consensus_reached=risk_debate_outcome.consensus_reached
        )

        # Update position size based on risk debate
        position_size.position_size_lots = risk_debate_outcome.final_position_size
        position_size.risk_percentage = risk_debate_outcome.final_risk_percentage

    # Step 8: Fund Manager Approval (optional but critical for production)
    fund_manager_approval = None
    final_decision = "EXECUTE"  # Default if fund manager disabled

    if enable_fund_manager:
        fund_manager_config = AgentConfig(
            agent_type=AgentType.PORTFOLIO_ALLOCATOR,
            layer=AgentLayer.APPROVAL,
            llm_tier=LLMTier.DEEP_THINK,
            llm_model="mistral:7b-instruct",
            temperature=0.2,
            max_tokens=3000
        )

        portfolio_limits = PortfolioLimits(
            max_account_risk_percent=5.0,
            max_portfolio_risk_percent=15.0,
            max_correlated_positions=3,
            event_risk_veto_hours=24,
            min_trade_quality_score=0.4
        )

        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        fund_manager_approval = await fund_manager.approve_trade(
            trade_intent=trade_intent,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_portfolio=current_portfolio,
            symbol=symbol
        )

        logger.info(
            "fund_manager_decision",
            symbol=symbol,
            decision=fund_manager_approval.decision.value,
            approved_size=fund_manager_approval.approved_position_size,
            trade_quality=fund_manager_approval.trade_quality_score
        )

        # Map ApprovalDecision to final decision
        if fund_manager_approval.decision == ApprovalDecision.APPROVE:
            final_decision = "EXECUTE"
        elif fund_manager_approval.decision == ApprovalDecision.MODIFY:
            final_decision = "MODIFY"
            # Apply modifications
            if fund_manager_approval.approved_position_size:
                position_size.position_size_lots = fund_manager_approval.approved_position_size
            if fund_manager_approval.approved_risk_percentage:
                position_size.risk_percentage = fund_manager_approval.approved_risk_percentage
        else:  # REJECT
            final_decision = "REJECT"

    # Calculate pipeline duration
    pipeline_duration_ms = int((datetime.utcnow() - pipeline_start_time).total_seconds() * 1000)

    logger.info(
        "trading_pipeline_complete",
        symbol=symbol,
        final_decision=final_decision,
        pipeline_duration_ms=pipeline_duration_ms
    )

    # Combine all results
    return {
        "symbol": symbol,
        "pipeline_duration_ms": pipeline_duration_ms,
        "analysis_messages": [
            {"source": msg.source, "content": msg.content}
            for msg in analysis_result.messages
        ],
        "debate_messages": [
            {"source": msg.source, "content": msg.content}
            for msg in debate_result.messages
        ],
        "trade_intent": trade_intent,
        "position_size": position_size.model_dump() if hasattr(position_size, "model_dump") else position_size.__dict__,
        "stop_loss": stop_loss.model_dump() if hasattr(stop_loss, "model_dump") else stop_loss.__dict__,
        "take_profit": take_profit.model_dump() if hasattr(take_profit, "model_dump") else take_profit.__dict__,
        "risk_debate_outcome": risk_debate_outcome.model_dump() if risk_debate_outcome and hasattr(risk_debate_outcome, "model_dump") else None,
        "fund_manager_approval": fund_manager_approval.model_dump() if fund_manager_approval and hasattr(fund_manager_approval, "model_dump") else None,
        "final_decision": final_decision,
        "recommendation": _extract_final_recommendation(
            analysis_result.messages,
            debate_result.messages,
            trade_intent,
            position_size,
            fund_manager_approval,
            final_decision
        ),
    }


def _extract_trade_intent_from_debate(debate_messages, symbol: str) -> Dict[str, Any]:
    """
    Extract TradeIntent from debate messages.

    This is a simplified extraction. In production, TradeDecisionAgent
    would synthesize the debate outcome into a structured TradeIntent.

    Args:
        debate_messages: Messages from debate team
        symbol: Trading symbol

    Returns:
        Dictionary with trade intent fields
    """
    # Extract final debate conclusion
    debate_conclusion = debate_messages[-1].content if debate_messages else ""

    # Simple heuristic: count LONG vs SHORT mentions in final message
    long_mentions = debate_conclusion.lower().count("long") + debate_conclusion.lower().count("buy")
    short_mentions = debate_conclusion.lower().count("short") + debate_conclusion.lower().count("sell")

    if long_mentions > short_mentions:
        direction = "LONG"
        conviction = min(0.5 + (long_mentions - short_mentions) * 0.1, 0.9)
    elif short_mentions > long_mentions:
        direction = "SHORT"
        conviction = min(0.5 + (short_mentions - long_mentions) * 0.1, 0.9)
    else:
        direction = "NEUTRAL"
        conviction = 0.3

    return {
        "symbol": symbol,
        "direction": direction,
        "conviction": conviction,
        "rationale": debate_conclusion[:500] if len(debate_conclusion) > 500 else debate_conclusion,
        "key_factors": ["Debate team conclusion"],
        "risk_assessment": "Based on adversarial debate analysis"
    }


def _extract_summary(messages) -> str:
    """Extract text summary from message list."""
    return "\n\n".join([f"{msg.source}: {msg.content}" for msg in messages])


def _extract_final_recommendation(
    analysis_messages,
    debate_messages,
    trade_intent: Dict[str, Any],
    position_size: Any,
    fund_manager_approval: Any,
    final_decision: str
) -> Dict[str, Any]:
    """
    Extract final trading recommendation from Phase 6 pipeline results.

    Args:
        analysis_messages: Messages from analysis team
        debate_messages: Messages from debate team
        trade_intent: Trade direction and conviction
        position_size: Position sizing decision
        fund_manager_approval: Fund manager approval (or None)
        final_decision: EXECUTE | MODIFY | REJECT

    Returns:
        Dictionary with human-readable recommendation
    """
    # Simple extraction - last message from sentiment analyst + debate conclusion
    sentiment_msg = [m for m in analysis_messages if m.source == "SentimentAnalyst"]
    last_sentiment = sentiment_msg[-1].content if sentiment_msg else "No sentiment analysis"

    debate_conclusion = debate_messages[-1].content if debate_messages else "No debate"

    # Build Phase 6 recommendation
    recommendation = {
        "sentiment_analysis": last_sentiment[:200],  # Truncate for readability
        "debate_conclusion": debate_conclusion[:200],
        "trade_direction": trade_intent.get("direction", "NEUTRAL"),
        "conviction": trade_intent.get("conviction", 0.0),
        "position_size_lots": position_size.position_size_lots if hasattr(position_size, "position_size_lots") else 0.0,
        "risk_percentage": position_size.risk_percentage if hasattr(position_size, "risk_percentage") else 0.0,
        "final_decision": final_decision,
        "status": "pipeline_complete",
    }

    # Add fund manager assessment if available
    if fund_manager_approval:
        recommendation["fund_manager_quality_score"] = fund_manager_approval.trade_quality_score
        recommendation["fund_manager_confidence"] = fund_manager_approval.confidence
        recommendation["fund_manager_rationale"] = fund_manager_approval.rationale[:200]

    return recommendation
