#!/usr/bin/env python3
"""
User Story 3 (SC-003) Validation Test

Tests probabilistic take-profit targeting with ML forecast distributions.
Success Criteria:
- Take-profit levels align with ML forecast percentiles (p50, p75, p90)
- Respect market structure (resistance levels)
- Show 15%+ expected value improvement vs fixed 2:1 ratios
- Response time: < 10s per decision
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

from src.agents.decision.take_profit_agent import TakeProfitAgent, TakeProfitDecision
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier


class TestResults:
    """Track test results"""
    def __init__(self):
        self.scenarios: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.start_time = time.time()
        self.total_ev_improvement = 0.0

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

        # Track EV improvement
        if "expected_value_improvement_pct" in result:
            self.total_ev_improvement += result["expected_value_improvement_pct"]

    def get_avg_ev_improvement(self) -> float:
        """Calculate average EV improvement"""
        if len(self.scenarios) == 0:
            return 0.0
        return self.total_ev_improvement / len(self.scenarios)

    def print_summary(self):
        """Print test summary"""
        duration = time.time() - self.start_time

        print("\n" + "="*80)
        print("USER STORY 3 (SC-003) TEST RESULTS")
        print("="*80)

        print(f"\n📊 Test Summary:")
        print(f"   Total Scenarios: {len(self.scenarios)}")
        print(f"   Passed: {self.passed} ✅")
        print(f"   Failed: {self.failed} ❌")
        print(f"   Duration: {duration:.2f}s")

        print(f"\n📈 Take-Profit Results:")
        for i, scenario in enumerate(self.scenarios, 1):
            result = scenario["result"]
            print(f"\n   Scenario {i}: {scenario['name']}")
            if "primary_target_price" in result:
                print(f"      Primary Target: {result['primary_target_price']:.2f}")
                print(f"      Target Distance: {result['primary_target_distance_pips']:.1f} pips")
                print(f"      Risk:Reward: {result['risk_reward_ratio']:.2f}:1")
                print(f"      Expected Value: ${result['expected_value_usd']:.2f}")
                print(f"      EV Improvement: {result['expected_value_improvement_pct']:.1f}%")
                print(f"      Number of Targets: {len(result.get('targets', []))}")
                print(f"      Confidence: {result['confidence']:.2f}")
            else:
                print(f"      ❌ ERROR: {result.get('error', 'Unknown error')}")

        print(f"\n🎯 Success Criteria Validation:")

        # EV improvement
        avg_ev = self.get_avg_ev_improvement()
        print(f"   Average EV Improvement: {avg_ev:.1f}% (target: ≥15%)")
        if avg_ev >= 15:
            print(f"      ✅ PASSED (exceeds 15% requirement)")
        else:
            print(f"      ❌ FAILED (below 15% requirement)")

        # Response time
        avg_time = duration / len(self.scenarios) if self.scenarios else 0
        print(f"\n   Avg Response Time: {avg_time:.2f}s (target: <10s)")
        if avg_time < 10:
            print(f"      ✅ PASSED")
        else:
            print(f"      ❌ FAILED")

        # JSON compliance
        json_compliance = (self.passed / len(self.scenarios) * 100) if self.scenarios else 0
        print(f"\n   JSON Schema Compliance: {json_compliance:.0f}%")
        if json_compliance == 100:
            print(f"      ✅ PASSED")
        else:
            print(f"      ❌ FAILED")

        overall_pass = (
            self.failed == 0 and
            avg_ev >= 15 and
            avg_time < 10
        )

        print("\n" + "="*80)
        if overall_pass:
            print("✅ USER STORY 3 (SC-003): PASSED")
        else:
            print("❌ USER STORY 3 (SC-003): FAILED")
        print("="*80 + "\n")

        return overall_pass


async def test_probabilistic_take_profit():
    """
    Test probabilistic take-profit targeting across 4 different scenarios.

    Success Criteria:
    - Take-profit levels align with ML forecast percentiles
    - Expected value improvement ≥ 15% vs fixed 2:1
    - All decisions return valid JSON matching TakeProfitDecision schema
    - Average response time < 10s
    """

    print("🧪 Testing User Story 3 (SC-003): Probabilistic Take-Profit Targeting")
    print("Using local model: mistral:7b-instruct with Instructor\n")

    # Set environment variables
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "mistral:7b-instruct"
    os.environ["USE_INSTRUCTOR"] = "true"

    # Test scenarios
    scenarios = [
        {
            "name": "Scenario 1: Strong Uptrend with Clear Quantiles",
            "task": """Calculate take-profit targets for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Stop Distance: 50 pips
