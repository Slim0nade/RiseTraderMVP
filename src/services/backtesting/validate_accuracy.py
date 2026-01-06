"""
Backtest Accuracy Validator

Compares current backtest results against accurate CFD cost modeling
to identify discrepancies and calculate the real P&L.

Usage:
    python -m src.services.backtesting.validate_accuracy
"""
from datetime import datetime, time
from decimal import Decimal
from typing import List, Dict, Tuple

# CFD Specifications for CrudeOIL
CRUDE_OIL_SPEC = {
    "contract_size": Decimal("100"),  # 100 barrels per lot
    "swap_long_per_lot": Decimal("-0.85"),  # Pay $0.85/lot/night for long
    "swap_short_per_lot": Decimal("-0.35"),  # Pay $0.35/lot/night for short
    "spread_pips": Decimal("3.0"),  # 3 pips = $0.03
    "pip_value_per_lot": Decimal("1.00"),  # $1 per pip per lot
    "rollover_time": time(22, 0),  # 22:00 UTC
    "triple_swap_day": 2,  # Wednesday
}


def calculate_nights_held(
    entry_time: datetime,
    exit_time: datetime,
    rollover_time: time = time(22, 0),
) -> Tuple[int, bool]:
    """
    Calculate number of overnight rollovers crossed.
    
    Returns:
        Tuple of (nights, includes_triple_swap_day)
    """
    from datetime import timedelta
    
    nights = 0
    triple_swap_nights = 0
    
    current = entry_time
    
    while current.date() <= exit_time.date():
        # Get rollover datetime for this day
        day_rollover = datetime.combine(current.date(), rollover_time)
        
        # Check if position was open across this rollover
        if entry_time < day_rollover < exit_time:
            weekday = current.weekday()
            
            if weekday == 2:  # Wednesday = triple swap
                nights += 3
                triple_swap_nights = 3
            else:
                nights += 1
        
        # Move to next day
        current = datetime.combine(current.date(), time(0, 0)) + timedelta(days=1)
    
    return nights, triple_swap_nights > 0


def calculate_swap_cost(
    direction: str,
    lot_size: Decimal,
    nights: int,
) -> Decimal:
    """Calculate swap cost for a position."""
    if direction.upper() in ["BUY", "LONG"]:
        rate = CRUDE_OIL_SPEC["swap_long_per_lot"]
    else:
        rate = CRUDE_OIL_SPEC["swap_short_per_lot"]
    
    return rate * lot_size * nights


def calculate_spread_cost(lot_size: Decimal) -> Decimal:
    """Calculate spread cost (paid on entry and exit)."""
    spread_pips = CRUDE_OIL_SPEC["spread_pips"]
    pip_value = CRUDE_OIL_SPEC["pip_value_per_lot"]
    # Spread is paid once (half on entry, half on exit effectively)
    return spread_pips * pip_value * lot_size


def validate_trade(trade: Dict) -> Dict:
    """
    Validate a single trade and calculate accurate costs.
    
    Args:
        trade: Trade dictionary from database
        
    Returns:
        Validation result with current vs accurate costs
    """
    # Parse trade data
    action = trade["action"]
    quantity = Decimal(str(trade["quantity"]))
    entry_price = Decimal(str(trade["entry_price"]))
    exit_price = Decimal(str(trade["exit_price"])) if trade["exit_price"] else None
    entry_time = trade["entry_timestamp"]
    exit_time = trade["exit_timestamp"]
    
    current_fees = Decimal(str(trade["fees_paid"]))
    current_gross_pnl = Decimal(str(trade["gross_pnl"])) if trade["gross_pnl"] else Decimal("0")
    current_net_pnl = Decimal(str(trade["net_pnl"])) if trade["net_pnl"] else Decimal("0")
    
    # Convert quantity to lots
    contract_size = CRUDE_OIL_SPEC["contract_size"]
    lot_size = quantity / contract_size
    
    # Calculate accurate costs
    if exit_time:
        nights, has_triple = calculate_nights_held(entry_time, exit_time)
    else:
        nights, has_triple = 0, False
    
    swap_cost = abs(calculate_swap_cost(action, lot_size, nights))
    spread_cost = calculate_spread_cost(lot_size)
    
    # Total accurate fees
    accurate_fees = spread_cost + swap_cost  # No commission for Fortrade
    
    # Recalculate P&L
    accurate_net_pnl = current_gross_pnl - accurate_fees
    
    # Calculate difference
    fee_difference = accurate_fees - current_fees
    pnl_difference = current_net_pnl - accurate_net_pnl
    
    return {
        "trade_id": str(trade["id"]),
        "action": action,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "holding_hours": float(trade["holding_hours"]) if trade.get("holding_hours") else 0,
        "lot_size": float(lot_size),
        "quantity_units": float(quantity),
        
        # Current (incorrect)
        "current_fees": float(current_fees),
        "current_gross_pnl": float(current_gross_pnl),
        "current_net_pnl": float(current_net_pnl),
        
        # Accurate
        "nights_held": nights,
        "has_triple_swap": has_triple,
        "swap_cost": float(swap_cost),
        "spread_cost": float(spread_cost),
        "accurate_fees": float(accurate_fees),
        "accurate_net_pnl": float(accurate_net_pnl),
        
        # Difference
        "fee_difference": float(fee_difference),
        "pnl_impact": float(pnl_difference),
    }


