#!/usr/bin/env python3
"""
Mock MT4 EA for integration testing.

This Python-based mock simulates an MT4 Expert Advisor for testing purposes.
It implements the same ZMQ protocol as the real MQL4 EA without requiring MT4.

Usage:
    python tests/integration/mock_mt4_ea.py
    python tests/integration/mock_mt4_ea.py --port 5555 --magic 100001
"""
import argparse
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal
from threading import Thread
from typing import Dict, List, Optional

import zmq


class MockPosition:
    """Represents a mock open position."""

    def __init__(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        volume: Decimal,
        open_price: Decimal,
        magic_number: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None
    ):
        self.ticket = ticket
        self.symbol = symbol
        self.direction = direction
        self.volume = volume
        self.open_price = open_price
        self.current_price = open_price
        self.magic_number = magic_number
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.open_time = datetime.utcnow()
        self.unrealized_pnl = Decimal('0.0')

    def update_price(self, bid: Decimal, ask: Decimal):
        """Update current price and calculate P&L."""
        self.current_price = bid if self.direction == "BUY" else ask
        price_diff = self.current_price - self.open_price

        if self.direction == "SELL":
            price_diff = -price_diff

        # Simplified P&L calculation (assumes 1000 contract size)
        self.unrealized_pnl = price_diff * self.volume * Decimal('1000')

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": float(self.volume),
            "open_price": float(self.open_price),
            "current_price": float(self.current_price),
            "unrealized_pnl": float(self.unrealized_pnl),
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "take_profit": float(self.take_profit) if self.take_profit else None,
            "magic_number": self.magic_number
        }


