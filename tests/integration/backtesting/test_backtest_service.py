"""
Integration tests for BacktestService.

Tests full backtest execution with synthetic mode,
database persistence, and metrics calculation.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.backtest import BacktestConfiguration, ExecutionMode
from src.database.models.market_data import MarketData
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.backtesting.backtest_service import BacktestService
from src.services.backtesting.synthetic_engine import SyntheticEngine


@pytest.fixture
def mock_session():
    """Create mock async session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_backtest_repo():
    """Create mock backtest repository."""
    return AsyncMock(spec=BacktestRepository)


@pytest.fixture
def mock_market_data_repo():
    """Create mock market data repository."""
    return AsyncMock(spec=MarketDataRepository)


@pytest.fixture
def backtest_service(mock_session, mock_backtest_repo, mock_market_data_repo):
    """Create BacktestService with mocked dependencies."""
    return BacktestService(
        session=mock_session,
        backtest_repository=mock_backtest_repo,
        market_data_repository=mock_market_data_repo
    )


class TestBacktestServiceConfiguration:
    """Test backtest configuration management."""

    @pytest.mark.asyncio
    async def test_create_configuration(self, backtest_service):
        """Test creating a backtest configuration."""
        config = await backtest_service.create_configuration(
            name="Test Backtest",
            symbol="EURUSD",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005")
        )

        assert config.name == "Test Backtest"
        assert config.symbol == "EURUSD"
        assert config.initial_capital == Decimal("10000.00")
        assert config.execution_mode == ExecutionMode.SYNTHETIC_FAST

    @pytest.mark.asyncio
    async def test_validate_configuration_success(
        self, backtest_service, mock_backtest_repo, mock_market_data_repo
    ):
        """Test configuration validation with sufficient data."""
        config = BacktestConfiguration(
            id=uuid4(),
            name="Test",
            symbol="EURUSD",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0"),
            max_leverage=Decimal("1.0"),
            allow_short_selling=False
        )

        # Mock validation response
        mock_market_data_repo.validate_data_continuity.return_value = {
            "total_candles": 10000,
            "has_gaps": False,
            "first_candle_time": datetime(2024, 1, 1),
            "last_candle_time": datetime(2024, 12, 31)
        }

        mock_market_data_repo.count_candles_in_range.return_value = 10000

        validation = await backtest_service.validate_configuration(config)

        assert validation["can_proceed"] is True
        assert validation["config_name"] == "Test"

    @pytest.mark.asyncio
    async def test_validate_configuration_insufficient_data(
        self, backtest_service, mock_market_data_repo
    ):
        """Test configuration validation with insufficient data."""
        config = BacktestConfiguration(
            id=uuid4(),
            name="Test",
            symbol="EURUSD",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0"),
            max_leverage=Decimal("1.0"),
            allow_short_selling=False
        )

        # Mock insufficient data
        mock_market_data_repo.validate_data_continuity.return_value = {
            "total_candles": 50,
            "has_gaps": False,
            "first_candle_time": datetime(2024, 1, 1),
            "last_candle_time": datetime(2024, 1, 2),
            "error": "Insufficient data"
        }

        mock_market_data_repo.count_candles_in_range.return_value = 50

        validation = await backtest_service.validate_configuration(config)

        assert validation["can_proceed"] is False


class TestBacktestServiceExecution:
    """Test backtest execution."""

    @pytest.mark.asyncio
    async def test_run_backtest_synthetic_mode(
        self, backtest_service, mock_backtest_repo, mock_market_data_repo, mock_session
    ):
        """Test running a backtest in synthetic mode."""
        # Create configuration
        config = BacktestConfiguration(
            id=uuid4(),
            name="MA Crossover Test",
            symbol="EURUSD",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 10),
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0"),
            max_leverage=Decimal("1.0"),
            allow_short_selling=False
        )

        # Mock config retrieval
        mock_backtest_repo.get_config.return_value = config

        # Mock validation
        mock_market_data_repo.validate_data_continuity.return_value = {
            "total_candles": 1000,
            "can_proceed": True,
            "recommendation": "Ready for backtest"
        }

        mock_market_data_repo.count_candles_in_range.return_value = 1000

        # Create mock candles
        mock_candles = [
            MarketData(
                id=i,
                symbol="EURUSD",
                time=datetime(2024, 1, 1) + timedelta(minutes=i*5),
                source="MT4",
                timeframe="M5",
                open=Decimal("1.1000") + Decimal(str(i * 0.0001)),
                high=Decimal("1.1010") + Decimal(str(i * 0.0001)),
                low=Decimal("1.0990") + Decimal(str(i * 0.0001)),
                last=Decimal("1.1005") + Decimal(str(i * 0.0001)),
                volume=Decimal("100")
            )
            for i in range(100)
        ]

        # Mock data streaming
        async def mock_stream(*args, **kwargs):
            yield mock_candles[:50]
            yield mock_candles[50:]

        mock_market_data_repo.get_historical_candles_streamed = mock_stream

        # Mock run creation
        from src.database.models.backtest import BacktestRun, RunStatus
        run = BacktestRun(
            id=uuid4(),
            config_id=config.id,
            status=RunStatus.RUNNING,
            start_time=datetime.now(),
            candles_processed=0,
            agent_decisions_count=0,
            total_trades=0
        )
        mock_backtest_repo.create_run.return_value = run
        mock_backtest_repo.update_run.return_value = run
        mock_backtest_repo.get_run.return_value = run
        mock_backtest_repo.get_snapshots.return_value = []
        mock_backtest_repo.get_trades.return_value = []

        # Create simple decision engine
        def decision_engine(tick):
            # Buy every 20th candle, close every 30th
            if int(tick.timestamp.timestamp()) % 20 == 0:
                return {"action": "buy", "quantity": Decimal("1.0")}
            elif int(tick.timestamp.timestamp()) % 30 == 0:
                return {"action": "close"}
            return None

        # Run backtest
        result = await backtest_service.run_backtest(
            config_id=config.id,
            decision_engine=decision_engine,
            timeframe="M5"
        )

        # Verify run was created and completed
        assert mock_backtest_repo.create_run.called
        assert mock_backtest_repo.update_run.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_run_backtest_configuration_not_found(
        self, backtest_service, mock_backtest_repo
    ):
        """Test running backtest with non-existent configuration."""
        mock_backtest_repo.get_config.return_value = None

        with pytest.raises(ValueError, match="Configuration .* not found"):
            await backtest_service.run_backtest(
                config_id=uuid4(),
                timeframe="M5"
            )

    @pytest.mark.asyncio
    async def test_run_backtest_validation_failure(
        self, backtest_service, mock_backtest_repo, mock_market_data_repo
    ):
        """Test running backtest when validation fails."""
        config = BacktestConfiguration(
            id=uuid4(),
            name="Test",
            symbol="EURUSD",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            initial_capital=Decimal("10000.00"),
            execution_mode=ExecutionMode.SYNTHETIC_FAST,
            slippage_pct=Decimal("0.001"),
            commission_pct=Decimal("0.0005"),
            commission_fixed=Decimal("0.0"),
            max_leverage=Decimal("1.0"),
            allow_short_selling=False
        )

        mock_backtest_repo.get_config.return_value = config

        # Mock failed validation
        mock_market_data_repo.validate_data_continuity.return_value = {
            "total_candles": 0,
            "can_proceed": False,
            "recommendation": "No data available"
        }

        mock_market_data_repo.count_candles_in_range.return_value = 0

        with pytest.raises(ValueError, match="Cannot proceed"):
            await backtest_service.run_backtest(
                config_id=config.id,
                timeframe="M5"
            )


