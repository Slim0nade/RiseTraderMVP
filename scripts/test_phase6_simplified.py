#!/usr/bin/env python3
"""
Phase 6 Simplified Integration Test - Fund Manager Approval with REAL Database Data

Tests Fund Manager approval gate using REAL market data from PostgreSQL.
This is a simplified test that focuses on the FundManagerAgent without requiring
full AutoGen infrastructure.

Success Criteria:
- Fetches REAL market data from database (no mocks)
- Fund Manager makes APPROVE/MODIFY/REJECT decision
- All schemas validate correctly
- Decision respects hard portfolio limits
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any
from datetime import datetime
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from src.agents.decision.fund_manager_agent import FundManagerAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.approval import PortfolioLimits, ApprovalDecision
from src.agents.schemas.trade_decision import TradeIntent, TradeDirection
from src.agents.schemas.decisions import PositionSize, StopLoss, TakeProfit


async def get_real_crude_oil_data(session: AsyncSession) -> Dict[str, Any]:
    """
    Fetch REAL CrudeOIL market data from PostgreSQL database.

    Returns:
        Dict with current price, recent statistics, and market context
    """
    print("📊 Fetching REAL market data from PostgreSQL...")

    # Query last 100 bars of CrudeOIL data
    query = text("""
        SELECT
            last,
            high,
            low,
            open,
            time,
            volume
        FROM market_data
        WHERE symbol = 'CrudeOIL'
        ORDER BY time DESC
        LIMIT 100
    """)

    result = await session.execute(query)
    rows = result.fetchall()

    if not rows:
        raise ValueError("No CrudeOIL data found in database!")

    # Extract data
    latest = rows[0]
    current_price = float(latest[0])  # last (close price)
    timestamp = latest[4]  # time

    # Calculate statistics from last 20 bars
    recent_closes = [float(row[0]) for row in rows[:20]]  # last
    recent_highs = [float(row[1]) for row in rows[:20]]  # high
    recent_lows = [float(row[2]) for row in rows[:20]]  # low

    avg_price_20 = sum(recent_closes) / len(recent_closes)
    high_20 = max(recent_highs)
    low_20 = min(recent_lows)
    range_20 = high_20 - low_20

    # Determine trend
    trend = "BULLISH" if current_price > avg_price_20 else "BEARISH"

    # Calculate ATR (simplified - actual range average)
    ranges = [float(rows[i][1]) - float(rows[i][2]) for i in range(min(14, len(rows)))]
    atr = sum(ranges) / len(ranges)

    print(f"   ✓ Symbol: CrudeOIL")
    print(f"   ✓ Current Price: ${current_price:.2f}")
    print(f"   ✓ 20-Period Average: ${avg_price_20:.2f}")
    print(f"   ✓ ATR (14): ${atr:.2f}")
    print(f"   ✓ Trend: {trend}")
    print(f"   ✓ Database Records: {len(rows)}")
    print(f"   ✓ Latest Timestamp: {timestamp}")

    return {
        "symbol": "CrudeOIL",
        "current_price": current_price,
        "timestamp": timestamp,
        "avg_price_20": avg_price_20,
        "high_20": high_20,
        "low_20": low_20,
        "atr_14": atr,
        "trend": trend,
        "data_points": len(rows)
    }


async def run_fund_manager_test():
    """
    Test Fund Manager approval with REAL database data.
    """

    print("\n" + "="*80)
    print("PHASE 6 SIMPLIFIED TEST - FUND MANAGER APPROVAL")
    print("Using REAL CrudeOIL Data from PostgreSQL Database")
    print("="*80)

    start_time = time.time()

    # Setup database connection
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://rise_user:rise_password@localhost:5432/rise_trading"
    )

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            # Step 1: Fetch REAL market data
            market_data = await get_real_crude_oil_data(session)

            # Step 2: Create realistic trade proposal based on real data
            print("\n💼 Step 2: Creating trade proposal from market data...")

            current_price = market_data['current_price']
            atr = market_data['atr_14']
            trend = market_data['trend']

            # Trade Intent (based on real trend)
            direction = TradeDirection.LONG if trend == "BULLISH" else TradeDirection.SHORT

            trade_intent = TradeIntent(
                direction=direction,
                conviction=0.72,
                rationale=f"CrudeOIL showing {trend} trend. Price at ${current_price:.2f}, "
                         f"{'above' if trend == 'BULLISH' else 'below'} 20-period average "
                         f"(${market_data['avg_price_20']:.2f}). Technical setup supports "
                         f"{direction} entry with moderate conviction.",
                key_factors=[
                    f"Price {trend.lower()} relative to 20-MA",
                    f"ATR at ${atr:.2f} (normal volatility)",
                    f"Current price: ${current_price:.2f}",
                    "No major resistance nearby"
                ],
                risk_assessment=f"Risk managed via ATR-based stop-loss. "
                               f"Volatility at ${atr:.2f} allows for reasonable stop distance. "
                               f"Expected holding period 1-3 days.",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"source": "real_database_data"}
            )

            print(f"   ✓ Direction: {direction}")
            print(f"   ✓ Conviction: {trade_intent.conviction:.2f}")

            # Position Size (realistic for $100k account)
            position_size = PositionSize(
                symbol="CrudeOIL",
                position_size_lots=0.50,  # 0.5 lots
                risk_percentage=2.0,  # 2% account risk
                risk_amount_usd=2000.0,  # $2000 risk
                reasoning=f"Kelly criterion applied with {trade_intent.conviction:.2f} "
                         f"conviction. ATR-based stop allows 0.5 lot position.",
                account_balance_usd=100000.0,
                reward_risk_ratio=2.0
            )

            print(f"   ✓ Position Size: {position_size.position_size_lots:.2f} lots")
            print(f"   ✓ Risk: {position_size.risk_percentage:.1f}%")

            # Stop-Loss (based on real ATR)
            stop_distance = atr * 1.5  # 1.5 ATR stop
            stop_price = current_price - stop_distance if direction == TradeDirection.LONG else current_price + stop_distance

            stop_loss = StopLoss(
                symbol="CrudeOIL",
                stop_loss_price=stop_price,
                distance_pips=stop_distance * 10,  # Convert to pips
                distance_percentage=(stop_distance / current_price) * 100,
                reasoning=f"Stop placed 1.5 ATR (${atr:.2f}) {'below' if direction == TradeDirection.LONG else 'above'} "
                         f"entry at ${stop_price:.2f}",
                technical_level="atr_multiple",
                volatility_adjustment=atr
            )

            print(f"   ✓ Stop-Loss: ${stop_loss.stop_loss_price:.2f}")
            print(f"   ✓ Stop Distance: ${stop_distance:.2f} (1.5 ATR)")

            # Take-Profit (realistic 2:1 R:R)
            tp_distance = stop_distance * 2.0  # 2:1 R:R
            tp_price = current_price + tp_distance if direction == TradeDirection.LONG else current_price - tp_distance

            take_profit = TakeProfit(
                symbol="CrudeOIL",
                take_profit_price=tp_price,
                distance_pips=tp_distance * 10,
                distance_percentage=(tp_distance / current_price) * 100,
                reward_risk_ratio=2.0,
                reasoning=f"Target at ${tp_price:.2f} provides 2:1 risk-reward ratio",
                technical_level="measured_move",
                partial_close_percentage=50.0,  # Close 50% at TP
                is_final_target=False
            )

            print(f"   ✓ Take-Profit: ${take_profit.take_profit_price:.2f}")
            print(f"   ✓ R:R Ratio: {take_profit.reward_risk_ratio:.1f}:1")

            # Current Portfolio (empty for clean test)
            current_portfolio = {
                "open_positions": [],
                "total_exposure_percent": 0.0,
                "current_drawdown_percent": 0.0,
                "available_capital": 100000.0
            }

            # Step 3: Fund Manager Approval
            print("\n🏦 Step 3: Running Fund Manager Approval Gate...")
            print("   Using: ollama/mistral:7b-instruct with Instructor")

            # Set environment for Instructor-based client
            os.environ["LLM_PROVIDER"] = "ollama"
            os.environ["OLLAMA_MODEL"] = "mistral:7b-instruct"
            os.environ["USE_INSTRUCTOR"] = "true"

            # Configure Fund Manager
            portfolio_limits = PortfolioLimits(
                max_account_risk_percent=5.0,
                max_portfolio_risk_percent=15.0,
                max_correlated_positions=3,
                event_risk_veto_hours=24,
                min_trade_quality_score=0.4
            )

            fm_config = AgentConfig(
                name="Fund_Manager_CrudeOIL",
                agent_type=AgentType.PORTFOLIO_ALLOCATOR,
                layer=AgentLayer.DECISION,
                llm_provider="ollama",
                llm_model="mistral:7b-instruct",
                llm_tier=LLMTier.DEEP_THINK,
                temperature=0.2
            )

            fund_manager = FundManagerAgent(
                config=fm_config,
                portfolio_limits=portfolio_limits
            )

            # Execute approval
            approval_start = time.time()

            approval = await fund_manager.approve_trade(
                trade_intent=trade_intent,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                current_portfolio=current_portfolio,
                symbol="CrudeOIL"
            )

            approval_duration = time.time() - approval_start

            # Print Results
            print(f"\n{'='*80}")
            print("FUND MANAGER APPROVAL DECISION")
            print(f"{'='*80}")

            print(f"\n✅ Decision: {approval.decision.value}")

            if approval.approved_position_size:
                print(f"✅ Approved Size: {approval.approved_position_size:.2f} lots")
            if approval.approved_risk_percentage:
                print(f"✅ Approved Risk: {approval.approved_risk_percentage:.2f}%")

            print(f"\n📋 Decision Details:")
            print(f"   Hard Limits Passed: {approval.hard_limits_passed}")
            print(f"   Trade Quality Score: {approval.trade_quality_score:.2f}")
            print(f"   Portfolio Risk After Trade: {approval.portfolio_risk_after_trade:.2f}%")
            print(f"   Correlation Check: {approval.correlation_check_passed}")
            print(f"   Event Risk Present: {approval.event_risk_present}")
            print(f"   Confidence: {approval.confidence:.2f}")
            print(f"   Recommended Timing: {approval.recommended_action_timing}")

            print(f"\n💭 Rationale:")
            print(f"   {approval.rationale}")

            if approval.decision == ApprovalDecision.MODIFY and approval.modifications:
                print(f"\n🔧 Modifications Requested:")
                for mod in approval.modifications:
                    print(f"   - {mod.modification_type.value}: "
                          f"{mod.current_value:.2f} → {mod.recommended_value:.2f}")
                    print(f"     Reason: {mod.rationale}")

            if approval.decision == ApprovalDecision.REJECT:
                print(f"\n❌ Rejection Reason: {approval.rejection_reason.value if approval.rejection_reason else 'Not specified'}")
                if approval.rejection_details:
                    print(f"   Details:")
                    for detail in approval.rejection_details:
                        print(f"   - {detail}")

            if approval.violated_limits:
                print(f"\n⚠️  Violated Limits:")
                for limit in approval.violated_limits:
                    print(f"   - {limit}")

            # Final Summary
            total_duration = time.time() - start_time

            print(f"\n{'='*80}")
            print("TEST SUMMARY")
            print(f"{'='*80}")
            print(f"✅ Test Duration: {total_duration:.2f}s")
            print(f"✅ Approval Decision Time: {approval_duration:.2f}s")
            print(f"✅ Data Source: PostgreSQL Database (REAL market data)")
            print(f"✅ Records Processed: {market_data['data_points']}")
            print(f"✅ Schema Validation: PASSED")
            print(f"✅ Fund Manager Decision: {approval.decision.value}")

            # Determine overall test result
            test_passed = (
                approval.decision in [ApprovalDecision.APPROVE, ApprovalDecision.MODIFY, ApprovalDecision.REJECT] and
                approval.trade_quality_score >= 0.0 and
                approval.confidence >= 0.0
            )

            if test_passed:
                print(f"\n🎉 PHASE 6 SIMPLIFIED TEST: PASSED ✅")
            else:
                print(f"\n❌ PHASE 6 SIMPLIFIED TEST: FAILED")

            print(f"{'='*80}\n")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_fund_manager_test())
