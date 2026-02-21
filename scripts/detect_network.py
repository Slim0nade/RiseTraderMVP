#!/usr/bin/env python3
"""
Automatic Network Detection for RiseTrader

Detects whether to use LOCAL or REMOTE network based on server availability.
Tries LOCAL first (faster), falls back to REMOTE if unreachable.

Usage:
    python3 scripts/detect_network.py           # Detect and switch
    python3 scripts/detect_network.py --test    # Just test, don't switch
    python3 scripts/detect_network.py --status  # Show current status
"""
import socket
import sys
from pathlib import Path

# Network configurations
LOCAL_IP = "192.168.0.123"
REMOTE_IP = "75.154.254.174"
TEST_PORT = 5555  # MT4 command port


def test_connection(host: str, port: int, timeout: int = 3) -> bool:
    """
    Test if a host:port is reachable.

    Args:
        host: IP address or hostname
        port: Port number
        timeout: Connection timeout in seconds

    Returns:
        True if connection succeeds, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"  ⚠️  Exception testing {host}:{port}: {e}")
        return False


def detect_network() -> tuple[str, str]:
    """
    Detect which network is currently accessible.

    Returns:
        Tuple of (network_name, ip_address)
        network_name: "local" or "remote"
        ip_address: IP address to use
    """
    print("🔍 Detecting network location...")
    print()

    # Try LOCAL first (faster if at home)
    print(f"  Testing LOCAL network ({LOCAL_IP})...")
    if test_connection(LOCAL_IP, TEST_PORT, timeout=2):
        print(f"  ✅ LOCAL network is accessible!")
        return "local", LOCAL_IP
    else:
        print(f"  ❌ LOCAL network unreachable (not at home)")

    print()

    # Fall back to REMOTE
    print(f"  Testing REMOTE network ({REMOTE_IP})...")
    if test_connection(REMOTE_IP, TEST_PORT, timeout=5):
        print(f"  ✅ REMOTE network is accessible!")
        return "remote", REMOTE_IP
    else:
        print(f"  ❌ REMOTE network unreachable")
        print()
        print("  ⚠️  WARNING: Neither local nor remote server is accessible!")
        print("  ⚠️  MT4 server may be down or network issues exist.")
        return None, None


def get_current_config() -> dict:
    """
    Read current configuration from .env file.

    Returns:
        Dictionary with current config values
    """
    env_file = Path(__file__).parent.parent / ".env"
    config = {}

    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key] = value

    return config


def update_env_file(network: str, ip: str):
    """
    Update .env file with new network configuration.

    Args:
        network: "local" or "remote"
        ip: IP address to use
    """
    env_file = Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        print(f"  ❌ .env file not found at {env_file}")
        return False

    # Read current file
    with open(env_file, 'r') as f:
        lines = f.readlines()

    # Update lines
    updated = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('NETWORK_LOCATION='):
            updated.append(f'NETWORK_LOCATION={network}\n')
        elif stripped.startswith('MT4_HOST='):
            updated.append(f'MT4_HOST={ip}\n')
        elif stripped.startswith('OLLAMA_BASE_URL='):
            updated.append(f'OLLAMA_BASE_URL=http://{ip}:11434\n')
        else:
            updated.append(line)

    # Write back
    with open(env_file, 'w') as f:
        f.writelines(updated)

    print(f"  ✅ Updated .env file with {network.upper()} configuration")
    return True


def show_status():
    """Show current network configuration."""
    config = get_current_config()

    network = config.get('NETWORK_LOCATION', 'unknown')
    mt4_host = config.get('MT4_HOST', 'unknown')
    ollama_url = config.get('OLLAMA_BASE_URL', 'unknown')

    print("=" * 60)
    print("🌐 CURRENT NETWORK CONFIGURATION")
    print("=" * 60)
    print()
    print(f"  Network Location: {network.upper()}")
    print(f"  MT4 Host:         {mt4_host}")
    print(f"  Ollama URL:       {ollama_url}")
    print()

    # Test connectivity
    if mt4_host != 'unknown':
        print(f"  Testing connectivity to {mt4_host}...")
        if test_connection(mt4_host, TEST_PORT):
            print(f"  ✅ Server is reachable")
        else:
            print(f"  ❌ Server is NOT reachable")
            print(f"  💡 Try: python3 scripts/detect_network.py")

    print("=" * 60)


def main():
    """Main entry point."""
    # Parse arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--status':
            show_status()
            return
        elif sys.argv[1] == '--test':
            # Just test, don't switch
            network, ip = detect_network()
            if network:
                print()
                print(f"📍 Detected network: {network.upper()} ({ip})")
                print()
                config = get_current_config()
                current = config.get('NETWORK_LOCATION', 'unknown')
                if current == network:
                    print(f"  ✅ .env file is already configured for {network.upper()}")
                else:
                    print(f"  ⚠️  .env file is set to {current.upper()}, but {network.upper()} is accessible")
                    print(f"  💡 Run: python3 scripts/detect_network.py (to switch)")
            return
        elif sys.argv[1] in ['-h', '--help']:
            print(__doc__)
            return

    # Detect and switch
    print("=" * 60)
    print("🔄 AUTOMATIC NETWORK DETECTION")
    print("=" * 60)
    print()

    network, ip = detect_network()

    if not network:
        print()
        print("=" * 60)
        print("❌ DETECTION FAILED")
        print("=" * 60)
        print()
        print("Neither LOCAL nor REMOTE server is accessible.")
        print("Please check:")
        print("  1. MT4 server is running")
        print("  2. ZMQ Expert Advisor is active")
        print("  3. Firewall allows connections")
        print("  4. Network connectivity")
        print()
        sys.exit(1)

    print()
    print("=" * 60)
    print(f"✅ DETECTED: {network.upper()} NETWORK")
    print("=" * 60)
    print()

    # Check current config
    config = get_current_config()
    current = config.get('NETWORK_LOCATION', 'unknown')

    if current == network:
        print(f"  ✅ .env file is already configured for {network.upper()}")
        print(f"  No changes needed.")
    else:
        print(f"  🔄 Switching from {current.upper()} to {network.upper()}...")
        print()
        if update_env_file(network, ip):
            print()
            print("  ✅ Network configuration updated successfully!")
            print()
            print("  ⚠️  IMPORTANT: Restart services for changes to take effect:")
            print("     docker-compose restart api")

    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
