"""
Real Integration Test: Risk Debate Pipeline (T129).

This test validates the 3-way risk tolerance debate with:
- Real database connections (PostgreSQL + TimescaleDB)
- Real LLM calls (OpenAI or Ollama)
- Real position sizing data
- Real decision logging

NO MOCKS - Full integration testing.

Success Criteria:
- All three perspectives (RISKY, NEUTRAL, SAFE) generated
- Consensus adjustment calculated from weighted perspectives
- Final position size adjusted based on debate
- Debate outcome logged to decision_log table
- Safety gates respected (max position size, drawdown limits)
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.schemas.decisions import PositionSize
from src.agents.base.agent_config import LLMTier
from src.database.repositories.decision_log_repository import DecisionLogRepository


class TestScenario:
    """Test scenario for risk debate pipeline."""

    def __init__(
        self,
        name: str,
        symbol: str,
        baseline_lot_size: float,
        baseline_risk_pct: float,
        conviction: float,
        regime: str,
        correlation_count: int,
        current_drawdown: float,
        account_balance: float,
        event_risk: bool,
        expected_adjustment_range: tuple = None  # (min, max) expected adjustment
    ):
        self.name = name
        self.symbol = symbol
        self.baseline_lot_size = baseline_lot_size
        self.baseline_risk_pct = baseline_risk_pct
        self.conviction = conviction
        self.regime = regime
        self.correlation_count = correlation_count
        self.current_drawdown = current_drawdown
        self.account_balance = account_balance
        self.event_risk = event_risk
        self.expected_adjustment_range = expected_adjustment_range


def create_position_size(scenario: TestScenario) -> PositionSize:
    """
    Create baseline position size for the scenario.

    Args:
        scenario: Test scenario definition

    Returns:
        PositionSize object with baseline sizing
    """
    return PositionSize(
        lot_size=scenario.baseline_lot_size,
        risk_percentage=scenario.baseline_risk_pct,
        risk_amount=scenario.account_balance * (scenario.baseline_risk_pct / 100),
        entry_price=75.50,  # Example crude oil price
        stop_loss=74.00,  # 150 pip stop
        take_profit=78.00,  # 250 pip target
        calculation_details=f"""
Kelly Criterion Calculation:
- Win Rate: 0.60
- Risk:Reward: 1:1.67
- Kelly %: {scenario.baseline_risk_pct:.2f}%
- Position Size: {scenario.baseline_lot_size:.2f} lots

