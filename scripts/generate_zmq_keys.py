#!/usr/bin/env python3
"""
ZMQ CurveZMQ Key Generation Utility

This script generates encryption keypairs for secure MT4 integration.
Run this once during setup and update your .env file with the generated keys.

Usage:
    python scripts/generate_zmq_keys.py

Output:
    - Client keypair (secret + public)
    - Server keypair (secret + public)
    - Ready-to-paste .env entries

Security:
    - Keep secret keys private and secure
    - Only share public keys
    - Rotate keys every 90 days
"""

import zmq.auth
import os
import sys
from pathlib import Path


def generate_keypair(name: str) -> tuple[bytes, bytes]:
    """
    Generate a CurveZMQ keypair.

    Args:
        name: Identifier for the keypair (e.g., "client", "server")

    Returns:
        Tuple of (secret_key, public_key) as Z85-encoded bytes
    """
    # Generate keypair using ZMQ's built-in curve keygen
    public_key, secret_key = zmq.curve_keypair()

    return secret_key, public_key


def format_key(key: bytes) -> str:
    """Convert bytes key to string for environment variables."""
    return key.decode('ascii')


def save_keys_to_file(keys: dict, output_dir: Path):
    """
    Save keys to individual files for secure storage.

    Args:
        keys: Dictionary of key names to values
        output_dir: Directory to save key files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for key_name, key_value in keys.items():
        key_file = output_dir / f"{key_name}.key"
        key_file.write_text(key_value)
        # Set restrictive permissions (owner read/write only)
        key_file.chmod(0o600)
        print(f"  ✓ Saved {key_name} to {key_file}")


def main():
    print("=" * 70)
    print("ZMQ CurveZMQ Key Generator for RiseTrader MT4 Integration")
    print("=" * 70)
    print()

    # Generate client keypair
    print("Generating client keypair...")
    client_secret, client_public = generate_keypair("client")
    print("  ✓ Client keys generated")

    # Generate server keypair
    print("\nGenerating server keypair...")
    server_secret, server_public = generate_keypair("server")
    print("  ✓ Server keys generated")

    # Format keys for display
    client_secret_str = format_key(client_secret)
    client_public_str = format_key(client_public)
    server_secret_str = format_key(server_secret)
    server_public_str = format_key(server_public)

    # Display keys for .env file
    print("\n" + "=" * 70)
    print("COPY THESE KEYS TO YOUR .env FILE")
    print("=" * 70)
    print()
    print("# ZMQ Client Keys (for RiseTrader application)")
    print(f"ZMQ_CLIENT_SECRET_KEY={client_secret_str}")
    print(f"ZMQ_CLIENT_PUBLIC_KEY={client_public_str}")
    print()
    print("# ZMQ Server Public Key (from MT4 EA)")
    print(f"ZMQ_SERVER_PUBLIC_KEY={server_public_str}")
    print()

    # Display keys for MT4 EA configuration
    print("=" * 70)
    print("CONFIGURE MT4 EA WITH THESE KEYS")
    print("=" * 70)
    print()
    print("In your MT4 Expert Advisor (HelloWorldServerEA.mq4), set:")
    print()
    print(f"  SERVER_SECRET_KEY = \"{server_secret_str}\"")
    print(f"  SERVER_PUBLIC_KEY = \"{server_public_str}\"")
    print(f"  CLIENT_PUBLIC_KEY = \"{client_public_str}\"")
    print()

    # Optional: Save keys to files
    print("=" * 70)
    print("KEY STORAGE")
    print("=" * 70)
    print()
    save_choice = input("Save keys to secure files in .zmq_keys/? (y/n): ").lower()

    if save_choice == 'y':
        project_root = Path(__file__).parent.parent
        keys_dir = project_root / ".zmq_keys"

        keys_to_save = {
            "client_secret": client_secret_str,
            "client_public": client_public_str,
            "server_secret": server_secret_str,
            "server_public": server_public_str,
        }

        print("\nSaving keys...")
        save_keys_to_file(keys_to_save, keys_dir)
        print(f"\n✓ Keys saved to {keys_dir}/")
        print(f"  ⚠️  WARNING: .zmq_keys/ is in .gitignore for security")
        print()

    # Security reminders
    print("=" * 70)
    print("SECURITY REMINDERS")
    print("=" * 70)
    print()
    print("1. ✓ Client secret key: Keep private, never share")
    print("2. ✓ Server secret key: Keep private, configure in MT4 EA only")
    print("3. ✓ Public keys: Safe to share between client/server")
    print("4. ✓ Rotate keys every 90 days (recommended)")
    print("5. ✓ Never commit .env or .zmq_keys/ to version control")
    print("6. ✓ Use different keys for dev/staging/production")
    print()

    # Key verification
    print("=" * 70)
    print("KEY VERIFICATION")
    print("=" * 70)
    print()
    print(f"Client Secret Key Length: {len(client_secret_str)} chars (expected: 40)")
    print(f"Client Public Key Length: {len(client_public_str)} chars (expected: 40)")
    print(f"Server Secret Key Length: {len(server_secret_str)} chars (expected: 40)")
    print(f"Server Public Key Length: {len(server_public_str)} chars (expected: 40)")

    if all(len(k) == 40 for k in [client_secret_str, client_public_str,
                                    server_secret_str, server_public_str]):
        print("\n✓ All keys are valid Z85-encoded 32-byte keys")
    else:
        print("\n✗ ERROR: Invalid key lengths!")
        sys.exit(1)

    print()
    print("=" * 70)
    print("Key generation complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Copy the client keys to your .env file")
    print("2. Configure the MT4 EA with server keys")
    print("3. Test the connection: python -m src.trading.execution.mt4_client")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nKey generation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        sys.exit(1)
