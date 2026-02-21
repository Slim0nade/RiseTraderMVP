#!/usr/bin/env python3
"""Test MT4 connection from Docker container."""
import asyncio
import sys
sys.path.insert(0, "/app")

async def test():
    from src.trading.execution.mt4_client import MT4Client
    from src.trading.execution.mt4_encryption import MT4EncryptionManager
    
    enc = MT4EncryptionManager(encryption_enabled=False)
    client = MT4Client(
        host="192.168.0.123",
        rep_port=5555,
        pub_port=5556,
        magic_number=123456,
        encryption_manager=enc,
        timeout_ms=5000,
        enable_circuit_breaker=False
    )
    
    await client.connect()
    print("✅ Connected to MT4 from Docker!")
    
    result = await client.get_account_info()
    info = result.get("account_info", {})
    print(f"✅ Account Balance: ${info.get('balance', 'N/A')}")
    
    pending = await client.get_pending_orders()
    orders = pending.get("orders", [])
    print(f"✅ Pending Orders: {len(orders)}")
    
    await client.disconnect()
    print("✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(test())
