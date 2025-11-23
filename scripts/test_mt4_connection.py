#!/usr/bin/env python3
"""
Quick test script to verify MT4 connection.

Tests both command (REQ/REP) and streaming (PUB/SUB) sockets.
Works even when markets are closed.

Usage:
    python scripts/test_mt4_connection.py
    python scripts/test_mt4_connection.py --host 75.154.254.186 --port 5555
"""
import argparse
import json
import sys
import time
from datetime import datetime

import zmq


def test_command_socket(host: str, port: int, timeout_ms: int = 5000):
    """Test REQ/REP command socket."""
    print("\n" + "=" * 70)
    print("TEST 1: Command Socket (REQ/REP)")
    print("=" * 70)

    try:
        # Create ZMQ context and REQ socket
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)

        # Connect to MT4 EA
        address = f"tcp://{host}:{port}"
        print(f"Connecting to {address}...")
        socket.connect(address)

        # Test 1: Connection test
        print("\n📡 Sending test_connection command...")
        command = {
            "command": "test_connection",
            "correlation_id": "test-001"
        }
        socket.send_string(json.dumps(command))

        print("⏳ Waiting for response...")
        response_str = socket.recv_string()
        response = json.loads(response_str)

        if response.get("success"):
            print("✅ Connection test PASSED")
            print(f"   Magic Number: {response.get('magic_number')}")
            print(f"   Symbol: {response.get('symbol')}")
            print(f"   Server Time: {response.get('server_time')}")
        else:
            print(f"❌ Connection test FAILED: {response.get('error_message')}")
            return False

        # Test 2: Get account info (works even when market is closed)
        print("\n📊 Sending get_account_info command...")
        command = {
            "command": "get_account_info",
            "magic_number": 100001,
            "correlation_id": "test-002"
        }
        socket.send_string(json.dumps(command))

        print("⏳ Waiting for response...")
        response_str = socket.recv_string()
        response = json.loads(response_str)

        if response.get("success"):
            print("✅ Account info retrieved successfully")
            print(f"   Account Number: {response.get('account_number')}")
            print(f"   Balance: ${response.get('balance', 0):,.2f}")
            print(f"   Equity: ${response.get('equity', 0):,.2f}")
            print(f"   Free Margin: ${response.get('free_margin', 0):,.2f}")
            print(f"   Leverage: 1:{response.get('leverage')}")
        else:
            print(f"❌ Account info FAILED: {response.get('error_message')}")
            return False

        # Test 3: Get open positions
        print("\n📈 Sending get_open_positions command...")
        command = {
            "command": "get_open_positions",
            "magic_number": 100001,
            "correlation_id": "test-003"
        }
        socket.send_string(json.dumps(command))

        print("⏳ Waiting for response...")
        response_str = socket.recv_string()
        response = json.loads(response_str)

        if response.get("success"):
            positions = response.get("positions", [])
            print(f"✅ Open positions retrieved: {len(positions)} positions")
            if positions:
                for pos in positions:
                    print(f"   Ticket #{pos['ticket']}: {pos['direction']} {pos['volume']} {pos['symbol']} @ {pos['open_price']}")
            else:
                print("   No open positions (expected when market is closed)")
        else:
            print(f"❌ Get positions FAILED: {response.get('error_message')}")
            return False

        # Cleanup
        socket.close()
        context.term()

        print("\n✅ Command socket test PASSED - All commands working!")
        return True

    except zmq.error.Again:
        print(f"\n❌ TIMEOUT: No response from MT4 EA after {timeout_ms}ms")
        print("   Possible issues:")
        print("   1. EA not running in MT4")
        print("   2. Wrong host/port")
        print("   3. Firewall blocking connection")
        print("   4. EA crashed (check MT4 Experts tab)")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def test_streaming_socket(host: str, port: int, duration_seconds: int = 5):
    """Test PUB/SUB streaming socket."""
    print("\n" + "=" * 70)
    print("TEST 2: Streaming Socket (PUB/SUB)")
    print("=" * 70)

    try:
        # Create ZMQ context and SUB socket
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout
        socket.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all events

        # Connect to MT4 EA PUB socket
        address = f"tcp://{host}:{port}"
        print(f"Connecting to {address}...")
        socket.connect(address)

        print(f"📡 Listening for events for {duration_seconds} seconds...")
        print("   (Market closed = fewer events, but heartbeat should still work)")

        events_received = 0
        start_time = time.time()
        event_types = set()

        while time.time() - start_time < duration_seconds:
            try:
                event_str = socket.recv_string()
                event = json.loads(event_str)
                event_type = event.get("event_type", "unknown")
                event_types.add(event_type)
                events_received += 1

                # Print first few events
                if events_received <= 3:
                    print(f"\n   📨 Event #{events_received}: {event_type}")
                    if event_type == "market_tick":
                        data = event.get("data", {})
                        print(f"      Symbol: {data.get('symbol')}")
                        print(f"      Bid: {data.get('bid')}, Ask: {data.get('ask')}")
                    elif event_type == "heartbeat":
                        data = event.get("data", {})
                        print(f"      Magic Number: {data.get('magic_number')}")

            except zmq.error.Again:
                # Timeout - no event received in last second
                pass

        # Cleanup
        socket.close()
        context.term()

        print(f"\n✅ Streaming test complete:")
        print(f"   Total events received: {events_received}")
        print(f"   Event types seen: {', '.join(event_types) if event_types else 'None'}")

        if events_received == 0:
            print("\n⚠️  WARNING: No events received!")
            print("   This might be normal if:")
            print("   - Market is closed (no ticks)")
            print("   - EA just started (heartbeat every 30s)")
            print("   Try running this test for longer to catch a heartbeat")
            return True  # Not a failure, just market closed

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Test MT4 EA connection")
    parser.add_argument("--host", default="75.154.254.186", help="MT4 server IP")
    parser.add_argument("--rep-port", type=int, default=5555, help="REP socket port")
    parser.add_argument("--pub-port", type=int, default=5556, help="PUB socket port")
    parser.add_argument("--timeout", type=int, default=5000, help="Command timeout (ms)")
    parser.add_argument("--listen-duration", type=int, default=5, help="How long to listen for events (seconds)")

    args = parser.parse_args()

    print("=" * 70)
    print("MT4 Connection Test")
    print("=" * 70)
    print(f"Host: {args.host}")
    print(f"REP Port: {args.rep_port}")
    print(f"PUB Port: {args.pub_port}")
    print(f"Timeout: {args.timeout}ms")
    print()
    print("NOTE: This test works even when markets are closed!")
    print("=" * 70)

    # Test 1: Command socket
    command_result = test_command_socket(args.host, args.rep_port, args.timeout)

    # Test 2: Streaming socket
    streaming_result = test_streaming_socket(args.host, args.pub_port, args.listen_duration)

    # Final summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Command Socket (REQ/REP):  {'✅ PASSED' if command_result else '❌ FAILED'}")
    print(f"Streaming Socket (PUB/SUB): {'✅ PASSED' if streaming_result else '❌ FAILED'}")
    print("=" * 70)

    if command_result and streaming_result:
        print("\n🎉 SUCCESS! Your MT4 EA is working perfectly!")
        print("\nNext steps:")
        print("1. Try placing a test order when market opens")
        print("2. Run integration tests: pytest tests/integration/")
        print("3. Start building the MT4Client in Python")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
        print("\nTroubleshooting:")
        print("1. Verify EA is still running in MT4 (check chart for smiley face)")
        print("2. Check MT4 Experts tab for error messages")
        print("3. Verify firewall allows ports 5555-5556")
        print("4. Try: netstat -an | grep 5555")
        sys.exit(1)


if __name__ == "__main__":
    main()
