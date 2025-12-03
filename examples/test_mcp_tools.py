#!/usr/bin/env python3
"""
Test MCP Tools Implementation.

Quick test script to verify MCP tools are working correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ml.tools.forecasting_tools import get_tcn_forecast, get_tft_prediction, get_fedformer_regime
from src.ml.tools.calculation_tools import calculate_kelly, calculate_atr
from src.ml.tools.market_structure_tools import get_support_resistance, detect_liquidity_clusters
from src.ml.tools.data_retrieval_tools import get_economic_events, get_cot_data


async def test_forecasting_tools():
    """Test forecasting MCP tools."""
    print("\n" + "="*70)
    print("Testing Forecasting Tools")
    print("="*70)

    # Test TCN forecast
    print("\n1. Testing get_tcn_forecast...")
    tcn_result = await get_tcn_forecast("CrudeOIL", "4h")
    print(f"   ✓ Symbol: {tcn_result['symbol']}")
    print(f"   ✓ Predictions: {tcn_result['predictions']}")
    print(f"   ✓ Direction Prob: {tcn_result['direction_prob']}")
    print(f"   ✓ Inference Time: {tcn_result['inference_time_ms']:.2f}ms")

    # Test TFT prediction
    print("\n2. Testing get_tft_prediction...")
    tft_result = await get_tft_prediction("Gold", "4h")
    print(f"   ✓ Symbol: {tft_result['symbol']}")
    print(f"   ✓ Quantiles: p10={tft_result['quantiles']['p10'][0]:.2f}, p50={tft_result['quantiles']['p50'][0]:.2f}, p90={tft_result['quantiles']['p90'][0]:.2f}")
    print(f"   ✓ Inference Time: {tft_result['inference_time_ms']:.2f}ms")

    # Test FEDformer regime
    print("\n3. Testing get_fedformer_regime...")
    regime_result = await get_fedformer_regime("CrudeOIL")
    print(f"   ✓ Symbol: {regime_result['symbol']}")
    print(f"   ✓ Regime: {regime_result['regime']}")
    print(f"   ✓ Confidence: {regime_result['regime_confidence']:.2f}")
    print(f"   ✓ Volatility Percentile: {regime_result['volatility_percentile']:.1f}")


async def test_calculation_tools():
    """Test calculation MCP tools."""
    print("\n" + "="*70)
    print("Testing Calculation Tools")
    print("="*70)

    # Test Kelly criterion
    print("\n1. Testing calculate_kelly...")
    kelly_result = await calculate_kelly(
        win_probability=0.55,
        win_loss_ratio=1.8,
        bankroll=40000.0,
        max_kelly_fraction=0.25,
    )
    print(f"   ✓ Kelly Fraction: {kelly_result['kelly_fraction']:.3f}")
    print(f"   ✓ Capped Kelly: {kelly_result['capped_kelly_fraction']:.3f}")
    print(f"   ✓ Recommended Position: ${kelly_result['recommended_position_size']:,.2f}")
    print(f"   ✓ Expected Growth Rate: {kelly_result['expected_growth_rate']:.4f}")

    # Test ATR
    print("\n2. Testing calculate_atr...")
    atr_result = await calculate_atr("CrudeOIL", 14, "4h")
    print(f"   ✓ Symbol: {atr_result['symbol']}")
    print(f"   ✓ ATR Value: {atr_result['atr_value']:.2f}")
    print(f"   ✓ ATR Percentage: {atr_result['atr_percentage']:.2f}%")
    print(f"   ✓ Current Price: ${atr_result['current_price']:.2f}")


async def test_market_structure_tools():
    """Test market structure MCP tools."""
    print("\n" + "="*70)
    print("Testing Market Structure Tools")
    print("="*70)

    # Test support/resistance
    print("\n1. Testing get_support_resistance...")
    sr_result = await get_support_resistance("CrudeOIL", 100, "4h")
    print(f"   ✓ Symbol: {sr_result['symbol']}")
    print(f"   ✓ Current Price: ${sr_result['current_price']:.2f}")
    print(f"   ✓ Nearest Support: ${sr_result['nearest_support']:.2f}")
    print(f"   ✓ Nearest Resistance: ${sr_result['nearest_resistance']:.2f}")
    print(f"   ✓ Support Levels: {len(sr_result['support_levels'])}")
    print(f"   ✓ Resistance Levels: {len(sr_result['resistance_levels'])}")

    # Test liquidity clusters
    print("\n2. Testing detect_liquidity_clusters...")
    liq_result = await detect_liquidity_clusters("Gold", 100, 0.6)
    print(f"   ✓ Symbol: {liq_result['symbol']}")
    print(f"   ✓ Clusters Found: {len(liq_result['clusters'])}")
    if liq_result['clusters']:
        cluster = liq_result['clusters'][0]
        print(f"   ✓ Top Cluster: ${cluster['price_level']:.2f} ({cluster['side']}, strength={cluster['cluster_strength']:.2f})")


async def test_data_retrieval_tools():
    """Test data retrieval MCP tools."""
    print("\n" + "="*70)
    print("Testing Data Retrieval Tools")
    print("="*70)

    # Test economic events
    print("\n1. Testing get_economic_events...")
    events_result = await get_economic_events("CrudeOIL", 48, "HIGH")
    print(f"   ✓ Symbol: {events_result['symbol']}")
    print(f"   ✓ Events Found: {len(events_result['events'])}")
    if events_result['events']:
        event = events_result['events'][0]
        print(f"   ✓ Next Event: {event['event_name']} ({event['impact']})")

    # Test COT data
    print("\n2. Testing get_cot_data...")
    cot_result = await get_cot_data("CrudeOIL", 4)
    print(f"   ✓ Symbol: {cot_result['symbol']}")
    print(f"   ✓ Latest Report: {cot_result['latest_report_date']}")
    print(f"   ✓ Commercial Net: {cot_result['commercial_positioning']['net_position']:,} contracts")
    print(f"   ✓ Sentiment Signal: {cot_result['sentiment_signal']}")


async def main():
    """Run all MCP tool tests."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║           MCP Tools Integration Test                           ║
║          Feature 005 - Phase 2 Implementation                  ║
╚════════════════════════════════════════════════════════════════╝
""")

    try:
        await test_forecasting_tools()
        await test_calculation_tools()
        await test_market_structure_tools()
        await test_data_retrieval_tools()

        print("\n" + "="*70)
        print("✅ ALL MCP TOOLS TESTS PASSED")
        print("="*70)
        print("\nNote: Tools currently return mock data when external APIs unavailable.")
        print("This is expected behavior with graceful fallback strategy.")
        print("\nNext Steps:")
        print("  1. Start ML Forecasting API (Feature 003) for real forecasts")
        print("  2. Configure economic calendar API for real event data")
        print("  3. Configure COT data API for real sentiment data")
        print("  4. Test tools with agents via API endpoints")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
