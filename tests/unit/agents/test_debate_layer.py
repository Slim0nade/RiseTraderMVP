"""
Unit tests for the Adversarial Debate Layer (Bull/Bear).

Tests cover:
- Initialization and configuration
- Individual bull/bear agent reasoning
- Debate dynamics and consensus building
- Error handling and edge cases
- Metrics collection
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

from src.agents.decision.debate_layer import (
    DebateLayer,
    BullAgent,
    BearAgent,
    DebateResult,
    DebateMetrics,
)
from src.agents.schemas.phase6_schemas import (
    BullAnalysis,
    BearAnalysis,
    DebateAnalysis,
    MarketContext,
)
from src.agents.utils.phase6_metrics import Phase6Metrics


@pytest.fixture
def mock_metrics():
    """Mock Phase6Metrics instance."""
    metrics = Mock(spec=Phase6Metrics)
    metrics.record_bull_analysis = Mock()
    metrics.record_bear_analysis = Mock()
    metrics.record_debate_consensus = Mock()
    metrics.record_debate_duration = Mock()
    return metrics


@pytest.fixture
def sample_market_context():
    """Sample market context for testing."""
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        current_price=Decimal("1.0950"),
        bid=Decimal("1.0949"),
        ask=Decimal("1.0951"),
        spread=Decimal("0.0002"),
        timestamp=datetime.now(),
        volume=1000,
        volatility=Decimal("0.0025"),
        trend="bullish",
        support_level=Decimal("1.0900"),
        resistance_level=Decimal("1.1000"),
        liquidity_score=Decimal("0.85"),
    )


@pytest.fixture
def bull_agent(mock_metrics):
    """Bull agent instance."""
    config = {
        "model": "gpt-4",
        "temperature": 0.3,
        "confidence_threshold": 0.6,
    }
    return BullAgent(config=config, metrics=mock_metrics)


@pytest.fixture
def bear_agent(mock_metrics):
    """Bear agent instance."""
    config = {
        "model": "gpt-4",
        "temperature": 0.3,
        "confidence_threshold": 0.6,
    }
    return BearAgent(config=config, metrics=mock_metrics)


@pytest.fixture
def debate_layer(mock_metrics):
    """DebateLayer instance."""
    config = {
        "max_rounds": 3,
        "consensus_threshold": 0.7,
        "model": "gpt-4",
        "temperature": 0.3,
    }
    return DebateLayer(config=config, metrics=mock_metrics)


class TestBullAgent:
    """Tests for BullAgent."""

    @pytest.mark.asyncio
    async def test_bull_agent_initialization(self, bull_agent):
        """Test bull agent initializes correctly."""
        assert bull_agent.role == "bull"
        assert bull_agent.config["model"] == "gpt-4"
        assert bull_agent.config["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_bull_agent_strong_bullish_analysis(
        self, bull_agent, sample_market_context, mock_metrics
    ):
        """Test bull agent produces strong bullish analysis."""
        # Mock LLM response
        mock_analysis = BullAnalysis(
            confidence=Decimal("0.85"),
            strength_score=Decimal("0.80"),
            key_bullish_factors=[
                "Strong uptrend confirmed",
                "Price above resistance",
                "High buying volume",
            ],
            risk_factors=["Overbought RSI"],
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0900"),
            reasoning="Strong bullish momentum with increasing volume.",
        )

        with patch.object(
            bull_agent, "_call_llm", new_callable=AsyncMock, return_value=mock_analysis
        ):
            result = await bull_agent.analyze(sample_market_context)

        assert result.confidence >= Decimal("0.7")
        assert result.strength_score >= Decimal("0.7")
        assert len(result.key_bullish_factors) >= 2
        assert result.target_price > sample_market_context.current_price
        mock_metrics.record_bull_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_bull_agent_weak_bullish_analysis(
        self, bull_agent, sample_market_context, mock_metrics
    ):
        """Test bull agent handles weak bullish signals."""
        # Mock weak bullish analysis
        mock_analysis = BullAnalysis(
            confidence=Decimal("0.45"),
            strength_score=Decimal("0.40"),
            key_bullish_factors=["Slight upward momentum"],
            risk_factors=[
                "Low volume",
                "Approaching resistance",
                "Divergence on indicators",
            ],
            target_price=Decimal("1.0980"),
            stop_loss=Decimal("1.0920"),
            reasoning="Weak bullish signals with significant risks.",
        )

        with patch.object(
            bull_agent, "_call_llm", new_callable=AsyncMock, return_value=mock_analysis
        ):
            result = await bull_agent.analyze(sample_market_context)

        assert result.confidence < Decimal("0.6")
        assert len(result.risk_factors) >= 2
        mock_metrics.record_bull_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_bull_agent_error_handling(
        self, bull_agent, sample_market_context, mock_metrics
    ):
        """Test bull agent handles LLM errors gracefully."""
        with patch.object(
            bull_agent,
            "_call_llm",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API error"),
        ):
            with pytest.raises(Exception, match="LLM API error"):
                await bull_agent.analyze(sample_market_context)


class TestBearAgent:
    """Tests for BearAgent."""

    @pytest.mark.asyncio
    async def test_bear_agent_initialization(self, bear_agent):
        """Test bear agent initializes correctly."""
        assert bear_agent.role == "bear"
        assert bear_agent.config["model"] == "gpt-4"
        assert bear_agent.config["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_bear_agent_strong_bearish_analysis(
        self, bear_agent, sample_market_context, mock_metrics
    ):
        """Test bear agent produces strong bearish analysis."""
        # Mock strong bearish analysis
        mock_analysis = BearAnalysis(
            confidence=Decimal("0.80"),
            strength_score=Decimal("0.75"),
            key_bearish_factors=[
                "Breakdown below support",
                "Increasing selling pressure",
                "Bearish divergence",
            ],
            counter_arguments=["Short-term oversold condition"],
            target_price=Decimal("1.0850"),
            stop_loss=Decimal("1.1000"),
            reasoning="Strong bearish momentum with technical breakdown.",
        )

        with patch.object(
            bear_agent, "_call_llm", new_callable=AsyncMock, return_value=mock_analysis
        ):
            result = await bear_agent.analyze(sample_market_context)

        assert result.confidence >= Decimal("0.7")
        assert result.strength_score >= Decimal("0.7")
        assert len(result.key_bearish_factors) >= 2
        assert result.target_price < sample_market_context.current_price
        mock_metrics.record_bear_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_bear_agent_weak_bearish_analysis(
        self, bear_agent, sample_market_context, mock_metrics
    ):
        """Test bear agent handles weak bearish signals."""
        mock_analysis = BearAnalysis(
            confidence=Decimal("0.40"),
            strength_score=Decimal("0.35"),
            key_bearish_factors=["Minor pullback"],
            counter_arguments=[
                "Strong support below",
                "Bullish trend intact",
                "Positive fundamentals",
            ],
            target_price=Decimal("1.0920"),
            stop_loss=Decimal("1.0980"),
            reasoning="Weak bearish signals with strong counter-arguments.",
        )

        with patch.object(
            bear_agent, "_call_llm", new_callable=AsyncMock, return_value=mock_analysis
        ):
            result = await bear_agent.analyze(sample_market_context)

        assert result.confidence < Decimal("0.6")
        assert len(result.counter_arguments) >= 2
        mock_metrics.record_bear_analysis.assert_called_once()


class TestDebateLayer:
    """Tests for DebateLayer."""

    @pytest.mark.asyncio
    async def test_debate_layer_initialization(self, debate_layer):
        """Test debate layer initializes correctly."""
        assert debate_layer.max_rounds == 3
        assert debate_layer.consensus_threshold == Decimal("0.7")
        assert debate_layer.bull_agent is not None
        assert debate_layer.bear_agent is not None

    @pytest.mark.asyncio
    async def test_strong_bullish_consensus(
        self, debate_layer, sample_market_context, mock_metrics
    ):
        """Test debate reaches strong bullish consensus."""
        # Mock strong bull, weak bear
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.85"),
            strength_score=Decimal("0.80"),
            key_bullish_factors=["Strong uptrend", "High volume", "Breakout"],
            risk_factors=["Minor resistance ahead"],
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0900"),
            reasoning="Strong bullish setup.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.30"),
            strength_score=Decimal("0.25"),
            key_bearish_factors=["Overbought RSI"],
            counter_arguments=["Strong trend", "High momentum"],
            target_price=Decimal("1.0920"),
            stop_loss=Decimal("1.1000"),
            reasoning="Weak bearish case.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            result = await debate_layer.conduct_debate(sample_market_context)

        assert result.final_decision == "bullish"
        assert result.confidence >= Decimal("0.7")
        assert result.bull_score > result.bear_score
        mock_metrics.record_debate_consensus.assert_called_once()

    @pytest.mark.asyncio
    async def test_strong_bearish_consensus(
        self, debate_layer, sample_market_context, mock_metrics
    ):
        """Test debate reaches strong bearish consensus."""
        # Mock weak bull, strong bear
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.35"),
            strength_score=Decimal("0.30"),
            key_bullish_factors=["Minor support"],
            risk_factors=["Weak momentum", "Breakdown risk"],
            target_price=Decimal("1.0980"),
            stop_loss=Decimal("1.0900"),
            reasoning="Weak bullish case.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.80"),
            strength_score=Decimal("0.75"),
            key_bearish_factors=["Support breakdown", "Bearish trend", "High volume"],
            counter_arguments=["Oversold indicators"],
            target_price=Decimal("1.0850"),
            stop_loss=Decimal("1.1000"),
            reasoning="Strong bearish setup.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            result = await debate_layer.conduct_debate(sample_market_context)

        assert result.final_decision == "bearish"
        assert result.confidence >= Decimal("0.7")
        assert result.bear_score > result.bull_score
        mock_metrics.record_debate_consensus.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_consensus_neutral(
        self, debate_layer, sample_market_context, mock_metrics
    ):
        """Test debate results in neutral when no consensus."""
        # Mock balanced arguments
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.55"),
            strength_score=Decimal("0.50"),
            key_bullish_factors=["Some support", "Slight uptrend"],
            risk_factors=["Resistance ahead", "Low volume"],
            target_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0900"),
            reasoning="Mixed bullish signals.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.50"),
            strength_score=Decimal("0.48"),
            key_bearish_factors=["Resistance overhead", "Divergence"],
            counter_arguments=["Support holding", "Positive trend"],
            target_price=Decimal("1.0900"),
            stop_loss=Decimal("1.1000"),
            reasoning="Mixed bearish signals.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            result = await debate_layer.conduct_debate(sample_market_context)

        assert result.final_decision == "neutral"
        assert result.confidence < Decimal("0.7")
        assert abs(result.bull_score - result.bear_score) < Decimal("0.15")
        mock_metrics.record_debate_consensus.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_round_debate(
        self, debate_layer, sample_market_context, mock_metrics
    ):
        """Test debate conducts multiple rounds when needed."""
        # Mock close scores requiring multiple rounds
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.60"),
            strength_score=Decimal("0.58"),
            key_bullish_factors=["Moderate uptrend"],
            risk_factors=["Some resistance"],
            target_price=Decimal("1.1020"),
            stop_loss=Decimal("1.0900"),
            reasoning="Moderate bullish case.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.55"),
            strength_score=Decimal("0.53"),
            key_bearish_factors=["Some weakness"],
            counter_arguments=["Trend support"],
            target_price=Decimal("1.0910"),
            stop_loss=Decimal("1.1000"),
            reasoning="Moderate bearish case.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            result = await debate_layer.conduct_debate(sample_market_context)

        # Should have conducted multiple rounds
        assert result.rounds_conducted >= 1
        assert result.rounds_conducted <= debate_layer.max_rounds

    @pytest.mark.asyncio
    async def test_debate_timeout(self, debate_layer, sample_market_context):
        """Test debate respects max_rounds limit."""
        # Mock balanced analyses that never reach consensus
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.50"),
            strength_score=Decimal("0.50"),
            key_bullish_factors=["Equal strength"],
            risk_factors=["Equal risk"],
            target_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0900"),
            reasoning="Balanced.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.50"),
            strength_score=Decimal("0.50"),
            key_bearish_factors=["Equal strength"],
            counter_arguments=["Equal counter"],
            target_price=Decimal("1.0900"),
            stop_loss=Decimal("1.1000"),
            reasoning="Balanced.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            result = await debate_layer.conduct_debate(sample_market_context)

        assert result.rounds_conducted == debate_layer.max_rounds
        assert result.final_decision == "neutral"

    @pytest.mark.asyncio
    async def test_debate_metrics_recording(
        self, debate_layer, sample_market_context, mock_metrics
    ):
        """Test debate records metrics correctly."""
        mock_bull_analysis = BullAnalysis(
            confidence=Decimal("0.75"),
            strength_score=Decimal("0.70"),
            key_bullish_factors=["Strong"],
            risk_factors=["Minor"],
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0900"),
            reasoning="Strong.",
        )

        mock_bear_analysis = BearAnalysis(
            confidence=Decimal("0.40"),
            strength_score=Decimal("0.35"),
            key_bearish_factors=["Weak"],
            counter_arguments=["Strong counter"],
            target_price=Decimal("1.0920"),
            stop_loss=Decimal("1.1000"),
            reasoning="Weak.",
        )

        with patch.object(
            debate_layer.bull_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bull_analysis,
        ), patch.object(
            debate_layer.bear_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_bear_analysis,
        ):
            await debate_layer.conduct_debate(sample_market_context)

        # Verify metrics were recorded
        assert mock_metrics.record_bull_analysis.call_count >= 1
        assert mock_metrics.record_bear_analysis.call_count >= 1
        assert mock_metrics.record_debate_consensus.call_count == 1
        assert mock_metrics.record_debate_duration.call_count == 1


class TestDebateResult:
    """Tests for DebateResult schema."""

    def test_debate_result_creation(self):
        """Test DebateResult can be created with valid data."""
        result = DebateResult(
            final_decision="bullish",
            confidence=Decimal("0.80"),
            bull_score=Decimal("0.75"),
            bear_score=Decimal("0.25"),
            consensus_strength=Decimal("0.70"),
            key_arguments=["Strong uptrend", "High volume"],
            risks_identified=["Overbought RSI"],
            rounds_conducted=2,
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0900"),
        )

        assert result.final_decision == "bullish"
        assert result.confidence == Decimal("0.80")
        assert result.rounds_conducted == 2

    def test_debate_result_validation(self):
        """Test DebateResult validates decision values."""
        with pytest.raises(ValueError):
            DebateResult(
                final_decision="invalid_decision",  # Should be bullish/bearish/neutral
                confidence=Decimal("0.80"),
                bull_score=Decimal("0.75"),
                bear_score=Decimal("0.25"),
                consensus_strength=Decimal("0.70"),
                key_arguments=["test"],
                risks_identified=["test"],
                rounds_conducted=1,
                target_price=Decimal("1.1050"),
                stop_loss=Decimal("1.0900"),
            )
