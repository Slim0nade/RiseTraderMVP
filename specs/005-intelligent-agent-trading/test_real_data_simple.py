#!/usr/bin/env python3
"""
Quick Phase 6 test with REAL data - uses specs/005-intelligent-agent-trading/src path.
"""

import asyncio
import sys
import os

# Add spec source to path
SPEC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SPEC_DIR, 'src'))
sys.path.insert(0, SPEC_DIR)

print(f"SPEC_DIR: {SPEC_DIR}")
print(f"Python path: {sys.path[:3]}")

# Now import from spec src
from agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from agents.teams.risk_debate_team import RiskDebateTeam
from agents.approval.fund_manager_agent import FundManagerAgent
from agents.schemas.approval import PortfolioLimits, ApprovalDecision

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime


DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/risetrader"


def fetch_data():
    """Fetch CrudeOIL data."""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    query = text("""
        SELECT time, symbol, open, high, low, last, volume
        FROM market_data
        WHERE symbol = 'CrudeOIL' AND timeframe = 'H1'
        ORDER BY time DESC
        LIMIT 20
    """)

    result = session.execute(query)
    rows = result.fetchall()
    session.close()

    data = []
    for row in rows:
        data.append({
            "time": row[0],
            "close": float(row[5]),
            "volume": int(row[6])
        })

    return data


async def test_phase6():
    """Test Phase 6 with real data."""

    print("\n" + "="*80)
    print("Phase 6: REAL DATA TEST")
    print("="*80 + "\n")

    # Fetch data
    data = fetch_data()
    if not data:
        print("✗ No data")
        return False

    print(f"✓ Fetched {len(data)} candles")
    current_price = data[0]["close"]
    print(f"  Latest price: ${current_price:.2f}\n")

    # Create configs
    risky_cfg = AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3
    )

    # Create team
    risk_team = RiskDebateTeam(risky_cfg, risky_cfg, risky_cfg)

    # Simple trade
    trade = {
        "direction": "LONG",
        "conviction": 0.70,
        "rationale": f"CrudeOIL at ${current_price:.2f}",
        "key_factors": ["Price action"],
        "risk_assessment": "Moderate"
    }

    sizing = {
        "position_size_lots": 1.5,
        "risk_percentage": 2.0,
        "kelly_fraction": 0.25,
        "win_rate": 0.55,
        "avg_win_loss_ratio": 2.5,
        "confidence": 0.75
    }

    stop = {
        "stop_loss_price": current_price * 0.98,
        "distance_pips": 50,
        "confidence": 0.80
    }

    print("Running Risk Debate (3 LLM calls)...")
    outcome = await risk_team.run_debate(
        trade_intent=trade,
        position_size_decision=sizing,
        stop_loss_decision=stop,
        account_balance=100000.0,
        symbol="CrudeOIL"
    )

    print(f"\n✓ Risk Debate Complete!")
    print(f"  Consensus: {outcome.consensus_adjustment:.2f}x")
    print(f"  Final size: {outcome.final_position_size:.2f} lots")
    print(f"  Final risk: {outcome.final_risk_percentage:.2f}%\n")

    print("="*80)
    print("✓ SUCCESS - Phase 6 Test Passed!")
    print("="*80)

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_phase6())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
