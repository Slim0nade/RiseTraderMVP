#!/usr/bin/env python3
"""
SIMPLIFIED Phase 6 Real Data Test - NO COMPLEX IMPORTS
Directly tests Risk Debate Team and Fund Manager with REAL PostgreSQL data.
"""

import asyncio
import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Simple approach: Add src to path, then import what we need individually
sys.path.insert(0, '/app')

# Import ONLY what Phase 6 needs - avoid complex team imports
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier

# Import Phase 6 agents directly using full module paths
from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.approval.fund_manager_agent import FundManagerAgent
from src.agents.schemas.approval import PortfolioLimits, ApprovalDecision

# Database connection
DATABASE_URL = "postgresql://postgres:postgres@postgres:5432/risetrader"


def fetch_real_market_data():
    """Fetch real CrudeOIL data from PostgreSQL."""
    print("=" * 80)
    print("FETCHING REAL MARKET DATA FROM POSTGRESQL")
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

    print(f"✓ Fetched {len(data)} real H1 candles from database")
    if data:
        latest = data[0]
        print(f"  Latest: {latest['time']}")
        print(f"  Price: ${latest['close']:.2f}")
        print(f"  Volume: {latest['volume']:,}")

    session.close()
    return data


async def test_phase6():
    """Test Phase 6 with REAL data and REAL LLM calls."""

    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "Phase 6: REAL DATA TEST (SIMPLIFIED)" + " " * 25 + "║")
    print("║" + " " * 10 + "NO MOCKS - REAL DATABASE + REAL LLM CALLS" + " " * 27 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    # Fetch REAL market data
    market_data = fetch_real_market_data()

    if not market_data or len(market_data) < 10:
        print("\n✗ FAIL: Insufficient market data")
        return False

    # Use REAL prices from database
    latest = market_data[0]
    prices = [candle["close"] for candle in market_data]
    current_price = latest["close"]
    recent_high = max(prices)
    recent_low = min(prices)

    print("\n" + "=" * 80)
    print("PREPARING TRADE FROM REAL MARKET DATA")
    print("=" * 80)
    print(f"  Symbol: CrudeOIL")
    print(f"  Current Price: ${current_price:.2f}")
    print(f"  20-Candle Range: ${recent_low:.2f} - ${recent_high:.2f}")

    # Create trade inputs based on REAL data
    trade_intent = {
        "direction": "LONG",
        "conviction": 0.70,
        "rationale": f"CrudeOIL at ${current_price:.2f}. Range: ${recent_low:.2f}-${recent_high:.2f}. Moderate conviction.",
        "key_factors": [f"Price: ${current_price:.2f}", f"High: ${recent_high:.2f}", "Moderate volume"],
        "risk_assessment": "Moderate risk"
    }

    stop_loss_price = current_price * 0.98
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

    print(f"  Position: 1.5 lots, 2.0% risk")
    print(f"  Stop Loss: ${stop_loss_price:.2f}")

    # Create REAL agent configs
    print("\n" + "=" * 80)
    print("CREATING AGENTS WITH REAL LLM CONFIGS")
    print("=" * 80)

    risky_config = AgentConfig(
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

    print(f"  ✓ Risk Debators: qwen2.5:14b-instruct")
    print(f"  ✓ Fund Manager: deepseek-reasoner:14b")

    # Create REAL agents
    risk_debate_team = RiskDebateTeam(risky_config, risky_config, risky_config)
    fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

    # Run Risk Debate (3 REAL LLM CALLS)
    print("\n" + "=" * 80)
    print("RUNNING RISK TOLERANCE DEBATE (3 REAL LLM CALLS)")
    print("=" * 80)
    print("  This may take 20-30 seconds...")

    try:
        risk_debate_outcome = await risk_debate_team.run_debate(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="CrudeOIL"
        )

        print(f"\n  ✓ Risk Debate Complete!")
        print(f"    Consensus: {risk_debate_outcome.consensus_adjustment:.2f}x")
        print(f"    Final size: {risk_debate_outcome.final_position_size:.2f} lots")
        print(f"    Final risk: {risk_debate_outcome.final_risk_percentage:.2f}%")

    except Exception as e:
        print(f"\n  ✗ Risk Debate FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Run Fund Manager (1 REAL LLM CALL)
    print("\n" + "=" * 80)
    print("RUNNING FUND MANAGER APPROVAL (1 REAL LLM CALL)")
    print("=" * 80)
    print("  This may take 15-20 seconds...")

    try:
        fund_manager_approval = await fund_manager.run(
            trade_intent=trade_intent,
            risk_debate_outcome=risk_debate_outcome.model_dump(),
            portfolio_state=portfolio_state,
            upcoming_events=[],
            symbol="CrudeOIL"
        )

        print(f"\n  ✓ Fund Manager Decision Complete!")
        print(f"    Decision: {fund_manager_approval.decision.value}")
        print(f"    Approved size: {fund_manager_approval.approved_position_size or 0:.2f} lots")
        print(f"    Approved risk: {fund_manager_approval.approved_risk_percentage or 0:.2f}%")
        print(f"    Trade quality: {fund_manager_approval.trade_quality_score:.2f}")

    except Exception as e:
        print(f"\n  ✗ Fund Manager FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Success!
    print("\n" + "=" * 80)
    print("✓ SUCCESS: Phase 6 Works with REAL DATA!")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Database records: {len(market_data)} CrudeOIL candles")
    print(f"  LLM calls: 4 (3 debate + 1 fund manager)")
    print(f"  Final decision: {fund_manager_approval.decision.value}")
    print(f"  Final size: {fund_manager_approval.approved_position_size or 0:.2f} lots")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_phase6())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
