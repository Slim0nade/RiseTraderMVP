"""
Network Location Configuration Manager

Handles switching between LOCAL (home) and REMOTE (internet) network locations
for MT4 and Ollama connections.
"""
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

# Persistent storage file for network location
NETWORK_LOCATION_FILE = Path("/app/.network_location")


class NetworkLocation(str, Enum):
    """Network location enum."""
    LOCAL = "local"   # Home network (192.168.0.123)
    REMOTE = "remote"  # Internet (75.154.254.186)


class MT4Endpoints(BaseModel):
    """MT4 connection endpoints."""
    host: str
    command_port: int = 5555
    stream_port: int = 5556

    @property
    def command_endpoint(self) -> str:
        """Get full command endpoint."""
        return f"tcp://{self.host}:{self.command_port}"

    @property
    def stream_endpoint(self) -> str:
        """Get full stream endpoint."""
        return f"tcp://{self.host}:{self.stream_port}"


class OllamaEndpoints(BaseModel):
    """Ollama connection endpoints."""
    base_url: str
    timeout: int = 60
    max_retries: int = 3

    @property
    def api_url(self) -> str:
        """Get API URL."""
        return f"{self.base_url}/api"

    @property
    def generate_url(self) -> str:
        """Get generate endpoint."""
        return f"{self.base_url}/api/generate"

    @property
    def chat_url(self) -> str:
        """Get chat endpoint."""
        return f"{self.base_url}/api/chat"


class NetworkConfig(BaseModel):
    """Complete network configuration for a location."""
    mt4: MT4Endpoints
    ollama: OllamaEndpoints


class NetworkLocationManager:
    """
    Manages network location switching between LOCAL and REMOTE.

    Usage:
        # Auto-detect or use env variable
        manager = NetworkLocationManager()

        # Get current MT4 connection
        mt4_config = manager.get_mt4_config()
        print(f"MT4 Host: {mt4_config.host}")

        # Switch to remote
        manager.set_location(NetworkLocation.REMOTE)

        # Get Ollama config
        ollama_config = manager.get_ollama_config()
        print(f"Ollama: {ollama_config.base_url}")
    """

    # Network configuration presets
    CONFIGS: Dict[NetworkLocation, NetworkConfig] = {
        NetworkLocation.LOCAL: NetworkConfig(
            mt4=MT4Endpoints(
                host="192.168.0.123",
                command_port=5555,
                stream_port=5556,
            ),
            ollama=OllamaEndpoints(
                base_url="http://192.168.0.123:11434",
                timeout=60,
                max_retries=3,
            ),
        ),
        NetworkLocation.REMOTE: NetworkConfig(
            mt4=MT4Endpoints(
                host="75.154.254.186",
                command_port=5555,
                stream_port=5556,
            ),
            ollama=OllamaEndpoints(
                base_url="http://75.154.254.186:11434",
                timeout=120,  # Longer timeout for remote
                max_retries=5,  # More retries for remote
            ),
        ),
    }

    def __init__(self, location: Optional[NetworkLocation] = None):
        """
        Initialize network location manager.

        Args:
            location: Explicit location, or None to read from persistent storage or env
        """
        if location:
            self._location = location
        else:
            # Try to read from persistent file first
            persisted_location = self._read_persisted_location()
            if persisted_location:
                self._location = NetworkLocation(persisted_location)
            else:
                # Fall back to environment variable, default to REMOTE for safety
                env_location = os.getenv("NETWORK_LOCATION", "remote").lower()
                self._location = NetworkLocation(env_location)

        logger.info(
            "network_location_initialized",
            location=self._location.value,
            mt4_host=self.get_mt4_config().host,
            ollama_url=self.get_ollama_config().base_url,
        )

    @property
    def location(self) -> NetworkLocation:
        """Get current network location."""
        return self._location

    def set_location(self, location: NetworkLocation) -> None:
        """
        Switch network location and persist to disk.

        Args:
            location: New network location
        """
        old_location = self._location
        self._location = location

        # Persist the location to file so it survives API restarts
        self._persist_location(location)

        logger.info(
            "network_location_changed",
            old_location=old_location.value,
            new_location=location.value,
            mt4_host=self.get_mt4_config().host,
            ollama_url=self.get_ollama_config().base_url,
        )

    def _read_persisted_location(self) -> Optional[str]:
        """
        Read network location from persistent file.

        Returns:
            Location string ("local" or "remote") or None if file doesn't exist
        """
        try:
            if NETWORK_LOCATION_FILE.exists():
                location = NETWORK_LOCATION_FILE.read_text().strip()
                if location in ["local", "remote"]:
                    logger.debug("read_persisted_location", location=location)
                    return location
                else:
                    logger.warning("invalid_persisted_location", location=location)
                    return None
        except Exception as e:
            logger.warning("failed_to_read_persisted_location", error=str(e))
        return None

    def _persist_location(self, location: NetworkLocation) -> None:
        """
        Write network location to persistent file.

        Args:
            location: Network location to persist
        """
        try:
            # Create parent directory if it doesn't exist
            NETWORK_LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Write location to file
            NETWORK_LOCATION_FILE.write_text(location.value)
            logger.debug("persisted_location", location=location.value, file=str(NETWORK_LOCATION_FILE))
        except Exception as e:
            logger.error("failed_to_persist_location", location=location.value, error=str(e))

    def get_config(self) -> NetworkConfig:
        """Get current network configuration."""
        return self.CONFIGS[self._location]

    def get_mt4_config(self) -> MT4Endpoints:
        """Get MT4 configuration for current location."""
        return self.get_config().mt4

    def get_ollama_config(self) -> OllamaEndpoints:
        """Get Ollama configuration for current location."""
        return self.get_config().ollama

    def is_local(self) -> bool:
        """Check if using local network."""
        return self._location == NetworkLocation.LOCAL

    def is_remote(self) -> bool:
        """Check if using remote network."""
        return self._location == NetworkLocation.REMOTE


# Global instance
_network_manager: Optional[NetworkLocationManager] = None


def get_network_manager() -> NetworkLocationManager:
    """
    Get global network location manager (singleton).

    Returns:
        NetworkLocationManager instance
    """
    global _network_manager
    if _network_manager is None:
        _network_manager = NetworkLocationManager()
    return _network_manager


def set_network_location(location: NetworkLocation) -> None:
    """
    Set global network location.

    Args:
        location: Network location to switch to
    """
    manager = get_network_manager()
    manager.set_location(location)


def get_mt4_host() -> str:
    """Get MT4 host for current location."""
    return get_network_manager().get_mt4_config().host


def get_mt4_command_endpoint() -> str:
    """Get MT4 command endpoint for current location."""
    return get_network_manager().get_mt4_config().command_endpoint


def get_mt4_stream_endpoint() -> str:
    """Get MT4 stream endpoint for current location."""
    return get_network_manager().get_mt4_config().stream_endpoint


def get_ollama_base_url() -> str:
    """Get Ollama base URL for current location."""
    return get_network_manager().get_ollama_config().base_url
