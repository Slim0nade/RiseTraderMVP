#!/usr/bin/env python3
"""
Test MT4 Direct Sync - Verify MT4 Connection

Tests MT4 connection and queries account/position data directly,
bypassing the sync service to diagnose connection issues.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from src.config.network_config import get_network_manager
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_encryption import MT4EncryptionManager
from src.trading.execution.mt4_models import (
    GetAccountInfoCommand,
    GetOpenPositionsCommand,
)

logger = structlog.get_logger(__name__)


async def test_mt4_connection():
    """Test direct MT4 connection."""
    print("\n" + "=" * 70)
    print("MT4 DIRECT CONNECTION TEST")
    print("=" * 70)

    # Get MT4 config
    network_manager = get_network_manager()
    mt4_config = network_manager.get_mt4_config()

    print(f"\nMT4 Configuration:")
    print(f"  Host: {mt4_config.host}")
    print(f"  Command Port: {mt4_config.command_port}")
    print(f"  Stream Port: {mt4_config.stream_port}")

    # Create encryption manager (disabled)
    encryption_manager = MT4EncryptionManager(encryption_enabled=False)

    # Create MT4 client
    mt4_client = MT4Client(
        host=mt4_config.host,
        rep_port=mt4_config.command_port,
        pub_port=mt4_config.stream_port,
        magic_number=0,
        encryption_manager=encryption_manager,
        timeout_ms=15000,  # 15 second timeout
    )

    try:
        print("\n[1/4] Connecting to MT4...")
        await mt4_client.connect()
        print("✅ Connected successfully")

        # Small delay to ensure socket is ready
        await asyncio.sleep(0.5)

        # Test account info
        print("\n[2/4] Querying account info...")
        account_command = GetAccountInfoCommand()
        account_response = await mt4_client.send_command(account_command)

        if account_response and account_response.get("success"):
            account_data = account_response.get("data", {})
            print("✅ Account info received:")
            print(f"  Balance: ${account_data.get('balance', 0):,.2f}")
            print(f"  Equity: ${account_data.get('equity', 0):,.2f}")
            print(f"  Margin: ${account_data.get('margin', 0):,.2f}")
            print(f"  Free Margin: ${account_data.get('free_margin', 0):,.2f}")
        else:
            print(f"❌ Account query failed: {account_response}")
            return False

        # Small delay between commands
        await asyncio.sleep(0.5)

        # Test positions
        print("\n[3/4] Querying open positions...")
        positions_command = GetOpenPositionsCommand()
        positions_response = await mt4_client.send_command(positions_command)

        if positions_response and positions_response.get("success"):
            positions_data = positions_response.get("data", {}).get("positions", [])
            print(f"✅ Positions received: {len(positions_data)} open positions")

            if positions_data:
                print("\nOpen Positions:")
                for pos in positions_data:
                    symbol = pos.get("symbol", "")
                    pos_type = pos.get("type", "")
                    lots = pos.get("lots", 0)
                    profit = pos.get("profit", 0)
                    print(f"  {symbol:10s} {pos_type:4s} {lots:7.2f} lots | P&L: ${profit:+8.2f}")
        else:
            print(f"❌ Positions query failed: {positions_response}")
            return False

        print("\n[4/4] Test complete!")
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        logger.error("test_failed", error=str(e), exc_info=True)
        return False

    finally:
        # Cleanup
        await mt4_client.disconnect()
        print("\nMT4 client disconnected")


async def main():
    """Main test runner."""
    success = await test_mt4_connection()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
