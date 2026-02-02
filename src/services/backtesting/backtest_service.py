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
from .technical_indicators import TechnicalIndicatorsCalculator

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
        max_candles: int = 150000,
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
            max_candles: Maximum candles to process (default 150,000, prevents infinite loops)
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
            "max_candles": max_candles,
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
        existing_run_id: Optional[UUID] = None,
    ) -> BacktestRun:
        """
        Execute a backtest run.

        Args:
            config_id: Configuration UUID
            timeframe: Market data timeframe (e.g., 'M5', 'H1')
            random_seed: Random seed for deterministic replay
            decision_engine: Decision function for synthetic mode
            progress_callback: Optional callback(processed, total, metrics)
            existing_run_id: Optional existing run ID to use (avoids creating duplicate)

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

        # Use existing run or create new one
        if existing_run_id:
            run = await self.backtest_repo.get_run(existing_run_id)
            if not run:
                raise ValueError(f"Existing run {existing_run_id} not found")
            logger.info(
                "using_existing_backtest_run",
                run_id=str(existing_run_id),
                config_id=str(config_id),
            )
        else:
            # Create new backtest run (legacy behavior)
            run = await self.backtest_repo.create_run({
                "id": uuid4(),
                "config_id": config.id,
                "status": RunStatus.RUNNING,
                "start_time": datetime.now(),
                "random_seed": random_seed,
            })
            logger.info(
                "created_new_backtest_run",
                run_id=str(run.id),
                config_id=str(config_id),
            )

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
        # Initialize Redis progress publisher (optional - gracefully degrade if unavailable)
        progress_publisher = None
        try:
            from src.services.backtest_progress_service import BacktestProgressPublisher
            from src.utils.redis_client import get_redis_client
            redis_client = await get_redis_client()
            if redis_client:
                progress_publisher = BacktestProgressPublisher(redis_client)
                logger.info("progress_publisher_initialized", run_id=str(run.id))
        except Exception as e:
            logger.warning("progress_publisher_unavailable", error=str(e))
        
        # If no decision_engine provided, try to create from config_params
        logger.info(
            "checking_decision_engine_setup",
            run_id=str(run.id),
            decision_engine_provided=decision_engine is not None,
            has_config_params=config.config_params is not None,
            config_params=config.config_params
        )

        if decision_engine is None and config.config_params:
            synthetic_strategy = config.config_params.get("synthetic_strategy")
            synthetic_params = config.config_params.get("synthetic_params", {})

            # Also check for strategy params at root level of config_params
            if not synthetic_strategy:
                synthetic_strategy = config.config_params.get("strategy")

            logger.info(
                "extracted_strategy_params",
                run_id=str(run.id),
                synthetic_strategy=synthetic_strategy,
                synthetic_params=synthetic_params
            )

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
                            "stop_loss": signal.stop_loss,
                            "take_profit": signal.take_profit,
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
        trades_opened = 0  # Track positions opened
        trades_closed = 0  # Track positions closed (completed round-trip trades)
        snapshot_interval = 10  # Snapshots every 10 candles for accurate equity curve
        progress_interval = 1000  # Publish progress every 1000 candles
        
        # Create INITIAL snapshot before any trading
        first_tick_processed = False

        # Replay historical data
        async for tick, processed, total in self.data_replay.replay_with_progress(
            symbol=config.symbol,
            timeframe=timeframe,
            start_date=config.start_date,
            end_date=config.end_date,
            progress_callback=progress_callback
        ):
            candles_processed += 1

            # Check max candles limit to prevent infinite loops
            if candles_processed > config.max_candles:
                logger.warning(
                    "max_candles_limit_reached",
                    run_id=str(run.id),
                    candles_processed=candles_processed,
                    max_candles=config.max_candles,
                )
                # Mark run as TIMEOUT and break
                run.status = RunStatus.TIMEOUT
                run.error_message = f"Exceeded max candles limit ({config.max_candles})"
                break

            # Update portfolio with current market price
            portfolio.update_market_price(tick.symbol, tick.close)
            
            # Create INITIAL snapshot on first tick (before any trading)
            if not first_tick_processed:
                first_tick_processed = True
                initial_snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                await self.backtest_repo.create_snapshot(initial_snapshot)
                logger.info(
                    "initial_snapshot_created",
                    run_id=str(run.id),
                    total_value=float(initial_snapshot["total_value"]),
                )

            # ========== SL/TP ENFORCEMENT ==========
            # Check all open positions for stop loss / take profit hits
            # This happens BEFORE decision engine to ensure risk management is enforced
            if portfolio.has_position(tick.symbol):
                exit_signals = portfolio.check_exit_signals(tick.symbol, tick.close)
                for position, exit_reason in exit_signals:
                    # Close the position due to SL/TP hit
                    exit_result, gross_pnl, net_pnl = simulator.execute_exit(
                        portfolio=portfolio,
                        symbol=tick.symbol,
                        exit_price=tick.close,
                        timestamp=tick.timestamp,
                        position_id=position.position_id,
                    )
                    trades_closed += 1

                    # Update trade record with exit details
                    await self.backtest_repo.update_trade(
                        trade_id=exit_result.trade_id,
                        update_data={
                            "exit_timestamp": tick.timestamp,
                            "exit_price": tick.close,
                            "gross_pnl": gross_pnl,
                            "net_pnl": net_pnl,
                            "holding_duration_seconds": int(
                                (tick.timestamp - exit_result.timestamp).total_seconds()
                            ) if exit_result.timestamp else None,
                        }
                    )
                    logger.info(
                        "position_closed_by_exit_signal",
                        run_id=str(run.id),
                        trade_id=str(exit_result.trade_id),
                        exit_reason=exit_reason,
                        exit_price=float(tick.close),
                        gross_pnl=float(gross_pnl),
                        net_pnl=float(net_pnl),
                        portfolio_value=float(portfolio.get_total_value()),
                    )
            # ========== END SL/TP ENFORCEMENT ==========

            # Get trading decision (if decision engine provided)
            if decision_engine:
                # DEBUG: Log every 500th candle
                if candles_processed % 500 == 0:
                    logger.info(
                        "calling_decision_engine",
                        candle_num=candles_processed,
                        timestamp=tick.timestamp
                    )

                decision = decision_engine(tick)

                # DEBUG: Log when we get a decision
                if decision:
                    logger.info(
                        "decision_engine_returned_decision",
                        candle_num=candles_processed,
                        decision=decision
                    )

                if decision:
                    action = decision.get("action")
                    quantity = decision.get("quantity", Decimal("1.0"))
                    stop_loss = decision.get("stop_loss")
                    take_profit = decision.get("take_profit")

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
                                timestamp=tick.timestamp,
                                stop_loss=stop_loss,
                                take_profit=take_profit,
                            )

                            if result.success:
                                trades_opened += 1
                                # Save trade to database
                                trade_dict = simulator.to_simulated_trade_dict(
                                    result=result,
                                    backtest_run_id=run.id
                                )
                                await self.backtest_repo.create_trade(trade_dict)
                                logger.info(
                                    "trade_opened",
                                    run_id=str(run.id),
                                    trade_id=str(result.trade_id),
                                    action=action,
                                    price=float(tick.close),
                                    quantity=float(quantity),
                                    stop_loss=float(stop_loss) if stop_loss else None,
                                    take_profit=float(take_profit) if take_profit else None,
                                    portfolio_value=float(portfolio.get_total_value()),
                                )

                    elif action in ["close", "exit", "close_long", "close_short"] and portfolio.has_position(tick.symbol):
                        # Close existing position
                        exit_result, gross_pnl, net_pnl = simulator.execute_exit(
                            portfolio=portfolio,
                            symbol=tick.symbol,
                            exit_price=tick.close,
                            timestamp=tick.timestamp
                        )

                        # Increment closed trades counter
                        trades_closed += 1

                        # Update trade record with exit details
                        await self.backtest_repo.update_trade(
                            trade_id=exit_result.trade_id,
                            update_data={
                                "exit_timestamp": tick.timestamp,
                                "exit_price": tick.close,
                                "gross_pnl": gross_pnl,
                                "net_pnl": net_pnl,
                                "holding_duration_seconds": int(
                                    (tick.timestamp - exit_result.timestamp).total_seconds()
                                ) if exit_result.timestamp else None,
                            }
                        )
                        logger.info(
                            "trade_closed",
                            run_id=str(run.id),
                            trade_id=str(exit_result.trade_id),
                            action=action,
                            exit_price=float(tick.close),
                            gross_pnl=float(gross_pnl),
                            net_pnl=float(net_pnl),
                            portfolio_value=float(portfolio.get_total_value()),
                        )

            # Periodic portfolio snapshot
            if candles_processed % snapshot_interval == 0:
                snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                await self.backtest_repo.create_snapshot(snapshot)
            
            # Publish progress to Redis (for SSE streaming)
            if progress_publisher and candles_processed % progress_interval == 0:
                await progress_publisher.publish_progress(
                    run_id=run.id,
                    candles_processed=candles_processed,
                    total_candles=total,
                    status="running",
                    trades_count=trades_closed,  # Report closed trades
                    current_capital=float(portfolio.get_total_value()),
                )
            
            # Update database with progress (every 100 candles for good UI responsiveness)
            if candles_processed % 100 == 0:
                # Count agent decisions so far
                agent_decision_count = len(await self.backtest_repo.get_agent_decision_logs(run.id))

                await self.backtest_repo.update_run(
                    run_id=run.id,
                    update_data={
                        "candles_processed": candles_processed,
                        "agent_decisions_count": agent_decision_count,
                    }
                )
                # Commit to make progress visible to polling clients
                await self.session.commit()

        # Create FINAL snapshot after all trading
        if first_tick_processed:
            final_snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
            await self.backtest_repo.create_snapshot(final_snapshot)
            logger.info(
                "final_snapshot_created",
                run_id=str(run.id),
                total_value=float(final_snapshot["total_value"]),
                trades_opened=trades_opened,
                trades_closed=trades_closed,
            )

        # Update run with candles processed
        await self.backtest_repo.update_run(
            run_id=run.id,
            update_data={"candles_processed": candles_processed}
        )
        
        # Publish completion event
        if progress_publisher:
            await progress_publisher.publish_complete(
                run_id=run.id,
                total_candles=candles_processed,
                trades_count=trades_closed,  # Report closed trades as the meaningful count
                final_capital=float(portfolio.get_total_value()),
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

        # Check Ollama availability BEFORE starting backtest
        import httpx
        try:
            logger.info("checking_ollama_availability", ollama_url=ollama_url)
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ollama_url.replace('/v1', '')}/api/tags")
                if response.status_code != 200:
                    raise ValueError(f"Ollama not available at {ollama_url} (status: {response.status_code})")
                logger.info("ollama_available", ollama_url=ollama_url)
        except Exception as e:
            error_msg = f"Ollama server not accessible at {ollama_url}: {str(e)}"
            logger.error("ollama_unavailable", error=error_msg, ollama_url=ollama_url)
            raise ValueError(error_msg)

        integrator = AgentIntegrator(
            backtest_run_id=run.id,
            backtest_repo=self.backtest_repo,  # Pass repository for real-time logging
            model=model,
            ollama_base_url=ollama_url,
            decision_threshold=decision_threshold,
        )

        try:
            # Initialize LLM connection (with timeout protection)
            import asyncio
            try:
                await asyncio.wait_for(integrator.initialize(), timeout=120.0)
            except asyncio.TimeoutError:
                raise ValueError("Timeout initializing agent integrator after 120 seconds")

            candles_processed = 0
            snapshot_interval = 10  # More frequent snapshots in full mode
            decision_interval = 10  # Only query agent every N candles (performance)

            # Initialize technical indicators calculator
            indicator_calc = TechnicalIndicatorsCalculator(lookback_period=200)

            # Track first tick for initial snapshot
            first_tick_processed = False

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

                # Update technical indicators with new tick
                indicator_calc.update(tick)
                
                # Create INITIAL snapshot on first tick (before any trading)
                if not first_tick_processed:
                    first_tick_processed = True
                    initial_snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                    await self.backtest_repo.create_snapshot(initial_snapshot)
                    logger.info(
                        "initial_snapshot_created_full_pipeline",
                        run_id=str(run.id),
                        total_value=float(initial_snapshot["total_value"]),
                    )

                # Query agent for decision (not every candle for performance)
                if candles_processed % decision_interval == 0:
                    # Build FULL market context with portfolio awareness
                    market_context = self._build_full_market_context(
                        portfolio=portfolio,
                        symbol=tick.symbol,
                        tick=tick,
                        indicators=indicator_calc.calculate_indicators(),
                        max_position_size=config.initial_capital * Decimal("0.5"),  # 50% max
                        allow_short=config.allow_short_selling,
                    )

                    # Get agent decision
                    decision = await integrator.get_trading_decision(market_context)

                    if decision and decision.action != "hold":
                        # Execute trade based on agent decision
                        if decision.action in ["buy", "sell"]:
                            # Check if we can open position (now allows multiple)
                            can_open, reason = portfolio.can_open_position(
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

                                    # DEBUG: Log detailed portfolio state after opening position
                                    symbol_positions = portfolio.get_positions_for_symbol(tick.symbol)
                                    logger.info(
                                        "trade_opened_full_pipeline",
                                        run_id=str(run.id),
                                        trade_id=str(result.trade_id),
                                        action=decision.action,
                                        price=float(tick.close),
                                        quantity=float(decision.quantity),
                                        total_positions=portfolio.get_position_count(),
                                        symbol_positions_count=len(symbol_positions),
                                        symbol_positions_detail=[
                                            {
                                                "id": str(p.position_id),
                                                "action": p.action,
                                                "qty": float(p.quantity),
                                                "entry": float(p.entry_price),
                                            }
                                            for p in symbol_positions
                                        ],
                                    )
                            else:
                                logger.debug(
                                    "position_open_rejected",
                                    reason=reason,
                                    action=decision.action,
                                    symbol=tick.symbol,
                                )

                        elif decision.action in ["close_long", "close_short"] and portfolio.has_position(tick.symbol):
                            # Close oldest position (FIFO)
                            exit_result, gross_pnl, net_pnl = simulator.execute_exit(
                                portfolio=portfolio,
                                symbol=tick.symbol,
                                exit_price=tick.close,
                                timestamp=tick.timestamp
                            )

                            # Update trade record with exit details
                            await self.backtest_repo.update_trade(
                                trade_id=exit_result.trade_id,
                                update_data={
                                    "exit_timestamp": tick.timestamp,
                                    "exit_price": tick.close,
                                    "gross_pnl": gross_pnl,
                                    "net_pnl": net_pnl,
                                    "holding_duration_seconds": int(
                                        (tick.timestamp - exit_result.timestamp).total_seconds()
                                    ) if exit_result.timestamp else None,
                                }
                            )
                            logger.info(
                                "trade_closed_full_pipeline",
                                run_id=str(run.id),
                                trade_id=str(exit_result.trade_id),
                                gross_pnl=float(gross_pnl),
                                remaining_positions=portfolio.get_position_count(tick.symbol),
                            )

                        elif decision.action == "close_all" and portfolio.has_position(tick.symbol):
                            # Close ALL positions for this symbol
                            close_results = portfolio.close_all_positions_for_symbol(
                                tick.symbol, tick.close
                            )
                            for closed_pos, gross_pnl, capital_return in close_results:
                                # Deduct fees
                                notional = tick.close * closed_pos.quantity
                                fees = notional * simulator.commission_pct + simulator.commission_fixed
                                portfolio.cash_balance -= fees
                                net_pnl = gross_pnl - fees
                                
                                # Update trade record
                                await self.backtest_repo.update_trade(
                                    trade_id=closed_pos.trade_id,
                                    update_data={
                                        "exit_timestamp": tick.timestamp,
                                        "exit_price": tick.close,
                                        "gross_pnl": gross_pnl,
                                        "net_pnl": net_pnl,
                                        "fees_paid": fees,
                                        "holding_duration_seconds": int(
                                            (tick.timestamp - closed_pos.entry_timestamp).total_seconds()
                                        ),
                                    }
                                )
                            logger.info(
                                "all_positions_closed",
                                run_id=str(run.id),
                                symbol=tick.symbol,
                                positions_closed=len(close_results),
                                total_pnl=sum(r[1] for r in close_results),
                            )

                # Periodic portfolio snapshot
                if candles_processed % snapshot_interval == 0:
                    snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                    await self.backtest_repo.create_snapshot(snapshot)

                # Update database with progress (every 100 candles for good UI responsiveness)
                if candles_processed % 100 == 0:
                    # Get latest trades and snapshots for real-time metrics
                    trades = await self.backtest_repo.get_trades(run.id)
                    snapshots = await self.backtest_repo.get_snapshots(run.id)

                    # Calculate trade statistics
                    closed_trades = [t for t in trades if t.exit_timestamp is not None]
                    buy_trades = [t for t in trades if t.action == "buy"]
                    sell_trades = [t for t in trades if t.action == "sell"]
                    winning_trades = [t for t in closed_trades if t.net_pnl and t.net_pnl > 0]
                    losing_trades = [t for t in closed_trades if t.net_pnl and t.net_pnl <= 0]

                    # Calculate P&L
                    total_realized_pnl = sum(t.net_pnl for t in closed_trades if t.net_pnl)
                    unrealized_pnl = portfolio.get_unrealized_pnl()

                    # Equity curve (last 50 points for chart)
                    equity_curve = [
                        {
                            "timestamp": s.timestamp.isoformat(),
                            "value": float(s.total_value),
                            "unrealized_pnl": float(s.unrealized_pnl),
                            "realized_pnl": float(s.realized_pnl),
                        }
                        for s in snapshots[-50:]  # Last 50 points
                    ]

                    await self.backtest_repo.update_run(
                        run_id=run.id,
                        update_data={
                            "candles_processed": candles_processed,
                            "agent_decisions_count": integrator.decision_count,
                        }
                    )
                    # Commit to make progress visible to polling clients
                    await self.session.commit()

                    # Broadcast enhanced progress event to WebSocket clients
                    try:
                        from .backtest_events import BacktestEvent, BacktestEventType, get_event_broadcaster
                        broadcaster = get_event_broadcaster()
                        progress_event = BacktestEvent(
                            event_type=BacktestEventType.PROGRESS_UPDATE,
                            run_id=run.id,
                            timestamp=datetime.now(),
                            data={
                                "candles_processed": candles_processed,
                                "total_candles": total,
                                "agent_decisions_count": integrator.decision_count,
                                "current_equity": float(portfolio.get_total_value()),
                                "progress_pct": (candles_processed / total * 100) if total > 0 else 0,
                                # Trade statistics
                                "total_trades": len(trades),
                                "closed_trades": len(closed_trades),
                                "buy_count": len(buy_trades),
                                "sell_count": len(sell_trades),
                                "win_count": len(winning_trades),
                                "loss_count": len(losing_trades),
                                "win_rate": (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0,
                                # P&L metrics
                                "realized_pnl": float(total_realized_pnl),
                                "unrealized_pnl": float(unrealized_pnl),
                                "total_pnl": float(total_realized_pnl + unrealized_pnl),
                                # Equity curve for charting
                                "equity_curve": equity_curve,
                                # Current positions
                                "open_positions": len(portfolio.positions),
                            }
                        )
                        await broadcaster.broadcast(progress_event)
                    except Exception as broadcast_error:
                        logger.warning(
                            "progress_broadcast_failed",
                            error=str(broadcast_error),
                            run_id=str(run.id),
                        )

                    logger.debug(
                        "progress_committed",
                        run_id=str(run.id),
                        candles_processed=candles_processed,
                        decisions=integrator.decision_count,
                        equity=float(portfolio.get_total_value()),
                        trades=len(trades),
                    )

            # Create FINAL snapshot after all trading
            if first_tick_processed:
                final_snapshot = portfolio.get_snapshot(tick.timestamp, run.id)
                await self.backtest_repo.create_snapshot(final_snapshot)
                logger.info(
                    "final_snapshot_created_full_pipeline",
                    run_id=str(run.id),
                    total_value=float(final_snapshot["total_value"]),
                )

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
        """
        Extract position info as dict for market context.
        DEPRECATED: Use _build_full_market_context instead.
        Kept for backward compatibility.
        """
        if portfolio.has_position(symbol):
            positions = portfolio.get_positions_for_symbol(symbol)
            if positions:
                # Return first position for backward compatibility
                pos = positions[0]
                return {
                    "direction": "long" if pos.action == "buy" else "short",
                    "quantity": float(pos.quantity),
                    "entry_price": float(pos.entry_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                }
        return {}

    def _build_full_market_context(
        self,
        portfolio: PortfolioState,
        symbol: str,
        tick: Any,
        indicators: Dict[str, float],
        max_position_size: Decimal,
        allow_short: bool,
    ) -> "MarketContext":
        """
        Build comprehensive market context with full portfolio awareness.

        Args:
            portfolio: Portfolio state
            symbol: Current symbol being analyzed
            tick: Current market tick
            indicators: Technical indicators
            max_position_size: Max position size constraint
            allow_short: Whether shorting is allowed

        Returns:
            MarketContext with full portfolio state
        """
        from .agent_integrator import MarketContext

        # Get full portfolio context
        portfolio_ctx = portfolio.get_full_portfolio_context()

        # DEBUG: Log portfolio state for diagnostics
        logger.debug(
            "building_market_context",
            symbol=symbol,
            total_positions=len(portfolio_ctx["positions"]),
            symbols_with_positions=list(portfolio_ctx["symbols_summary"].keys()),
            portfolio_symbols_detail={
                sym: summary["position_count"]
                for sym, summary in portfolio_ctx["symbols_summary"].items()
            },
        )

        # Get current symbol positions
        current_symbol_positions = [
            p for p in portfolio_ctx["positions"] if p["symbol"] == symbol
        ]

        # DEBUG: Log filtered positions for current symbol
        logger.debug(
            "symbol_positions_filtered",
            symbol=symbol,
            matching_positions=len(current_symbol_positions),
            position_details=[
                {
                    "direction": p["direction"],
                    "quantity": p["quantity"],
                    "entry_price": p["entry_price"],
                }
                for p in current_symbol_positions
            ] if current_symbol_positions else "NONE",
        )
        
        # Get net direction for current symbol
        net_direction, net_qty = portfolio.get_net_position(symbol)
        
        return MarketContext(
            symbol=symbol,
            timestamp=tick.timestamp,
            current_price=tick.close,
            open=tick.open,
            high=tick.high,
            low=tick.low,
            close=tick.close,
            volume=tick.volume,
            indicators=indicators,
            
            # Full portfolio state
            cash_balance=Decimal(str(portfolio_ctx["cash_balance"])),
            buying_power=Decimal(str(portfolio_ctx["buying_power"])),
            portfolio_positions=portfolio_ctx["positions"],
            symbols_summary=portfolio_ctx["symbols_summary"],
            total_position_count=portfolio_ctx["total_position_count"],
            total_exposure=Decimal(str(portfolio_ctx["total_exposure"])),
            exposure_pct=Decimal(str(portfolio_ctx["exposure_pct"])),
            total_unrealized_pnl=Decimal(str(portfolio_ctx["total_unrealized_pnl"])),
            realized_pnl=Decimal(str(portfolio_ctx["realized_pnl"])),
            total_portfolio_value=Decimal(str(portfolio_ctx["total_value"])),
            
            # Current symbol specifics
            current_symbol_positions=current_symbol_positions,
            current_symbol_net_direction=net_direction,
            current_symbol_net_quantity=net_qty,
            
            # Risk constraints
            max_position_size=max_position_size,
            allow_short=allow_short,
            
            # Backward compatibility
            current_positions=self._get_position_dict(portfolio, symbol),
            unrealized_pnl=portfolio.get_unrealized_pnl(),
        )

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
