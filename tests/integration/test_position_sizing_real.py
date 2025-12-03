"""
Real Integration Test: Position Sizing with Actual LLM and Database.

This test validates User Story 1 (SC-001) with:
- Real database connections (PostgreSQL)
- Real LLM calls (Ollama with deepseek-r1:14b)
- Real MCP tool invocations
- Real circuit breaker behavior

NO MOCKS - Full integration testing.

Success Criterion (SC-001):
- Position sizes must vary by 50%+ across different scenarios
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.config import DatabaseConfig
from src.agents.decision.position_sizing_agent import create_position_sizing_agent
import uuid
import os


class TestScenario:
    """Test scenario definition."""

    def __init__(
        self,
        name: str,
        description: str,
        account_balance: float,
        current_drawdown: float,
        trade_conviction: float,
        stop_distance_pips: float,
        target_distance_pips: float,
        win_rate: float = 0.55,
        avg_win_pips: float = 125.0,
        avg_loss_pips: float = 50.0,
        correlation_with_existing: float = None,
        major_event_within_24h: bool = False,
        major_event_within_48h: bool = False,
    ):
        self.name = name
        self.description = description
        self.account_balance = account_balance
        self.current_drawdown = current_drawdown
        self.trade_conviction = trade_conviction
        self.stop_distance_pips = stop_distance_pips
        self.target_distance_pips = target_distance_pips
        self.win_rate = win_rate
        self.avg_win_pips = avg_win_pips
        self.avg_loss_pips = avg_loss_pips
        self.correlation_with_existing = correlation_with_existing
        self.major_event_within_24h = major_event_within_24h
        self.major_event_within_48h = major_event_within_48h


async def test_position_sizing_variance():
    """
    Test position sizing across 4 scenarios with real LLM and database.
    """
    print("\n" + "="*80)
    print("Real Integration Test - Position Sizing Variance (SC-001)")
    print("Using: Real Database + Real Ollama LLM + Real MCP Tools")
    print("="*80)

    # Define test scenarios
    scenarios = [
        TestScenario(
            name="Scenario 1: Favorable Conditions",
            description="Low volatility, no drawdown, high conviction",
            account_balance=50000.0,
            current_drawdown=0.0,  # No drawdown
            trade_conviction=0.85,  # High conviction
            stop_distance_pips=50,
            target_distance_pips=125,
            win_rate=0.60,  # Strong edge
            avg_win_pips=125.0,
            avg_loss_pips=50.0,
            correlation_with_existing=0.2,  # Low correlation
            major_event_within_24h=False,
        ),
        TestScenario(
            name="Scenario 2: Adverse Conditions",
            description="High volatility, significant drawdown, low conviction",
            account_balance=50000.0,
            current_drawdown=0.12,  # 12% drawdown
            trade_conviction=0.45,  # Low conviction
            stop_distance_pips=80,  # Wider stop
            target_distance_pips=120,
            win_rate=0.52,  # Marginal edge
            avg_win_pips=100.0,
            avg_loss_pips=80.0,
            correlation_with_existing=0.3,
        ),
        TestScenario(
            name="Scenario 3: High Correlation Risk",
            description="Moderate conditions but high correlation",
            account_balance=50000.0,
            current_drawdown=0.05,
            trade_conviction=0.70,
            stop_distance_pips=60,
            target_distance_pips=135,
            win_rate=0.58,
            avg_win_pips=120.0,
            avg_loss_pips=60.0,
            correlation_with_existing=0.75,  # High correlation!
        ),
        TestScenario(
            name="Scenario 4: Event Risk",
            description="Good conditions but major event within 24h",
            account_balance=50000.0,
            current_drawdown=0.02,
            trade_conviction=0.80,
            stop_distance_pips=55,
            target_distance_pips=140,
            win_rate=0.62,
            avg_win_pips=130.0,
            avg_loss_pips=55.0,
            correlation_with_existing=0.25,
            major_event_within_24h=True,  # Event risk!
        ),
    ]

    # Create database configuration
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://risetrader:risetrader@postgres:5432/risetrader"
    )

    db = DatabaseConfig(database_url=database_url, echo=False)

    async with db.get_session() as session:
        # Create agent with real session
        agent_id = uuid.uuid4()
        symbol = "Gold"

        print(f"\nCreating Position Sizing Agent...")
        print(f"  Agent ID: {agent_id}")
        print(f"  Symbol: {symbol}")
        print(f"  LLM: Ollama deepseek-r1:14b")

        agent = create_position_sizing_agent(
            agent_id=agent_id,
            session=session,
            symbol=symbol,
        )

        print(f"  ✓ Agent created successfully\n")

        # Run all scenarios
        results: List[Dict] = []

        for i, scenario in enumerate(scenarios, 1):
            print(f"{'-'*80}")
            print(f"{i}. {scenario.name}")
            print(f"   {scenario.description}")
            print(f"{'-'*80}")
            print(f"   Parameters:")
            print(f"     Conviction: {scenario.trade_conviction:.2f}")
            print(f"     Drawdown: {scenario.current_drawdown*100:.1f}%")
            print(f"     Stop: {scenario.stop_distance_pips} pips")
            print(f"     Target: {scenario.target_distance_pips} pips")
            if scenario.correlation_with_existing:
                print(f"     Correlation: {scenario.correlation_with_existing:.2f}")
            if scenario.major_event_within_24h:
                print(f"     Event Risk: YES (within 24h)")
            print()

            try:
                print(f"   Calling LLM... (this may take 30-60 seconds)")

                decision = await agent.determine_position_size(
                    symbol=symbol,
                    account_balance=scenario.account_balance,
                    current_drawdown=scenario.current_drawdown,
                    trade_conviction=scenario.trade_conviction,
                    stop_distance_pips=scenario.stop_distance_pips,
                    target_distance_pips=scenario.target_distance_pips,
                    win_rate=scenario.win_rate,
                    avg_win_pips=scenario.avg_win_pips,
                    avg_loss_pips=scenario.avg_loss_pips,
                    correlation_with_existing=scenario.correlation_with_existing,
                    major_event_within_24h=scenario.major_event_within_24h,
                    major_event_within_48h=scenario.major_event_within_48h,
                )

                # Store result
                results.append({
                    "scenario": scenario.name,
                    "lot_quantity": decision.get("lot_quantity", 0.0),
                    "risk_pct": decision.get("dynamic_risk_percentage", 0.0),
                    "kelly_fraction": decision.get("kelly_fraction_applied", 0.0),
                    "adjustments": decision.get("adjustments", {}),
                    "reasoning": decision.get("reasoning", ""),
                    "confidence": decision.get("confidence", 0.0),
                })

                print(f"   ✓ Position Size: {decision.get('lot_quantity', 0.0):.2f} lots")
                print(f"   ✓ Risk Percentage: {decision.get('dynamic_risk_percentage', 0.0):.2f}%")
                print(f"   ✓ Kelly Fraction: {decision.get('kelly_fraction_applied', 0.0):.3f}")
                print(f"   ✓ Confidence: {decision.get('confidence', 0.0):.2f}")

                adjustments = decision.get("adjustments", {})
                if adjustments:
                    print(f"\n   Adjustments Applied:")
                    for adj_name, adj_value in adjustments.items():
                        print(f"     - {adj_name}: {adj_value:.2f}x")

                reasoning = decision.get("reasoning", "")
                if reasoning:
                    print(f"\n   Reasoning:")
                    # Print first 200 chars of reasoning
                    reasoning_preview = reasoning[:200]
                    if len(reasoning) > 200:
                        reasoning_preview += "..."
                    for line in reasoning_preview.split(". ")[:2]:
                        if line.strip():
                            print(f"     {line.strip()}.")

                print()

            except Exception as e:
                print(f"   ✗ FAILED: {str(e)}")
                import traceback
                traceback.print_exc()
                results.append({
                    "scenario": scenario.name,
                    "lot_quantity": 0.0,
                    "risk_pct": 0.0,
                    "kelly_fraction": 0.0,
                    "adjustments": {},
                    "reasoning": f"Error: {str(e)}",
                    "confidence": 0.0,
                    "error": str(e),
                })

    # Analyze variance
    print(f"{'='*80}")
    print("Variance Analysis - Success Criterion (SC-001)")
    print(f"{'='*80}\n")

    lot_quantities = [r["lot_quantity"] for r in results if r["lot_quantity"] > 0]
    risk_percentages = [r["risk_pct"] for r in results if r["risk_pct"] > 0]

    if len(lot_quantities) >= 2:
        min_lots = min(lot_quantities)
        max_lots = max(lot_quantities)
        min_risk = min(risk_percentages)
        max_risk = max(risk_percentages)

        lots_variance = ((max_lots - min_lots) / max_lots) * 100
        risk_variance = ((max_risk - min_risk) / max_risk) * 100

        print("Lot Quantity Variance:")
        print(f"  Min: {min_lots:.2f} lots")
        print(f"  Max: {max_lots:.2f} lots")
        print(f"  Variance: {lots_variance:.1f}% {'✅ PASS' if lots_variance >= 50 else '❌ FAIL'}")

        print(f"\nRisk Percentage Variance:")
        print(f"  Min: {min_risk:.2f}%")
        print(f"  Max: {max_risk:.2f}%")
        print(f"  Variance: {risk_variance:.1f}% {'✅ PASS' if risk_variance >= 50 else '❌ FAIL'}")

        # Detailed results table
        print(f"\n{'='*80}")
        print("Detailed Results")
        print(f"{'='*80}\n")
        print(f"{'Scenario':<40} {'Lots':<10} {'Risk %':<10} {'Kelly':<10}")
        print(f"{'-'*80}")
        for r in results:
            scenario_name = r['scenario'].split(":")[0]  # Shorten name
            print(f"{scenario_name:<40} {r['lot_quantity']:<10.2f} {r['risk_pct']:<10.2f} {r['kelly_fraction']:<10.3f}")

        # Success criterion
        print(f"\n{'='*80}")
        if lots_variance >= 50 or risk_variance >= 50:
            print("✅ SUCCESS: Position sizing demonstrates 50%+ variance")
            print("   User Story 1 (SC-001) VALIDATED!")
            print(f"{'='*80}")
            return True
        else:
            print("❌ FAILURE: Position sizing variance < 50%")
            print("   User Story 1 (SC-001) NOT MET")
            print(f"{'='*80}")
            return False
    else:
        print("❌ Not enough valid results to analyze variance")
        return False


async def main():
    """Run position sizing variance test with real LLM."""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║   Real Integration Test - User Story 1 (SC-001)                           ║
║   Position Sizing Variance with Real LLM + Database                       ║
╚════════════════════════════════════════════════════════════════════════════╝
""")

    try:
        success = await test_position_sizing_variance()

        if success:
            print("\n🎉 User Story 1 (SC-001) COMPLETE AND VALIDATED")
            sys.exit(0)
        else:
            print("\n❌ User Story 1 (SC-001) VALIDATION FAILED")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
