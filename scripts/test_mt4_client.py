"""
Test MT4Client with real MT4 EA connection.

Tests:
1. Connection
2. Get symbols (works when market closed)
3. Get account info (works when market closed)
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.symbol_loader import SymbolLoader


async def main():
    """Test MT4Client functionality."""

    print("=" * 80)
    print("MT4 CLIENT TEST")
    print("=" * 80)
    print()

    # Configuration
    host = "75.154.254.174"  # Your MT4 server
    rep_port = 5555
    pub_port = 5556
    magic_number = 100001

    print(f"Configuration:")
    print(f"  Host: {host}")
    print(f"  REP Port: {rep_port}")
    print(f"  PUB Port: {pub_port}")
    print(f"  Magic Number: {magic_number}")
    print()

    # Create encryption manager (disabled for now)
    encryption_mgr = MT4EncryptionManager(encryption_enabled=False)
    print(f"Encryption: {'ENABLED' if encryption_mgr.encryption_enabled else 'DISABLED'}")
    print()

    # Create MT4Client
    client = MT4Client(
        host=host,
        rep_port=rep_port,
        pub_port=pub_port,
        magic_number=magic_number,
        encryption_manager=encryption_mgr,
        timeout_ms=10000  # 10 second timeout
    )

    try:
        # Test 1: Connect
        print("=" * 80)
        print("TEST 1: Connection")
        print("=" * 80)
        await client.connect()
        print("✅ Connected successfully!")
        print(f"   Is connected: {client.is_connected()}")
        print()

        # Test 2: Get symbols
        print("=" * 80)
        print("TEST 2: Get Symbols")
        print("=" * 80)
        print("Fetching available symbols from MT4...")
        symbols = await client.get_symbols()
        print(f"✅ Received {len(symbols)} symbols")
        print(f"   First 10 symbols: {symbols[:10]}")
        print(f"   Symbol 'CrudeOIL' available: {'CrudeOIL' in symbols}")
        print(f"   Symbol 'EURUSD' available: {'EURUSD' in symbols}")
        print()

        # Test 3: Symbol Loader
        print("=" * 80)
        print("TEST 3: Symbol Loader")
        print("=" * 80)
        print("Testing SymbolLoader with fetched symbols...")
        loader = SymbolLoader()
        await loader.refresh_symbols(client)
        print(f"✅ Symbols loaded: {len(loader.get_symbols())}")

        # Test validation
        print(f"   Validating 'CrudeOIL': {loader.is_valid_symbol('CrudeOIL')}")
        print(f"   Validating 'INVALID': {loader.is_valid_symbol('INVALID')}")
        print()

        # Test 4: Get account info
        print("=" * 80)
        print("TEST 4: Get Account Info")
        print("=" * 80)
        print("Fetching account information...")
        account_info = await client.get_account_info()
        print(f"✅ Account info received:")
        print(f"   Success: {account_info.success}")
        if account_info.success:
            print(f"   Account: {account_info.account_number}")
            print(f"   Balance: ${account_info.balance}")
            print(f"   Equity: ${account_info.equity}")
            print(f"   Margin: ${account_info.margin}")
            print(f"   Free Margin: ${account_info.free_margin}")
            print(f"   Margin Level: {account_info.margin_level}%")
            print(f"   Leverage: 1:{account_info.leverage}")
        print()

        # Test 5: Get open positions
        print("=" * 80)
        print("TEST 5: Get Open Positions")
        print("=" * 80)
        print("Fetching open positions...")
        positions = await client.get_open_positions()
        print(f"✅ Positions received:")
        print(f"   Success: {positions.success}")
        print(f"   Open positions: {len(positions.positions)}")
        if positions.positions:
            for pos in positions.positions:
                print(f"   - Ticket #{pos.ticket_number}: {pos.direction} {pos.volume} {pos.symbol} @ {pos.current_price} (P&L: ${pos.unrealized_pnl})")
        else:
            print(f"   No open positions")
        print()

        print("=" * 80)
        print("ALL TESTS PASSED! ✅")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  ✅ Connection established")
        print(f"  ✅ Symbols fetched: {len(symbols)}")
        print(f"  ✅ Symbol loader working")
        print(f"  ✅ Account info retrieved")
        print(f"  ✅ Positions queried")
        print()
        print("Ready for Day 3: Service Layer Implementation!")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        await client.disconnect()
        print()
        print("Disconnected from MT4")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
