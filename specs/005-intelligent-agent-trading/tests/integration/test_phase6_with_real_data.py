"""
Integration test for Phase 6 using REAL historical data from database.

This test:
1. Fetches real historical CrudeOIL data from PostgreSQL
2. Runs REAL LLM calls (no mocks) through full Phase 6 pipeline
3. Tests: Risk Debate → Fund Manager Approval
4. Validates decision quality and safety gates

NO MOCKS - REAL DATA - REAL LLMs
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.approval.fund_manager_agent import FundManagerAgent
from src.agents.schemas.approval import PortfolioLimits, ApprovalDecision


# Database connection from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/risetrader"
)


@pytest.fixture(scope="module")
def db_session():
    """Create database session for fetching real data."""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def recent_market_data(db_session):
    """Fetch recent CrudeOIL market data (last 100 candles)."""
    query = text("""
        SELECT time, symbol, open, high, low, last, volume, change_percent
        FROM market_data
        WHERE symbol = 'CrudeOIL'
          AND timeframe = 'H1'
          AND time >= NOW() - INTERVAL '7 days'
        ORDER BY time DESC
        LIMIT 100
    """)

    result = db_session.execute(query)
    rows = result.fetchall()

    # Convert to dict
    data = []
    for row in rows:
        data.append({
            "time": row[0],
            "symbol": row[1],
            "open": float(row[2]),
            "high": float(row[3]),
            "low": float(row[4]),
            "close": float(row[5]),
            "volume": int(row[6]),
            "change_percent": float(row[7])
        })

    return data


@pytest.fixture
def risky_config():
    """Risky debator config - REAL LLM."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def neutral_config():
    """Neutral debator config - REAL LLM."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def safe_config():
    """Safe debator config - REAL LLM."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def fund_manager_config():
    """Fund manager config - REAL LLM."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.APPROVAL,
        llm_tier=LLMTier.DEEP_THINK,
        llm_model="deepseek-reasoner:14b",
        temperature=0.2,
        max_tokens=3000
    )


@pytest.fixture
def portfolio_limits():
    """Standard portfolio limits."""
    return PortfolioLimits(
        max_account_risk_percent=5.0,
        max_portfolio_risk_percent=15.0,
        max_correlated_positions=3,
        event_risk_veto_hours=24,
        min_trade_quality_score=0.4
    )


class TestPhase6WithRealData:
    """Test Phase 6 pipeline with real historical data and real LLM calls."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_moderate_position_size_with_real_data(
        self,
        recent_market_data,
        risky_config,
        neutral_config,
        safe_config,
        fund_manager_config,
        portfolio_limits
    ):
        """
        Test moderate position sizing with real CrudeOIL data.

        Scenario: 2.0% risk, moderate conviction (0.70)
        Expected: Should pass risk debate and get approved or modified slightly
        """
        # Skip if no data
        if not recent_market_data or len(recent_market_data) < 10:
            pytest.skip("Insufficient market data in database")

        # Calculate recent price statistics from real data
        latest = recent_market_data[0]
        prices = [candle["close"] for candle in recent_market_data[:20]]
        current_price = latest["close"]
        recent_high = max(prices)
        recent_low = min(prices)

        # Create trade intent based on real data
        trade_intent = {
            "direction": "LONG",
            "conviction": 0.70,
            "rationale": (
                f"CrudeOIL at ${current_price:.2f}. "
                f"Recent range: ${recent_low:.2f} - ${recent_high:.2f}. "
                f"Moderate conviction based on price action and volume."
            ),
            "key_factors": [
                f"Current price: ${current_price:.2f}",
                f"20-candle high: ${recent_high:.2f}",
                "Volume analysis shows moderate strength"
            ],
            "risk_assessment": "Moderate risk with defined stop loss"
        }

        # Position sizing: 2.0% risk
        stop_loss_price = current_price * 0.98  # 2% stop
        position_size_decision = {
            "position_size_lots": 1.5,
            "risk_percentage": 2.0,
            "kelly_fraction": 0.25,
            "win_rate": 0.55,
            "avg_win_loss_ratio": 2.5,
            "confidence": 0.75
        }

        stop_loss_decision = {
            "stop_loss_price": stop_loss_price,
            "distance_pips": int((current_price - stop_loss_price) * 100),
            "confidence": 0.80
        }

        # Portfolio state: healthy, room for risk
        portfolio_state = {
            "total_risk_percentage": 3.0,
            "open_positions_count": 1,
            "recent_pnl": 2500.0,
            "available_capacity_pct": 80.0
        }

        print(f"\n{'='*80}")
        print(f"REAL DATA TEST: CrudeOIL @ ${current_price:.2f}")
        print(f"Range (20 candles): ${recent_low:.2f} - ${recent_high:.2f}")
        print(f"Position: 1.5 lots, 2.0% risk, Stop: ${stop_loss_price:.2f}")
        print(f"{'='*80}\n")

        # Create agents (REAL LLMs, no mocks!)
        risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        # Step 1: Run Risk Tolerance Debate (REAL LLM CALLS)
        print("Step 1: Running Risk Tolerance Debate (3 LLM calls)...")
        risk_debate_outcome = await risk_debate_team.run_debate(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="CrudeOIL"
        )

        print(f"\nRisk Debate Results:")
        print(f"  Risky adjustment:   {risk_debate_outcome.risky_perspective.recommended_size_adjustment:.2f}x")
        print(f"  Neutral adjustment: {risk_debate_outcome.neutral_perspective.recommended_size_adjustment:.2f}x")
        print(f"  Safe adjustment:    {risk_debate_outcome.safe_perspective.recommended_size_adjustment:.2f}x")
        print(f"  Consensus:          {risk_debate_outcome.consensus_adjustment:.2f}x")
        print(f"  Consensus reached:  {risk_debate_outcome.consensus_reached}")
        print(f"  Final size:         {risk_debate_outcome.final_position_size:.2f} lots")
        print(f"  Final risk:         {risk_debate_outcome.final_risk_percentage:.2f}%")

        # Step 2: Run Fund Manager Approval (REAL LLM CALL)
        print(f"\nStep 2: Running Fund Manager Approval (1 LLM call)...")
        fund_manager_approval = await fund_manager.run(
            trade_intent=trade_intent,
            risk_debate_outcome=risk_debate_outcome.model_dump(),
            portfolio_state=portfolio_state,
            upcoming_events=[],
            symbol="CrudeOIL"
        )

        print(f"\nFund Manager Decision:")
        print(f"  Decision:           {fund_manager_approval.decision.value}")
        print(f"  Approved size:      {fund_manager_approval.approved_position_size or 'N/A'}")
        print(f"  Approved risk:      {fund_manager_approval.approved_risk_percentage or 'N/A'}%")
        print(f"  Hard limits passed: {fund_manager_approval.hard_limits_passed}")
        print(f"  Trade quality:      {fund_manager_approval.trade_quality_score:.2f}")
        print(f"  Confidence:         {fund_manager_approval.confidence:.2f}")
        print(f"  Portfolio risk:     {fund_manager_approval.portfolio_risk_after_trade:.2f}%")
        print(f"\n  Rationale: {fund_manager_approval.rationale[:200]}...")

        # Assertions
        assert risk_debate_outcome is not None
        assert risk_debate_outcome.final_position_size > 0
        assert 0.0 <= risk_debate_outcome.final_risk_percentage <= 10.0

        assert fund_manager_approval is not None
        assert fund_manager_approval.decision in [
            ApprovalDecision.APPROVE,
            ApprovalDecision.MODIFY
        ]

        # For moderate setup, should NOT reject
        assert fund_manager_approval.decision != ApprovalDecision.REJECT

        # Hard limits should pass for moderate trade
        assert fund_manager_approval.hard_limits_passed is True

        # Portfolio risk should be reasonable
        assert fund_manager_approval.portfolio_risk_after_trade < 15.0

        print(f"\n{'='*80}")
        print(f"✓ SUCCESS: Phase 6 pipeline completed with real data")
        print(f"{'='*80}\n")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_aggressive_position_should_get_modified(
        self,
        recent_market_data,
        risky_config,
        neutral_config,
        safe_config,
        fund_manager_config,
        portfolio_limits
    ):
        """
        Test aggressive position sizing with real data.

        Scenario: 4.5% risk (near limit), aggressive Kelly
        Expected: Risk debate should reduce, Fund Manager should MODIFY or REJECT
        """
        if not recent_market_data or len(recent_market_data) < 10:
            pytest.skip("Insufficient market data in database")

        latest = recent_market_data[0]
        current_price = latest["close"]

        # Aggressive setup
        trade_intent = {
            "direction": "LONG",
            "conviction": 0.65,  # Not super high
            "rationale": f"Speculative long at ${current_price:.2f}",
            "key_factors": ["Hopeful breakout"],
            "risk_assessment": "High risk, aggressive sizing"
        }

        # AGGRESSIVE sizing: 4.5% risk, 0.50 Kelly (too much)
        stop_loss_price = current_price * 0.955  # 4.5% stop
        position_size_decision = {
            "position_size_lots": 3.0,  # Large
            "risk_percentage": 4.5,  # Near max
            "kelly_fraction": 0.50,  # Aggressive
            "win_rate": 0.60,
            "avg_win_loss_ratio": 2.0,
            "confidence": 0.60
        }

        stop_loss_decision = {
            "stop_loss_price": stop_loss_price,
            "distance_pips": int((current_price - stop_loss_price) * 100),
            "confidence": 0.70
        }

        portfolio_state = {
            "total_risk_percentage": 6.0,  # Already elevated
            "open_positions_count": 2,
            "recent_pnl": 1000.0,
            "available_capacity_pct": 60.0
        }

        print(f"\n{'='*80}")
        print(f"AGGRESSIVE TEST: CrudeOIL @ ${current_price:.2f}")
        print(f"Position: 3.0 lots, 4.5% risk (AGGRESSIVE)")
        print(f"Portfolio already at 6% risk")
        print(f"{'='*80}\n")

        risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        # Run Risk Debate
        print("Running Risk Debate on aggressive trade...")
        risk_debate_outcome = await risk_debate_team.run_debate(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="CrudeOIL"
        )

        print(f"\nRisk Debate Results:")
        print(f"  Consensus adjustment: {risk_debate_outcome.consensus_adjustment:.2f}x")
        print(f"  Final size:           {risk_debate_outcome.final_position_size:.2f} lots")
        print(f"  Final risk:           {risk_debate_outcome.final_risk_percentage:.2f}%")
        print(f"  Warnings:             {', '.join(risk_debate_outcome.key_warnings) if risk_debate_outcome.key_warnings else 'None'}")

        # Run Fund Manager
        print(f"\nRunning Fund Manager approval...")
        fund_manager_approval = await fund_manager.run(
            trade_intent=trade_intent,
            risk_debate_outcome=risk_debate_outcome.model_dump(),
            portfolio_state=portfolio_state,
            upcoming_events=[],
            symbol="CrudeOIL"
        )

        print(f"\nFund Manager Decision:")
        print(f"  Decision:             {fund_manager_approval.decision.value}")
        print(f"  Hard limits passed:   {fund_manager_approval.hard_limits_passed}")
        print(f"  Modifications:        {len(fund_manager_approval.modifications)}")
        print(f"  Final approved size:  {fund_manager_approval.approved_position_size or 'REJECTED'}")
        print(f"  Portfolio risk after: {fund_manager_approval.portfolio_risk_after_trade:.2f}%")

        # Assertions
        # Risk debate should reduce (consensus < 1.0 or divergent)
        assert (
            risk_debate_outcome.consensus_adjustment < 1.0 or
            not risk_debate_outcome.consensus_reached
        ), "Risk debate should reduce aggressive sizing or show divergence"

        # Fund Manager should either MODIFY or REJECT (not APPROVE as-is)
        assert fund_manager_approval.decision in [
            ApprovalDecision.MODIFY,
            ApprovalDecision.REJECT
        ], "Aggressive trade should be modified or rejected"

        # If modified, size should be reduced
        if fund_manager_approval.decision == ApprovalDecision.MODIFY:
            assert fund_manager_approval.approved_position_size < position_size_decision["position_size_lots"]
            assert fund_manager_approval.approved_risk_percentage < position_size_decision["risk_percentage"]

        print(f"\n{'='*80}")
        print(f"✓ SUCCESS: Aggressive trade correctly handled")
        print(f"{'='*80}\n")


