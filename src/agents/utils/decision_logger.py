"""
Decision Logger - Utility for logging Phase 6 agent decisions to database.

Provides structured logging for:
- Bull/Bear debate outcomes
- Risk debate outcomes
- Fund Manager approval decisions
- Trade intent, position sizing, stop-loss, take-profit decisions

All decisions are logged to the decision_log TimescaleDB hypertable
for historical analysis and reinforcement learning.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.decision_log import DecisionLog
from src.agents.schemas.debate import DebateOutcome, RiskDebateOutcome
from src.agents.schemas.approval import FundManagerApproval
from src.agents.schemas.decisions import PositionSize, StopLoss, TakeProfit
from src.agents.schemas.trade_decision import TradeIntent

logger = structlog.get_logger(__name__)


class DecisionLogger:
    """
    Decision Logger for Phase 6 agent decisions.

    Handles logging all major decision points in the trading pipeline
    to the decision_log database table for:
    - Audit trail
    - Performance analysis
    - Reinforcement learning training data
    - Debugging and troubleshooting
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize DecisionLogger.

        Args:
            session: Async SQLAlchemy session for database operations
        """
        self.session = session

    async def log_debate_decision(
        self,
        agent_id: UUID,
        debate_outcome: DebateOutcome,
        symbol: str,
        timeframe: str = "H1",
        decision_latency_ms: Optional[int] = None,
        strategy_team_id: Optional[UUID] = None
    ) -> UUID:
        """
        Log Bull/Bear debate decision to database.

        Args:
            agent_id: UUID of the debate team agent
            debate_outcome: DebateOutcome from BullBearDebateTeam
            symbol: Trading symbol
            timeframe: Chart timeframe
            decision_latency_ms: Time taken for decision (milliseconds)
            strategy_team_id: Optional strategy team ID

        Returns:
            UUID of created decision log entry
        """
        decision_log = DecisionLog(
            decided_at=datetime.utcnow(),
            agent_id=agent_id,
            agent_type="DEBATE_TEAM",
            strategy_team_id=strategy_team_id,
            symbol=symbol,
            timeframe=timeframe,
            input_data={
                "debate_type": "bull_bear_adversarial",
                "analyst_reports": "Debate input context"  # TODO: Add actual analyst reports
            },
            reasoning=debate_outcome.consensus_rationale if hasattr(debate_outcome, 'consensus_rationale') else None,
            decision_type="debate_outcome",
            decision_data=debate_outcome.model_dump() if hasattr(debate_outcome, 'model_dump') else debate_outcome.__dict__,
            confidence=debate_outcome.consensus_confidence if hasattr(debate_outcome, 'consensus_confidence') else None,
            was_executed=False,  # Debate doesn't execute trades
            decision_latency_ms=decision_latency_ms
        )

        self.session.add(decision_log)
        await self.session.flush()

        logger.info(
            "debate_decision_logged",
            decision_id=str(decision_log.id),
            symbol=symbol,
            agent_id=str(agent_id)
        )

        return decision_log.id

    async def log_risk_debate_decision(
        self,
        agent_id: UUID,
        risk_debate_outcome: RiskDebateOutcome,
        symbol: str,
        timeframe: str = "H1",
        decision_latency_ms: Optional[int] = None,
        strategy_team_id: Optional[UUID] = None
    ) -> UUID:
        """
        Log Risk Debate Team decision to database.

        Args:
            agent_id: UUID of the risk debate team
            risk_debate_outcome: RiskDebateOutcome from RiskDebateTeam
            symbol: Trading symbol
            timeframe: Chart timeframe
            decision_latency_ms: Time taken for decision (milliseconds)
            strategy_team_id: Optional strategy team ID

        Returns:
            UUID of created decision log entry
        """
        decision_log = DecisionLog(
            decided_at=datetime.utcnow(),
            agent_id=agent_id,
            agent_type="RISK_DEBATE_TEAM",
            strategy_team_id=strategy_team_id,
            symbol=symbol,
            timeframe=timeframe,
            input_data={
                "debate_type": "risk_tolerance_3way",
                "baseline_position_size": risk_debate_outcome.metadata.get("baseline_lot_size") if hasattr(risk_debate_outcome, 'metadata') else None,
                "baseline_risk_percent": risk_debate_outcome.metadata.get("baseline_risk_percent") if hasattr(risk_debate_outcome, 'metadata') else None
            },
            reasoning=risk_debate_outcome.divergence_rationale if hasattr(risk_debate_outcome, 'divergence_rationale') else None,
            decision_type="risk_debate_outcome",
            decision_data=risk_debate_outcome.model_dump() if hasattr(risk_debate_outcome, 'model_dump') else risk_debate_outcome.__dict__,
            confidence=None,  # Risk debate has consensus_reached instead
            was_executed=False,  # Risk debate adjusts sizing, doesn't execute
            decision_latency_ms=decision_latency_ms
        )

        self.session.add(decision_log)
        await self.session.flush()

        logger.info(
            "risk_debate_decision_logged",
            decision_id=str(decision_log.id),
            symbol=symbol,
            consensus_adjustment=risk_debate_outcome.consensus_adjustment,
            consensus_reached=risk_debate_outcome.consensus_reached
        )

        return decision_log.id

    async def log_approval_decision(
        self,
        agent_id: UUID,
        fund_manager_approval: FundManagerApproval,
        symbol: str,
        timeframe: str = "H1",
        decision_latency_ms: Optional[int] = None,
        strategy_team_id: Optional[UUID] = None
    ) -> UUID:
        """
        Log Fund Manager approval decision to database.

        Args:
            agent_id: UUID of the fund manager agent
            fund_manager_approval: FundManagerApproval from FundManagerAgent
            symbol: Trading symbol
            timeframe: Chart timeframe
            decision_latency_ms: Time taken for decision (milliseconds)
            strategy_team_id: Optional strategy team ID

        Returns:
            UUID of created decision log entry
        """
        decision_log = DecisionLog(
            decided_at=datetime.utcnow(),
            agent_id=agent_id,
            agent_type="FUND_MANAGER",
            strategy_team_id=strategy_team_id,
            symbol=symbol,
            timeframe=timeframe,
            input_data={
                "approval_type": "final_gate",
                "hard_limits_passed": fund_manager_approval.hard_limits_passed,
                "violated_limits": fund_manager_approval.violated_limits if hasattr(fund_manager_approval, 'violated_limits') else [],
                "portfolio_risk_after": fund_manager_approval.portfolio_risk_after_trade
            },
            reasoning=fund_manager_approval.rationale,
            decision_type="fund_manager_approval",
            decision_data=fund_manager_approval.model_dump() if hasattr(fund_manager_approval, 'model_dump') else fund_manager_approval.__dict__,
            confidence=fund_manager_approval.confidence,
            was_executed=fund_manager_approval.decision.value == "APPROVE",  # Only approved trades execute
            decision_latency_ms=decision_latency_ms
        )

        self.session.add(decision_log)
        await self.session.flush()

        logger.info(
            "approval_decision_logged",
            decision_id=str(decision_log.id),
            symbol=symbol,
            decision=fund_manager_approval.decision.value,
            trade_quality=fund_manager_approval.trade_quality_score
        )

        return decision_log.id

    async def log_trade_intent(
        self,
        agent_id: UUID,
        trade_intent: TradeIntent,
        symbol: str,
        timeframe: str = "H1",
        decision_latency_ms: Optional[int] = None,
        strategy_team_id: Optional[UUID] = None
    ) -> UUID:
        """
        Log TradeIntent decision to database.

        Args:
            agent_id: UUID of the trade decision agent
            trade_intent: TradeIntent from TradeDecisionAgent
            symbol: Trading symbol
            timeframe: Chart timeframe
            decision_latency_ms: Time taken for decision (milliseconds)
            strategy_team_id: Optional strategy team ID

        Returns:
            UUID of created decision log entry
        """
        decision_log = DecisionLog(
            decided_at=datetime.utcnow(),
            agent_id=agent_id,
            agent_type="TRADE_DECISION",
            strategy_team_id=strategy_team_id,
            symbol=symbol,
            timeframe=timeframe,
            input_data={
                "decision_type": "trade_intent",
                "direction": trade_intent.direction.value if hasattr(trade_intent.direction, 'value') else str(trade_intent.direction)
            },
            reasoning=trade_intent.rationale if hasattr(trade_intent, 'rationale') else None,
            decision_type="trade_intent",
            decision_data=trade_intent.model_dump() if hasattr(trade_intent, 'model_dump') else trade_intent.__dict__,
            confidence=trade_intent.conviction if hasattr(trade_intent, 'conviction') else None,
            was_executed=False,  # Intent doesn't execute, only approves
            decision_latency_ms=decision_latency_ms
        )

        self.session.add(decision_log)
        await self.session.flush()

        logger.info(
            "trade_intent_logged",
            decision_id=str(decision_log.id),
            symbol=symbol,
            direction=trade_intent.direction.value if hasattr(trade_intent.direction, 'value') else str(trade_intent.direction)
        )

        return decision_log.id

    async def log_position_size(
        self,
        agent_id: UUID,
        position_size: PositionSize,
        symbol: str,
        timeframe: str = "H1",
        decision_latency_ms: Optional[int] = None,
        strategy_team_id: Optional[UUID] = None
    ) -> UUID:
        """
        Log Position Sizing decision to database.

        Args:
            agent_id: UUID of the position sizing agent
            position_size: PositionSize from PositionSizingAgent
            symbol: Trading symbol
            timeframe: Chart timeframe
            decision_latency_ms: Time taken for decision (milliseconds)
            strategy_team_id: Optional strategy team ID

        Returns:
            UUID of created decision log entry
        """
        decision_log = DecisionLog(
            decided_at=datetime.utcnow(),
            agent_id=agent_id,
            agent_type="POSITION_SIZER",
            strategy_team_id=strategy_team_id,
            symbol=symbol,
            timeframe=timeframe,
            input_data={
                "decision_type": "position_sizing",
                "lot_size": position_size.position_size_lots,
                "risk_percent": position_size.risk_percentage
            },
            reasoning=position_size.reasoning if hasattr(position_size, 'reasoning') else None,
            decision_type="position_size",
            decision_data=position_size.model_dump() if hasattr(position_size, 'model_dump') else position_size.__dict__,
            confidence=position_size.confidence if hasattr(position_size, 'confidence') else None,
            was_executed=False,
            decision_latency_ms=decision_latency_ms
        )

        self.session.add(decision_log)
        await self.session.flush()

        logger.info(
            "position_size_logged",
            decision_id=str(decision_log.id),
            symbol=symbol,
            lot_size=position_size.position_size_lots,
            risk_percent=position_size.risk_percentage
        )

        return decision_log.id

    async def commit(self):
        """Commit all logged decisions to database."""
        await self.session.commit()
        logger.info("decision_logs_committed")

    async def rollback(self):
        """Rollback all logged decisions."""
        await self.session.rollback()
        logger.warning("decision_logs_rolled_back")