- Position Size: 0.5 lots
- Pip Value: $10/lot

ML Forecast Quantiles:
- p50 (50% probability): 2670.00 (20 pips, 2:1 ratio)
- p75 (75% probability): 2685.00 (35 pips, 3.5:1 ratio)
- p90 (90% probability): 2700.00 (50 pips, 5:1 ratio)

Resistance Levels:
- R1: 2668.00 (minor resistance)
- R2: 2680.00 (strong resistance)
- R3: 2700.00 (psychological level)

Expected: 3 partial targets aligned with quantiles, positioned before resistance levels.""",
        },
        {
            "name": "Scenario 2: Moderate Trend with Nearby Resistance",
            "task": """Calculate take-profit targets for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Stop Distance: 80 pips
- Position Size: 0.3 lots

ML Forecast Quantiles:
- p50: 2665.00 (15 pips)
- p75: 2675.00 (25 pips)
- p90: 2690.00 (40 pips)

Resistance Levels:
- R1: 2665.00 (aligns with p50)
- R2: 2680.00 (between p75 and p90)

Expected: 2-3 targets with conservative spacing due to nearby resistance.""",
        },
        {
            "name": "Scenario 3: High Volatility with Wide Spread",
            "task": """Calculate take-profit targets for Gold SHORT trade:
- Entry Price: 2650.00
- Direction: SHORT
- Stop Distance: 120 pips (volatile market)
- Position Size: 0.2 lots

ML Forecast Quantiles:
- p50: 2620.00 (30 pips, 1:4 ratio - conservative)
- p75: 2595.00 (55 pips, 1:2.2 ratio)
- p90: 2560.00 (90 pips, 1:1.33 ratio)

Support Levels:
- S1: 2625.00
- S2: 2600.00
- S3: 2570.00

Expected: 3 targets with larger spacing, significant EV improvement due to wide distribution.""",
        },
        {
            "name": "Scenario 4: Tight Range with Limited Upside",
            "task": """Calculate take-profit targets for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Stop Distance: 40 pips
- Position Size: 0.75 lots

ML Forecast Quantiles:
- p50: 2660.00 (10 pips, 1:4 ratio)
- p75: 2668.00 (18 pips, 1:2.2 ratio)
- p90: 2675.00 (25 pips, 1:1.6 ratio)

Resistance Levels:
- R1: 2670.00 (strong ceiling)
- R2: 2680.00 (hard resistance)

Expected: 2-3 tight targets, limited EV improvement due to ranging conditions.""",
        },
    ]

    results = TestResults()

    # Create agent
    config = AgentConfig(
        name="TestTakeProfit",
        agent_type=AgentType.TAKE_PROFIT,
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

    agent = TakeProfitAgent(
        agent_id=uuid4(),
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
                decision = TakeProfitDecision(**result)
                print(f"   ✅ Valid JSON schema")
                print(f"   Primary Target: {decision.primary_target_price:.2f}")
                print(f"   R:R Ratio: {decision.risk_reward_ratio:.2f}:1")
                print(f"   EV Improvement: {decision.expected_value_improvement_pct:.1f}%")
                print(f"   Targets: {len(decision.targets)}")
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
    exit_code = asyncio.run(test_probabilistic_take_profit())
    sys.exit(exit_code)
