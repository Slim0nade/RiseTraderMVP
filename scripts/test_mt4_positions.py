"""Test script to query MT4 positions and see actual data."""
import asyncio
import json
import sys

sys.path.insert(0, '/app')

from src.trading.execution.mt4_client import MT4Client
from src.trading.commands.get_open_positions import GetOpenPositionsCommand
from src.services.network_manager import get_network_manager
from src.services.encryption.mt4_encryption_manager import MT4EncryptionManager


async def main():
    network_manager = get_network_manager()
    mt4_config = network_manager.get_mt4_config()
    encryption_manager = MT4EncryptionManager(encryption_enabled=False)

    client = MT4Client(
        host=mt4_config.host,
        rep_port=mt4_config.command_port,
        pub_port=mt4_config.stream_port,
        magic_number=0,
        encryption_manager=encryption_manager,
        timeout_ms=10000,
    )

    print("Connecting to MT4...")
    await client.connect()

    print("\nQuerying open positions...")
    command = GetOpenPositionsCommand()
    response = await client.send_command(command)

    print("\n=== MT4 Response ===")
    print(json.dumps(response, indent=2))

    # Extract positions
    if "data" in response:
        positions_data = response.get("data", {}).get("positions", [])
    else:
        positions_data = response.get("positions", [])

    print(f"\n=== Found {len(positions_data)} positions ===")
    for i, pos in enumerate(positions_data, 1):
        print(f"\nPosition {i}:")
        for key, value in pos.items():
            print(f"  {key}: {value}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
