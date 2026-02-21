#!/usr/bin/env python3
"""
Listen for real-time updates from MT4 EA on PUB socket.
This should receive the updates every minute that we see in the MT4 logs.
"""
import json
import zmq
import sys

def main():
    host = "75.154.254.174"
    pub_port = 5556

    print(f"Connecting to MT4 PUB socket at tcp://{host}:{pub_port}")
    print("Waiting for real-time updates...")
    print("=" * 80)

    # Create ZMQ context and SUB socket
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
    socket.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to ALL messages

    # Connect
    socket.connect(f"tcp://{host}:{pub_port}")

    print("✓ Connected! Listening for messages...")
    print("  (Press Ctrl+C to stop)")
    print("=" * 80)

    message_count = 0

    try:
        while True:
            try:
                # Receive message
                message_str = socket.recv_string()
                message_count += 1

                # Parse JSON
                try:
                    message = json.loads(message_str)
                    msg_type = message.get("type", "unknown")

                    print(f"\n📨 Message #{message_count}: {msg_type}")

                    if msg_type == "real_time_update":
                        data = message
                        print(f"   Symbol: {data.get('symbol')}")
                        print(f"   Market Open: {data.get('market_open')}")

                        price_data = data.get('price_data', {})
                        print(f"   Price: O={price_data.get('open')} H={price_data.get('high')} L={price_data.get('low')} C={price_data.get('close')}")

                        signals = data.get('signals', {})
                        print(f"   Signals: CCI={signals.get('cci_signal')} BB={signals.get('bb_signal')} MACD={signals.get('macd_signal')}")

                    elif msg_type == "test_message":
                        print(f"   Content: {message.get('content')}")

                    else:
                        print(f"   Full message: {message}")

                except json.JSONDecodeError:
                    print(f"   Raw (not JSON): {message_str[:200]}")

            except zmq.error.Again:
                # Timeout - no message in last 5 seconds
                print(".", end="", flush=True)

    except KeyboardInterrupt:
        print(f"\n\n✓ Stopped. Received {message_count} messages total.")

    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    main()
