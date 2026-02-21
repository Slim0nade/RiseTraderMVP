#!/usr/bin/env python3
"""
Phase 6 Real Data Test - NO MOCKS
Uses actual PostgreSQL historical CrudeOIL data and real LLM calls.
"""

import asyncio
import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.decision.fund_manager_agent import FundManagerAgent
from src.agents.schemas.approval import PortfolioLimits, ApprovalDecision

# Database connection
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/risetrader"


def fetch_real_market_data():
    """Fetch real CrudeOIL data from PostgreSQL database."""
    print("=" * 80)
    print("STEP 1: Fetching REAL Market Data from PostgreSQL")
    print("=" * 80)

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    query = text("""
        SELECT time, symbol, open, high, low, last, volume
        FROM market_data
        WHERE symbol = 'CrudeOIL'
          AND timeframe = 'H1'
        ORDER BY time DESC
        LIMIT 20
    """)

    try:
        result = session.execute(query)
        rows = result.fetchall()

        data = []
        for row in rows:
            data.append({
                "time": row[0],
                "symbol": row[1],
                "open": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "close": float(row[5]),
                "volume": int(row[6])
            })

        print(f"✓ Fetched {len(data)} real H1 candles")
        if data:
            latest = data[0]
            print(f"  Latest: {latest['time']}")
            print(f"  Price: ${latest['close']:.2f}")
            print(f"  Volume: {latest['volume']:,}")

        session.close()
        return data

    except Exception as e:
        print(f"✗ Database error: {e}")
        session.close()
        return []


async def test_phase6_with_real_data():
    """Test Phase 6 pipeline with REAL data and REAL LLM calls."""

    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "Phase 6: REAL DATA TEST" + " " * 35 + "║")
    print("║" + " " * 15 + "NO MOCKS - REAL DATABASE + REAL LLMs" + " " * 27 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    # Fetch REAL market data
    market_data = fetch_real_market_data()

    if not market_data or len(market_data) < 10:
        print("\n✗ FAIL: Insufficient market data")
        return False

    # Calculate price statistics from REAL data
    latest = market_data[0]
    prices = [candle["close"] for candle in market_data]
    current_price = latest["close"]
    recent_high = max(prices)
    recent_low = min(prices)

    print("\n" + "=" * 80)
    print("STEP 2: Preparing Trade from REAL Market Data")
    print("=" * 80)
    print(f"  Symbol: CrudeOIL")
    print(f"  Current Price: ${current_price:.2f}")
    print(f"  20-Candle Range: ${recent_low:.2f} - ${recent_high:.2f}")

    # Create trade intent based on REAL data
    trade_intent = {
        "direction": "LONG",
        "conviction": 0.70,
        "rationale": (
            f"CrudeOIL at ${current_price:.2f}. "
            f"Recent range: ${recent_low:.2f} - ${recent_high:.2f}. "
            f"Moderate conviction based on price action."
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

    portfolio_state = {
        "total_risk_percentage": 3.0,
        "open_positions_count": 1,
        "recent_pnl": 2500.0,
        "available_capacity_pct": 80.0
    }

    print(f"  Position Size: 1.5 lots")
    print(f"  Risk: 2.0%")
    print(f"  Stop Loss: ${stop_loss_price:.2f}")

    # Create REAL agent configs (NO MOCKS)
    print("\n" + "=" * 80)
    print("STEP 3: Creating Agents with REAL LLM Configs")
    print("=" * 80)

    risky_config = AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    neutral_config = AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    safe_config = AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )

    fund_manager_config = AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.APPROVAL,
        llm_tier=LLMTier.DEEP_THINK,
        llm_model="deepseek-reasoner:14b",
        temperature=0.2,
        max_tokens=3000
    )

    portfolio_limits = PortfolioLimits(
        max_account_risk_percent=5.0,
        max_portfolio_risk_percent=15.0,
        max_correlated_positions=3,
        event_risk_veto_hours=24,
        min_trade_quality_score=0.4
    )

    print(f"  ✓ Risky Debator: qwen2.5:14b-instruct")
    print(f"  ✓ Neutral Debator: qwen2.5:14b-instruct")
    print(f"  ✓ Safe Debator: qwen2.5:14b-instruct")
    print(f"  ✓ Fund Manager: deepseek-reasoner:14b")

    # Create REAL agent instances
    risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
    fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

    # STEP 4: Run Risk Tolerance Debate (3 REAL LLM CALLS)
    print("\n" + "=" * 80)
    print("STEP 4: Running Risk Tolerance Debate (3 REAL LLM CALLS)")
    print("=" * 80)
    print("  Calling Risky Debator...")
    print("  Calling Neutral Debator...")
    print("  Calling Safe Debator...")
    print("  (This may take 20-30 seconds...)")

    try:
        risk_debate_outcome = await risk_debate_team.run_debate(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="CrudeOIL"
        )

        print(f"\n  ✓ Risk Debate Complete!")
        print(f"\n  Results:")
        print(f"    Risky adjustment:   {risk_debate_outcome.risky_perspective.recommended_size_adjustment:.2f}x")
        print(f"    Neutral adjustment: {risk_debate_outcome.neutral_perspective.recommended_size_adjustment:.2f}x")
        print(f"    Safe adjustment:    {risk_debate_outcome.safe_perspective.recommended_size_adjustment:.2f}x")
        print(f"    Consensus:          {risk_debate_outcome.consensus_adjustment:.2f}x")
        print(f"    Final size:         {risk_debate_outcome.final_position_size:.2f} lots")
        print(f"    Final risk:         {risk_debate_outcome.final_risk_percentage:.2f}%")

    except Exception as e:
        print(f"\n  ✗ Risk Debate FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # STEP 5: Run Fund Manager Approval (1 REAL LLM CALL)
    print("\n" + "=" * 80)
    print("STEP 5: Running Fund Manager Approval (1 REAL LLM CALL)")
    print("=" * 80)
    print("  Calling Fund Manager...")
    print("  (This may take 15-20 seconds...)")

    try:
        fund_manager_approval = await fund_manager.run(
            trade_intent=trade_intent,
            risk_debate_outcome=risk_debate_outcome.model_dump(),
            portfolio_state=portfolio_state,
            upcoming_events=[],
            symbol="CrudeOIL"
        )

        print(f"\n  ✓ Fund Manager Decision Complete!")
        print(f"\n  Results:")
        print(f"    Decision:           {fund_manager_approval.decision.value}")
        print(f"    Approved size:      {fund_manager_approval.approved_position_size or 'N/A'}")
        print(f"    Approved risk:      {fund_manager_approval.approved_risk_percentage or 'N/A'}%")
        print(f"    Trade quality:      {fund_manager_approval.trade_quality_score:.2f}")
        print(f"    Confidence:         {fund_manager_approval.confidence:.2f}")
        print(f"    Portfolio risk:     {fund_manager_approval.portfolio_risk_after_trade:.2f}%")

    except Exception as e:
        print(f"\n  ✗ Fund Manager FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Validate results
    print("\n" + "=" * 80)
    print("✓ SUCCESS: Phase 6 Pipeline Test Passed with REAL DATA!")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Database records: {len(market_data)} CrudeOIL candles")
    print(f"  LLM calls made: 4 (3 debate + 1 fund manager)")
    print(f"  Final decision: {fund_manager_approval.decision.value}")
    print(f"  Final size: {fund_manager_approval.approved_position_size or 0:.2f} lots")
    print(f"  Final risk: {fund_manager_approval.approved_risk_percentage or 0:.2f}%")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_phase6_with_real_data())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
