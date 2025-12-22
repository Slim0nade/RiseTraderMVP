"""
API Configuration for RiseTrader FastAPI Application

Manages API settings, CORS configuration, rate limits, and feature flags.
"""
import os
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """
    API Configuration Settings

    Loads from environment variables with defaults.
    """

    # Application Info
    app_name: str = "RiseTrader API"
    app_version: str = "1.0.0"
    app_description: str = "Autonomous Algorithmic Trading Platform API"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8003
    debug: bool = False
    reload: bool = False
    workers: int = 4

    # CORS Configuration
    cors_enabled: bool = True
    cors_origins: Union[str, List[str]] = [
        "http://localhost:3000",  # React Dashboard
        "http://localhost:3001",  # Grafana
        "http://localhost:3003",  # React Dashboard (alternate port)
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3003",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    cors_credentials: bool = True
    cors_methods: List[str] = ["*"]
    cors_headers: List[str] = ["*"]

    # Database Configuration
    database_url: str = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 0
    redis_max_connections: int = 50

    # Agent Configuration
    agent_config_path: str = "/app/config/agents.yaml"  # Docker container path
    mcp_server_url: str = "http://localhost:7000"
    ollama_base_url: str = "http://192.168.0.123:11434"  # External Ollama instance

    # Security
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    api_key: Optional[str] = None
    valid_api_keys: List[str] = []

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Feature Flags
    enable_paper_trading: bool = True
    enable_live_trading: bool = False
    enable_forecasting: bool = True
    enable_ml_predictions: bool = True
    enable_regime_detection: bool = True
    enable_strategy_optimization: bool = True

    # MT4 Configuration
    mt4_host: str = "75.154.254.186"
    mt4_command_port: int = 5555
    mt4_stream_port: int = 5556
    mt4_timeout: int = 10
    mt4_sync_interval_seconds: int = 60  # Sync positions/account every 60 seconds

    # Monitoring
    prometheus_enabled: bool = True
    jaeger_enabled: bool = False
    jaeger_agent_host: str = "localhost"
    jaeger_agent_port: int = 6831

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: Optional[str] = None

    # Performance
    request_timeout: int = 30
    websocket_timeout: int = 300
    max_request_size: int = 10_485_760  # 10 MB

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 500

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"


# Global settings instance
settings = APISettings()


def get_settings() -> APISettings:
    """
    Get API settings instance.

    Returns:
        APISettings instance
    """
    return settings


# CORS origins helper
def get_cors_origins() -> List[str]:
    """
    Get CORS allowed origins.

    Handles both comma-separated strings from env vars and list values.
    The field_validator in APISettings already parses comma-separated strings.

    Returns:
        List of allowed origins
    """
    origins = settings.cors_origins
    # Ensure we always return a list (validator should handle this, but safety check)
    if isinstance(origins, str):
        return [origin.strip() for origin in origins.split(",")]
    return origins


# API Keys validation
def is_valid_api_key(api_key: str) -> bool:
    """
    Validate API key.

    Args:
        api_key: API key to validate

    Returns:
        True if valid, False otherwise
    """
    if not settings.valid_api_keys:
        # If no API keys configured, allow all (development mode)
        return True

    return api_key in settings.valid_api_keys
