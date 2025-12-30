"""
Unit tests for the Risk Debate Team (Conservative/Aggressive agents).

Tests cover:
- Individual conservative/aggressive agent analysis
- Risk debate dynamics
- Position sizing recommendations
- Error handling
- Metrics collection
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from decimal import Decimal

from src.agents.decision.risk_debate_team import (
    RiskDebateTeam,
    ConservativeAgent,
    AggressiveAgent,
    RiskDebateResult,
)
from src.agents.schemas.phase6_schemas import (
    ConservativeRiskAnalysis,
    AggressiveRiskAnalysis,
    RiskDebateAnalysis,
    RiskContext,
    MarketContext,
)
from src.agents.utils.phase6_metrics import Phase6Metrics


@pytest.fixture
def mock_metrics():
    """Mock Phase6Metrics instance."""
    metrics = Mock(spec=Phase6Metrics)
    metrics.record_conservative_analysis = Mock()
    metrics.record_aggressive_analysis = Mock()
    metrics.record_risk_debate_outcome = Mock()
    metrics.record_risk_debate_duration = Mock()
    return metrics


@pytest.fixture
def sample_risk_context():
    """Sample risk context for testing."""
    return RiskContext(
        account_balance=Decimal("100000.00"),
        equity=Decimal("102000.00"),
        margin_used=Decimal("5000.00"),
        margin_available=Decimal("97000.00"),
        open_positions_count=2,
        total_exposure=Decimal("15000.00"),
        max_drawdown=Decimal("0.05"),
        daily_pnl=Decimal("2000.00"),
        win_rate=Decimal("0.65"),
        sharpe_ratio=Decimal("1.8"),
        current_var=Decimal("2500.00"),
        portfolio_beta=Decimal("0.95"),
    )


@pytest.fixture
def sample_market_context():
    """Sample market context."""
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
def conservative_agent(mock_metrics):
    """Conservative agent instance."""
    config = {
        "model": "gpt-4",
        "temperature": 0.2,
        "risk_tolerance": 0.02,
    }
    return ConservativeAgent(config=config, metrics=mock_metrics)


@pytest.fixture
def aggressive_agent(mock_metrics):
    """Aggressive agent instance."""
    config = {
        "model": "gpt-4",
        "temperature": 0.4,
        "risk_tolerance": 0.05,
    }
    return AggressiveAgent(config=config, metrics=mock_metrics)


@pytest.fixture
def risk_debate_team(mock_metrics):
    """RiskDebateTeam instance."""
    config = {
        "max_rounds": 3,
        "consensus_threshold": 0.7,
        "model": "gpt-4",
    }
    return RiskDebateTeam(config=config, metrics=mock_metrics)


class TestConservativeAgent:
    """Tests for ConservativeAgent."""

    @pytest.mark.asyncio
    async def test_conservative_agent_initialization(self, conservative_agent):
        """Test conservative agent initializes correctly."""
        assert conservative_agent.role == "conservative"
        assert conservative_agent.config["risk_tolerance"] == 0.02

    @pytest.mark.asyncio
    async def test_conservative_small_position_size(
        self, conservative_agent, sample_risk_context, sample_market_context, mock_metrics
    ):
        """Test conservative agent recommends small position sizes."""
        mock_analysis = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("0.5"),  # 0.5% of account
            max_risk_per_trade=Decimal("0.01"),  # 1% max risk
            stop_loss_distance=Decimal("0.0030"),  # 30 pips
            confidence=Decimal("0.85"),
            risk_factors=[
                "High market volatility",
                "Multiple open positions",
                "Recent drawdown",
            ],
            protective_measures=[
                "Tight stop loss",
                "Reduced position size",
                "Monitor closely",
            ],
            reasoning="Conservative sizing due to current market conditions.",
        )

        with patch.object(
            conservative_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            result = await conservative_agent.analyze(
                sample_risk_context, sample_market_context, "bullish"
            )

        assert result.recommended_position_size <= Decimal("1.0")
        assert result.max_risk_per_trade <= Decimal("0.02")
        assert len(result.risk_factors) >= 2
        assert len(result.protective_measures) >= 2
        mock_metrics.record_conservative_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_conservative_high_risk_rejection(
        self, conservative_agent, sample_risk_context, sample_market_context, mock_metrics
    ):
        """Test conservative agent rejects high-risk scenarios."""
        # Modify risk context to be high-risk
        high_risk_context = sample_risk_context.model_copy()
        high_risk_context.max_drawdown = Decimal("0.15")  # 15% drawdown
        high_risk_context.margin_available = Decimal("10000.00")  # Low margin
        high_risk_context.open_positions_count = 10  # Many positions

        mock_analysis = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("0.0"),  # No position
            max_risk_per_trade=Decimal("0.0"),
            stop_loss_distance=Decimal("0.0"),
            confidence=Decimal("0.95"),
            risk_factors=[
                "Excessive drawdown",
                "Low margin available",
                "Too many open positions",
                "High portfolio risk",
            ],
            protective_measures=["Close existing positions", "Wait for better conditions"],
            reasoning="Risk too high - recommend no new positions.",
        )

        with patch.object(
            conservative_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            result = await conservative_agent.analyze(
                high_risk_context, sample_market_context, "bullish"
            )

        assert result.recommended_position_size == Decimal("0.0")
        assert len(result.risk_factors) >= 3
        mock_metrics.record_conservative_analysis.assert_called_once()


class TestAggressiveAgent:
    """Tests for AggressiveAgent."""

    @pytest.mark.asyncio
    async def test_aggressive_agent_initialization(self, aggressive_agent):
        """Test aggressive agent initializes correctly."""
        assert aggressive_agent.role == "aggressive"
        assert aggressive_agent.config["risk_tolerance"] == 0.05

    @pytest.mark.asyncio
    async def test_aggressive_larger_position_size(
        self, aggressive_agent, sample_risk_context, sample_market_context, mock_metrics
    ):
        """Test aggressive agent recommends larger position sizes."""
        mock_analysis = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("3.0"),  # 3% of account
            max_risk_per_trade=Decimal("0.04"),  # 4% max risk
            stop_loss_distance=Decimal("0.0050"),  # 50 pips
            confidence=Decimal("0.80"),
            opportunity_factors=[
                "Strong bullish signal",
                "High win rate",
                "Positive Sharpe ratio",
            ],
            calculated_risks=[
                "Wider stop loss",
                "Larger position size",
            ],
            reasoning="Strong opportunity justifies increased position size.",
        )

        with patch.object(
            aggressive_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            result = await aggressive_agent.analyze(
                sample_risk_context, sample_market_context, "bullish"
            )

        assert result.recommended_position_size >= Decimal("2.0")
        assert result.max_risk_per_trade <= Decimal("0.05")
        assert len(result.opportunity_factors) >= 2
        mock_metrics.record_aggressive_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggressive_moderate_position_on_weak_signal(
        self, aggressive_agent, sample_risk_context, sample_market_context, mock_metrics
    ):
        """Test aggressive agent moderates on weak signals."""
        # Modify market context for weak signal
        weak_market = sample_market_context.model_copy()
        weak_market.volatility = Decimal("0.0050")  # High volatility

        mock_analysis = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("1.5"),  # Moderate
            max_risk_per_trade=Decimal("0.025"),
            stop_loss_distance=Decimal("0.0040"),
            confidence=Decimal("0.60"),
            opportunity_factors=["Potential upside"],
            calculated_risks=[
                "High volatility",
                "Weak signal strength",
                "Uncertain conditions",
            ],
            reasoning="Moderate position due to weaker setup.",
        )

        with patch.object(
            aggressive_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            result = await aggressive_agent.analyze(
                sample_risk_context, weak_market, "bullish"
            )

        assert result.recommended_position_size < Decimal("2.5")
        assert len(result.calculated_risks) >= 2


class TestRiskDebateTeam:
    """Tests for RiskDebateTeam."""

    @pytest.mark.asyncio
    async def test_risk_debate_team_initialization(self, risk_debate_team):
        """Test risk debate team initializes correctly."""
        assert risk_debate_team.max_rounds == 3
        assert risk_debate_team.conservative_agent is not None
        assert risk_debate_team.aggressive_agent is not None

    @pytest.mark.asyncio
    async def test_conservative_wins_high_risk(
        self,
        risk_debate_team,
        sample_risk_context,
        sample_market_context,
        mock_metrics,
    ):
        """Test conservative agent wins in high-risk scenarios."""
        # Mock conservative small, aggressive moderate
        mock_conservative = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("0.5"),
            max_risk_per_trade=Decimal("0.01"),
            stop_loss_distance=Decimal("0.0030"),
            confidence=Decimal("0.90"),
            risk_factors=["High volatility", "Market uncertainty"],
            protective_measures=["Tight SL", "Small size"],
            reasoning="Too risky.",
        )

        mock_aggressive = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("2.0"),
            max_risk_per_trade=Decimal("0.03"),
            stop_loss_distance=Decimal("0.0045"),
            confidence=Decimal("0.60"),
            opportunity_factors=["Some opportunity"],
            calculated_risks=["Moderate risk"],
            reasoning="Moderate opportunity.",
        )

        with patch.object(
            risk_debate_team.conservative_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_conservative,
        ), patch.object(
            risk_debate_team.aggressive_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_aggressive,
        ):
            result = await risk_debate_team.conduct_debate(
                sample_risk_context, sample_market_context, "bullish", Decimal("0.80")
            )

        # Conservative should win (higher confidence)
        assert result.final_position_size <= Decimal("1.5")
        assert result.conservative_weight >= result.aggressive_weight
        mock_metrics.record_risk_debate_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggressive_wins_low_risk(
        self,
        risk_debate_team,
        sample_risk_context,
        sample_market_context,
        mock_metrics,
    ):
        """Test aggressive agent wins in low-risk favorable scenarios."""
        # Mock conservative moderate, aggressive strong
        mock_conservative = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("1.0"),
            max_risk_per_trade=Decimal("0.015"),
            stop_loss_distance=Decimal("0.0035"),
            confidence=Decimal("0.65"),
            risk_factors=["Some risk"],
            protective_measures=["Standard measures"],
            reasoning="Acceptable risk.",
        )

        mock_aggressive = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("3.5"),
            max_risk_per_trade=Decimal("0.045"),
            stop_loss_distance=Decimal("0.0050"),
            confidence=Decimal("0.85"),
            opportunity_factors=[
                "Strong signal",
                "High win rate",
                "Good conditions",
            ],
            calculated_risks=["Manageable"],
            reasoning="Excellent opportunity.",
        )

        with patch.object(
            risk_debate_team.conservative_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_conservative,
        ), patch.object(
            risk_debate_team.aggressive_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_aggressive,
        ):
            result = await risk_debate_team.conduct_debate(
                sample_risk_context, sample_market_context, "bullish", Decimal("0.85")
            )

        # Aggressive should have more weight
        assert result.final_position_size >= Decimal("2.0")
        assert result.aggressive_weight >= result.conservative_weight
        mock_metrics.record_risk_debate_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_balanced_debate_outcome(
        self,
        risk_debate_team,
        sample_risk_context,
        sample_market_context,
        mock_metrics,
    ):
        """Test balanced outcome when both agents have similar confidence."""
        mock_conservative = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("1.0"),
            max_risk_per_trade=Decimal("0.015"),
            stop_loss_distance=Decimal("0.0035"),
            confidence=Decimal("0.75"),
            risk_factors=["Moderate risk"],
            protective_measures=["Standard"],
            reasoning="Balanced.",
        )

        mock_aggressive = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("2.5"),
            max_risk_per_trade=Decimal("0.035"),
            stop_loss_distance=Decimal("0.0045"),
            confidence=Decimal("0.72"),
            opportunity_factors=["Good opportunity"],
            calculated_risks=["Acceptable"],
            reasoning="Good setup.",
        )

        with patch.object(
            risk_debate_team.conservative_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_conservative,
        ), patch.object(
            risk_debate_team.aggressive_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_aggressive,
        ):
            result = await risk_debate_team.conduct_debate(
                sample_risk_context, sample_market_context, "bullish", Decimal("0.75")
            )

        # Should be weighted average
        expected_size = (
            mock_conservative.recommended_position_size * result.conservative_weight
            + mock_aggressive.recommended_position_size * result.aggressive_weight
        )
        assert abs(result.final_position_size - expected_size) < Decimal("0.1")

    @pytest.mark.asyncio
    async def test_risk_debate_respects_max_limits(
        self,
        risk_debate_team,
        sample_risk_context,
        sample_market_context,
        mock_metrics,
    ):
        """Test debate respects system max risk limits."""
        # Mock very aggressive recommendation
        mock_conservative = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("2.0"),
            max_risk_per_trade=Decimal("0.025"),
            stop_loss_distance=Decimal("0.0040"),
            confidence=Decimal("0.70"),
            risk_factors=[],
            protective_measures=[],
            reasoning="Acceptable.",
        )

        mock_aggressive = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("8.0"),  # Very large
            max_risk_per_trade=Decimal("0.10"),  # 10% risk!
            stop_loss_distance=Decimal("0.0080"),
            confidence=Decimal("0.80"),
            opportunity_factors=["Huge opportunity"],
            calculated_risks=["High but justified"],
            reasoning="Go big.",
        )

        with patch.object(
            risk_debate_team.conservative_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_conservative,
        ), patch.object(
            risk_debate_team.aggressive_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_aggressive,
        ):
            result = await risk_debate_team.conduct_debate(
                sample_risk_context, sample_market_context, "bullish", Decimal("0.75")
            )

        # Should cap at reasonable max (e.g., 5% of account)
        assert result.final_position_size <= Decimal("5.0")
        assert result.final_risk_per_trade <= Decimal("0.05")

    @pytest.mark.asyncio
    async def test_risk_debate_metrics_recording(
        self,
        risk_debate_team,
        sample_risk_context,
        sample_market_context,
        mock_metrics,
    ):
        """Test risk debate records metrics correctly."""
        mock_conservative = ConservativeRiskAnalysis(
            recommended_position_size=Decimal("1.0"),
            max_risk_per_trade=Decimal("0.015"),
            stop_loss_distance=Decimal("0.0035"),
            confidence=Decimal("0.75"),
            risk_factors=[],
            protective_measures=[],
            reasoning="OK.",
        )

        mock_aggressive = AggressiveRiskAnalysis(
            recommended_position_size=Decimal("2.5"),
            max_risk_per_trade=Decimal("0.035"),
            stop_loss_distance=Decimal("0.0045"),
            confidence=Decimal("0.70"),
            opportunity_factors=[],
            calculated_risks=[],
            reasoning="OK.",
        )

        with patch.object(
            risk_debate_team.conservative_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_conservative,
        ), patch.object(
            risk_debate_team.aggressive_agent,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_aggressive,
        ):
            await risk_debate_team.conduct_debate(
                sample_risk_context, sample_market_context, "bullish", Decimal("0.75")
            )

        # Verify metrics recorded
        assert mock_metrics.record_conservative_analysis.call_count >= 1
        assert mock_metrics.record_aggressive_analysis.call_count >= 1
        assert mock_metrics.record_risk_debate_outcome.call_count == 1
        assert mock_metrics.record_risk_debate_duration.call_count == 1
