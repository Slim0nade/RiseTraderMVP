"""
CurveZMQ encryption setup for secure MT4 communication.

Handles encryption key loading and ZMQ socket configuration.
"""
import os
from typing import Optional, Tuple

import zmq


class MT4EncryptionManager:
    """
    Manages CurveZMQ encryption for MT4 connections.

    Handles key loading from environment variables and socket configuration.
    """

    def __init__(
        self,
        client_secret_key: Optional[str] = None,
        client_public_key: Optional[str] = None,
        server_public_key: Optional[str] = None,
        encryption_enabled: bool = True
    ):
        """
        Initialize encryption manager.

        Args:
            client_secret_key: Z85-encoded client secret key (40 chars)
            client_public_key: Z85-encoded client public key (40 chars)
            server_public_key: Z85-encoded server public key (40 chars)
            encryption_enabled: Whether encryption is enabled

        Raises:
            ValueError: If encryption is enabled but keys are missing/invalid
        """
        self.encryption_enabled = encryption_enabled

        if self.encryption_enabled:
            # Load keys from parameters or environment variables
            self.client_secret_key = (
                client_secret_key or os.getenv('ZMQ_CLIENT_SECRET_KEY')
            )
            self.client_public_key = (
                client_public_key or os.getenv('ZMQ_CLIENT_PUBLIC_KEY')
            )
            self.server_public_key = (
                server_public_key or os.getenv('ZMQ_SERVER_PUBLIC_KEY')
            )

            # Validate keys
            self._validate_keys()
        else:
            self.client_secret_key = None
            self.client_public_key = None
            self.server_public_key = None

    def _validate_keys(self):
        """
        Validate encryption keys.

        Raises:
            ValueError: If keys are missing or invalid
        """
        if not self.client_secret_key:
            raise ValueError(
                "ZMQ_CLIENT_SECRET_KEY environment variable is not set. "
                "Generate keys with: python scripts/generate_zmq_keys.py"
            )

        if not self.client_public_key:
            raise ValueError(
                "ZMQ_CLIENT_PUBLIC_KEY environment variable is not set. "
                "Generate keys with: python scripts/generate_zmq_keys.py"
            )

        if not self.server_public_key:
            raise ValueError(
                "ZMQ_SERVER_PUBLIC_KEY environment variable is not set. "
                "Generate keys with: python scripts/generate_zmq_keys.py"
            )

        # Validate key lengths (Z85-encoded 32-byte keys are 40 characters)
        if len(self.client_secret_key) != 40:
            raise ValueError(
                f"Client secret key must be 40 characters (Z85-encoded), "
                f"got {len(self.client_secret_key)}"
            )

        if len(self.client_public_key) != 40:
            raise ValueError(
                f"Client public key must be 40 characters (Z85-encoded), "
                f"got {len(self.client_public_key)}"
            )

        if len(self.server_public_key) != 40:
            raise ValueError(
                f"Server public key must be 40 characters (Z85-encoded), "
                f"got {len(self.server_public_key)}"
            )

    def configure_socket(self, socket: zmq.Socket) -> zmq.Socket:
        """
        Configure socket with encryption keys.

        Args:
            socket: ZMQ socket to configure

        Returns:
            Configured socket with encryption enabled (if applicable)
        """
        if not self.encryption_enabled:
            return socket

        # Configure client keys
        socket.curve_secretkey = self.client_secret_key.encode('ascii')
        socket.curve_publickey = self.client_public_key.encode('ascii')

        # Configure server public key
        socket.curve_serverkey = self.server_public_key.encode('ascii')

        return socket

    def get_keys_info(self) -> dict:
        """
        Get information about loaded keys (for logging/debugging).

        Returns:
            Dictionary with key information (keys are masked for security)
        """
        if not self.encryption_enabled:
            return {
                "encryption_enabled": False,
                "message": "Encryption is disabled"
            }

        def mask_key(key: Optional[str]) -> str:
            """Mask key for secure logging."""
            if not key:
                return "MISSING"
            return f"{key[:4]}...{key[-4:]}"

        return {
            "encryption_enabled": True,
            "client_secret_key": mask_key(self.client_secret_key),
            "client_public_key": mask_key(self.client_public_key),
            "server_public_key": mask_key(self.server_public_key),
            "key_length": 40 if self.client_secret_key else 0
        }

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """
        Generate a new CurveZMQ keypair.

        Returns:
            Tuple of (secret_key, public_key) as Z85-encoded strings

        Note:
            For production use, keys should be generated using
            scripts/generate_zmq_keys.py and stored securely.
        """
        public_key, secret_key = zmq.curve_keypair()
        return secret_key.decode('ascii'), public_key.decode('ascii')

    def test_encryption(self) -> bool:
        """
        Test that encryption is properly configured.

        Returns:
            True if encryption is working, False otherwise
        """
        if not self.encryption_enabled:
            return True

        try:
            # Create a test socket
            context = zmq.Context()
            socket = context.socket(zmq.REQ)

            # Configure encryption
            self.configure_socket(socket)

            # Verify keys are set
            assert socket.curve_secretkey is not None
            assert socket.curve_publickey is not None
            assert socket.curve_serverkey is not None

            # Clean up
            socket.close()
            context.term()

            return True

        except Exception:
            return False


def load_encryption_from_env() -> MT4EncryptionManager:
    """
    Load encryption manager from environment variables.

    Returns:
        MT4EncryptionManager instance

    Raises:
        ValueError: If encryption is enabled but keys are missing
    """
    encryption_enabled = os.getenv('MT4_ENCRYPTION_ENABLED', 'true').lower() == 'true'

    return MT4EncryptionManager(encryption_enabled=encryption_enabled)


def validate_encryption_setup() -> Tuple[bool, str]:
    """
    Validate that encryption is properly set up.

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        manager = load_encryption_from_env()

        if not manager.encryption_enabled:
            return True, "Encryption is disabled (WARNING: Not recommended for production)"

        # Test encryption
        if manager.test_encryption():
            return True, "Encryption is properly configured"
        else:
            return False, "Encryption test failed"

    except Exception as e:
        return False, f"Encryption validation failed: {str(e)}"


if __name__ == "__main__":
    """Test encryption setup when run directly."""
    print("Testing MT4 Encryption Setup...")
    print("-" * 60)

    is_valid, message = validate_encryption_setup()

    if is_valid:
        print(f"✓ {message}")

        manager = load_encryption_from_env()
        print("\nEncryption Keys Info:")
        for key, value in manager.get_keys_info().items():
            print(f"  {key}: {value}")
    else:
        print(f"✗ {message}")
        print("\nTo fix:")
        print("1. Run: python scripts/generate_zmq_keys.py")
        print("2. Copy keys to your .env file")
        print("3. Restart the application")
        exit(1)

    print("-" * 60)
    print("Encryption setup test complete!")
