"""
Debug script to see raw MT4 responses.
"""
import asyncio
import json
import zmq
import zmq.asyncio

async def test_raw_responses():
    """Send raw commands and print responses."""

    context = zmq.asyncio.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://75.154.254.186:5555")

    print("=" * 80)
    print("RAW MT4 RESPONSE DEBUG")
    print("=" * 80)
    print()

    # Test 1: get_symbols
    print("TEST 1: get_symbols command")
    print("-" * 80)
    command = {
        "command": "get_symbols",
        "magic_number": 100001,
        "correlation_id": "test-123"
    }
    print(f"Sending: {json.dumps(command, indent=2)}")
    await socket.send_string(json.dumps(command))

    if await socket.poll(timeout=5000):
        response = await socket.recv_string()
        print(f"Received: {response}")
        try:
            parsed = json.loads(response)
            print(f"Parsed JSON: {json.dumps(parsed, indent=2)}")
        except:
            print("Failed to parse as JSON")
    else:
        print("TIMEOUT")
    print()

    # Test 2: get_account_info
    print("TEST 2: get_account_info command")
    print("-" * 80)
    command = {
        "command": "get_account_info",
        "magic_number": 100001,
        "correlation_id": "test-456"
    }
    print(f"Sending: {json.dumps(command, indent=2)}")
    await socket.send_string(json.dumps(command))

    if await socket.poll(timeout=5000):
        response = await socket.recv_string()
        print(f"Received: {response}")
        try:
            parsed = json.loads(response)
            print(f"Parsed JSON: {json.dumps(parsed, indent=2)}")
        except:
            print("Failed to parse as JSON")
    else:
        print("TIMEOUT")
    print()

    # Test 3: test_connection
    print("TEST 3: test_connection command")
    print("-" * 80)
    command = {
        "command": "test_connection",
        "magic_number": 100001,
        "correlation_id": "test-789"
    }
    print(f"Sending: {json.dumps(command, indent=2)}")
    await socket.send_string(json.dumps(command))

    if await socket.poll(timeout=5000):
        response = await socket.recv_string()
        print(f"Received: {response}")
        try:
            parsed = json.loads(response)
            print(f"Parsed JSON: {json.dumps(parsed, indent=2)}")
        except:
            print("Failed to parse as JSON")
    else:
        print("TIMEOUT")

    socket.close()
    context.term()

if __name__ == "__main__":
    asyncio.run(test_raw_responses())
