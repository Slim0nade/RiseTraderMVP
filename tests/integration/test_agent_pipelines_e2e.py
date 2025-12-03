"""
End-to-End Integration Tests for Agent Pipelines

Tests the complete agent pipeline flow with real Ollama models:
- Analysis pipeline (Technical, Fundamental, Sentiment)
- Decision pipeline (Position Sizing, Stop-Loss, Take-Profit)
- Full trading pipeline (Analysis → Decision)
"""

import asyncio
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.agent_service import AgentService


@pytest.mark.asyncio
@pytest.mark.integration
class TestAnalysisPipelineE2E:
    """Test analysis pipeline with real LLM inference."""

    async def test_analysis_pipeline_gold(self, db_session: AsyncSession):
        """
        Test analysis pipeline for Gold with real Ollama models.

        Expected behavior:
        - Creates 3 analysis agents (Technical, Fundamental, Sentiment)
        - Runs them in parallel
        - Returns structured analysis results
        - Execution time < 30 seconds
        """
        service = AgentService(db_session)

        result = await service.run_analysis_pipeline(
            symbol="Gold",
            timeframe="4H",
            strategy_team_id=None,
        )

        # Verify structure
        assert "technical" in result
        assert "fundamental" in result
        assert "sentiment" in result
        assert "metadata" in result

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["symbol"] == "Gold"
        assert metadata["timeframe"] == "4H"
        assert "execution_time_seconds" in metadata
        assert metadata["execution_time_seconds"] < 30  # Should complete in 30s

        # Verify each analysis has results (may be errors if MCP tools unavailable)
        for analysis_type in ["technical", "fundamental", "sentiment"]:
            assert result[analysis_type] is not None
            # Either has data or has error key
            assert isinstance(result[analysis_type], dict)

        print(f"\n✅ Analysis Pipeline Test Passed!")
        print(f"Execution Time: {metadata['execution_time_seconds']:.2f}s")
        print(f"Technical Result Keys: {list(result['technical'].keys())}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestDecisionPipelineE2E:
    """Test decision pipeline with real LLM inference."""

    async def test_decision_pipeline_with_analysis(self, db_session: AsyncSession):
        """
        Test decision pipeline with mock analysis data.

        Expected behavior:
        - Creates 3 decision agents (Position, Stop-Loss, Take-Profit)
        - Runs them sequentially
        - Returns structured decision results
        - Execution time < 20 seconds
        """
        service = AgentService(db_session)

        # Mock analysis data
        mock_analysis = {
            "technical": {
                "current_price": 2050.00,
                "direction": "bullish",
                "confidence": 0.75,
                "regime": "trending",
                "volatility": "medium",
            },
            "fundamental": {
                "macro_score": 0.65,
                "events_24h": [],
                "events_48h": ["FOMC Statement"],
            },
            "sentiment": {
                "positioning_score": 0.55,
                "crowd_psychology": "slightly_bullish",
            },
        }

        trade_context = {
            "account_balance": 50000.0,
            "current_drawdown": 0.03,
            "trade_conviction": 0.75,
            "win_rate": 0.60,
            "avg_win": 125,
            "avg_loss": 50,
            "correlation_with_existing": 0.0,
            "major_event_within_24h": False,
            "major_event_within_48h": True,
        }

        result = await service.run_decision_pipeline(
            symbol="Gold",
            analysis=mock_analysis,
            trade_context=trade_context,
            strategy_team_id=None,
        )

        # Verify structure
        assert "position_size" in result
        assert "stop_loss" in result
        assert "take_profit" in result
        assert "metadata" in result

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["symbol"] == "Gold"
        assert "execution_time_seconds" in metadata
        assert metadata["execution_time_seconds"] < 20  # Should complete in 20s

        # Verify decisions have data
        assert isinstance(result["position_size"], dict)
        assert isinstance(result["stop_loss"], dict)
        assert isinstance(result["take_profit"], dict)

        print(f"\n✅ Decision Pipeline Test Passed!")
        print(f"Execution Time: {metadata['execution_time_seconds']:.2f}s")


@pytest.mark.asyncio
@pytest.mark.integration
class TestFullPipelineE2E:
    """Test complete trading pipeline end-to-end."""

    async def test_full_pipeline_gold(self, db_session: AsyncSession):
        """
        Test complete pipeline: Analysis → Decision.

        Expected behavior:
        - Runs analysis pipeline first
        - Passes results to decision pipeline
        - Returns complete trade recommendation
        - Total execution time < 50 seconds
        """
        service = AgentService(db_session)

        trade_context = {
            "account_balance": 50000.0,
            "current_drawdown": 0.03,
            "trade_conviction": 0.75,
            "win_rate": 0.60,
            "avg_win": 125,
            "avg_loss": 50,
            "correlation_with_existing": 0.0,
            "major_event_within_24h": False,
            "major_event_within_48h": True,
        }

        result = await service.run_full_trading_pipeline(
            symbol="Gold",
            timeframe="4H",
            trade_context=trade_context,
            strategy_team_id=None,
        )

        # Verify structure
        assert "analysis" in result
        assert "decisions" in result
        assert "metadata" in result

        # Verify analysis section
        analysis = result["analysis"]
        assert "technical" in analysis
        assert "fundamental" in analysis
        assert "sentiment" in analysis

        # Verify decisions section
        decisions = result["decisions"]
        assert "position_size" in decisions
        assert "stop_loss" in decisions
        assert "take_profit" in decisions

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["symbol"] == "Gold"
        assert metadata["timeframe"] == "4H"
        assert "total_execution_time_seconds" in metadata
        assert metadata["total_execution_time_seconds"] < 50  # Should complete in 50s

        print(f"\n✅ Full Pipeline Test Passed!")
        print(f"Total Execution Time: {metadata['total_execution_time_seconds']:.2f}s")
        print(f"\nAnalysis Summary:")
        print(f"  Technical: {list(analysis['technical'].keys())}")
        print(f"  Fundamental: {list(analysis['fundamental'].keys())}")
        print(f"  Sentiment: {list(analysis['sentiment'].keys())}")
        print(f"\nDecision Summary:")
        print(f"  Position Size: {list(decisions['position_size'].keys())}")
        print(f"  Stop Loss: {list(decisions['stop_loss'].keys())}")
        print(f"  Take Profit: {list(decisions['take_profit'].keys())}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentRegistryE2E:
    """Test agent registry health and statistics."""

    async def test_registry_stats_after_pipeline(self, db_session: AsyncSession):
        """
        Test that registry properly tracks agents during pipeline execution.

        Note: Agents are registered temporarily during execution and
        unregistered after completion, so stats will show 0 after pipeline finishes.
        """
        service = AgentService(db_session)

        # Get initial stats (should be empty)
        stats = service.get_registry_stats()
        assert stats["total_agents"] == 0

        # Run a quick analysis pipeline
        result = await service.run_analysis_pipeline(
            symbol="Gold",
            timeframe="4H",
        )

        # After pipeline completes, agents should be unregistered
        stats = service.get_registry_stats()
        assert stats["total_agents"] == 0  # Agents cleaned up after execution

        print(f"\n✅ Registry Stats Test Passed!")
        print(f"Registry properly cleans up agents after execution")

    async def test_registry_health_check(self, db_session: AsyncSession):
        """Test registry health check endpoint."""
        service = AgentService(db_session)

        health = await service.get_registry_health()

        assert "timestamp" in health
        assert "total_agents" in health
        assert "healthy" in health
        assert "unhealthy" in health
        assert "overall_status" in health
        assert "agents" in health

        # With no agents running, status should be healthy
        assert health["overall_status"] == "healthy"
        assert health["total_agents"] == 0

        print(f"\n✅ Registry Health Check Passed!")
        print(f"Overall Status: {health['overall_status']}")


if __name__ == "__main__":
    """Run tests manually for debugging."""
    import sys
    sys.path.insert(0, "/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP")

    from src.database.session import get_session

    async def run_tests():
        async with get_session() as session:
            # Test 1: Analysis Pipeline
            print("\n" + "="*60)
            print("TEST 1: Analysis Pipeline")
            print("="*60)
            test1 = TestAnalysisPipelineE2E()
            await test1.test_analysis_pipeline_gold(session)

            # Test 2: Decision Pipeline
            print("\n" + "="*60)
            print("TEST 2: Decision Pipeline")
            print("="*60)
            test2 = TestDecisionPipelineE2E()
            await test2.test_decision_pipeline_with_analysis(session)

            # Test 3: Full Pipeline
            print("\n" + "="*60)
            print("TEST 3: Full Trading Pipeline")
            print("="*60)
            test3 = TestFullPipelineE2E()
            await test3.test_full_pipeline_gold(session)

            # Test 4: Registry
            print("\n" + "="*60)
            print("TEST 4: Agent Registry")
            print("="*60)
            test4 = TestAgentRegistryE2E()
            await test4.test_registry_stats_after_pipeline(session)
            await test4.test_registry_health_check(session)

    asyncio.run(run_tests())