class TestBacktestServiceStatus:
    """Test backtest status tracking."""

    @pytest.mark.asyncio
    async def test_get_run_status(self, backtest_service, mock_backtest_repo):
        """Test retrieving run status."""
        from src.database.models.backtest import BacktestRun, RunStatus

        run = BacktestRun(
            id=uuid4(),
            config_id=uuid4(),
            status=RunStatus.COMPLETED,
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now(),
            candles_processed=10000,
            total_trades=50,
            total_return_pct=Decimal("15.5"),
            sharpe_ratio=Decimal("1.8"),
            max_drawdown_pct=Decimal("8.2"),
            win_rate=Decimal("0.62"),
            agent_decisions_count=0
        )

        mock_backtest_repo.get_run.return_value = run
        mock_backtest_repo.get_run_summary.return_value = {
            "total_trades": 50,
            "winning_trades": 31
        }

        status = await backtest_service.get_run_status(run.id)

        assert status["status"] == RunStatus.COMPLETED
        assert status["metrics"] is not None
        assert status["metrics"]["total_return_pct"] == 15.5

    @pytest.mark.asyncio
    async def test_cancel_run(self, backtest_service, mock_backtest_repo, mock_session):
        """Test cancelling a running backtest."""
        from src.database.models.backtest import BacktestRun, RunStatus

        run = BacktestRun(
            id=uuid4(),
            config_id=uuid4(),
            status=RunStatus.RUNNING,
            start_time=datetime.now(),
            candles_processed=5000,
            total_trades=0,
            agent_decisions_count=0
        )

        mock_backtest_repo.get_run.return_value = run

        result = await backtest_service.cancel_run(run.id)

        assert result is True
        assert mock_backtest_repo.update_run.called
        assert mock_session.commit.called


class TestSyntheticEngineIntegration:
    """Test SyntheticEngine integration with BacktestService."""

    def test_ma_crossover_signal_generation(self):
        """Test MA crossover generates signals correctly."""
        engine = SyntheticEngine(
            strategy="ma_crossover",
            params={"fast_period": 5, "slow_period": 10, "quantity": Decimal("1.0")}
        )

        # Feed candles with uptrend
        for i in range(15):
            from src.services.backtesting.data_replay_engine import MarketTick
            tick = MarketTick(
                symbol="EURUSD",
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=i*5),
                open=Decimal("1.1000") + Decimal(str(i * 0.001)),
                high=Decimal("1.1010") + Decimal(str(i * 0.001)),
                low=Decimal("1.0990") + Decimal(str(i * 0.001)),
                close=Decimal("1.1005") + Decimal(str(i * 0.001)),
                volume=100
            )

            signal = engine.process_tick(tick)

            # After warmup, should eventually generate buy signal
            if i >= 10 and signal.action:
                assert signal.action in ["buy", "close"]

    def test_rsi_strategy_signals(self):
        """Test RSI strategy generates overbought/oversold signals."""
        engine = SyntheticEngine(
            strategy="rsi",
            params={
                "rsi_period": 14,
                "oversold": 30,
                "overbought": 70,
                "quantity": Decimal("1.0")
            }
        )

        # Feed candles
        for i in range(20):
            from src.services.backtesting.data_replay_engine import MarketTick
            price = Decimal("1.1000") + Decimal(str((i % 5) * 0.001))
            tick = MarketTick(
                symbol="EURUSD",
                timestamp=datetime(2024, 1, 1) + timedelta(minutes=i*5),
                open=price,
                high=price + Decimal("0.001"),
                low=price - Decimal("0.001"),
                close=price,
                volume=100
            )

            signal = engine.process_tick(tick)

            # RSI should be calculated after warmup
            if i >= 15:
                assert signal.reason.startswith("RSI")
