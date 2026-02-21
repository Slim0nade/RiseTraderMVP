#!/usr/bin/env python3
"""
Network Location Switcher CLI

Easily switch between LOCAL (home) and REMOTE (internet) network locations.

Usage:
    python scripts/switch_network.py local   # Switch to home network
    python scripts/switch_network.py remote  # Switch to internet
    python scripts/switch_network.py status  # Show current location
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.network_config import (
    NetworkLocation,
    NetworkLocationManager,
    get_network_manager,
)


def update_env_file(location: NetworkLocation) -> None:
    """
    Update .env file with new network location.

    Args:
        location: Network location to set
    """
    env_file = project_root / ".env"
    if not env_file.exists():
        print(f"❌ Error: .env file not found at {env_file}")
        sys.exit(1)

    # Read current .env
    with open(env_file, "r") as f:
        lines = f.readlines()

    # Update NETWORK_LOCATION line
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("NETWORK_LOCATION="):
            lines[i] = f"NETWORK_LOCATION={location.value}\n"
            updated = True
            break

    if not updated:
        # Add if not found
        lines.append(f"\nNETWORK_LOCATION={location.value}\n")

    # Get config for the location
    manager = NetworkLocationManager(location)
    mt4_config = manager.get_mt4_config()
    ollama_config = manager.get_ollama_config()

    # Update MT4_HOST
    for i, line in enumerate(lines):
        if line.startswith("MT4_HOST="):
            lines[i] = f"MT4_HOST={mt4_config.host}\n"

    # Update OLLAMA_BASE_URL
    for i, line in enumerate(lines):
        if line.startswith("OLLAMA_BASE_URL="):
            lines[i] = f"OLLAMA_BASE_URL={ollama_config.base_url}\n"

    # Write back
    with open(env_file, "w") as f:
        f.writelines(lines)

    print(f"✅ Updated .env file with {location.value.upper()} configuration")


def show_status() -> None:
    """Show current network location status."""
    manager = get_network_manager()
    mt4_config = manager.get_mt4_config()
    ollama_config = manager.get_ollama_config()

    print("\n" + "="*60)
    print(f"🌐 CURRENT NETWORK LOCATION: {manager.location.value.upper()}")
    print("="*60)

    print("\n📡 MT4 Connection:")
    print(f"   Host:            {mt4_config.host}")
    print(f"   Command Port:    {mt4_config.command_port}")
    print(f"   Stream Port:     {mt4_config.stream_port}")
    print(f"   Command Endpoint: {mt4_config.command_endpoint}")
    print(f"   Stream Endpoint:  {mt4_config.stream_endpoint}")

    print("\n🤖 Ollama Connection:")
    print(f"   Base URL:        {ollama_config.base_url}")
    print(f"   API URL:         {ollama_config.api_url}")
    print(f"   Timeout:         {ollama_config.timeout}s")
    print(f"   Max Retries:     {ollama_config.max_retries}")

    print("\n" + "="*60)
    print("\nℹ️  To switch locations:")
    print("   python scripts/switch_network.py local")
    print("   python scripts/switch_network.py remote")
    print("="*60 + "\n")


def test_connections() -> None:
    """Test connections to MT4 and Ollama."""
    import requests
    import zmq

    manager = get_network_manager()
    mt4_config = manager.get_mt4_config()
    ollama_config = manager.get_ollama_config()

    print("\n🧪 Testing Connections...")
    print("="*60)

    # Test Ollama
    print(f"\n1️⃣  Testing Ollama at {ollama_config.base_url}...")
    try:
        response = requests.get(
            f"{ollama_config.base_url}/api/tags",
            timeout=5
        )
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"   ✅ Ollama is accessible")
            print(f"   📦 Available models: {len(models)}")
            for model in models[:3]:  # Show first 3
                print(f"      - {model.get('name', 'unknown')}")
        else:
            print(f"   ❌ Ollama returned status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Cannot connect to Ollama: {e}")

    # Test MT4 (basic ZMQ connection test)
    print(f"\n2️⃣  Testing MT4 at {mt4_config.host}:{mt4_config.command_port}...")
    try:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s timeout
        socket.connect(mt4_config.command_endpoint)

        # Try to send a ping
        socket.send_json({"command": "PING"})

        try:
            response = socket.recv_json()
            print(f"   ✅ MT4 is accessible")
            print(f"   📨 Response: {response}")
        except zmq.Again:
            print(f"   ⚠️  MT4 port is open but no response (EA may not be running)")

        socket.close()
        context.term()

    except zmq.ZMQError as e:
        print(f"   ❌ Cannot connect to MT4: {e}")
    except Exception as e:
        print(f"   ❌ Error testing MT4: {e}")

    print("\n" + "="*60 + "\n")


def restart_api() -> bool:
    """
    Restart the API container to apply network changes.

    Returns:
        True if successful, False otherwise
    """
    import subprocess

    print("\n🔄 Restarting API container...")

    try:
        # Try docker restart first (faster)
        result = subprocess.run(
            ["docker", "restart", "risetrader-api"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("✅ API container restarted successfully")
            return True
        else:
            # Fall back to docker-compose
            print("   Trying docker-compose...")
            result = subprocess.run(
                ["docker-compose", "restart", "api"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_root
            )

            if result.returncode == 0:
                print("✅ API container restarted successfully")
                return True
            else:
                print(f"⚠️  Failed to restart API: {result.stderr}")
                return False

    except subprocess.TimeoutExpired:
        print("⚠️  Restart timed out (30s)")
        return False
    except FileNotFoundError:
        print("⚠️  Docker not found. Please restart manually:")
        print("   docker restart risetrader-api")
        return False
    except Exception as e:
        print(f"⚠️  Error restarting API: {e}")
        return False


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("❌ Usage: python scripts/switch_network.py [local|remote|status|test]")
        sys.exit(1)

    command = sys.argv[1].lower()

    # Check for --no-restart flag
    no_restart = "--no-restart" in sys.argv

    if command == "status":
        show_status()

    elif command == "test":
        show_status()
        test_connections()

    elif command in ["local", "home"]:
        location = NetworkLocation.LOCAL
        print(f"\n🔄 Switching to LOCAL network (192.168.0.123)...")
        update_env_file(location)

        manager = NetworkLocationManager(location)
        mt4_config = manager.get_mt4_config()
        ollama_config = manager.get_ollama_config()

        print(f"\n✅ Network location switched to LOCAL")
        print(f"   MT4:    {mt4_config.host}")
        print(f"   Ollama: {ollama_config.base_url}")

        if not no_restart:
            if restart_api():
                print(f"\n🎉 All done! Now using LOCAL network (192.168.0.123)")
            else:
                print(f"\n⚠️  Please restart API manually:")
                print(f"   docker restart risetrader-api")
        else:
            print(f"\n⚠️  Restart skipped (--no-restart flag)")
            print(f"   Restart manually: docker restart risetrader-api")
        print()

    elif command in ["remote", "internet", "wan"]:
        location = NetworkLocation.REMOTE
        print(f"\n🔄 Switching to REMOTE network (75.154.254.174)...")
        update_env_file(location)

        manager = NetworkLocationManager(location)
        mt4_config = manager.get_mt4_config()
        ollama_config = manager.get_ollama_config()

        print(f"\n✅ Network location switched to REMOTE")
        print(f"   MT4:    {mt4_config.host}")
        print(f"   Ollama: {ollama_config.base_url}")

        if not no_restart:
            if restart_api():
                print(f"\n🎉 All done! Now using REMOTE network (75.154.254.174)")
            else:
                print(f"\n⚠️  Please restart API manually:")
                print(f"   docker restart risetrader-api")
        else:
            print(f"\n⚠️  Restart skipped (--no-restart flag)")
            print(f"   Restart manually: docker restart risetrader-api")
        print()

    else:
        print(f"❌ Unknown command: {command}")
        print("   Valid commands: local, remote, status, test")
        sys.exit(1)


if __name__ == "__main__":
    main()
