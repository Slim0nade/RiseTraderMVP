#!/usr/bin/env python3
"""
Test live order execution: open → monitor → close
USES REAL MONEY - BE CAREFUL!
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager


async def main():
    print("=" * 80)
    print("LIVE ORDER TEST - REAL MONEY!")
    print("=" * 80)
    print()

    # Configuration
    host = "75.154.254.186"
    rep_port = 5555
    pub_port = 5556
    magic_number = 100001

    # Small test order
    symbol = "CrudeOIL"
    volume = 0.01  # VERY SMALL SIZE - 0.01 lots

    print(f"Configuration:")
    print(f"  Symbol: {symbol}")
    print(f"  Volume: {volume} lots (MICRO SIZE)")
    print(f"  Magic Number: {magic_number}")
    print()

    # Create client
    encryption_mgr = MT4EncryptionManager(encryption_enabled=False)
    client = MT4Client(
        host=host,
        rep_port=rep_port,
        pub_port=pub_port,
        magic_number=magic_number,
        encryption_manager=encryption_mgr,
        timeout_ms=10000
    )

    ticket_number = None

    try:
        # Step 1: Connect
        print("=" * 80)
        print("STEP 1: Connect to MT4")
        print("=" * 80)
        await client.connect()
        print("✅ Connected!\n")

        # Step 2: Get account info
        print("=" * 80)
        print("STEP 2: Get Account Info")
        print("=" * 80)
        account_info = await client.get_account_info()

        # Adapt old format
        if isinstance(account_info, dict):
            account_data = account_info.get('account_info', account_info)
            balance = account_data.get('balance')
            equity = account_data.get('equity')
            free_margin = account_data.get('freeMargin')

            print(f"Account Balance: ${balance:,.2f}")
            print(f"Account Equity: ${equity:,.2f}")
            print(f"Free Margin: ${free_margin:,.2f}")
            print()

            if free_margin < 100:
                print("⚠️  WARNING: Low free margin. Canceling test.")
                return

        # Step 3: Get current positions
        print("=" * 80)
        print("STEP 3: Check Existing Positions")
        print("=" * 80)
        positions = await client.get_open_positions()

        if isinstance(positions, dict):
            pos_list = positions.get('positions', [])
            print(f"Open positions: {len(pos_list)}")
            if pos_list:
                for pos in pos_list:
                    print(f"  - Ticket #{pos.get('ticket')}: {pos.get('type')} {pos.get('volume')} {pos.get('symbol')}")
            print()

        # Step 4: Place BUY order
        print("=" * 80)
        print(f"STEP 4: Place BUY Order ({volume} lots {symbol})")
        print("=" * 80)
        print("⚠️  THIS WILL USE REAL MONEY!")
        print("⚠️  AUTO-EXECUTING IN 3 SECONDS - Ctrl+C to cancel!")
        print()

        await asyncio.sleep(3)

        print("Placing order...")
        order_result = await client.create_instant_order(
            symbol=symbol,
            direction="BUY",
            volume=volume
        )

        print(f"Order result: {order_result}")

        # Extract ticket number (OrderResponse object)
        if hasattr(order_result, 'success'):
            if order_result.success:
                ticket_number = order_result.ticket_number
                execution_price = order_result.execution_price
                print(f"✅ ORDER OPENED!")
                print(f"   Ticket: #{ticket_number}")
                print(f"   Price: {execution_price if execution_price else 'N/A'}")
                print()

                if not ticket_number:
                    print(f"⚠️  WARNING: No ticket number returned!")
                    return
            else:
                print(f"❌ Order failed: {order_result.error_message}")
                return
        else:
            print(f"❌ Unexpected response format: {order_result}")
            return

        # Step 5: Monitor position
        print("=" * 80)
        print("STEP 5: Monitor Position (5 seconds)")
        print("=" * 80)

        await asyncio.sleep(2)

        positions = await client.get_open_positions()
        if isinstance(positions, dict):
            pos_list = positions.get('positions', [])
            for pos in pos_list:
                if pos.get('ticket') == ticket_number:
                    print(f"Position #{ticket_number}:")
                    print(f"  Symbol: {pos.get('symbol')}")
                    print(f"  Type: {pos.get('type')}")
                    print(f"  Volume: {pos.get('volume')}")
                    print(f"  Open Price: {pos.get('openPrice')}")
                    print(f"  Current Price: {pos.get('currentPrice')}")
                    print(f"  P&L: ${pos.get('profit', 0):.2f}")
                    break

        print()
        await asyncio.sleep(3)

        # Step 6: Close position
        print("=" * 80)
        print(f"STEP 6: Close Position (Ticket #{ticket_number})")
        print("=" * 80)

        close_result = await client.close_position(
            ticket_number=ticket_number
        )

        print(f"Close result: {close_result}")

        if isinstance(close_result, dict):
            if close_result.get('status') == 'OK':
                final_profit = close_result.get('profit', 0)
                close_price = close_result.get('closePrice')
                print(f"✅ POSITION CLOSED!")
                print(f"   Close Price: {close_price}")
                print(f"   Final P&L: ${final_profit:.2f}")
                print()
            else:
                print(f"❌ Close failed: {close_result.get('message')}")

        # Step 7: Verify closed
        print("=" * 80)
        print("STEP 7: Verify Position Closed")
        print("=" * 80)

        await asyncio.sleep(1)

        positions = await client.get_open_positions()
        if isinstance(positions, dict):
            pos_list = positions.get('positions', [])
            still_open = False
            for pos in pos_list:
                if pos.get('ticket') == ticket_number:
                    still_open = True
                    break

            if still_open:
                print(f"⚠️  Position #{ticket_number} still open!")
            else:
                print(f"✅ Position #{ticket_number} confirmed closed!")

        print()
        print("=" * 80)
        print("TEST COMPLETE!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

        # Try to close position if it was opened
        if ticket_number:
            print(f"\nAttempting emergency close of ticket #{ticket_number}...")
            try:
                await client.close_position(ticket_number=ticket_number)
                print("✅ Emergency close successful")
            except Exception as e2:
                print(f"❌ Emergency close failed: {e2}")

    finally:
        await client.disconnect()
        print("\nDisconnected from MT4")


if __name__ == "__main__":
    asyncio.run(main())
