"""
AgentService: High-level orchestration for agent operations.

Provides:
- Agent lifecycle management (create, start, stop, health check)
- Pipeline orchestration (analysis → decision → execution)
- Error recovery and retry logic
- Integration with AgentRegistry
"""

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.coordination.agent_registry import AgentRegistry, AgentRegistryService
from src.agents.providers.model_router import LLMRouter

# Analysis layer
from src.agents.analysis import (
    create_technical_analyst,
    create_fundamental_analyst,
    create_sentiment_analyst,
)

# Decision layer
from src.agents.decision import (
    create_position_sizing_agent,
    create_stop_loss_agent,
    create_take_profit_agent,
)

# Execution layer
from src.agents.execution_layer import (
    create_trade_executor,
    create_position_monitor,
)

from src.database.repositories import (
    AgentRepository,
    StrategyTeamRepository,
)

logger = structlog.get_logger(__name__)


class AgentService:
    """
    High-level service for agent orchestration.

    Provides centralized management of:
    - Agent creation and registration
    - Pipeline orchestration
    - Health monitoring
    - Error recovery
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize agent service.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self.registry_service = AgentRegistryService(session)
        self.registry = self.registry_service.registry
        self.llm_router = LLMRouter()

        self._agent_repo = AgentRepository(session)
        self._team_repo = StrategyTeamRepository(session)

        logger.info("agent_service_initialized")

    # ========================================================================
    # Analysis Pipeline
    # ========================================================================

    async def run_analysis_pipeline(
        self,
        symbol: str,
        timeframe: str = "4H",
        strategy_team_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Run all analysis agents in parallel for a symbol.

        Args:
            symbol: Trading symbol (e.g., "Gold", "CrudeOIL")
            timeframe: Analysis timeframe (e.g., "1H", "4H", "1D")
            strategy_team_id: Optional team ID for agent grouping

        Returns:
            Dictionary containing:
            - technical: TechnicalReport
            - fundamental: FundamentalReport
            - sentiment: SentimentReport
            - metadata: Execution metadata
        """
        start_time = datetime.utcnow()

        logger.info(
            "analysis_pipeline_started",
            symbol=symbol,
            timeframe=timeframe,
            team_id=str(strategy_team_id) if strategy_team_id else None,
        )

        try:
            # Create analysis agents
            technical_agent = create_technical_analyst(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            fundamental_agent = create_fundamental_analyst(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            sentiment_agent = create_sentiment_analyst(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            # Register agents
            self.registry.register(technical_agent, symbol=symbol, team_id=strategy_team_id)
            self.registry.register(fundamental_agent, symbol=symbol, team_id=strategy_team_id)
            self.registry.register(sentiment_agent, symbol=symbol, team_id=strategy_team_id)

            # Run agents in parallel
            task_context = {
                "symbol": symbol,
                "timeframe": timeframe,
                "analysis_type": "swing_trade",
            }

            results = await asyncio.gather(
                technical_agent.run(
                    task=f"Analyze {symbol} technical conditions for {timeframe} trading",
                    context=task_context,
                ),
                fundamental_agent.run(
                    task=f"Analyze {symbol} fundamental and macro conditions",
                    context=task_context,
                ),
                sentiment_agent.run(
                    task=f"Analyze {symbol} sentiment and positioning",
                    context=task_context,
                ),
                return_exceptions=True,
            )

            # Unregister agents
            self.registry.unregister(technical_agent.agent_id)
            self.registry.unregister(fundamental_agent.agent_id)
            self.registry.unregister(sentiment_agent.agent_id)

            # Process results
            technical_result, fundamental_result, sentiment_result = results

            # Check for exceptions
            if isinstance(technical_result, Exception):
                logger.error("technical_analysis_failed", error=str(technical_result))
                technical_result = {"error": str(technical_result)}

            if isinstance(fundamental_result, Exception):
                logger.error("fundamental_analysis_failed", error=str(fundamental_result))
                fundamental_result = {"error": str(fundamental_result)}

            if isinstance(sentiment_result, Exception):
                logger.error("sentiment_analysis_failed", error=str(sentiment_result))
                sentiment_result = {"error": str(sentiment_result)}

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "technical": technical_result,
                "fundamental": fundamental_result,
                "sentiment": sentiment_result,
                "metadata": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "execution_time_seconds": execution_time,
                    "timestamp": datetime.utcnow().isoformat(),
                    "strategy_team_id": str(strategy_team_id) if strategy_team_id else None,
                },
            }

            logger.info(
                "analysis_pipeline_complete",
                symbol=symbol,
                execution_time_seconds=round(execution_time, 2),
            )

            return result

        except Exception as e:
            logger.error(
                "analysis_pipeline_error",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========================================================================
    # Decision Pipeline
    # ========================================================================

    async def run_decision_pipeline(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        trade_context: Dict[str, Any],
        strategy_team_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Run decision agents sequentially.

        Args:
            symbol: Trading symbol
            analysis: Output from analysis pipeline
            trade_context: Additional context (account balance, drawdown, etc.)
            strategy_team_id: Optional team ID

        Returns:
            Dictionary containing:
            - position_size: PositionSizeDecision
            - stop_loss: StopLossDecision
            - take_profit: TakeProfitDecision
            - metadata: Execution metadata
        """
        start_time = datetime.utcnow()

        logger.info(
            "decision_pipeline_started",
            symbol=symbol,
            team_id=str(strategy_team_id) if strategy_team_id else None,
        )

        try:
            # Create decision agents
            position_agent = create_position_sizing_agent(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            stop_agent = create_stop_loss_agent(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            tp_agent = create_take_profit_agent(
                agent_id=uuid4(),
                session=self.session,
                symbol=symbol,
                strategy_team_id=strategy_team_id,
            )

            # Register agents
            self.registry.register(position_agent, symbol=symbol, team_id=strategy_team_id)
            self.registry.register(stop_agent, symbol=symbol, team_id=strategy_team_id)
            self.registry.register(tp_agent, symbol=symbol, team_id=strategy_team_id)

            # Extract key info from analysis
            technical = analysis.get("technical", {})
            entry_price = technical.get("current_price", 0.0)

            # Step 1: Position Sizing
            position_decision = await position_agent.run(
                task=f"Determine optimal position size for {symbol} trade",
                context={
                    "symbol": symbol,
                    "analysis": analysis,
                    **trade_context,
                },
            )

            # Step 2: Stop-Loss Placement
            stop_decision = await stop_agent.run(
                task=f"Determine optimal stop-loss for {symbol} trade at ${entry_price:.2f}",
                context={
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "analysis": analysis,
                    **trade_context,
                },
            )

            # Step 3: Take-Profit Targeting
            tp_decision = await tp_agent.run(
                task=f"Determine optimal take-profit for {symbol} trade",
                context={
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "stop_price": stop_decision.get("stop_price"),
                    "analysis": analysis,
                    **trade_context,
                },
            )

            # Unregister agents
            self.registry.unregister(position_agent.agent_id)
            self.registry.unregister(stop_agent.agent_id)
            self.registry.unregister(tp_agent.agent_id)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "position_size": position_decision,
                "stop_loss": stop_decision,
                "take_profit": tp_decision,
                "metadata": {
                    "symbol": symbol,
                    "execution_time_seconds": execution_time,
                    "timestamp": datetime.utcnow().isoformat(),
                    "strategy_team_id": str(strategy_team_id) if strategy_team_id else None,
                },
            }

            logger.info(
                "decision_pipeline_complete",
                symbol=symbol,
                execution_time_seconds=round(execution_time, 2),
                lot_quantity=position_decision.get("lot_quantity"),
                stop_price=stop_decision.get("stop_price"),
                target_price=tp_decision.get("primary_target_price"),
            )

            return result

        except Exception as e:
            logger.error(
                "decision_pipeline_error",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========================================================================
    # Full Trading Pipeline
    # ========================================================================

    async def run_full_trading_pipeline(
        self,
        symbol: str,
        timeframe: str = "4H",
        trade_context: Optional[Dict[str, Any]] = None,
        strategy_team_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Run complete trading pipeline: analysis → decision.

        Args:
            symbol: Trading symbol
            timeframe: Analysis timeframe
            trade_context: Trading context (account, risk parameters)
            strategy_team_id: Optional team ID

        Returns:
            Complete pipeline result with analysis and decisions
        """
        start_time = datetime.utcnow()

        logger.info(
            "full_pipeline_started",
            symbol=symbol,
            timeframe=timeframe,
        )

        try:
            # Step 1: Analysis
            analysis_result = await self.run_analysis_pipeline(
                symbol=symbol,
                timeframe=timeframe,
                strategy_team_id=strategy_team_id,
            )

            # Step 2: Decision
            decision_result = await self.run_decision_pipeline(
                symbol=symbol,
                analysis=analysis_result,
                trade_context=trade_context or {},
                strategy_team_id=strategy_team_id,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "analysis": analysis_result,
                "decisions": decision_result,
                "metadata": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "total_execution_time_seconds": execution_time,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }

            logger.info(
                "full_pipeline_complete",
                symbol=symbol,
                execution_time_seconds=round(execution_time, 2),
            )

            return result

        except Exception as e:
            logger.error(
                "full_pipeline_error",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========================================================================
    # Health & Registry Management
    # ========================================================================

    async def get_registry_health(self) -> Dict[str, Any]:
        """
        Get health status of all registered agents.

        Returns:
            Health status dictionary
        """
        return await self.registry.health_check_all()

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Statistics dictionary
        """
        return self.registry.get_statistics()

    async def shutdown_all_agents(self):
        """
        Gracefully shutdown all registered agents.
        """
        logger.info("shutting_down_all_agents")
        await self.registry.shutdown_all()
        logger.info("all_agents_shutdown_complete")
