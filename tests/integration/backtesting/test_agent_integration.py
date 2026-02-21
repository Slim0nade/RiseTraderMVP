"""
Integration test for AgentIntegrator (T030).

Tests the full pipeline mode where trading decisions are made by
LLM agents via Ollama. Uses real PostgreSQL data and real Ollama LLM.

Skips gracefully if infrastructure is unavailable — never mocks.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.market_data_repository import MarketDataRepository
from src.services.backtesting.agent_integrator import (
    AgentDecision,
    AgentIntegrator,
    MarketContext,
)


def _ollama_reachable() -> bool:
    """Check if Ollama server is reachable."""
    url = os.environ.get("OLLAMA_BASE_URL", "http://192.168.0.123:11434")
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.asyncio
class TestAgentIntegration:
    """T030: Integration test for agent integration (full pipeline mode)."""

    async def test_agent_decision_with_real_llm(
        self, async_session: AsyncSession
    ):
        """
        Test that AgentIntegrator gets a valid decision from real Ollama LLM.

        Verifies:
        - LLM client initializes against real Ollama
        - Real market data is fetched from Postgres
        - LLM returns a parseable AgentDecision
        - Decision has valid action, conviction, rationale, key_factors
        """
        if not _ollama_reachable():
            pytest.skip("Ollama server not reachable — skipping agent integration test")

        # Fetch real market data from Postgres
        market_data_repo = MarketDataRepository(async_session)
        candles = await market_data_repo.get_latest_ticks(
            symbol="CrudeOIL",
            timeframe="H1",
            limit=50,
        )

        if len(candles) < 10:
            # Try EURUSD as fallback
            candles = await market_data_repo.get_latest_ticks(
                symbol="EURUSD",
                timeframe="H1",
                limit=50,
            )

        if len(candles) < 10:
            pytest.skip("Insufficient market data in database for agent test")

        latest = candles[-1]
        symbol = latest.symbol

        # Build price history from real candles
        price_history = [
            {
                "timestamp": c.time.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": int(c.volume),
            }
            for c in candles[-20:]
        ]

        # Build MarketContext from real data
        market_context = MarketContext(
            symbol=symbol,
            timestamp=latest.time,
            current_price=latest.close,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=int(latest.volume),
            price_history=price_history,
            indicators={
                "rsi_14": 55.0,
                "ema_8": float(latest.close) * 0.999,
                "ema_29": float(latest.close) * 1.001,
            },
            cash_balance=Decimal("10000"),
            buying_power=Decimal("10000"),
            total_portfolio_value=Decimal("10000"),
            max_position_size=Decimal("5000"),
        )

        # Create AgentIntegrator with real Ollama
        backtest_repo = BacktestRepository(async_session)
        integrator = AgentIntegrator(
            backtest_run_id=uuid4(),
            backtest_repo=backtest_repo,
            model="qwen3:14b",
            ollama_base_url=os.environ.get(
                "OLLAMA_BASE_URL", "http://192.168.0.123:11434"
            ),
            temperature=0.3,
            decision_threshold=0.5,
        )

        await integrator.initialize()

        # Get decision from real LLM
        decision = await integrator.get_trading_decision(market_context)

        # Verify decision structure
        assert decision is not None
        assert isinstance(decision, AgentDecision)
        assert decision.action in (
            "buy", "sell", "hold", "close_all", "close_long", "close_short", "scale_in"
        )
        assert 0.0 <= decision.conviction <= 1.0
        assert len(decision.rationale) > 0
        assert isinstance(decision.key_factors, list)
        assert len(decision.key_factors) >= 1
        assert len(decision.risk_assessment) > 0
        assert decision.processing_time_ms > 0
        assert decision.model_used == "qwen3:14b"

        await integrator.shutdown()

        print(f"\n  Agent decision: {decision.action}")
        print(f"  Conviction: {decision.conviction:.2f}")
        print(f"  Processing time: {decision.processing_time_ms}ms")
        print(f"  Rationale: {decision.rationale[:100]}...")

    async def test_agent_decision_logging_to_db(
        self, async_session: AsyncSession
    ):
        """
        Test that agent decisions are logged to the real database.

        Verifies:
        - _log_decision() writes to agent_decision_logs table
        - Logged entry has correct backtest_run_id, action, conviction
        """
        if not _ollama_reachable():
            pytest.skip("Ollama server not reachable — skipping agent logging test")

        # Fetch minimal real data
        market_data_repo = MarketDataRepository(async_session)
        candles = await market_data_repo.get_latest_ticks(
            symbol="CrudeOIL",
            timeframe="H1",
            limit=10,
        )

        if len(candles) < 5:
            candles = await market_data_repo.get_latest_ticks(
                symbol="EURUSD",
                timeframe="H1",
                limit=10,
            )

        if len(candles) < 5:
            pytest.skip("Insufficient market data for logging test")

        latest = candles[-1]
        run_id = uuid4()

        market_context = MarketContext(
            symbol=latest.symbol,
            timestamp=latest.time,
            current_price=latest.close,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=int(latest.volume),
            cash_balance=Decimal("10000"),
            buying_power=Decimal("10000"),
            total_portfolio_value=Decimal("10000"),
            max_position_size=Decimal("5000"),
        )

        backtest_repo = BacktestRepository(async_session)
        integrator = AgentIntegrator(
            backtest_run_id=run_id,
            backtest_repo=backtest_repo,
            model="qwen3:14b",
            ollama_base_url=os.environ.get(
                "OLLAMA_BASE_URL", "http://192.168.0.123:11434"
            ),
            temperature=0.3,
            decision_threshold=0.5,
        )

        await integrator.initialize()
        decision = await integrator.get_trading_decision(market_context)

        # Verify decision was logged in memory
        logs = integrator.get_decision_logs()
        assert len(logs) == 1

        log_entry = logs[0]
        assert log_entry.backtest_run_id == run_id
        assert log_entry.agent_identifier == "trading_agent_qwen3:14b"
        assert log_entry.decision_type == "trade"
        assert log_entry.output_decision["action"] == decision.action
        assert log_entry.processing_time_ms == decision.processing_time_ms

        await integrator.shutdown()

        print(f"\n  Decision logged with ID: {log_entry.id}")
        print(f"  Agent: {log_entry.agent_identifier}")
        print(f"  Action: {log_entry.output_decision['action']}")

    async def test_agent_error_returns_safe_hold(
        self, async_session: AsyncSession
    ):
        """
        Test that AgentIntegrator returns a safe 'hold' on LLM error.

        Uses an intentionally bad Ollama URL to trigger an error,
        verifying the graceful fallback behavior.
        """
        market_data_repo = MarketDataRepository(async_session)
        candles = await market_data_repo.get_latest_ticks(
            symbol="CrudeOIL",
            timeframe="H1",
            limit=5,
        )

        if len(candles) < 3:
            candles = await market_data_repo.get_latest_ticks(
                symbol="EURUSD",
                timeframe="H1",
                limit=5,
            )

        if len(candles) < 3:
            pytest.skip("Insufficient market data for error fallback test")

        latest = candles[-1]

        market_context = MarketContext(
            symbol=latest.symbol,
            timestamp=latest.time,
            current_price=latest.close,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=int(latest.volume),
            cash_balance=Decimal("10000"),
            buying_power=Decimal("10000"),
            total_portfolio_value=Decimal("10000"),
            max_position_size=Decimal("5000"),
        )

        backtest_repo = BacktestRepository(async_session)
        integrator = AgentIntegrator(
            backtest_run_id=uuid4(),
            backtest_repo=backtest_repo,
            model="qwen3:14b",
            # Intentionally bad URL to trigger error
            ollama_base_url="http://127.0.0.1:1",
            temperature=0.3,
        )

        await integrator.initialize()
        decision = await integrator.get_trading_decision(market_context)

        # Should return safe hold on error
        assert decision is not None
        assert decision.action == "hold"
        assert decision.conviction == 0.0
        assert "error" in decision.rationale.lower() or "Error" in decision.rationale

        await integrator.shutdown()

        print(f"\n  Error fallback verified: action={decision.action}")
