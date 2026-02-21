#!/usr/bin/env python3
"""
MT4 Direct Pending Orders - Venezuela Crude Strategy

This script places pending orders DIRECTLY to MT4 via ZeroMQ.
Requires MT4 with RiseTraderMT4Server EA running.

Usage:
    cd /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP
    python scripts/mt4_pending_orders.py
"""

import zmq
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

# MT4 ZMQ Configuration
MT4_REQ_PORT = 5555  # Request-Reply port
MT4_HOST = "localhost"

# Order definitions for Venezuela Crude Strategy
PENDING_ORDERS = [
    # Phase 1: Catch the Spike (Aggressive - Optional)
    {
        "id": "SPIKE_LONG_1",
        "phase": "CATCH_SPIKE",
        "cmd": "OP_BUYSTOP",  # MT4 order type
        "symbol": "CrudeOIL",
        "volume": 0.50,
        "price": 58.50,
        "sl": 57.00,
        "tp": 61.50,
        "comment": "VZ_SPIKE_1",
        "enabled": True
    },
    {
        "id": "SPIKE_LONG_2",
        "phase": "CATCH_SPIKE", 
        "cmd": "OP_BUYSTOP",
        "symbol": "CrudeOIL",
        "volume": 0.30,
        "price": 59.00,
        "sl": 57.50,
        "tp": 62.00,
        "comment": "VZ_SPIKE_2",
        "enabled": True
    },
    
    # Phase 2: Fade the Rally (Primary Strategy)
    {
        "id": "FADE_SHORT_1",
        "phase": "FADE_RALLY",
        "cmd": "OP_SELLLIMIT",
        "symbol": "CrudeOIL",
        "volume": 0.75,
        "price": 60.50,
        "sl": 62.50,
        "tp": 57.00,
        "comment": "VZ_FADE_1",
        "enabled": True
    },
    {
        "id": "FADE_SHORT_2",
        "phase": "FADE_RALLY",
        "cmd": "OP_SELLLIMIT",
        "symbol": "CrudeOIL",
        "volume": 0.75,
        "price": 61.50,
        "sl": 63.50,
        "tp": 56.50,
        "comment": "VZ_FADE_2",
        "enabled": True
    },
    {
        "id": "FADE_SHORT_3",
        "phase": "FADE_RALLY",
        "cmd": "OP_SELLLIMIT",
        "symbol": "CrudeOIL",
        "volume": 0.50,
        "price": 62.50,
        "sl": 64.00,
        "tp": 57.50,
        "comment": "VZ_FADE_3",
        "enabled": True
    },
    
    # Phase 3: Breakdown Trade (If No Spike)
    {
        "id": "BREAKDOWN_SHORT_1",
        "phase": "BREAKDOWN",
        "cmd": "OP_SELLSTOP",
        "symbol": "CrudeOIL",
        "volume": 1.00,
        "price": 56.50,
        "sl": 58.50,
        "tp": 53.00,
        "comment": "VZ_BRKDN_1",
        "enabled": True
    },
    {
        "id": "BREAKDOWN_SHORT_2",
        "phase": "BREAKDOWN",
        "cmd": "OP_SELLSTOP",
        "symbol": "CrudeOIL",
        "volume": 0.75,
        "price": 55.00,
        "sl": 57.00,
        "tp": 51.50,
        "comment": "VZ_BRKDN_2",
        "enabled": True
    },
    
    # Phase 4: Medium-Term Position
    {
        "id": "MEDIUM_TERM_SHORT",
        "phase": "TREND_FOLLOW",
        "cmd": "OP_SELLLIMIT",
        "symbol": "CrudeOIL",
        "volume": 1.50,
        "price": 59.00,
        "sl": 62.00,
        "tp": 52.00,
        "comment": "VZ_MED_TERM",
        "enabled": True
    },
]


