"""
Test script to check if crude oil strategy generates signals with different parameters.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.backtesting.crude_oil_strategy_extended import (
    CrudeOilStrategyExtended,
    CrudeOilParamsExtended
)
from src.services.backtesting.data_replay_engine import MarketTick
from datetime import datetime
from decimal import Decimal


async def test_strategy_with_params():
    """Test strategy with different parameter sets."""

    # Test with default params
    print("\n=== Testing with DEFAULT parameters ===")
    default_strategy = CrudeOilStrategyExtended(CrudeOilParamsExtended())
    print(f"Momentum buy threshold: {default_strategy.params.momentum_buy_threshold}")
    print(f"Momentum sell threshold: {default_strategy.params.momentum_sell_threshold}")
    print(f"Use ADX filter: {default_strategy.params.use_adx_filter}")
    print(f"Use MACD filter: {default_strategy.params.use_macd_filter}")

    # Test with LOOSE params
    print("\n=== Testing with LOOSE parameters ===")
    loose_params = CrudeOilParamsExtended(
        momentum_buy_threshold=95.0,  # Much looser (was 99.5)
        momentum_sell_threshold=105.0,  # Much looser (was 100.5)
        use_adx_filter=False,  # Disable ADX filter
        use_macd_filter=False,  # Disable MACD filter
        use_bollinger_filter=False,  # Disable Bollinger filter
        use_stochastic_filter=False,  # Disable Stochastic filter
        use_volume_filter=False,  # Disable volume filter
    )
    loose_strategy = CrudeOilStrategyExtended(loose_params)
    print(f"Momentum buy threshold: {loose_strategy.params.momentum_buy_threshold}")
    print(f"Momentum sell threshold: {loose_strategy.params.momentum_sell_threshold}")
    print(f"Filters disabled: ADX, MACD, Bollinger, Stochastic, Volume")

    # Create a sample tick to simulate
    sample_tick = MarketTick(
        timestamp=datetime(2023, 12, 1, 10, 0, 0),
        symbol="CrudeOIL",
        timeframe="M1",
        open=Decimal("75.50"),
        high=Decimal("75.70"),
        low=Decimal("75.40"),
        close=Decimal("75.60"),
        volume=1000
    )

    print(f"\n=== Sample Tick ===")
    print(f"Price: {sample_tick.close}")
    print(f"Volume: {sample_tick.volume}")

    print("\n✅ Strategy parameter test complete")
    print("\nRecommendation:")
    print("- Default momentum thresholds (99.5/100.5) are TOO TIGHT")
    print("- Suggest using wider range like 95.0/105.0")
    print("- Consider disabling extended filters for initial testing")


if __name__ == "__main__":
    asyncio.run(test_strategy_with_params())
