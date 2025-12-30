"""
Unit tests for the Fund Manager Agent (Phase 6 final approval).

Tests cover:
- Final decision making logic
- Safety gate validation
- Approval/rejection scenarios
- Error handling
- Metrics collection
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from decimal import Decimal

from src.agents.decision.fund_manager_agent import FundManagerAgent
from src.agents.schemas.phase6_schemas import (
    FundManagerDecision,
    DebateAnalysis,
    RiskDebateAnalysis,
    MarketContext,
    RiskContext,
)
from src.agents.utils.phase6_metrics import Phase6Metrics


@pytest.fixture
def mock_metrics():
    """Mock Phase6Metrics instance."""
    metrics = Mock(spec=Phase6Metrics)
    metrics.record_fund_manager_decision = Mock()
    metrics.record_safety_gate_rejection = Mock()
    metrics.record_fund_manager_duration = Mock()
    return metrics


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
def sample_risk_context():
    """Sample risk context."""
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
def strong_bullish_debate():
    """Strong bullish debate result."""
    return DebateAnalysis(
        final_decision="bullish",
        confidence=Decimal("0.85"),
        bull_score=Decimal("0.80"),
        bear_score=Decimal("0.30"),
        consensus_strength=Decimal("0.75"),
        key_arguments=[
            "Strong uptrend confirmed",
            "Breakout above resistance",
            "High volume support",
        ],
        risks_identified=["Minor overbought"],
        rounds_conducted=2,
    )


@pytest.fixture
def balanced_risk_debate():
    """Balanced risk debate result."""
    return RiskDebateAnalysis(
        final_position_size=Decimal("2.0"),
        final_risk_per_trade=Decimal("0.025"),
        final_stop_loss=Decimal("0.0040"),
        conservative_weight=Decimal("0.50"),
        aggressive_weight=Decimal("0.50"),
        consensus_reached=True,
        key_risk_factors=["Moderate volatility"],
        protective_measures=["Standard stop loss"],
        rounds_conducted=1,
    )


@pytest.fixture
def fund_manager_agent(mock_metrics):
    """FundManagerAgent instance."""
    config = {
        "model": "gpt-4",
        "temperature": 0.1,
        "safety_gates": {
            "max_position_size_pct": 5.0,
            "max_risk_per_trade_pct": 5.0,
            "min_confidence": 0.6,
            "max_drawdown_pct": 20.0,
            "min_margin_available_pct": 30.0,
        },
    }
    return FundManagerAgent(config=config, metrics=mock_metrics)


class TestFundManagerAgent:
    """Tests for FundManagerAgent."""

    @pytest.mark.asyncio
    async def test_fund_manager_initialization(self, fund_manager_agent):
        """Test fund manager initializes correctly."""
        assert fund_manager_agent.config["model"] == "gpt-4"
        assert fund_manager_agent.config["temperature"] == 0.1
        assert "safety_gates" in fund_manager_agent.config

    @pytest.mark.asyncio
    async def test_approve_strong_bullish_trade(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test fund manager approves strong bullish trade."""
        mock_decision = FundManagerDecision(
            approved=True,
            confidence=Decimal("0.90"),
            final_position_size=Decimal("2.0"),
            final_risk_per_trade=Decimal("0.025"),
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0910"),
            take_profit=Decimal("1.1100"),
            rationale="Strong bullish consensus with acceptable risk.",
            safety_checks_passed=True,
            concerns=[],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        assert result.approved is True
        assert result.confidence >= Decimal("0.8")
        assert result.safety_checks_passed is True
        assert len(result.concerns) == 0
        mock_metrics.record_fund_manager_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_low_confidence_trade(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test fund manager rejects low confidence trade."""
        # Low confidence debate
        weak_debate = DebateAnalysis(
            final_decision="neutral",
            confidence=Decimal("0.40"),
            bull_score=Decimal("0.45"),
            bear_score=Decimal("0.48"),
            consensus_strength=Decimal("0.35"),
            key_arguments=["Weak signals"],
            risks_identified=["High uncertainty"],
            rounds_conducted=3,
        )

        mock_decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.35"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Insufficient confidence in trading signal.",
            safety_checks_passed=False,
            concerns=["Low confidence", "No clear direction"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                weak_debate,
                balanced_risk_debate,
            )

        assert result.approved is False
        assert result.confidence < Decimal("0.6")
        assert len(result.concerns) >= 1
        mock_metrics.record_safety_gate_rejection.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_gate_max_position_size(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        mock_metrics,
    ):
        """Test safety gate rejects oversized position."""
        # Oversized risk debate
        oversized_debate = RiskDebateAnalysis(
            final_position_size=Decimal("10.0"),  # 10% - too large!
            final_risk_per_trade=Decimal("0.08"),
            final_stop_loss=Decimal("0.0080"),
            conservative_weight=Decimal("0.30"),
            aggressive_weight=Decimal("0.70"),
            consensus_reached=True,
            key_risk_factors=[],
            protective_measures=[],
            rounds_conducted=1,
        )

        mock_decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.50"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Position size exceeds safety limits.",
            safety_checks_passed=False,
            concerns=["Position size too large (10.0% > 5.0%)"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                oversized_debate,
            )

        assert result.approved is False
        assert "Position size" in result.concerns[0] or "too large" in result.concerns[0]
        mock_metrics.record_safety_gate_rejection.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_gate_max_drawdown(
        self,
        fund_manager_agent,
        sample_market_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test safety gate rejects when max drawdown exceeded."""
        # High drawdown context
        high_drawdown_context = RiskContext(
            account_balance=Decimal("100000.00"),
            equity=Decimal("80000.00"),  # 20% drawdown
            margin_used=Decimal("5000.00"),
            margin_available=Decimal("75000.00"),
            open_positions_count=2,
            total_exposure=Decimal("15000.00"),
            max_drawdown=Decimal("0.25"),  # 25% drawdown!
            daily_pnl=Decimal("-5000.00"),
            win_rate=Decimal("0.45"),
            sharpe_ratio=Decimal("0.5"),
            current_var=Decimal("5000.00"),
            portfolio_beta=Decimal("1.2"),
        )

        mock_decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.30"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Maximum drawdown exceeded - trading suspended.",
            safety_checks_passed=False,
            concerns=["Drawdown 25.0% exceeds limit 20.0%"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                high_drawdown_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        assert result.approved is False
        assert "drawdown" in result.concerns[0].lower() or "Drawdown" in result.concerns[0]
        mock_metrics.record_safety_gate_rejection.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_gate_low_margin(
        self,
        fund_manager_agent,
        sample_market_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test safety gate rejects when margin too low."""
        # Low margin context
        low_margin_context = RiskContext(
            account_balance=Decimal("100000.00"),
            equity=Decimal("102000.00"),
            margin_used=Decimal("80000.00"),  # High usage
            margin_available=Decimal("22000.00"),  # Only 22% available
            open_positions_count=10,
            total_exposure=Decimal("80000.00"),
            max_drawdown=Decimal("0.05"),
            daily_pnl=Decimal("1000.00"),
            win_rate=Decimal("0.60"),
            sharpe_ratio=Decimal("1.5"),
            current_var=Decimal("3000.00"),
            portfolio_beta=Decimal("1.0"),
        )

        mock_decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.40"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Insufficient margin available for new position.",
            safety_checks_passed=False,
            concerns=["Margin available 21.6% below minimum 30.0%"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                low_margin_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        assert result.approved is False
        assert "margin" in result.concerns[0].lower() or "Margin" in result.concerns[0]
        mock_metrics.record_safety_gate_rejection.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_with_minor_concerns(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test fund manager can approve with minor concerns noted."""
        mock_decision = FundManagerDecision(
            approved=True,
            confidence=Decimal("0.75"),
            final_position_size=Decimal("1.5"),
            final_risk_per_trade=Decimal("0.02"),
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0920"),
            take_profit=Decimal("1.1100"),
            rationale="Approved with monitoring for volatility.",
            safety_checks_passed=True,
            concerns=["Slightly elevated volatility - monitor closely"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        assert result.approved is True
        assert result.safety_checks_passed is True
        assert len(result.concerns) >= 1  # Has concerns but still approved
        mock_metrics.record_fund_manager_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_reduce_position_size_for_safety(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test fund manager reduces position size for safety."""
        # Mock decision with reduced size
        mock_decision = FundManagerDecision(
            approved=True,
            confidence=Decimal("0.70"),
            final_position_size=Decimal("1.0"),  # Reduced from debate's 2.0
            final_risk_per_trade=Decimal("0.015"),  # Reduced from 0.025
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0920"),
            take_profit=Decimal("1.1100"),
            rationale="Position size reduced for additional safety margin.",
            safety_checks_passed=True,
            concerns=["Position size reduced from 2.0% to 1.0% as precaution"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            result = await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        assert result.approved is True
        assert result.final_position_size < balanced_risk_debate.final_position_size
        assert result.final_risk_per_trade < balanced_risk_debate.final_risk_per_trade
        mock_metrics.record_fund_manager_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_llm_failure(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
    ):
        """Test fund manager handles LLM failures gracefully."""
        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API error"),
        ):
            with pytest.raises(Exception, match="LLM API error"):
                await fund_manager_agent.make_final_decision(
                    sample_market_context,
                    sample_risk_context,
                    strong_bullish_debate,
                    balanced_risk_debate,
                )

    @pytest.mark.asyncio
    async def test_metrics_recording_on_approval(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test metrics recorded correctly on approval."""
        mock_decision = FundManagerDecision(
            approved=True,
            confidence=Decimal("0.85"),
            final_position_size=Decimal("2.0"),
            final_risk_per_trade=Decimal("0.025"),
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0920"),
            take_profit=Decimal("1.1100"),
            rationale="Approved.",
            safety_checks_passed=True,
            concerns=[],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        mock_metrics.record_fund_manager_decision.assert_called_once_with(
            decision="approved", confidence=mock_decision.confidence
        )
        mock_metrics.record_fund_manager_duration.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_recording_on_rejection(
        self,
        fund_manager_agent,
        sample_market_context,
        sample_risk_context,
        strong_bullish_debate,
        balanced_risk_debate,
        mock_metrics,
    ):
        """Test metrics recorded correctly on rejection."""
        mock_decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.30"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Rejected.",
            safety_checks_passed=False,
            concerns=["Test concern"],
        )

        with patch.object(
            fund_manager_agent,
            "_call_llm",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ):
            await fund_manager_agent.make_final_decision(
                sample_market_context,
                sample_risk_context,
                strong_bullish_debate,
                balanced_risk_debate,
            )

        mock_metrics.record_safety_gate_rejection.assert_called_once_with(
            reason="Test concern"
        )
        mock_metrics.record_fund_manager_duration.assert_called_once()


class TestFundManagerDecision:
    """Tests for FundManagerDecision schema."""

    def test_fund_manager_decision_creation(self):
        """Test FundManagerDecision can be created with valid data."""
        decision = FundManagerDecision(
            approved=True,
            confidence=Decimal("0.85"),
            final_position_size=Decimal("2.0"),
            final_risk_per_trade=Decimal("0.025"),
            target_price=Decimal("1.1050"),
            stop_loss=Decimal("1.0920"),
            take_profit=Decimal("1.1100"),
            rationale="Strong bullish setup with acceptable risk.",
            safety_checks_passed=True,
            concerns=[],
        )

        assert decision.approved is True
        assert decision.confidence == Decimal("0.85")
        assert decision.safety_checks_passed is True

    def test_fund_manager_decision_rejection(self):
        """Test FundManagerDecision for rejection."""
        decision = FundManagerDecision(
            approved=False,
            confidence=Decimal("0.40"),
            final_position_size=Decimal("0.0"),
            final_risk_per_trade=Decimal("0.0"),
            target_price=None,
            stop_loss=None,
            take_profit=None,
            rationale="Insufficient confidence.",
            safety_checks_passed=False,
            concerns=["Low confidence", "High risk"],
        )

        assert decision.approved is False
        assert decision.final_position_size == Decimal("0.0")
        assert len(decision.concerns) == 2
