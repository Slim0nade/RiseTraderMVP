#!/usr/bin/env python3
"""
User Story 1 (SC-001) Validation Test

Tests adaptive position sizing with local models (mistral:7b-instruct).
Success Criteria:
- Position size variance ≥ 50% across 4 scenarios
- JSON schema compliance: 100%
- Response time: < 10s per decision
- Mathematical correctness: Kelly Criterion applied
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any, List
from datetime import datetime
from uuid import uuid4

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.agents.decision.position_sizing_agent import PositionSizingAgent, PositionSizeDecision
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier


class TestResults:
    """Track test results"""
    def __init__(self):
        self.scenarios: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.start_time = time.time()

    def add_result(self, scenario_name: str, result: Dict[str, Any], passed: bool):
        self.scenarios.append({
            "name": scenario_name,
            "result": result,
            "passed": passed,
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def calculate_variance(self) -> Dict[str, float]:
        """Calculate variance metrics"""
        lot_sizes = [s["result"]["lot_quantity"] for s in self.scenarios if "lot_quantity" in s["result"]]
        risk_pcts = [s["result"]["dynamic_risk_percentage"] for s in self.scenarios if "dynamic_risk_percentage" in s["result"]]

        if not lot_sizes or not risk_pcts:
            return {"lot_variance": 0.0, "risk_variance": 0.0}

        # Calculate variance as (max - min) / min * 100%
        lot_min, lot_max = min(lot_sizes), max(lot_sizes)
        risk_min, risk_max = min(risk_pcts), max(risk_pcts)

        lot_variance = ((lot_max - lot_min) / lot_min * 100) if lot_min > 0 else 0.0
        risk_variance = ((risk_max - risk_min) / risk_min * 100) if risk_min > 0 else 0.0

        return {
            "lot_variance": lot_variance,
            "risk_variance": risk_variance,
            "lot_min": lot_min,
            "lot_max": lot_max,
            "risk_min": risk_min,
            "risk_max": risk_max,
        }

    def print_summary(self):
        """Print test summary"""
        duration = time.time() - self.start_time
        variance = self.calculate_variance()

        print("\n" + "="*80)
        print("USER STORY 1 (SC-001) TEST RESULTS")
        print("="*80)

        print(f"\n📊 Test Summary:")
        print(f"   Total Scenarios: {len(self.scenarios)}")
        print(f"   Passed: {self.passed} ✅")
        print(f"   Failed: {self.failed} ❌")
        print(f"   Duration: {duration:.2f}s")

        print(f"\n📈 Position Sizing Results:")
        for i, scenario in enumerate(self.scenarios, 1):
            result = scenario["result"]
            print(f"\n   Scenario {i}: {scenario['name']}")
            if "lot_quantity" in result:
                print(f"      Lot Size: {result['lot_quantity']:.2f} lots")
                print(f"      Risk %: {result['dynamic_risk_percentage']:.2f}%")
                print(f"      Kelly Fraction: {result['kelly_fraction_applied']:.3f}")
                print(f"      Confidence: {result['confidence']:.2f}")
            else:
                print(f"      ❌ ERROR: {result.get('error', 'Unknown error')}")

        print(f"\n🎯 Success Criteria Validation:")
        print(f"   Lot Size Variance: {variance['lot_variance']:.1f}% (target: ≥50%)")
        if variance['lot_variance'] >= 50:
            print(f"      ✅ PASSED (exceeds 50% requirement)")
        else:
            print(f"      ❌ FAILED (below 50% requirement)")

        print(f"   Risk % Variance: {variance['risk_variance']:.1f}% (target: ≥50%)")
        if variance['risk_variance'] >= 50:
            print(f"      ✅ PASSED (exceeds 50% requirement)")
        else:
            print(f"      ❌ FAILED (below 50% requirement)")

        print(f"\n   Range: {variance['lot_min']:.2f} - {variance['lot_max']:.2f} lots")
        print(f"   Risk Range: {variance['risk_min']:.2f}% - {variance['risk_max']:.2f}%")

        avg_time = duration / len(self.scenarios) if self.scenarios else 0
        print(f"\n   Avg Response Time: {avg_time:.2f}s (target: <10s)")
        if avg_time < 10:
            print(f"      ✅ PASSED")
        else:
            print(f"      ❌ FAILED")

        overall_pass = (
            self.failed == 0 and
            variance['lot_variance'] >= 50 and
            avg_time < 10
        )

        print("\n" + "="*80)
        if overall_pass:
            print("✅ USER STORY 1 (SC-001): PASSED")
        else:
            print("❌ USER STORY 1 (SC-001): FAILED")
        print("="*80 + "\n")

        return overall_pass


async def test_position_sizing_variance():
    """
    Test position sizing variance across 4 different market scenarios.

    Success Criteria:
    - Variance ≥ 50% between smallest and largest position sizes
    - All decisions return valid JSON matching PositionSizeDecision schema
    - Average response time < 10s
    """

    print("🧪 Testing User Story 1 (SC-001): Adaptive Position Sizing")
    print("Using local model: mistral:7b-instruct with Instructor\n")

    # Set environment variable to use Ollama with Instructor
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "mistral:7b-instruct"
    os.environ["USE_INSTRUCTOR"] = "true"

    # Test scenarios
    scenarios = [
        {
            "name": "Scenario 1: Favorable Conditions",
            "task": """Calculate position size for Gold with these conditions:
