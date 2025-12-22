"""
Backtesting service orchestration.

Main entry point for running backtests. Coordinates data replay,
portfolio management, trade execution, and metrics calculation.
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.backtest import BacktestConfiguration, BacktestRun, ExecutionMode, RunStatus
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository

from .data_replay_engine import DataReplayEngine
from .data_validator import DataValidator
from .metrics_calculator import MetricsCalculator
from .portfolio_state import PortfolioState
from .trade_simulator import TradeSimulator

logger = structlog.get_logger(__name__)


class BacktestService:
    """
    Main backtesting orchestration service.

    Coordinates:
    - Historical data replay
    - Portfolio state management
    - Trade execution simulation
    - Performance metrics calculation
    - Database persistence

    Supports two execution modes:
    - Full pipeline: Real agent decisions via MCP
    - Synthetic fast: Rule-based simulation (100x+ faster)
    """

    def __init__(
        self,
        session: AsyncSession,
        backtest_repository: BacktestRepository,
        market_data_repository: MarketDataRepository,
    ):
        """
        Initialize backtesting service.

        Args:
            session: Async database session
            backtest_repository: Repository for backtest entities
            market_data_repository: Repository for market data
        """
        self.session = session
        self.backtest_repo = backtest_repository
        self.market_data_repo = market_data_repository

        # Initialize components
        self.data_replay = DataReplayEngine(
            repository=market_data_repository,
            chunk_size=1000
        )
        self.data_validator = DataValidator()

    async def create_configuration(
        self,
        name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: Decimal,
        execution_mode: ExecutionMode,
        agent_config_ref: Optional[str] = None,
        slippage_pct: Decimal = Decimal("0.001"),
        commission_pct: Decimal = Decimal("0.0005"),
        commission_fixed: Decimal = Decimal("0.0"),
        max_leverage: Decimal = Decimal("1.0"),
        allow_short_selling: bool = False,
        config_params: Optional[Dict] = None,
    ) -> BacktestConfiguration:
        """
        Create a new backtest configuration.

        Args:
            name: Human-readable configuration name
            symbol: Trading symbol
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital
            execution_mode: 'full_pipeline' or 'synthetic_fast'
            agent_config_ref: Reference to agent config (for full mode)
            slippage_pct: Slippage percentage
            commission_pct: Commission percentage
            commission_fixed: Fixed commission per trade
            max_leverage: Maximum leverage allowed
            allow_short_selling: Whether short selling is allowed
            config_params: Mode-specific parameters (JSON)

        Returns:
            Created BacktestConfiguration
        """
        config_data = {
            "id": uuid4(),
            "name": name,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "execution_mode": execution_mode,
            "agent_config_ref": agent_config_ref,
            "slippage_pct": slippage_pct,
            "commission_pct": commission_pct,
            "commission_fixed": commission_fixed,
            "max_leverage": max_leverage,
            "allow_short_selling": allow_short_selling,
            "config_params": config_params or {},
        }

        config = BacktestConfiguration(**config_data)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)

        return config

    async def validate_configuration(
        self,
        config: BacktestConfiguration,
        timeframe: str = "M5"
    ) -> Dict:
        """
        Validate backtest configuration and data availability.

        Args:
            config: Backtest configuration to validate
            timeframe: Market data timeframe

        Returns:
            Validation results dictionary
        """
        # Validate data availability
        validation = await self.data_replay.validate_data_availability(
            symbol=config.symbol,
            timeframe=timeframe,
            start_date=config.start_date,
            end_date=config.end_date
        )

        return {
            "config_id": str(config.id),
            "config_name": config.name,
            "can_proceed": validation["can_proceed"],
            "data_validation": validation,
            "configuration_valid": True,  # Could add more validation here
        }

    async def run_backtest(
        self,
        config_id: UUID,
        timeframe: str = "M5",
        random_seed: Optional[int] = None,
        decision_engine: Optional[callable] = None,
        progress_callback: Optional[callable] = None,
    ) -> BacktestRun:
        """
        Execute a backtest run.

        Args:
            config_id: Configuration UUID
            timeframe: Market data timeframe (e.g., 'M5', 'H1')
            random_seed: Random seed for deterministic replay
            decision_engine: Decision function for synthetic mode
            progress_callback: Optional callback(processed, total, metrics)

        Returns:
            Completed BacktestRun with results

        Raises:
            ValueError: If configuration not found or validation fails
        """
        # Load configuration
        config = await self.backtest_repo.get_config(config_id)
        if not config:
            raise ValueError(f"Configuration {config_id} not found")

        # Validate before starting
        validation = await self.validate_configuration(config, timeframe)
        if not validation["can_proceed"]:
            raise ValueError(
                f"Cannot proceed with backtest: {validation['data_validation']['recommendation']}"
            )

        # Create backtest run
        run = await self.backtest_repo.create_run({
            "id": uuid4(),
            "config_id": config.id,
            "status": RunStatus.RUNNING,
            "start_time": datetime.now(),
            "random_seed": random_seed,
        })

        try:
            # Initialize components for this run
            portfolio = PortfolioState(
                initial_capital=config.initial_capital,
                max_leverage=config.max_leverage,
                allow_short_selling=config.allow_short_selling
            )

            simulator = TradeSimulator(
                slippage_pct=config.slippage_pct,
                commission_pct=config.commission_pct,
                commission_fixed=config.commission_fixed
            )

            # Execute backtest based on mode
            if config.execution_mode == ExecutionMode.FULL_PIPELINE:
                await self._run_full_pipeline_mode(
                    run=run,
                    config=config,
                    timeframe=timeframe,
                    portfolio=portfolio,
                    simulator=simulator,
                    progress_callback=progress_callback
                )
            else:  # SYNTHETIC_FAST
                await self._run_synthetic_mode(
                    run=run,
                    config=config,
                    timeframe=timeframe,
                    portfolio=portfolio,
                    simulator=simulator,
                    decision_engine=decision_engine,
                    progress_callback=progress_callback
                )

            # Calculate final metrics
            metrics = await self._calculate_final_metrics(run.id, portfolio, config)

            # Update run with results
            await self.backtest_repo.update_run(
                run_id=run.id,
                update_data={
                    "status": RunStatus.COMPLETED,
                    "end_time": datetime.now(),
                    "final_capital": portfolio.get_total_value(),
                    "total_return_pct": metrics.total_return_pct,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
                    "win_rate": metrics.win_rate,
                    "total_trades": metrics.total_trades,
                    "avg_trade_duration_hours": metrics.avg_trade_duration_hours,
                    "profit_factor": metrics.profit_factor,
                    "metrics": metrics.to_dict(),
                }
            )

            await self.session.commit()

            # Reload run with updated data
            return await self.backtest_repo.get_run(run.id)

        except Exception as e:
            # Mark run as failed
            await self.backtest_repo.update_run(
                run_id=run.id,
                update_data={
                    "status": RunStatus.FAILED,
                    "end_time": datetime.now(),
                    "error_message": str(e),
                }
            )
            await self.session.commit()
            raise

    async def _run_synthetic_mode(
        self,
        run: BacktestRun,
        config: BacktestConfiguration,
        timeframe: str,
        portfolio: PortfolioState,
        simulator: TradeSimulator,
        decision_engine: Optional[callable],
        progress_callback: Optional[callable],
    ) -> None:
        """
        Run backtest in synthetic fast mode.

        Args:
            run: BacktestRun instance
            config: Configuration
            timeframe: Timeframe
            portfolio: Portfolio state
            simulator: Trade simulator
            decision_engine: Decision function(candle) -> Optional[action]
            progress_callback: Progress callback
        """
        # If no decision_engine provided, try to create from config_params
        if decision_engine is None and config.config_params:
            synthetic_strategy = config.config_params.get("synthetic_strategy")
            synthetic_params = config.config_params.get("synthetic_params", {})
            
            # Also check for strategy params at root level of config_params
            if not synthetic_strategy:
                synthetic_strategy = config.config_params.get("strategy")
            
            if synthetic_strategy:
                logger.info(
                    "creating_synthetic_engine_from_config",
                    run_id=str(run.id),
                    strategy=synthetic_strategy,
                    params=synthetic_params,
                )
                
                from .synthetic_engine import SyntheticEngine
                
                # Merge params: synthetic_params takes precedence, but also check config_params root
                merged_params = {**config.config_params, **synthetic_params}
                # Remove meta keys
                merged_params.pop("synthetic_strategy", None)
                merged_params.pop("synthetic_params", None)
                merged_params.pop("strategy", None)
                
                synthetic_engine = SyntheticEngine(
                    strategy=synthetic_strategy,
                    params=merged_params if merged_params else None,
                )
                
                # Create decision_engine callable from synthetic_engine
                def decision_engine(tick):
                    signal = synthetic_engine.process_tick(tick)
                    if signal.action:
                        return {
                            "action": signal.action,
                            "quantity": signal.quantity,
                        }
                    return None
                
                logger.info(
                    "synthetic_engine_created",
                    run_id=str(run.id),
                    strategy=synthetic_strategy,
                )
            else:
                logger.warning(
                    "no_synthetic_strategy_found",
                    run_id=str(run.id),
                    config_params=config.config_params,
                )
        
        candles_processed = 0
        snapshot_interval = 100  # Snapshots every 100 candles

        # Replay historical data
        async for tick, processed, total in self.data_replay.replay_with_progress(
            symbol=config.symbol,
            timeframe=timeframe,
            start_date=config.start_date,
            end_date=config.end_date,
            progress_callback=progress_callback
        ):
            candles_processed += 1

            # Update portfolio with current market price
            portfolio.update_market_price(tick.symbol, tick.close)

            # Get trading decision (if decision engine provided)
            if decision_engine:
                decision = decision_engine(tick)

                if decision:
                    action = decision.get("action")
                    quantity = decision.get("quantity", Decimal("1.0"))

                    # Execute trade based on decision
                    if action in ["buy", "sell"]:
                        # Check if we can open position
                        can_open, _ = portfolio.can_open_position(
                            tick.symbol, action, tick.close, quantity
                        )

                        if can_open:
                            result = simulator.execute_entry(
                                portfolio=portfolio,
                                symbol=tick.symbol,
                                action=action,
                                price=tick.close,
                                quantity=quantity,
                                timestamp=tick.timestamp
                            )

                            if result.success:
                                # Save trade to database
                                trade_dict = simulator.to_simulated_trade_dict(
                                    result=result,
                                    backtest_run_id=run.id
                                )
                                await self.backtest_repo.create_trade(trade_dict)

                    elif action in ["close", "exit"] and portfolio.has_position(tick.symbol):
                        # Close existing position
                        exit_result, gross_pnl, net_pnl = simulator.execute_exit(
                            portfolio=portfolio,
                            symbol=tick.symbol,
                            exit_price=tick.close,
                            timestamp=tick.timestamp
                        )

                        # Update trade record with exit details
                        # (Would need to fetch trade by ID and update)

            # Periodic portfolio snapshot
            if candles_processed % snapshot_interval == 0:
                snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                await self.backtest_repo.create_snapshot(snapshot)

        # Update run with candles processed
        await self.backtest_repo.update_run(
            run_id=run.id,
            update_data={"candles_processed": candles_processed}
        )

    async def _run_full_pipeline_mode(
        self,
        run: BacktestRun,
        config: BacktestConfiguration,
        timeframe: str,
        portfolio: PortfolioState,
        simulator: TradeSimulator,
        progress_callback: Optional[callable],
    ) -> None:
        """
        Run backtest in full agent pipeline mode using LLM-powered trading agents.

        Uses AgentIntegrator to make trading decisions via Ollama LLMs.
        Slower than synthetic mode (~5s per decision) but provides realistic
        agent behavior for validation.

        Args:
            run: BacktestRun instance
            config: Configuration
            timeframe: Timeframe
            portfolio: Portfolio state
            simulator: Trade simulator
            progress_callback: Progress callback
        """
        from .agent_integrator import AgentIntegrator, MarketContext

        # Initialize AgentIntegrator
        agent_config = config.config_params.get("agent_config", {})
        model = agent_config.get("model", "qwen3:14b")
        ollama_url = agent_config.get("ollama_base_url", "http://192.168.0.123:11434/v1")
        decision_threshold = agent_config.get("decision_threshold", 0.6)

        integrator = AgentIntegrator(
            backtest_run_id=run.id,
            backtest_repo=self.backtest_repo,  # Pass repository for real-time logging
            model=model,
            ollama_base_url=ollama_url,
            decision_threshold=decision_threshold,
        )

        try:
            # Initialize LLM connection
            await integrator.initialize()

            candles_processed = 0
            snapshot_interval = 100  # More frequent snapshots in full mode
            decision_interval = 10  # Only query agent every N candles (performance)

            # Replay historical data
            async for tick, processed, total in self.data_replay.replay_with_progress(
                symbol=config.symbol,
                timeframe=timeframe,
                start_date=config.start_date,
                end_date=config.end_date,
                progress_callback=progress_callback
            ):
                candles_processed += 1

                # Update portfolio with current market price
                portfolio.update_market_price(tick.symbol, tick.close)

                # Query agent for decision (not every candle for performance)
                if candles_processed % decision_interval == 0:
                    # Build market context
                    market_context = MarketContext(
                        symbol=tick.symbol,
                        timestamp=tick.timestamp,
                        current_price=tick.close,
                        open=tick.open,
                        high=tick.high,
                        low=tick.low,
                        close=tick.close,
                        volume=tick.volume,
                        cash_balance=portfolio.cash_balance,
                        current_positions=self._get_position_dict(portfolio, tick.symbol),
                        unrealized_pnl=portfolio.get_unrealized_pnl(),
                        max_position_size=config.initial_capital * Decimal("0.5"),  # 50% max
                        allow_short=config.allow_short_selling,
                    )

                    # Get agent decision
                    decision = await integrator.get_trading_decision(market_context)

                    if decision and decision.action != "hold":
                        # Execute trade based on agent decision
                        if decision.action in ["buy", "sell"]:
                            # Check if we can open position
                            can_open, _ = portfolio.can_open_position(
                                tick.symbol, decision.action, tick.close, decision.quantity
                            )

                            if can_open:
                                result = simulator.execute_entry(
                                    portfolio=portfolio,
                                    symbol=tick.symbol,
                                    action=decision.action,
                                    price=tick.close,
                                    quantity=decision.quantity,
                                    timestamp=tick.timestamp
                                )

                                if result.success:
                                    # Save trade to database
                                    trade_dict = simulator.to_simulated_trade_dict(
                                        result=result,
                                        backtest_run_id=run.id
                                    )
                                    await self.backtest_repo.create_trade(trade_dict)

                        elif decision.action == "close_long" and portfolio.has_position(tick.symbol):
                            # Close existing position
                            exit_result, gross_pnl, net_pnl = simulator.execute_exit(
                                portfolio=portfolio,
                                symbol=tick.symbol,
                                exit_price=tick.close,
                                timestamp=tick.timestamp
                            )

                # Periodic portfolio snapshot
                if candles_processed % snapshot_interval == 0:
                    snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                    await self.backtest_repo.create_snapshot(snapshot)

            # Update run with candles processed and agent decision count
            await self.backtest_repo.update_run(
                run.id,
                {
                    "candles_processed": candles_processed,
                    "agent_decisions_count": integrator.decision_count,
                }
            )

            # Decision logs already saved in real-time by integrator._log_decision()
            # No need to batch save at the end

            logger.info(
                "full_pipeline_backtest_completed",
                run_id=str(run.id),
                candles_processed=candles_processed,
                agent_decisions=integrator.decision_count,
            )

        finally:
            await integrator.shutdown()

    def _get_position_dict(self, portfolio: PortfolioState, symbol: str) -> Dict[str, Any]:
        """Extract position info as dict for market context."""
        if portfolio.has_position(symbol):
            position = portfolio.positions.get(symbol)
            if position:
                return {
                    "direction": "long" if position.quantity > 0 else "short",
                    "quantity": abs(float(position.quantity)),
                    "entry_price": float(position.entry_price),
                    "unrealized_pnl": float(position.unrealized_pnl),
                }
        return {}

    async def _calculate_final_metrics(
        self,
        run_id: UUID,
        portfolio: PortfolioState,
        config: BacktestConfiguration
    ) -> "PerformanceMetrics":
        """
        Calculate final performance metrics for completed backtest.

        Args:
            run_id: Backtest run UUID
            portfolio: Final portfolio state
            config: Configuration

        Returns:
            PerformanceMetrics instance
        """
        # Get all snapshots
        snapshots = await self.backtest_repo.get_snapshots(run_id)

        # Get all closed trades
        trades = await self.backtest_repo.get_trades(run_id)
        closed_trades = [t for t in trades if t.exit_timestamp is not None]

        # Extract data for metrics calculation
        equity_curve = [s.total_value for s in snapshots]
        timestamps = [s.timestamp for s in snapshots]

        trade_pnls = [t.net_pnl for t in closed_trades if t.net_pnl is not None]
        entry_times = [t.entry_timestamp for t in closed_trades]
        exit_times = [t.exit_timestamp for t in closed_trades if t.exit_timestamp]

        # Calculate comprehensive metrics
        metrics = MetricsCalculator.calculate_all_metrics(
            initial_capital=config.initial_capital,
            final_capital=portfolio.get_total_value(),
            equity_curve=equity_curve if equity_curve else [config.initial_capital],
            timestamps=timestamps if timestamps else [datetime.now()],
            trade_pnls=trade_pnls,
            entry_times=entry_times,
            exit_times=exit_times
        )

        return metrics

    async def get_run_status(self, run_id: UUID) -> Dict:
        """
        Get current status of a backtest run.

        Args:
            run_id: Backtest run UUID

        Returns:
            Status dictionary with progress and metrics
        """
        run = await self.backtest_repo.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        summary = await self.backtest_repo.get_run_summary(run_id)

        return {
            "run_id": str(run.id),
            "status": run.status,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "progress": {
                "candles_processed": run.candles_processed,
                "total_trades": summary["total_trades"],
            },
            "metrics": {
                "total_return_pct": float(run.total_return_pct or 0),
                "sharpe_ratio": float(run.sharpe_ratio or 0),
                "max_drawdown_pct": float(run.max_drawdown_pct or 0),
                "win_rate": float(run.win_rate or 0),
            } if run.status == RunStatus.COMPLETED else None,
            "error": run.error_message if run.status == RunStatus.FAILED else None
        }

    async def cancel_run(self, run_id: UUID) -> bool:
        """
        Cancel a running backtest.

        Args:
            run_id: Backtest run UUID

        Returns:
            True if cancelled successfully
        """
        run = await self.backtest_repo.get_run(run_id)
        if not run or run.status != RunStatus.RUNNING:
            return False

        await self.backtest_repo.update_run(
            run_id=run_id,
            update_data={
                "status": RunStatus.FAILED,
                "end_time": datetime.now(),
                "error_message": "Cancelled by user"
            }
        )

        await self.session.commit()
        return True
