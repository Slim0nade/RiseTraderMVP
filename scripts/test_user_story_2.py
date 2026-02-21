#!/usr/bin/env python3
"""
User Story 2 (SC-002) Validation Test

Tests intelligent stop-loss placement with structure-based methodology.
Success Criteria:
- 70%+ stops positioned relative to market structure (not just ATR distance)
- Structure-based reasoning documented
- Response time: < 10s per decision
- JSON schema compliance: 100%
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

from src.agents.decision.stop_loss_agent import StopLossAgent, StopLossDecision, StopPlacementType
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier


class TestResults:
    """Track test results"""
    def __init__(self):
        self.scenarios: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.start_time = time.time()
        self.structure_based_count = 0
        self.total_scenarios = 0

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

        # Track structure-based percentage
        self.total_scenarios += 1
        if result.get("placement_type") in ["structure", "hybrid"]:
            self.structure_based_count += 1

    def get_structure_percentage(self) -> float:
        """Calculate percentage of structure-based stops"""
        if self.total_scenarios == 0:
            return 0.0
        return (self.structure_based_count / self.total_scenarios) * 100

    def print_summary(self):
        """Print test summary"""
        duration = time.time() - self.start_time

        print("\n" + "="*80)
        print("USER STORY 2 (SC-002) TEST RESULTS")
        print("="*80)

        print(f"\n📊 Test Summary:")
        print(f"   Total Scenarios: {len(self.scenarios)}")
        print(f"   Passed: {self.passed} ✅")
        print(f"   Failed: {self.failed} ❌")
        print(f"   Duration: {duration:.2f}s")

        print(f"\n📈 Stop Placement Results:")
        for i, scenario in enumerate(self.scenarios, 1):
            result = scenario["result"]
            print(f"\n   Scenario {i}: {scenario['name']}")
            if "stop_price" in result:
                print(f"      Stop Price: {result['stop_price']:.2f}")
                print(f"      Stop Distance: {result['stop_distance_pips']:.1f} pips")
                print(f"      Placement Type: {result['placement_type']}")
                print(f"      ATR Multiplier: {result['atr_multiplier']:.2f}x")
                print(f"      Structure Level: {result.get('structure_level', 'N/A')}")
                print(f"      Structure Type: {result.get('structure_type', 'N/A')}")
                print(f"      Confidence: {result['confidence']:.2f}")
            else:
                print(f"      ❌ ERROR: {result.get('error', 'Unknown error')}")

        print(f"\n🎯 Success Criteria Validation:")

        # Structure-based percentage
        structure_pct = self.get_structure_percentage()
        print(f"   Structure-Based Stops: {structure_pct:.1f}% (target: ≥70%)")
        if structure_pct >= 70:
            print(f"      ✅ PASSED (exceeds 70% requirement)")
        else:
            print(f"      ❌ FAILED (below 70% requirement)")

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
            structure_pct >= 70 and
            avg_time < 10
        )

        print("\n" + "="*80)
        if overall_pass:
            print("✅ USER STORY 2 (SC-002): PASSED")
        else:
            print("❌ USER STORY 2 (SC-002): FAILED")
        print("="*80 + "\n")

        return overall_pass


async def test_stop_loss_structure_intelligence():
    """
    Test stop-loss structure intelligence across 4 different market scenarios.

    Success Criteria:
    - 70%+ stops positioned relative to market structure
    - All decisions return valid JSON matching StopLossDecision schema
    - Average response time < 10s
    """

    print("🧪 Testing User Story 2 (SC-002): Intelligent Stop-Loss Placement")
    print("Using local model: mistral:7b-instruct with Instructor\n")

    # Set environment variable to use Ollama with Instructor
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "mistral:7b-instruct"
    os.environ["USE_INSTRUCTOR"] = "true"

    # Test scenarios
    scenarios = [
        {
            "name": "Scenario 1: Long with Clear Swing Low",
            "task": """Calculate stop-loss for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Current ATR: 80 pips
- Position Size: 0.5 lots
- Account Balance: $10,000
- Max Risk: 2.0%

Market Structure:
- Recent Swing Low: 2635.00 (15 pips below entry)
- Support Level: 2630.00 (20 pips below entry)
- Nearest Liquidity Cluster: 2640.00 (round number)
- Regime: TRENDING_UP
- Volatility: MEDIUM

Expected: Structure-based stop below swing low (2630-2635), avoiding liquidity cluster at 2640.""",
        },
        {
            "name": "Scenario 2: Short in Volatile Market",
            "task": """Calculate stop-loss for Gold SHORT trade:
- Entry Price: 2650.00
- Direction: SHORT
- Current ATR: 120 pips (high volatility)
- Position Size: 0.3 lots
- Account Balance: $10,000
- Max Risk: 1.5%

Market Structure:
- Recent Swing High: 2668.00 (18 pips above entry)
- Resistance Level: 2670.00 (20 pips above entry)
- Nearest Liquidity Cluster: 2675.00
- Regime: VOLATILE
- Volatility: HIGH

Expected: Wider stop with 3.0x ATR multiplier due to volatile regime, positioned above resistance.""",
        },
        {
            "name": "Scenario 3: Long in Ranging Market (Pure ATR)",
            "task": """Calculate stop-loss for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Current ATR: 60 pips
- Position Size: 0.75 lots
- Account Balance: $10,000
- Max Risk: 2.0%

Market Structure:
- No Clear Swing Lows (ranging market)
- Support Levels: Far away (2580.00)
- No Nearby Liquidity Clusters
- Regime: RANGING
- Volatility: LOW

Expected: Pure ATR-based stop (1.5x-2.0x multiplier) since no clear structure.""",
        },
        {
            "name": "Scenario 4: Hybrid Stop (Structure + ATR Buffer)",
            "task": """Calculate stop-loss for Gold LONG trade:
- Entry Price: 2650.00
- Direction: LONG
- Current ATR: 90 pips
- Position Size: 0.6 lots
- Account Balance: $10,000
- Max Risk: 2.0%

Market Structure:
- Swing Low: 2640.00 (10 pips below entry, very close)
- Support Level: 2625.00 (25 pips below entry)
- Liquidity Cluster: 2635.00 (avoid)
- Regime: TRENDING_UP
- Volatility: MEDIUM
- ML Forecast Std Dev: 45 pips

Expected: Hybrid placement - position below swing low with ATR buffer, offset from liquidity cluster.""",
        },
    ]

    results = TestResults()

    # Create agent (no database session needed for standalone test)
    config = AgentConfig(
        name="TestStopLoss",
        agent_type=AgentType.STOP_LOSS,
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

    agent = StopLossAgent(
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
                decision = StopLossDecision(**result)
                print(f"   ✅ Valid JSON schema")
                print(f"   Stop Price: {decision.stop_price:.2f}")
                print(f"   Distance: {decision.stop_distance_pips:.1f} pips")
                print(f"   Type: {decision.placement_type}")
                print(f"   ATR Multiplier: {decision.atr_multiplier:.2f}x")
                print(f"   Structure: {decision.structure_type or 'N/A'}")
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
    exit_code = asyncio.run(test_stop_loss_structure_intelligence())
    sys.exit(exit_code)