class MT4Client:
    """Client for communicating with MT4 via ZeroMQ."""
    
    def __init__(self, host: str = "localhost", port: int = 5555):
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = None
        
    def connect(self) -> bool:
        """Connect to MT4 ZMQ server."""
        try:
            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
            self.socket.setsockopt(zmq.SNDTIMEO, 5000)
            self.socket.connect(f"tcp://{self.host}:{self.port}")
            print(f"✓ Connected to MT4 at tcp://{self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MT4."""
        if self.socket:
            self.socket.close()
        self.context.term()
    
    def send_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a command to MT4 and get response."""
        try:
            # Send command as JSON
            self.socket.send_string(json.dumps(command))
            
            # Receive response
            response = self.socket.recv_string()
            return json.loads(response)
        except zmq.error.Again:
            print("  ⚠ Timeout waiting for MT4 response")
            return None
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test connection to MT4."""
        response = self.send_command({"command": "test_connection"})
        if response and response.get("status") == "OK":
            return True
        return False
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information from MT4."""
        response = self.send_command({"command": "getAccountInfo"})
        return response
    
    def place_pending_order(
        self,
        symbol: str,
        cmd: str,
        volume: float,
        price: float,
        sl: float = 0,
        tp: float = 0,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        Place a pending order in MT4.
        
        Args:
            symbol: Trading symbol
            cmd: Order type (OP_BUYSTOP, OP_SELLSTOP, OP_BUYLIMIT, OP_SELLLIMIT)
            volume: Lot size
            price: Entry price
            sl: Stop loss price
            tp: Take profit price
            comment: Order comment
        """
        command = {
            "command": "placePendingOrder",
            "symbol": symbol,
            "cmd": cmd,
            "volume": volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment
        }
        
        response = self.send_command(command)
        return response or {"status": "ERROR", "message": "No response from MT4"}
    
    def get_pending_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get all pending orders, optionally filtered by symbol."""
        command = {"command": "getPendingOrders"}
        if symbol:
            command["symbol"] = symbol
        
        response = self.send_command(command)
        if response and response.get("status") == "OK":
            return response.get("orders", [])
        return []
    
    def delete_pending_order(self, ticket: int) -> Dict[str, Any]:
        """Delete a pending order by ticket number."""
        command = {
            "command": "deletePendingOrder",
            "ticket": ticket
        }
        return self.send_command(command) or {"status": "ERROR"}


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*60}")
    print(f"{text.center(60)}")
    print(f"{'='*60}\n")


def print_order(order: Dict[str, Any], index: int):
    """Pretty print an order."""
    cmd = order.get("cmd", "UNKNOWN")
    symbol = order.get("symbol", "UNKNOWN")
    price = order.get("price", 0)
    sl = order.get("sl", 0)
    tp = order.get("tp", 0)
    volume = order.get("volume", 0)
    phase = order.get("phase", "")
    comment = order.get("comment", "")
    
    # Direction indicator
    if "BUY" in cmd:
        direction = "🟢 LONG"
    else:
        direction = "🔴 SHORT"
    
    # Order type
    if "STOP" in cmd:
        order_type = "STOP"
    else:
        order_type = "LIMIT"
    
    risk = abs(price - sl) * volume * 100 if sl else 0
    reward = abs(tp - price) * volume * 100 if tp else 0
    rr = reward / risk if risk > 0 else 0
    
    print(f"  #{index} {direction} {order_type} @ ${price:.2f}")
    print(f"      Volume: {volume} lots | SL: ${sl:.2f} | TP: ${tp:.2f}")
    print(f"      Risk: ${risk:.0f} | Reward: ${reward:.0f} | R:R = {rr:.2f}")
    print(f"      Phase: {phase} | Comment: {comment}")
    print()


def main():
    print_header("🛢️ MT4 PENDING ORDERS - VENEZUELA CRUDE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Strategy: Spike & Fade on Venezuela/Maduro Capture\n")
    
    # Display all orders
    print_header("📋 ORDERS TO BE PLACED")
    
    # Group by phase
    phases = {}
    for order in PENDING_ORDERS:
        phase = order.get("phase", "OTHER")
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(order)
    
    total_risk = 0
    for phase, orders in phases.items():
        print(f"\n--- {phase} ---")
        for i, order in enumerate(orders, 1):
            if order.get("enabled", True):
                print_order(order, i)
                sl = order.get("sl", 0)
                price = order.get("price", 0)
                volume = order.get("volume", 0)
                if sl:
                    total_risk += abs(price - sl) * volume * 100
    
    print(f"\n{'='*60}")
    print(f"TOTAL POTENTIAL RISK: ${total_risk:.0f}")
    print(f"{'='*60}")
    
    # Ask for mode
    print("\nOptions:")
    print("  1. Place orders via MT4 ZMQ (requires MT4 running)")
    print("  2. Generate MT4 script file (.mq4)")
    print("  3. Display orders only (for manual entry)")
    print("  4. Exit")
    
    choice = input("\nSelect option (1-4): ").strip()
    
    if choice == "1":
        # Connect to MT4
        print_header("🔗 CONNECTING TO MT4")
        
        client = MT4Client(MT4_HOST, MT4_REQ_PORT)
        if not client.connect():
            print("\n⚠ Could not connect to MT4.")
            print("Make sure:")
            print("  1. MT4 is running")
            print("  2. RiseTraderMT4Server EA is attached to a chart")
            print("  3. Auto trading is enabled")
            client.disconnect()
            return
        
        # Test connection
        if not client.test_connection():
            print("⚠ MT4 connection test failed")
            client.disconnect()
            return
        
        print("✓ MT4 connection verified")
        
        # Get account info
        account = client.get_account_info()
        if account:
            print(f"\nAccount: {account.get('account', 'N/A')}")
            print(f"Balance: ${account.get('balance', 0):,.2f}")
            print(f"Equity: ${account.get('equity', 0):,.2f}")
        
        # Confirm
        confirm = input(f"\nPlace {len([o for o in PENDING_ORDERS if o.get('enabled')])} pending orders? (yes/no): ").strip().lower()
        
        if confirm != "yes":
            print("Cancelled.")
            client.disconnect()
            return
        
        # Place orders
        print_header("⚡ PLACING ORDERS")
        
        success = 0
        failed = 0
        
        for order in PENDING_ORDERS:
            if not order.get("enabled", True):
                continue
            
            print(f"Placing {order['id']}...", end=" ")
            
            result = client.place_pending_order(
                symbol=order["symbol"],
                cmd=order["cmd"],
                volume=order["volume"],
                price=order["price"],
                sl=order.get("sl", 0),
                tp=order.get("tp", 0),
                comment=order.get("comment", "")
            )
            
            if result.get("status") == "OK":
                print(f"✓ Ticket: {result.get('ticket', 'N/A')}")
                success += 1
            else:
                print(f"✗ {result.get('message', 'Unknown error')}")
                failed += 1
            
            time.sleep(0.5)  # Small delay between orders
        
        print(f"\n{'='*60}")
        print(f"Results: {success} placed, {failed} failed")
        print(f"{'='*60}")
        
        client.disconnect()
        
    elif choice == "2":
        # Generate MQ4 script
        print_header("📝 GENERATING MT4 SCRIPT")
        
        script = generate_mq4_script(PENDING_ORDERS)
        filename = "Venezuela_Crude_Orders.mq4"
        
        with open(filename, 'w') as f:
            f.write(script)
        
        print(f"✓ Script saved to: {filename}")
        print("\nTo use:")
        print("  1. Copy to MT4/MQL4/Scripts/")
        print("  2. In MT4, open Navigator → Scripts")
        print("  3. Drag 'Venezuela_Crude_Orders' to any chart")
        print("  4. Confirm execution")
        
    elif choice == "3":
        print("\nOrders displayed above for manual entry in MT4.")
        print("\nManual Entry Steps:")
        print("  1. Right-click chart → Trading → New Order")
        print("  2. Type: Pending Order")
        print("  3. Select appropriate order type (Buy Stop, Sell Limit, etc.)")
        print("  4. Enter price, SL, TP, and volume")
        print("  5. Click 'Place'")
    
    else:
        print("Exiting.")


def generate_mq4_script(orders: List[Dict[str, Any]]) -> str:
    """Generate an MQ4 script to place all pending orders."""
    
    # Map order types
    type_map = {
        "OP_BUYSTOP": "OP_BUYSTOP",
        "OP_SELLSTOP": "OP_SELLSTOP",
        "OP_BUYLIMIT": "OP_BUYLIMIT",
        "OP_SELLLIMIT": "OP_SELLLIMIT"
    }
    
    order_lines = []
    for order in orders:
        if not order.get("enabled", True):
            continue
        
        order_lines.append(f'''
   // {order['id']} - {order['phase']}
   ticket = OrderSend(
      "{order['symbol']}",  // symbol
      {type_map.get(order['cmd'], 'OP_BUYSTOP')},  // order type
      {order['volume']},  // volume
      {order['price']},  // price
      3,  // slippage
      {order.get('sl', 0)},  // stop loss
      {order.get('tp', 0)},  // take profit
      "{order.get('comment', '')}",  // comment
      12345,  // magic number
      0,  // expiration
      clrNone  // color
   );
   if(ticket < 0) {{
      Print("Error placing {order['id']}: ", GetLastError());
      errors++;
   }} else {{
      Print("Placed {order['id']}, ticket: ", ticket);
      success++;
   }}
   Sleep(500);  // Delay between orders
''')
    
    script = f'''//+------------------------------------------------------------------+
//|                                     Venezuela_Crude_Orders.mq4  |
//|                     Generated by RiseTrader - {datetime.now().strftime('%Y-%m-%d')}              |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright "RiseTrader"
#property link      ""
#property version   "1.00"
#property strict
#property show_inputs
#property script_show_confirm

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{{
   int ticket;
   int success = 0;
   int errors = 0;
   
   Print("=== Venezuela Crude Strategy - Placing Pending Orders ===");
   Print("Time: ", TimeToString(TimeCurrent()));
   
{"".join(order_lines)}
   
   Print("=== COMPLETE ===");
   Print("Success: ", success, " | Errors: ", errors);
   
   if(errors > 0) {{
      Alert("Some orders failed! Check Experts tab for details.");
   }} else {{
      Alert("All ", success, " pending orders placed successfully!");
   }}
}}
//+------------------------------------------------------------------+
'''
    
    return script


if __name__ == "__main__":
    main()