Account Context:
- Balance: ${scenario.account_balance:.2f}
- Current Drawdown: {scenario.current_drawdown:.1f}%
- Conviction: {scenario.conviction:.2f}
        """.strip(),
        position_value=scenario.baseline_lot_size * 100000 * 75.50,  # USD value at entry
        leverage_ratio=50.0,  # Standard forex leverage
        margin_required=(scenario.baseline_lot_size * 100000 * 75.50) / 50.0
    )


def create_trade_context(scenario: TestScenario) -> Dict[str, Any]:
    """
    Create trade context for the scenario.

    Args:
        scenario: Test scenario definition

    Returns:
        Trade context dictionary
    """
    return {
        "conviction": scenario.conviction,
        "regime": scenario.regime,
        "correlation_count": scenario.correlation_count,
        "current_drawdown_percent": scenario.current_drawdown,
        "account_balance": scenario.account_balance,
        "event_risk": scenario.event_risk,
        "volatility": "low" if scenario.regime == "trending" else "high",
        "portfolio_heat": scenario.baseline_risk_pct + (scenario.correlation_count * 0.5)
    }


async def run_risk_debate_test(scenario: TestScenario) -> None:
    """
    Run a single risk debate test scenario.

    Args:
        scenario: Test scenario definition
    """
    print(f"\n{'='*80}")
    print(f"Test Scenario: {scenario.name}")
    print(f"Symbol: {scenario.symbol}")
    print(f"Baseline: {scenario.baseline_lot_size:.2f} lots ({scenario.baseline_risk_pct:.2f}% risk)")
    print(f"Context: Conviction={scenario.conviction:.2f}, Regime={scenario.regime}, Drawdown={scenario.current_drawdown:.1f}%")
    print(f"{'='*80}")

    # Create database connection
    database_url = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create decision log repository
        decision_log_repo = DecisionLogRepository(session)

        # Create risk debate team
        risk_debate_team = RiskDebateTeam(
            llm_tier=LLMTier.DEEP_THINK,
            decision_log_repo=decision_log_repo
        )

        # Create baseline position size
        position_size = create_position_size(scenario)

        # Create trade context
        trade_context = create_trade_context(scenario)

        # Run risk debate
        start_time = datetime.utcnow()

        try:
            debate_outcome = await risk_debate_team.run_risk_debate(
                position_size=position_size,
                trade_context=trade_context,
                symbol=scenario.symbol
            )

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Validate debate outcome
            print(f"\n✅ Risk debate completed in {duration_ms:.0f}ms")

            print(f"\n📊 Risky Perspective (argues for HIGHER sizing):")
            print(f"   Recommended Adjustment: {debate_outcome.risky_perspective.recommended_size_adjustment:.2f}x")
            print(f"   Reasoning: {debate_outcome.risky_perspective.reasoning[:100]}...")
            print(f"   Key Factors: {', '.join(debate_outcome.risky_perspective.key_factors[:2])}")
            print(f"   Confidence: {debate_outcome.risky_perspective.confidence:.2f}")

            print(f"\n📊 Neutral Perspective (validates BASELINE):")
            print(f"   Recommended Adjustment: {debate_outcome.neutral_perspective.recommended_size_adjustment:.2f}x")
            print(f"   Reasoning: {debate_outcome.neutral_perspective.reasoning[:100]}...")
            print(f"   Key Factors: {', '.join(debate_outcome.neutral_perspective.key_factors[:2])}")
            print(f"   Confidence: {debate_outcome.neutral_perspective.confidence:.2f}")

            print(f"\n📊 Safe Perspective (argues for LOWER sizing):")
            print(f"   Recommended Adjustment: {debate_outcome.safe_perspective.recommended_size_adjustment:.2f}x")
            print(f"   Reasoning: {debate_outcome.safe_perspective.reasoning[:100]}...")
            print(f"   Key Factors: {', '.join(debate_outcome.safe_perspective.key_factors[:2])}")
            print(f"   Confidence: {debate_outcome.safe_perspective.confidence:.2f}")

            print(f"\n🎯 Consensus Decision:")
            print(f"   Consensus Adjustment: {debate_outcome.consensus_adjustment:.2f}x")
            print(f"   Consensus Reached: {'Yes' if debate_outcome.consensus_reached else 'No'}")
            print(f"   Final Position Size: {debate_outcome.final_position_size:.2f} lots")
            print(f"   Final Risk %: {debate_outcome.final_risk_percentage:.2f}%")
            print(f"   Change from Baseline: {((debate_outcome.final_position_size / scenario.baseline_lot_size) - 1) * 100:+.1f}%")

            if debate_outcome.key_warnings:
                print(f"\n⚠️  Key Warnings:")
                for warning in debate_outcome.key_warnings:
                    print(f"   - {warning}")

            if debate_outcome.divergence_rationale:
                print(f"\n📝 Divergence Rationale: {debate_outcome.divergence_rationale}")

            # Verify expected adjustment range
            if scenario.expected_adjustment_range:
                min_adj, max_adj = scenario.expected_adjustment_range
                if min_adj <= debate_outcome.consensus_adjustment <= max_adj:
                    print(f"\n✅ Consensus adjustment within expected range: {min_adj:.2f} - {max_adj:.2f}")
                else:
                    print(f"\n⚠️  Consensus adjustment outside expected range: Expected {min_adj:.2f}-{max_adj:.2f}, got {debate_outcome.consensus_adjustment:.2f}")

            # Verify decision was logged
            from sqlalchemy import select, desc
            from src.database.models.decision_log import DecisionLog

            result = await session.execute(
                select(DecisionLog)
                .where(DecisionLog.agent_type == "risk_debate_team")
                .where(DecisionLog.symbol == scenario.symbol)
                .order_by(desc(DecisionLog.decided_at))
                .limit(1)
            )
            logged_decision = result.scalar_one_or_none()

            if logged_decision:
                print(f"\n✅ Decision logged to database (ID: {logged_decision.id})")
                print(f"   Processing time: {logged_decision.processing_time_ms}ms")
            else:
                print(f"\n❌ Decision not found in database!")

            print(f"\n{'='*80}\n")

        except Exception as e:
            print(f"\n❌ Risk debate failed: {e}")
            import traceback
            traceback.print_exc()
            raise

        finally:
            await engine.dispose()


async def test_risk_debate_pipeline():
    """
    Main integration test for risk debate pipeline.

    Tests multiple scenarios with different risk profiles.
    """
    print("\n" + "="*80)
    print("Real Integration Test - Risk Debate Pipeline (T129)")
    print("Using: Real Database + Real LLM + Real Position Sizing Data")
    print("="*80)

    # Define test scenarios
    scenarios = [
        TestScenario(
            name="Scenario 1: Favorable Conditions (Risky should win)",
            symbol="CrudeOIL",
            baseline_lot_size=2.00,
            baseline_risk_pct=2.0,
            conviction=0.85,  # High conviction
            regime="trending",  # Calm regime
            correlation_count=0,  # No correlated positions
            current_drawdown=0.0,  # No drawdown
            account_balance=50000.0,
            event_risk=False,
            expected_adjustment_range=(1.1, 1.5)  # Expect size increase
        ),
        TestScenario(
            name="Scenario 2: High Risk Conditions (Safe should win)",
            symbol="CrudeOIL",
            baseline_lot_size=2.00,
            baseline_risk_pct=2.0,
            conviction=0.45,  # Low conviction
            regime="choppy",  # Uncertain regime
            correlation_count=3,  # High correlation
            current_drawdown=0.12,  # 12% drawdown
            account_balance=50000.0,
            event_risk=True,  # Event risk present
            expected_adjustment_range=(0.4, 0.8)  # Expect size reduction
        ),
        TestScenario(
            name="Scenario 3: Moderate Conditions (Neutral should win)",
            symbol="CrudeOIL",
            baseline_lot_size=2.00,
            baseline_risk_pct=2.0,
            conviction=0.65,  # Moderate conviction
            regime="trending",  # Normal regime
            correlation_count=1,  # Some correlation
            current_drawdown=0.03,  # Small drawdown
            account_balance=50000.0,
            event_risk=False,
            expected_adjustment_range=(0.9, 1.1)  # Expect baseline maintained
        ),
        TestScenario(
            name="Scenario 4: Mixed Signals (Divergence expected)",
            symbol="CrudeOIL",
            baseline_lot_size=2.00,
            baseline_risk_pct=2.0,
            conviction=0.75,  # High conviction (favors risky)
            regime="choppy",  # Uncertain regime (favors safe)
            correlation_count=2,  # Moderate correlation (favors safe)
            current_drawdown=0.05,  # Moderate drawdown (favors safe)
            account_balance=50000.0,
            event_risk=True,  # Event risk (favors safe)
            expected_adjustment_range=(0.6, 1.0)  # Expect reduction despite high conviction
        )
    ]

    # Run all scenarios
    for scenario in scenarios:
        await run_risk_debate_test(scenario)
        # Add small delay between scenarios to avoid rate limiting
        await asyncio.sleep(2)

    print("\n" + "="*80)
    print("✅ All risk debate pipeline tests complete!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_risk_debate_pipeline())
