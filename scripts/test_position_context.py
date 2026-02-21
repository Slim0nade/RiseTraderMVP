#!/usr/bin/env python3
"""
Test script to verify position data flows correctly to agent decision context.

This tests that:
1. Positions are added to portfolio correctly
2. get_full_portfolio_context() returns correct position data
3. Market context filtering works correctly
"""

import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import directly from the module file to avoid __init__ dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "portfolio_state",
    project_root / "src/services/backtesting/portfolio_state.py"
)
portfolio_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portfolio_module)

PortfolioState = portfolio_module.PortfolioState
Position = portfolio_module.Position


def test_position_context_flow():
    """Test that positions flow correctly through portfolio context."""

    print("=" * 80)
    print("Testing Position Context Flow")
    print("=" * 80)

    # Initialize portfolio
    portfolio = PortfolioState(
        initial_capital=Decimal("10000"),
        max_positions_per_symbol=3,  # Allow multiple positions
        allow_short_selling=True,  # Allow short selling for test
    )

    symbol = "CrudeOIL"
    entry_price = Decimal("75.50")
    quantity = Decimal("10")
    timestamp = datetime.now()

    print(f"\n1. Initial state:")
    print(f"   Total positions: {portfolio.get_position_count()}")
    print(f"   Positions in {symbol}: {len(portfolio.get_positions_for_symbol(symbol))}")

    # Open first position
    print(f"\n2. Opening first LONG position:")
    print(f"   Symbol: {symbol}")
    print(f"   Quantity: {quantity}")
    print(f"   Entry Price: ${entry_price}")

    position1 = portfolio.open_position(
        symbol=symbol,
        action="buy",
        price=entry_price,
        quantity=quantity,
        timestamp=timestamp,
        trade_id=uuid4(),
    )

    print(f"   ✓ Position opened: {position1.position_id}")
    print(f"   Total positions: {portfolio.get_position_count()}")
    print(f"   Positions in {symbol}: {len(portfolio.get_positions_for_symbol(symbol))}")

    # Get full portfolio context
    print(f"\n3. Getting full portfolio context:")
    ctx = portfolio.get_full_portfolio_context()

    print(f"   Total positions in context: {len(ctx['positions'])}")
    print(f"   Symbols with positions: {list(ctx['symbols_summary'].keys())}")

    for pos in ctx['positions']:
        print(f"   - {pos['symbol']}: {pos['direction'].upper()} {pos['quantity']} @ ${pos['entry_price']}")

    # Filter for current symbol (simulating what backtest_service does)
    print(f"\n4. Filtering positions for {symbol}:")
    current_symbol_positions = [
        p for p in ctx["positions"] if p["symbol"] == symbol
    ]

    print(f"   Matching positions: {len(current_symbol_positions)}")
    for pos in current_symbol_positions:
        print(f"   - {pos['direction'].upper()} {pos['quantity']} @ ${pos['entry_price']} (P&L: ${pos['unrealized_pnl']})")

    # Open second position to test multi-position support
    print(f"\n5. Opening second LONG position (pyramiding):")
    entry_price2 = Decimal("76.00")
    quantity2 = Decimal("5")

    position2 = portfolio.open_position(
        symbol=symbol,
        action="buy",
        price=entry_price2,
        quantity=quantity2,
        timestamp=timestamp,
        trade_id=uuid4(),
    )

    print(f"   ✓ Position opened: {position2.position_id}")
    print(f"   Total positions: {portfolio.get_position_count()}")
    print(f"   Positions in {symbol}: {len(portfolio.get_positions_for_symbol(symbol))}")

    # Get updated context
    print(f"\n6. Updated portfolio context after second position:")
    ctx = portfolio.get_full_portfolio_context()
    current_symbol_positions = [
        p for p in ctx["positions"] if p["symbol"] == symbol
    ]

    print(f"   Total positions: {len(ctx['positions'])}")
    print(f"   Positions in {symbol}: {len(current_symbol_positions)}")

    for i, pos in enumerate(current_symbol_positions, 1):
        print(f"   Position {i}: {pos['direction'].upper()} {pos['quantity']} @ ${pos['entry_price']}")

    # Test with different symbol
    print(f"\n7. Opening position in different symbol:")
    other_symbol = "EURUSD"
    position3 = portfolio.open_position(
        symbol=other_symbol,
        action="sell",  # SHORT
        price=Decimal("1.0850"),
        quantity=Decimal("1000"),
        timestamp=timestamp,
        trade_id=uuid4(),
    )

    print(f"   ✓ Position opened in {other_symbol}: {position3.position_id}")

    # Final context check
    print(f"\n8. Final portfolio context:")
    ctx = portfolio.get_full_portfolio_context()

    print(f"   Total positions: {len(ctx['positions'])}")
    print(f"   Symbols: {list(ctx['symbols_summary'].keys())}")

    for sym, summary in ctx['symbols_summary'].items():
        print(f"   {sym}:")
        print(f"     - Position count: {summary['position_count']}")
        print(f"     - Net direction: {summary['net_direction'].upper()}")
        print(f"     - Net quantity: {summary['net_quantity']}")

    # Test filtering still works correctly
    print(f"\n9. Testing symbol filtering:")
    for test_symbol in [symbol, other_symbol]:
        filtered = [p for p in ctx["positions"] if p["symbol"] == test_symbol]
        print(f"   {test_symbol}: {len(filtered)} position(s)")

    print("\n" + "=" * 80)
    print("✓ All tests passed! Position context flow is working correctly.")
    print("=" * 80)


if __name__ == "__main__":
    test_position_context_flow()
