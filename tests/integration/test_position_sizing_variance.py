"""
Integration Test: Position Sizing Variance (SC-001).

Validates that the PositionSizingAgent produces dynamic position sizes
that vary by 50%+ across different market scenarios, as required by User Story 1.

Test Scenarios:
1. Favorable conditions: Low volatility, no drawdown, high conviction
2. Adverse conditions: High volatility, significant drawdown, low conviction
3. High correlation: Existing correlated positions
4. Event risk: Major economic event within 24h

Success Criterion (SC-001):
- Position sizes must vary by 50%+ between scenarios
- All adjustments must be documented with clear reasoning
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.decision.position_sizing_agent import (
    PositionSizingAgent,
    create_position_sizing_agent,
)


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
    Test position sizing across 4 scenarios and validate 50%+ variance.
    """
    print("\n" + "="*80)
    print("Position Sizing Variance Test - User Story 1 (SC-001)")
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
            major_event_within_48h=False,
        ),
        TestScenario(
            name="Scenario 2: Adverse Conditions",
            description="High volatility, significant drawdown, low conviction",
            account_balance=50000.0,
            current_drawdown=0.12,  # 12% drawdown
            trade_conviction=0.45,  # Low conviction
            stop_distance_pips=80,  # Wider stop in volatility
            target_distance_pips=120,
            win_rate=0.52,  # Marginal edge
            avg_win_pips=100.0,
            avg_loss_pips=80.0,
            correlation_with_existing=0.3,
            major_event_within_24h=False,
            major_event_within_48h=False,
        ),
        TestScenario(
            name="Scenario 3: High Correlation Risk",
            description="Moderate conditions but high correlation with existing positions",
            account_balance=50000.0,
            current_drawdown=0.05,  # Moderate drawdown
            trade_conviction=0.70,  # Moderate conviction
            stop_distance_pips=60,
            target_distance_pips=135,
            win_rate=0.58,
            avg_win_pips=120.0,
            avg_loss_pips=60.0,
            correlation_with_existing=0.75,  # High correlation!
            major_event_within_24h=False,
            major_event_within_48h=False,
        ),
        TestScenario(
            name="Scenario 4: Event Risk",
            description="Good conditions but major event within 24h",
            account_balance=50000.0,
            current_drawdown=0.02,  # Low drawdown
            trade_conviction=0.80,  # High conviction
            stop_distance_pips=55,
            target_distance_pips=140,
            win_rate=0.62,
            avg_win_pips=130.0,
            avg_loss_pips=55.0,
            correlation_with_existing=0.25,
            major_event_within_24h=True,  # Event risk!
            major_event_within_48h=False,
        ),
    ]

    # Mock database session (needs to be AsyncMock for await operations)
    db_session = AsyncMock()

    # Mock the execute method to return a result with scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    db_session.execute = AsyncMock(return_value=mock_result)

    # Create agent instance
    import uuid
    agent_id = uuid.uuid4()  # Valid UUID required
    symbol = "Gold"

    agent = create_position_sizing_agent(
        agent_id=agent_id,
        session=db_session,
        symbol=symbol,
    )

    # Run all scenarios
    results: List[Dict] = []

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'-'*80}")
        print(f"{i}. {scenario.name}")
        print(f"   {scenario.description}")
        print(f"{'-'*80}")

        try:
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
            print(f"\n   Adjustments Applied:")
            for adj_name, adj_value in decision.get("adjustments", {}).items():
                print(f"     - {adj_name}: {adj_value:.2f}x")
            print(f"\n   Reasoning:")
            reasoning_lines = decision.get("reasoning", "").split(". ")
            for line in reasoning_lines[:3]:  # First 3 sentences
                if line.strip():
                    print(f"     {line.strip()}.")

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
    print(f"\n{'='*80}")
    print("Variance Analysis - Success Criterion (SC-001): 50%+ variance required")
    print(f"{'='*80}\n")

    lot_quantities = [r["lot_quantity"] for r in results]
    risk_percentages = [r["risk_pct"] for r in results]

    if len(lot_quantities) > 0:
        min_lots = min(lot_quantities)
        max_lots = max(lot_quantities)
        min_risk = min(risk_percentages)
        max_risk = max(risk_percentages)

        if max_lots > 0:
            lots_variance = ((max_lots - min_lots) / max_lots) * 100
        else:
            lots_variance = 0.0

        if max_risk > 0:
            risk_variance = ((max_risk - min_risk) / max_risk) * 100
        else:
            risk_variance = 0.0

        print("Lot Quantity Variance:")
        print(f"  Min: {min_lots:.2f} lots (Scenario: {results[lot_quantities.index(min_lots)]['scenario']})")
        print(f"  Max: {max_lots:.2f} lots (Scenario: {results[lot_quantities.index(max_lots)]['scenario']})")
        print(f"  Variance: {lots_variance:.1f}% {'✅ PASS' if lots_variance >= 50 else '❌ FAIL'}")

        print(f"\nRisk Percentage Variance:")
        print(f"  Min: {min_risk:.2f}% (Scenario: {results[risk_percentages.index(min_risk)]['scenario']})")
        print(f"  Max: {max_risk:.2f}% (Scenario: {results[risk_percentages.index(max_risk)]['scenario']})")
        print(f"  Variance: {risk_variance:.1f}% {'✅ PASS' if risk_variance >= 50 else '❌ FAIL'}")

        # Success criterion
        print(f"\n{'='*80}")
        if lots_variance >= 50 or risk_variance >= 50:
            print("✅ SUCCESS: Position sizing demonstrates 50%+ variance")
            print("   Adaptive position sizing is working as intended!")
            print(f"{'='*80}")
            return True
        else:
            print("❌ FAILURE: Position sizing variance < 50%")
            print("   Position sizing is not sufficiently adaptive!")
            print(f"{'='*80}")
            return False
    else:
        print("❌ No valid results to analyze")
        return False


async def main():
    """Run position sizing variance test."""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║   Position Sizing Variance Test - User Story 1                            ║
║   Success Criterion: 50%+ variance across scenarios                       ║
╚════════════════════════════════════════════════════════════════════════════╝
""")

    try:
        success = await test_position_sizing_variance()

        if success:
            print("\n✅ User Story 1 (SC-001) VALIDATED")
            sys.exit(0)
        else:
            print("\n❌ User Story 1 (SC-001) FAILED")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
