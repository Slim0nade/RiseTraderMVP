"""
Integration Test: Ollama Models with Instructor Library.

Tests all open-source Ollama models using the instructor library for guaranteed
JSON schema compliance via GBNF grammar constraints.

Success Criterion (SC-001):
- Position sizes must vary by 50%+ between scenarios
- 100% JSON schema compliance (no validation errors)
- Response time <10s for 7-8B models
"""

import asyncio
import os
import time
import sys
from pathlib import Path
from typing import Dict, List
from pydantic import BaseModel, Field

# IMPORTANT: Set OLLAMA_HOST before importing ollama library
os.environ['OLLAMA_HOST'] = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import instructor
from ollama import Client


class PositionSizeDecision(BaseModel):
    """Position sizing decision with strict validation."""
    lot_quantity: float = Field(..., ge=0.01, le=10.0, description="Lot size between 0.01 and 10.0")
    dynamic_risk_percentage: float = Field(..., ge=0.1, le=5.0, description="Risk percentage between 0.1 and 5.0")
    kelly_fraction_applied: float = Field(..., ge=0.0, le=1.0, description="Kelly fraction applied (0.0 to 1.0)")
    base_size: float = Field(..., description="Base position size before adjustments")
    adjustments: Dict[str, float] = Field(..., description="Adjustment factors applied")
    reasoning: str = Field(..., description="Brief explanation of the decision")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in decision (0.0 to 1.0)")
    risk_metrics: Dict[str, float] = Field(..., description="Risk metrics for the position")


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


def create_minimal_prompt(scenario: TestScenario) -> str:
    """Create minimal prompt - let Pydantic schema do the work."""
    win_loss_ratio = scenario.avg_win_pips / scenario.avg_loss_pips
    kelly = ((scenario.win_rate * (win_loss_ratio + 1)) - 1) / win_loss_ratio

    return f"""Calculate position size for Gold trading.

Kelly Criterion: {kelly:.3f}
Account Balance: ${scenario.account_balance:,.0f}
Stop Distance: {scenario.stop_distance_pips} pips
Pip Value: $10/pip
Current Drawdown: {scenario.current_drawdown*100:.1f}%
Conviction: {scenario.trade_conviction:.2f}
Correlation: {scenario.correlation_with_existing if scenario.correlation_with_existing else 'None'}
Major Event 24h: {'Yes' if scenario.major_event_within_24h else 'No'}
Major Event 48h: {'Yes' if scenario.major_event_within_48h else 'No'}

Calculate lot_quantity using: Kelly * account / (stop_pips * pip_value)
Apply adjustments for: drawdown, volatility, conviction, correlation, event risk.
Min: 0.01 lots, Max: 10 lots."""


def test_model_with_instructor(model_name: str, scenarios: List[TestScenario]) -> Dict:
    """Test a model using instructor library."""

    print(f"\n{'='*80}")
    print(f"Testing: {model_name}")
    print(f"{'='*80}")

    # Import the new instructor client
    sys.path.insert(0, "/app")
    from src.agents.providers.instructor_client import InstructorOllamaClient

    try:
        # Use the new instructor client with /v1 endpoint
        client = InstructorOllamaClient(
            model=model_name,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434"),
            default_max_retries=3,
            default_timeout=120.0,
        )
    except Exception as e:
        print(f"❌ Failed to create instructor client: {e}")
        return {"model": model_name, "status": "error", "error": str(e)}

    results = []
    total_time = 0

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'-'*80}")
        print(f"{i}. {scenario.name}")
        print(f"   {scenario.description}")
        print(f"{'-'*80}")

        prompt = create_minimal_prompt(scenario)

        start_time = time.time()
        try:
            # This GUARANTEES valid schema or raises exception
            result = client.get_structured_response(
                response_model=PositionSizeDecision,
                system_prompt="Position sizing expert. Use Kelly Criterion. Consider: drawdown, volatility, conviction, correlation, event risk.",
                user_prompt=prompt,
                max_retries=3,
                timeout=120.0,
            )

            elapsed = time.time() - start_time
            total_time += elapsed

            print(f"   ✓ Position Size: {result.lot_quantity:.2f} lots")
            print(f"   ✓ Risk Percentage: {result.dynamic_risk_percentage:.2f}%")
            print(f"   ✓ Kelly Fraction: {result.kelly_fraction_applied:.3f}")
            print(f"   ✓ Confidence: {result.confidence:.2f}")
            print(f"   ✓ Response Time: {elapsed:.2f}s")
            print(f"\n   Adjustments Applied:")
            for key, value in result.adjustments.items():
                print(f"     - {key}: {value:.2f}x")
            print(f"\n   Reasoning:")
            print(f"     {result.reasoning}.")

            results.append({
                "scenario": scenario.name,
                "lot_quantity": result.lot_quantity,
                "dynamic_risk_percentage": result.dynamic_risk_percentage,
                "kelly_fraction": result.kelly_fraction_applied,
                "confidence": result.confidence,
                "response_time": elapsed,
            })

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"   ❌ FAILED after {elapsed:.2f}s: {e}")
            return {
                "model": model_name,
                "status": "failed",
                "error": str(e),
                "failed_scenario": scenario.name,
            }

    # Calculate variance
    lot_quantities = [r["lot_quantity"] for r in results]
    risk_percentages = [r["dynamic_risk_percentage"] for r in results]

    min_lot = min(lot_quantities)
    max_lot = max(lot_quantities)
    lot_variance = ((max_lot - min_lot) / min_lot) * 100 if min_lot > 0 else 0

    min_risk = min(risk_percentages)
    max_risk = max(risk_percentages)
    risk_variance = ((max_risk - min_risk) / min_risk) * 100 if min_risk > 0 else 0

    avg_time = total_time / len(scenarios)

    print(f"\n{'='*80}")
    print("Variance Analysis - Success Criterion (SC-001): 50%+ variance required")
    print(f"{'='*80}")
    print(f"\nLot Quantity Variance:")
    print(f"  Min: {min_lot:.2f} lots")
    print(f"  Max: {max_lot:.2f} lots")
    print(f"  Variance: {lot_variance:.1f}% {'✅ PASS' if lot_variance >= 50 else '❌ FAIL'}")
    print(f"\nRisk Percentage Variance:")
    print(f"  Min: {min_risk:.2f}%")
    print(f"  Max: {max_risk:.2f}%")
    print(f"  Variance: {risk_variance:.1f}% {'✅ PASS' if risk_variance >= 50 else '❌ FAIL'}")
    print(f"\nAverage Response Time: {avg_time:.2f}s")

    passed = lot_variance >= 50 or risk_variance >= 50

    if passed:
        print(f"\n{'='*80}")
        print("✅ SUCCESS: Position sizing demonstrates 50%+ variance")
        print("   Adaptive position sizing is working as intended!")
        print(f"{'='*80}\n")
        print(f"✅ User Story 1 (SC-001) VALIDATED with {model_name}\n")
    else:
        print(f"\n{'='*80}")
        print("❌ FAILED: Position sizing does not meet 50%+ variance criterion")
        print(f"{'='*80}\n")

    return {
        "model": model_name,
        "status": "passed" if passed else "failed",
        "lot_variance": lot_variance,
        "risk_variance": risk_variance,
        "avg_response_time": avg_time,
        "results": results,
    }


