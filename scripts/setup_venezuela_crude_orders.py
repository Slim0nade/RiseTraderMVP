#!/usr/bin/env python3
"""
Venezuela Crude Oil Strategy - Pending Orders Setup Script

This script loads and places all pending orders for the Venezuela/Maduro
crude oil spike-and-fade strategy via the RiseTrader MCP system.

Run this BEFORE market opens on Sunday 6pm ET!

Usage:
    python scripts/setup_venezuela_crude_orders.py
    
    # Or with options:
    python scripts/setup_venezuela_crude_orders.py --dry-run  # Preview only
    python scripts/setup_venezuela_crude_orders.py --phase fade  # Only fade orders
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# STRATEGY CONFIGURATION
# ============================================================================

STRATEGY_FILE = "venezuela_crude_strategy.json"

# Order phases - can be filtered
PHASES = {
    "CATCH_SPIKE": "Gap-up momentum plays (BUY_STOP)",
    "FADE_RALLY": "Fade the spike (SELL_LIMIT)", 
    "BREAKDOWN": "Catch breakdown (SELL_STOP)",
    "TREND_FOLLOW": "Medium-term position"
}


# ============================================================================
# PENDING ORDER MANAGER
# ============================================================================

class PendingOrderManager:
    """Manages pending orders via RiseTrader system."""
    
    def __init__(self, api_url: str = "http://localhost:8003"):
        self.api_url = api_url
        self.orders: Dict[str, Dict[str, Any]] = {}
        
    async def place_pending_order(
        self,
        symbol: str,
        order_type: str,
        entry_price: float,
        lot_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        expiration: Optional[str] = None,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place a pending order."""
        import uuid
        
        order_id = f"PO_{uuid.uuid4().hex[:8].upper()}"
        
        order = {
            "id": order_id,
            "symbol": symbol,
            "order_type": order_type,
            "entry_price": entry_price,
            "lot_size": lot_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "expiration": expiration,
            "comment": comment,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        self.orders[order_id] = order
        
        # Calculate risk metrics
        risk_per_lot = abs(entry_price - stop_loss) * 100 if stop_loss else None
        reward_per_lot = abs(take_profit - entry_price) * 100 if take_profit else None
        risk_reward = reward_per_lot / risk_per_lot if risk_per_lot and reward_per_lot else None
        
        return {
            "success": True,
            "order_id": order_id,
            "order": order,
            "risk_metrics": {
                "risk_per_lot_usd": risk_per_lot,
                "reward_per_lot_usd": reward_per_lot,
                "risk_reward_ratio": round(risk_reward, 2) if risk_reward else None,
                "total_risk_usd": risk_per_lot * lot_size if risk_per_lot else None
            }
        }
    
    def get_orders_summary(self) -> Dict[str, Any]:
        """Get summary of all pending orders."""
        by_phase = {}
        total_risk = 0
        total_lots = 0
        
        for order in self.orders.values():
            phase = order.get("comment", "").split(" - ")[0] if " - " in order.get("comment", "") else "OTHER"
            if phase not in by_phase:
                by_phase[phase] = []
            by_phase[phase].append(order)
            total_lots += order["lot_size"]
            
            if order["stop_loss"]:
                risk = abs(order["entry_price"] - order["stop_loss"]) * 100 * order["lot_size"]
                total_risk += risk
        
        return {
            "total_orders": len(self.orders),
            "total_lots": total_lots,
            "total_risk_usd": round(total_risk, 2),
            "by_phase": {k: len(v) for k, v in by_phase.items()},
            "orders": list(self.orders.values())
        }


# ============================================================================
# MT4 INTEGRATION
# ============================================================================

class MT4PendingOrderPlacer:
    """Places pending orders directly to MT4 via ZMQ."""
    
    def __init__(self, host: str = "localhost", port: int = 5555):
        self.host = host
        self.port = port
        self.context = None
        self.socket = None
        
    async def connect(self):
        """Connect to MT4 ZMQ server."""
        try:
            import zmq
            import zmq.asyncio
            
            self.context = zmq.asyncio.Context()
            self.socket = self.context.socket(zmq.REQ)
            self.socket.connect(f"tcp://{self.host}:{self.port}")
            self.socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
            
            # Test connection
            await self.socket.send_string('{"command": "test_connection"}')
            response = await self.socket.recv_string()
            
            return {"success": True, "message": "Connected to MT4"}
        except ImportError:
            return {"success": False, "error": "pyzmq not installed. Run: pip install pyzmq"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Place a pending order in MT4."""
        if not self.socket:
            return {"success": False, "error": "Not connected to MT4"}
        
        # MT4 order type mapping
        order_type_map = {
            "BUY_STOP": 4,
            "SELL_STOP": 5,
            "BUY_LIMIT": 2,
            "SELL_LIMIT": 3
        }
        
        mt4_type = order_type_map.get(order["order_type"])
        if mt4_type is None:
            return {"success": False, "error": f"Invalid order type: {order['order_type']}"}
        
        request = {
            "command": "OrderSend",
            "symbol": order["symbol"],
            "cmd": mt4_type,
            "volume": order["lot_size"],
            "price": order["entry_price"],
            "slippage": 3,
            "stoploss": order.get("stop_loss", 0),
            "takeprofit": order.get("take_profit", 0),
            "comment": order.get("comment", ""),
            "magic": 123456,
            "expiration": order.get("expiration", "")
        }
        
        try:
            await self.socket.send_string(json.dumps(request))
            response = await self.socket.recv_string()
            result = json.loads(response)
            
            return {
                "success": result.get("status") == "OK",
                "ticket": result.get("ticket"),
                "message": result.get("message", ""),
                "error": result.get("error")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Close ZMQ connection."""
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def load_strategy(strategy_file: str) -> Dict[str, Any]:
    """Load strategy from JSON file."""
    config_path = PROJECT_ROOT / "config" / "pending_orders" / strategy_file
    
    if not config_path.exists():
        return {"success": False, "error": f"Strategy file not found: {config_path}"}
    
    with open(config_path) as f:
        return {"success": True, "strategy": json.load(f)}


def print_order_table(orders: List[Dict[str, Any]]):
    """Print orders in a nice table format."""
    print("\n" + "=" * 100)
    print(f"{'ID':<20} {'TYPE':<12} {'ENTRY':>10} {'SL':>10} {'TP':>10} {'LOTS':>8} {'RISK $':>10}")
    print("=" * 100)
    
    total_risk = 0
    for order in orders:
        sl = order.get("stop_loss", 0) or 0
        tp = order.get("take_profit", 0) or 0
        entry = order["entry_price"]
        lots = order["lot_size"]
        
        risk = abs(entry - sl) * 100 * lots if sl else 0
        total_risk += risk
        
        print(f"{order['id']:<20} {order['order_type']:<12} {entry:>10.2f} {sl:>10.2f} {tp:>10.2f} {lots:>8.2f} {risk:>10.2f}")
    
    print("=" * 100)
    print(f"{'TOTAL RISK:':<72} {total_risk:>10.2f}")
    print("=" * 100)


async def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup Venezuela Crude Oil Pending Orders")
    parser.add_argument("--dry-run", action="store_true", help="Preview orders without placing")
    parser.add_argument("--phase", type=str, help="Only process specific phase (CATCH_SPIKE, FADE_RALLY, BREAKDOWN, TREND_FOLLOW)")
    parser.add_argument("--mt4", action="store_true", help="Place orders directly to MT4 via ZMQ")
    parser.add_argument("--host", type=str, default="localhost", help="MT4 ZMQ host")
    parser.add_argument("--port", type=int, default=5555, help="MT4 ZMQ port")
    
    args = parser.parse_args()
    
    print("\n" + "🛢️ " * 20)
    print("  VENEZUELA CRUDE OIL STRATEGY - PENDING ORDERS SETUP")
    print("🛢️ " * 20)
    print(f"\n📅 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Mode: {'DRY RUN (Preview Only)' if args.dry_run else 'LIVE ORDER PLACEMENT'}")
    
    # Load strategy
    print("\n📂 Loading strategy file...")
    result = await load_strategy(STRATEGY_FILE)
    
    if not result["success"]:
        print(f"❌ Error: {result['error']}")
        return 1
    
    strategy = result["strategy"]
    print(f"✅ Loaded: {strategy['strategy_name']}")
    print(f"📝 {strategy['description']}")
    
    # Filter orders by phase if specified
    orders = strategy.get("pending_orders", [])
    if args.phase:
        orders = [o for o in orders if o.get("phase") == args.phase]
        print(f"\n🔍 Filtering to phase: {args.phase} ({len(orders)} orders)")
    
    # Show market context
    ctx = strategy.get("market_context", {})
    print(f"\n📈 MARKET CONTEXT:")
    print(f"   Event: {ctx.get('event', 'N/A')}")
    print(f"   Current Price: ${ctx.get('current_price', 'N/A')}")
    print(f"   Expected Gap: {ctx.get('expected_gap_up', 'N/A')}")
    
    # Show risk management
    rm = strategy.get("risk_management", {})
    print(f"\n⚠️  RISK MANAGEMENT:")
    print(f"   Max Risk/Trade: {rm.get('max_risk_per_trade_pct', 'N/A')}%")
    print(f"   Max Exposure: {rm.get('max_total_exposure_pct', 'N/A')}%")
    print(f"   Account Balance: ${rm.get('account_balance_estimate', 'N/A'):,}")
    
    # Initialize order manager
    manager = PendingOrderManager()
    
    # Process orders
    print(f"\n📋 PROCESSING {len(orders)} PENDING ORDERS...")
    
    placed_orders = []
    for order_def in orders:
        if not order_def.get("enabled", True):
            print(f"   ⏭️  Skipping disabled order: {order_def['id']}")
            continue
        
        result = await manager.place_pending_order(
            symbol=order_def["symbol"],
            order_type=order_def["order_type"],
            entry_price=order_def["entry_price"],
            lot_size=order_def["lot_size"],
            stop_loss=order_def.get("stop_loss"),
            take_profit=order_def.get("take_profit"),
            expiration=order_def.get("expiration"),
            comment=f"{order_def.get('phase', '')} - {order_def.get('notes', order_def['id'])}"
        )
        
        if result["success"]:
            placed_orders.append(result["order"])
            metrics = result["risk_metrics"]
            print(f"   ✅ {order_def['id']}: {order_def['order_type']} @ ${order_def['entry_price']:.2f}")
            print(f"      Risk: ${metrics['total_risk_usd']:.2f} | R:R = {metrics['risk_reward_ratio']}")
        else:
            print(f"   ❌ {order_def['id']}: {result.get('error', 'Unknown error')}")
    
    # Print summary table
    print_order_table(placed_orders)
    
    # Show execution playbook
    playbook = strategy.get("execution_playbook", {})
    if playbook:
        print("\n📖 EXECUTION PLAYBOOK:")
        for scenario, details in playbook.items():
            print(f"\n   {scenario.upper()} (Probability: {details.get('probability', '?')}%)")
            print(f"   {details.get('description', '')}")
            for action in details.get("actions", [])[:3]:
                print(f"      → {action}")
    
    # Show key levels
    levels = strategy.get("key_levels", {})
    if levels:
        print("\n🎯 KEY LEVELS:")
        print(f"   Resistance: {levels.get('resistance', [])}")
        print(f"   Support: {levels.get('support', [])}")
        print(f"   Pivot: ${levels.get('pivot', 'N/A')}")
    
    # Show timeline
    timeline = strategy.get("timeline", {})
    if timeline:
        print("\n⏰ TIMELINE:")
        for time_key, action in timeline.items():
            print(f"   {time_key}: {action}")
    
    # MT4 placement (if requested)
    if args.mt4 and not args.dry_run:
        print("\n🔌 CONNECTING TO MT4...")
        mt4 = MT4PendingOrderPlacer(host=args.host, port=args.port)
        conn_result = await mt4.connect()
        
        if conn_result["success"]:
            print("   ✅ Connected to MT4")
            
            print("\n📤 PLACING ORDERS IN MT4...")
            for order in placed_orders:
                mt4_result = await mt4.place_order(order)
                if mt4_result["success"]:
                    print(f"   ✅ {order['id']}: Ticket #{mt4_result.get('ticket', 'N/A')}")
                else:
                    print(f"   ❌ {order['id']}: {mt4_result.get('error', 'Unknown error')}")
            
            await mt4.close()
        else:
            print(f"   ❌ MT4 Connection Failed: {conn_result.get('error', 'Unknown error')}")
            print("   💡 Make sure MT4 is running with RiseTraderMT4Server EA attached")
    
    # Final summary
    summary = manager.get_orders_summary()
    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)
    print(f"   Total Orders: {summary['total_orders']}")
    print(f"   Total Lots: {summary['total_lots']:.2f}")
    print(f"   Total Risk: ${summary['total_risk_usd']:,.2f}")
    print(f"   By Phase: {summary['by_phase']}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN COMPLETE - No orders were actually placed")
        print("   Run without --dry-run to place orders")
    
    print("\n🚀 Ready for market open!")
    print("   Markets open: Sunday 6:00 PM ET")
    print("   Monitor: https://www.tradingview.com/chart/?symbol=TVC%3AUSOIL")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
