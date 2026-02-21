#!/usr/bin/env python3
"""
Test REQ/REP socket with MT4 EA.
This should work if the EA is responding to commands.
"""
import json
import zmq
import time

def main():
    host = "75.154.254.174"
    rep_port = 5555

    print(f"Connecting to MT4 REP socket at tcp://{host}:{rep_port}")
    print("=" * 80)

    # Create ZMQ context and REQ socket
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
    socket.setsockopt(zmq.LINGER, 0)

    # Connect
    socket.connect(f"tcp://{host}:{rep_port}")
    print("✓ Connected!")
    print()

    # Test 1: test_connection
    print("Test 1: Sending test_connection command...")
    command = {
        "command": "test_connection",
        "correlation_id": "python-test-001"
    }

    start = time.time()
    socket.send_string(json.dumps(command))
    print(f"  Sent at {time.strftime('%H:%M:%S')}")

    try:
        response_str = socket.recv_string()
        elapsed = time.time() - start
        print(f"  ✅ Response received in {elapsed*1000:.0f}ms")
        response = json.loads(response_str)
        print(f"  Response: {json.dumps(response, indent=2)}")
    except zmq.error.Again:
        print(f"  ❌ TIMEOUT after 5 seconds")
        socket.close()
        context.term()
        return False

    print()

    # Test 2: get_symbols (needs fresh socket!)
    print("Test 2: Sending get_symbols command...")
    command = {
        "command": "get_symbols",
        "magic_number": 100001,
        "correlation_id": "python-test-002"
    }

    start = time.time()
    socket.send_string(json.dumps(command))
    print(f"  Sent at {time.strftime('%H:%M:%S')}")

    try:
        response_str = socket.recv_string()
        elapsed = time.time() - start
        print(f"  ✅ Response received in {elapsed*1000:.0f}ms")
        response = json.loads(response_str)
        if "symbols" in response:
            print(f"  Symbols count: {len(response['symbols'])}")
            print(f"  First 10: {response['symbols'][:10]}")
        else:
            print(f"  Response: {json.dumps(response, indent=2)}")
    except zmq.error.Again:
        print(f"  ❌ TIMEOUT after 5 seconds")
        socket.close()
        context.term()
        return False

    socket.close()
    context.term()

    print()
    print("=" * 80)
    print("✅ SUCCESS! Both commands worked!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