class MockMT4EA:
    """
    Mock MT4 Expert Advisor.

    Simulates MT4 EA behavior with ZMQ sockets for testing.
    """

    def __init__(
        self,
        rep_port: int = 5555,
        pub_port: int = 5556,
        magic_number: int = 100001,
        symbol: str = "CrudeOIL",
        enable_encryption: bool = False
    ):
        """
        Initialize mock MT4 EA.

        Args:
            rep_port: REP socket port for commands
            pub_port: PUB socket port for streaming
            magic_number: Magic number for this EA
            symbol: Primary trading symbol
            enable_encryption: Enable CurveZMQ (for testing)
        """
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.magic_number = magic_number
        self.symbol = symbol
        self.enable_encryption = enable_encryption

        # State
        self.is_running = False
        self.next_ticket = 10001
        self.positions: Dict[int, MockPosition] = {}
        self.account_balance = Decimal('50000.00')
        self.account_equity = Decimal('50000.00')

        # Market data simulation
        self.current_bid = Decimal('75.50')
        self.current_ask = Decimal('75.55')

        # ZMQ sockets
        self.context = None
        self.rep_socket = None
        self.pub_socket = None

        # Threads
        self.command_thread = None
        self.streaming_thread = None

    def start(self):
        """Start the mock EA."""
        print(f"Starting Mock MT4 EA...")
        print(f"  Magic Number: {self.magic_number}")
        print(f"  REP Port: {self.rep_port}")
        print(f"  PUB Port: {self.pub_port}")
        print(f"  Symbol: {self.symbol}")
        print(f"  Encryption: {'ENABLED' if self.enable_encryption else 'DISABLED'}")

        # Initialize ZMQ
        self.context = zmq.Context()

        # Setup REP socket
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.bind(f"tcp://*:{self.rep_port}")
        print(f"  REP socket bound to tcp://*:{self.rep_port}")

        # Setup PUB socket
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{self.pub_port}")
        print(f"  PUB socket bound to tcp://*:{self.pub_port}")

        # Publish initial connection status
        self.publish_connection_status("ACTIVE", "")

        # Start threads
        self.is_running = True
        self.command_thread = Thread(target=self._command_loop, daemon=True)
        self.streaming_thread = Thread(target=self._streaming_loop, daemon=True)

        self.command_thread.start()
        self.streaming_thread.start()

        print("✓ Mock MT4 EA started successfully")
        print("Press Ctrl+C to stop...")

    def stop(self):
        """Stop the mock EA."""
        print("\nStopping Mock MT4 EA...")
        self.is_running = False

        # Publish disconnection
        self.publish_connection_status("INACTIVE", "EA stopped")

        # Close sockets
        if self.rep_socket:
            self.rep_socket.close()
        if self.pub_socket:
            self.pub_socket.close()
        if self.context:
            self.context.term()

        print("✓ Mock MT4 EA stopped")

    def _command_loop(self):
        """Process incoming commands."""
        while self.is_running:
            try:
                # Receive command (with timeout)
                if self.rep_socket.poll(100):  # 100ms timeout
                    message = self.rep_socket.recv_string()
                    print(f"\n📨 Received command: {message[:100]}...")

                    # Process command
                    response = self.handle_command(message)

                    # Send response
                    self.rep_socket.send_string(response)
                    print(f"📤 Sent response: {response[:100]}...")

            except Exception as e:
                print(f"❌ Error in command loop: {e}")
                if self.is_running:
                    time.sleep(0.1)

    def _streaming_loop(self):
        """Publish streaming data."""
        last_tick = time.time()
        last_heartbeat = time.time()

        while self.is_running:
            try:
                current_time = time.time()

                # Publish market ticks every second
                if current_time - last_tick >= 1.0:
                    self._simulate_market_movement()
                    self.publish_market_tick()
                    self._check_position_updates()
                    last_tick = current_time

                # Publish heartbeat every 30 seconds
                if current_time - last_heartbeat >= 30.0:
                    self.publish_heartbeat()
                    last_heartbeat = current_time

                time.sleep(0.1)

            except Exception as e:
                print(f"❌ Error in streaming loop: {e}")
                if self.is_running:
                    time.sleep(0.1)

    def handle_command(self, command_json: str) -> str:
        """Handle incoming command and return response."""
        try:
            command = json.loads(command_json)
            command_type = command.get("command")

            if command_type == "create_instant_order":
                return self._handle_create_order(command)
            elif command_type == "get_account_info":
                return self._handle_get_account_info(command)
            elif command_type == "get_open_positions":
                return self._handle_get_open_positions(command)
            elif command_type == "close_position":
                return self._handle_close_position(command)
            elif command_type == "test_connection":
                return self._handle_test_connection(command)
            else:
                return json.dumps({
                    "success": False,
                    "error_code": 1000,
                    "error_message": f"Unknown command: {command_type}"
                })

        except Exception as e:
            return json.dumps({
                "success": False,
                "error_code": 1001,
                "error_message": f"Command processing error: {str(e)}"
            })

    def _handle_create_order(self, command: dict) -> str:
        """Handle create_instant_order command."""
        symbol = command.get("symbol", self.symbol)
        direction = command.get("direction")
        volume = Decimal(str(command.get("volume")))
        stop_loss = Decimal(str(command.get("stop_loss"))) if command.get("stop_loss") else None
        take_profit = Decimal(str(command.get("take_profit"))) if command.get("take_profit") else None

        # Generate ticket number
        ticket = self.next_ticket
        self.next_ticket += 1

        # Get execution price
        execution_price = self.current_ask if direction == "BUY" else self.current_bid

        # Create position
        position = MockPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=execution_price,
            magic_number=self.magic_number,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        self.positions[ticket] = position

        print(f"  ✓ Created {direction} order: ticket={ticket}, volume={volume}, price={execution_price}")

        # Publish order_confirmed event
        self.publish_order_confirmed(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            execution_price=execution_price
        )

        return json.dumps({
            "success": True,
            "ticket_number": ticket,
            "execution_price": float(execution_price),
            "execution_time": datetime.utcnow().isoformat(),
            "correlation_id": command.get("correlation_id")
        })

    def _handle_get_account_info(self, command: dict) -> str:
        """Handle get_account_info command."""
        # Calculate margin used
        margin_used = Decimal('0.0')
        for position in self.positions.values():
            # Simplified margin calculation
            margin_used += position.volume * position.open_price

        free_margin = self.account_equity - margin_used
        margin_level = (self.account_equity / margin_used * 100) if margin_used > 0 else Decimal('999.99')

        return json.dumps({
            "success": True,
            "account_number": 12345678,
            "balance": float(self.account_balance),
            "equity": float(self.account_equity),
            "margin": float(margin_used),
            "free_margin": float(free_margin),
            "margin_level": float(margin_level),
            "leverage": 100,
            "correlation_id": command.get("correlation_id")
        })

    def _handle_get_open_positions(self, command: dict) -> str:
        """Handle get_open_positions command."""
        positions = [pos.to_dict() for pos in self.positions.values()]

        return json.dumps({
            "success": True,
            "positions": positions,
            "correlation_id": command.get("correlation_id")
        })

    def _handle_close_position(self, command: dict) -> str:
        """Handle close_position command."""
        # Support both 'ticket' and 'ticket_number' for backwards compatibility
        ticket = command.get("ticket") or command.get("ticket_number")

        if ticket in self.positions:
            position = self.positions.pop(ticket)
            print(f"  ✓ Closed position: ticket={ticket}, P&L={position.unrealized_pnl}")

            # Publish position_closed event
            self.publish_position_closed(ticket)

            return json.dumps({
                "success": True,
                "ticket": ticket,
                "correlation_id": command.get("correlation_id")
            })
        else:
            return json.dumps({
                "success": False,
                "error_code": 4108,
                "error_message": f"Position {ticket} not found",
                "correlation_id": command.get("correlation_id")
            })

    def _handle_test_connection(self, command: dict) -> str:
        """Handle test_connection command."""
        return json.dumps({
            "success": True,
            "message": "Connection OK",
            "magic_number": self.magic_number,
            "symbol": self.symbol,
            "server_time": datetime.utcnow().isoformat(),
            "correlation_id": command.get("correlation_id")
        })

    def _simulate_market_movement(self):
        """Simulate random market price movement."""
        import random

        # Random walk (±0.5%)
        change_pct = Decimal(str(random.uniform(-0.005, 0.005)))
        self.current_bid *= (1 + change_pct)
        self.current_ask = self.current_bid + Decimal('0.05')  # 5 pip spread

        # Update all positions
        for position in self.positions.values():
            position.update_price(self.current_bid, self.current_ask)

    def _check_position_updates(self):
        """Check and publish position updates."""
        for position in self.positions.values():
            self.publish_position_updated(position)

    def publish_market_tick(self):
        """Publish market_tick event."""
        event = {
            "event_type": "market_tick",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": self.symbol,
                "bid": float(self.current_bid),
                "ask": float(self.current_ask)
            }
        }
        self.pub_socket.send_string(json.dumps(event))

    def publish_order_confirmed(self, ticket: int, symbol: str, direction: str,
                                volume: Decimal, execution_price: Decimal):
        """Publish order_confirmed event."""
        event = {
            "event_type": "order_confirmed",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "ticket_number": ticket,
                "magic_number": self.magic_number,
                "symbol": symbol,
                "direction": direction,
                "volume": float(volume),
                "execution_price": float(execution_price),
                "execution_time": datetime.utcnow().isoformat()
            }
        }
        self.pub_socket.send_string(json.dumps(event))
        print(f"  📡 Published order_confirmed event for ticket {ticket}")

    def publish_position_updated(self, position: MockPosition):
        """Publish position_updated event."""
        event = {
            "event_type": "position_updated",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "ticket_number": position.ticket,
                "magic_number": self.magic_number,
                "symbol": position.symbol,
                "direction": position.direction,
                "volume": float(position.volume),
                "open_price": float(position.open_price),
                "current_price": float(position.current_price),
                "unrealized_pnl": float(position.unrealized_pnl),
                "stop_loss": float(position.stop_loss) if position.stop_loss else None,
                "take_profit": float(position.take_profit) if position.take_profit else None,
                "open_time": position.open_time.isoformat(),
                "last_updated": datetime.utcnow().isoformat()
            }
        }
        self.pub_socket.send_string(json.dumps(event))

    def publish_position_closed(self, ticket: int):
        """Publish position_closed event."""
        event = {
            "event_type": "position_closed",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "ticket_number": ticket,
                "magic_number": self.magic_number
            }
        }
        self.pub_socket.send_string(json.dumps(event))
        print(f"  📡 Published position_closed event for ticket {ticket}")

    def publish_connection_status(self, status: str, error: str):
        """Publish connection_status_changed event."""
        event = {
            "event_type": "connection_status_changed",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "magic_number": self.magic_number,
                "status": status,
                "error_message": error
            }
        }
        self.pub_socket.send_string(json.dumps(event))
        print(f"  📡 Published connection_status: {status}")

    def publish_heartbeat(self):
        """Publish heartbeat event."""
        event = {
            "event_type": "heartbeat",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "magic_number": self.magic_number
            }
        }
        self.pub_socket.send_string(json.dumps(event))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Mock MT4 EA for testing")
    parser.add_argument("--rep-port", type=int, default=5555, help="REP socket port")
    parser.add_argument("--pub-port", type=int, default=5556, help="PUB socket port")
    parser.add_argument("--magic", type=int, default=100001, help="Magic number")
    parser.add_argument("--symbol", type=str, default="CrudeOIL", help="Trading symbol")
    parser.add_argument("--encryption", action="store_true", help="Enable encryption")

    args = parser.parse_args()

    ea = MockMT4EA(
        rep_port=args.rep_port,
        pub_port=args.pub_port,
        magic_number=args.magic,
        symbol=args.symbol,
        enable_encryption=args.encryption
    )

    try:
        ea.start()

        # Keep running until interrupted
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        ea.stop()


if __name__ == "__main__":
    main()