- Account Balance: $10,000
- Current Drawdown: 0% (peak balance)
- Win Rate: 65%
- Risk/Reward Ratio: 2.5:1
- Kelly Fraction: 0.250
- Stop Loss Distance: 50 pips
- Pip Value: $10/lot
- Market Regime: TRENDING_UP (stable uptrend)
- Trade Conviction: 0.85 (high confidence)
- Correlation with Existing Positions: 0.0 (no other positions)
- Event Risk: None (no high-impact events scheduled)

Expected: HIGH position size due to favorable conditions.""",
        },
        {
            "name": "Scenario 2: Adverse Conditions",
            "task": """Calculate position size for Gold with these conditions:
- Account Balance: $10,000
- Current Drawdown: -12% (near risk limit)
- Win Rate: 45%
- Risk/Reward Ratio: 1.5:1
- Kelly Fraction: 0.034
- Stop Loss Distance: 80 pips
- Pip Value: $10/lot
- Market Regime: VOLATILE (choppy, uncertain)
- Trade Conviction: 0.40 (low confidence)
- Correlation with Existing Positions: 0.0
- Event Risk: None

Expected: LOW position size due to adverse conditions.""",
        },
        {
            "name": "Scenario 3: High Correlation Risk",
            "task": """Calculate position size for Gold with these conditions:
- Account Balance: $10,000
- Current Drawdown: -5%
- Win Rate: 58%
- Risk/Reward Ratio: 2.0:1
- Kelly Fraction: 0.092
- Stop Loss Distance: 60 pips
- Pip Value: $10/lot
- Market Regime: RANGING (sideways)
- Trade Conviction: 0.60 (moderate)
- Correlation with Existing Positions: 0.75 (high correlation - already long Silver and Oil)
- Event Risk: None

Expected: REDUCED position size due to correlation risk.""",
        },
        {
            "name": "Scenario 4: High Event Risk",
            "task": """Calculate position size for Gold with these conditions:
- Account Balance: $10,000
- Current Drawdown: -3%
- Win Rate: 60%
- Risk/Reward Ratio: 2.2:1
- Kelly Fraction: 0.115
- Stop Loss Distance: 55 pips
- Pip Value: $10/lot
- Market Regime: TRENDING_UP
- Trade Conviction: 0.70
- Correlation with Existing Positions: 0.20 (low)
- Event Risk: HIGH (FOMC meeting in 4 hours, NFP tomorrow)

Expected: REDUCED position size due to event risk.""",
        },
    ]

    results = TestResults()

    # Create agent (no database session needed for standalone test)
    config = AgentConfig(
        name="TestPositionSizing",
        agent_type=AgentType.POSITION_SIZING,
        layer=AgentLayer.DECISION,
        llm_provider="ollama",
        llm_model="mistral:7b-instruct",
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.0,
        max_tokens=1000,
        config_overrides={
            "ollama_host": os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434"),
            "use_instructor": True,
        },
    )

    agent = PositionSizingAgent(
        agent_id=uuid4(),  # Use UUID for agent_id
        config=config,
        session=None,  # No DB session for test
        tools=[],
    )

    # Run each scenario
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📝 Running {scenario['name']}...")
        start_time = time.time()

        try:
            result = await agent.run(
                task=scenario["task"],
                context={},
            )

            duration = time.time() - start_time

            # Validate result schema
            try:
                decision = PositionSizeDecision(**result)
                print(f"   ✅ Valid JSON schema")
                print(f"   Lot Size: {decision.lot_quantity:.2f} lots")
                print(f"   Risk: {decision.dynamic_risk_percentage:.2f}%")
                print(f"   Kelly: {decision.kelly_fraction_applied:.3f}")
                print(f"   Time: {duration:.2f}s")

                results.add_result(scenario["name"], result, True)

            except Exception as e:
                print(f"   ❌ Invalid schema: {str(e)}")
                results.add_result(scenario["name"], {"error": f"Schema validation failed: {str(e)}"}, False)

        except Exception as e:
            print(f"   ❌ Execution failed: {str(e)}")
            results.add_result(scenario["name"], {"error": str(e)}, False)

    # Print summary
    overall_pass = results.print_summary()

    return 0 if overall_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_position_sizing_variance())
    sys.exit(exit_code)