class TestPhase6DataQuality:
    """Test data quality and database fixtures."""

    def test_database_has_sufficient_data(self, db_session):
        """Verify database has enough data for testing."""
        query = text("""
            SELECT COUNT(*) as count, symbol
            FROM market_data
            WHERE timeframe = 'H1'
            GROUP BY symbol
        """)

        result = db_session.execute(query)
        rows = result.fetchall()

        print(f"\nAvailable data:")
        for row in rows:
            print(f"  {row[1]}: {row[0]:,} records")

        assert len(rows) > 0, "No market data found in database"

        # Should have CrudeOIL
        symbols = [row[1] for row in rows]
        assert "CrudeOIL" in symbols, "CrudeOIL data not found"

        # Should have enough records for testing
        crude_count = [row[0] for row in rows if row[1] == "CrudeOIL"][0]
        assert crude_count > 1000, f"Insufficient CrudeOIL data (need >1000, have {crude_count})"

    def test_recent_data_available(self, recent_market_data):
        """Verify recent data is available for testing."""
        assert len(recent_market_data) > 0, "No recent market data available"
        assert len(recent_market_data) >= 10, "Need at least 10 recent candles"

        latest = recent_market_data[0]
        print(f"\nLatest candle:")
        print(f"  Time:   {latest['time']}")
        print(f"  Symbol: {latest['symbol']}")
        print(f"  Close:  ${latest['close']:.2f}")
        print(f"  Volume: {latest['volume']:,}")

        assert latest["symbol"] == "CrudeOIL"
        assert latest["close"] > 0
        assert latest["volume"] >= 0