def validate_backtest_run(trades: List[Dict]) -> Dict:
    """
    Validate all trades in a backtest run.
    
    Args:
        trades: List of trade dictionaries
        
    Returns:
        Summary of validation results
    """
    validations = []
    total_current_fees = Decimal("0")
    total_accurate_fees = Decimal("0")
    total_current_pnl = Decimal("0")
    total_accurate_pnl = Decimal("0")
    total_swap_cost = Decimal("0")
    total_nights = 0
    
    for trade in trades:
        if trade.get("exit_timestamp"):  # Only closed trades
            v = validate_trade(trade)
            validations.append(v)
            
            total_current_fees += Decimal(str(v["current_fees"]))
            total_accurate_fees += Decimal(str(v["accurate_fees"]))
            total_current_pnl += Decimal(str(v["current_net_pnl"]))
            total_accurate_pnl += Decimal(str(v["accurate_net_pnl"]))
            total_swap_cost += Decimal(str(v["swap_cost"]))
            total_nights += v["nights_held"]
    
    return {
        "total_trades": len(validations),
        "trades_with_overnight": sum(1 for v in validations if v["nights_held"] > 0),
        "total_nights_held": total_nights,
        
        "current_total_fees": float(total_current_fees),
        "accurate_total_fees": float(total_accurate_fees),
        "fee_undercharge": float(total_accurate_fees - total_current_fees),
        
        "total_swap_cost": float(total_swap_cost),
        
        "current_total_pnl": float(total_current_pnl),
        "accurate_total_pnl": float(total_accurate_pnl),
        "pnl_overstatement": float(total_current_pnl - total_accurate_pnl),
        
        "trade_details": validations,
    }


def print_validation_report(summary: Dict) -> None:
    """Print a formatted validation report."""
    print("\n" + "="*70)
    print("BACKTEST ACCURACY VALIDATION REPORT")
    print("="*70)
    
    print(f"\nTotal Closed Trades: {summary['total_trades']}")
    print(f"Trades with Overnight Holding: {summary['trades_with_overnight']}")
    print(f"Total Nights Held: {summary['total_nights_held']}")
    
    print("\n--- FEE COMPARISON ---")
    print(f"Current Total Fees:   ${summary['current_total_fees']:,.2f}")
    print(f"Accurate Total Fees:  ${summary['accurate_total_fees']:,.2f}")
    print(f"Fee Undercharge:      ${summary['fee_undercharge']:,.2f}")
    print(f"  - Swap Costs:       ${summary['total_swap_cost']:,.2f}")
    
    print("\n--- P&L IMPACT ---")
    print(f"Current Total P&L:    ${summary['current_total_pnl']:,.2f}")
    print(f"Accurate Total P&L:   ${summary['accurate_total_pnl']:,.2f}")
    print(f"P&L Overstatement:    ${summary['pnl_overstatement']:,.2f}")
    
    if summary['trade_details']:
        print("\n--- OVERNIGHT TRADES DETAIL ---")
        overnight_trades = [t for t in summary['trade_details'] if t['nights_held'] > 0]
        for t in overnight_trades[:10]:  # Show first 10
            print(f"\n  Trade: {t['trade_id'][:8]}...")
            print(f"    Action: {t['action']}, Lots: {t['lot_size']:.2f}")
            print(f"    Holding: {t['holding_hours']:.1f} hours, Nights: {t['nights_held']}")
            print(f"    Swap Cost: ${t['swap_cost']:.2f}")
            print(f"    Current Net P&L: ${t['current_net_pnl']:.2f} → Accurate: ${t['accurate_net_pnl']:.2f}")
    
    print("\n" + "="*70)


# Example usage and test data
if __name__ == "__main__":
    # Test with sample trades from database query
    sample_trades = [
        {
            "id": "96767e1d-c061-4977-813e-874eec0b189f",
            "action": "BUY",
            "symbol": "CrudeOIL",
            "entry_timestamp": datetime(2025, 1, 12, 23, 1),  # Sunday
            "exit_timestamp": datetime(2025, 1, 13, 14, 44),  # Monday
            "holding_hours": 15.72,
            "entry_price": "76.52645",
            "exit_price": "76.47",
            "quantity": "49.05166776",
            "gross_pnl": "-2.77",
            "net_pnl": "-3.52",
            "fees_paid": "0.75",
        },
        {
            "id": "b554005f-1905-45b9-927b-35938795acd8",
            "action": "BUY",
            "symbol": "CrudeOIL",
            "entry_timestamp": datetime(2025, 2, 3, 21, 43),  # Monday
            "exit_timestamp": datetime(2025, 2, 4, 3, 44),   # Tuesday
            "holding_hours": 6.02,
            "entry_price": "72.35228",
            "exit_price": "72.37",
            "quantity": "51.88157167",
            "gross_pnl": "0.92",
            "net_pnl": "0.17",
            "fees_paid": "0.75",
        },
        {
            "id": "77f21a68-9258-45cc-b90e-2dc5e6adf06e",
            "action": "BUY",
            "symbol": "CrudeOIL",
            "entry_timestamp": datetime(2025, 3, 24, 14, 31),  # Monday
            "exit_timestamp": datetime(2025, 3, 25, 1, 42),   # Tuesday
            "holding_hours": 11.18,
            "entry_price": "68.98892",
            "exit_price": "69.06",
            "quantity": "54.41091120",
            "gross_pnl": "3.87",
            "net_pnl": "3.12",
            "fees_paid": "0.75",
        },
    ]
    
    summary = validate_backtest_run(sample_trades)
    print_validation_report(summary)
