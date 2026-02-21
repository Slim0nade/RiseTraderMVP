import asyncio
import json
from src.trading.execution.mt4_client import MT4Client
from src.trading.execution.mt4_models import GetOpenPositionsCommand
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
    
    await client.connect()
    command = GetOpenPositionsCommand()
    response = await client.send_command(command)
    
    print("=== RAW MT4 RESPONSE ===")
    print(json.dumps(response, indent=2, default=str))
    
    # Extract positions like the sync service does
    if "data" in response:
        positions_data = response.get("data", {}).get("positions", [])
    else:
        positions_data = response.get("positions", [])
    
    print(f"\n=== POSITIONS DATA ({len(positions_data)} positions) ===")
    for i, pos in enumerate(positions_data):
        print(f"\nPosition {i+1}:")
        print(json.dumps(pos, indent=2, default=str))
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