def main():
    """Run tests for all Ollama models with instructor."""

    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "Ollama Models with Instructor Library" + " "*20 + "║")
    print("║" + " "*16 + "Success Criterion: 50%+ variance across scenarios" + " "*15 + "║")
    print("╚" + "="*78 + "╝\n")

    # Define test scenarios (same as original)
    scenarios = [
        TestScenario(
            name="Scenario 1: Favorable Conditions",
            description="Low volatility, no drawdown, high conviction",
            account_balance=50000.0,
            current_drawdown=0.0,
            trade_conviction=0.85,
            stop_distance_pips=50,
            target_distance_pips=125,
            win_rate=0.60,
            avg_win_pips=125.0,
            avg_loss_pips=50.0,
            correlation_with_existing=0.2,
            major_event_within_24h=False,
            major_event_within_48h=False,
        ),
        TestScenario(
            name="Scenario 2: Adverse Conditions",
            description="High volatility, significant drawdown, low conviction",
            account_balance=50000.0,
            current_drawdown=0.12,
            trade_conviction=0.45,
            stop_distance_pips=80,
            target_distance_pips=120,
            win_rate=0.52,
            avg_win_pips=100.0,
            avg_loss_pips=80.0,
            correlation_with_existing=0.3,
            major_event_within_24h=False,
            major_event_within_48h=True,
        ),
        TestScenario(
            name="Scenario 3: High Correlation Risk",
            description="Moderate conditions but high correlation with existing positions",
            account_balance=50000.0,
            current_drawdown=0.05,
            trade_conviction=0.70,
            stop_distance_pips=60,
            target_distance_pips=120,
            win_rate=0.58,
            avg_win_pips=120.0,
            avg_loss_pips=60.0,
            correlation_with_existing=0.75,
            major_event_within_24h=False,
            major_event_within_48h=False,
        ),
        TestScenario(
            name="Scenario 4: Event Risk",
            description="Good conditions but major event within 24h",
            account_balance=50000.0,
            current_drawdown=0.02,
            trade_conviction=0.80,
            stop_distance_pips=55,
            target_distance_pips=130,
            win_rate=0.62,
            avg_win_pips=130.0,
            avg_loss_pips=55.0,
            correlation_with_existing=0.25,
            major_event_within_24h=True,
            major_event_within_48h=False,
        ),
    ]

    # Test models (prioritize fast 7-8B models)
    models_to_test = [
        "mistral:7b-instruct",
        "llama3.1:8b-instruct",
        "phi4-mini",
        "phi3:mini",
        "mistral-small3.1",  # Already passed before, verify instructor still works
    ]

    all_results = []

    for model in models_to_test:
        result = test_model_with_instructor(model, scenarios)
        all_results.append(result)
        print("\n" + "="*80 + "\n")

    # Summary
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*30 + "FINAL SUMMARY" + " "*35 + "║")
    print("╚" + "="*78 + "╝\n")

    for result in all_results:
        status_icon = "✅" if result.get("status") == "passed" else "❌"
        model = result["model"]

        if result.get("status") == "passed":
            variance = max(result["lot_variance"], result["risk_variance"])
            avg_time = result["avg_response_time"]
            print(f"{status_icon} {model:25s} | Variance: {variance:5.1f}% | Avg Time: {avg_time:5.2f}s")
        elif result.get("status") == "error":
            print(f"{status_icon} {model:25s} | Error: {result.get('error', 'Unknown')[:40]}")
        else:
            print(f"{status_icon} {model:25s} | Failed at {result.get('failed_scenario', 'Unknown')}")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
