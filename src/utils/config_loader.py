"""
Configuration Loader for Stealth Stop Manager

Loads and validates YAML configuration with:
- JSON Schema validation
- Per-symbol override merging
- Hot-reload support via watchdog
- Thread-safe configuration access
"""

import os
import yaml
import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    logging.warning("jsonschema not installed, config validation disabled")

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logging.warning("watchdog not installed, hot-reload disabled")

logger = logging.getLogger("config-loader")

# Default configuration file paths
DEFAULT_CONFIG_PATH = "config/stealth_stops.yaml"
DEFAULT_SCHEMA_PATH = "specs/007-stealth-stop-protection/contracts/stealth_stops.yaml.schema"


@dataclass
class FeatureFlags:
    """Feature flags for gradual rollout."""
    enable_disaster_stops: bool = True
    enable_profit_erosion: bool = True
    enable_early_breakeven: bool = True
    enable_audit_trail: bool = False
    enable_institutional_pricing: bool = True


@dataclass
class SymbolConfig:
    """Configuration for a specific symbol (merged with defaults)."""
    disaster_stop_multiplier: float = 3.0
    trail_trigger_atr: float = 0.5
    breakeven_trigger_atr: float = 0.5
    erosion_threshold_atr: float = 0.5
    erosion_alert_threshold_atr: float = 0.3
    atr_multiplier_trail: float = 1.5
    trail_step_atr: float = 0.5
    breakeven_offset_pips: float = 10.0
    monitoring_cycle_seconds: int = 60
    max_volatility_adjustment: float = 0.5
    atr_fallback_percentage: float = 0.02
    manual_override_grace_period: int = 60
    min_offset_pips: float = 5.0
    max_offset_pips: float = 15.0
    pip_value: float = 0.01


@dataclass
class StealthStopConfig:
    """Complete stealth stop manager configuration."""
    defaults: SymbolConfig = field(default_factory=SymbolConfig)
    symbol_overrides: Dict[str, SymbolConfig] = field(default_factory=dict)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    loaded_at: datetime = field(default_factory=datetime.now)
    config_path: str = ""

    def get_symbol_config(self, symbol: str) -> SymbolConfig:
        """
        Get configuration for a specific symbol.

        Merges defaults with symbol-specific overrides.

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL", "EURUSD")

        Returns:
            SymbolConfig with merged settings
        """
        # Normalize symbol to uppercase
        normalized = symbol.upper()

        # Check for exact match or partial match
        for key, override in self.symbol_overrides.items():
            if key == normalized or normalized.startswith(key):
                return override

        return self.defaults

    def validate_constraints(self) -> List[str]:
        """
        Validate configuration constraints.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check erosion_alert_threshold < erosion_threshold
        if self.defaults.erosion_alert_threshold_atr >= self.defaults.erosion_threshold_atr:
            errors.append(
                f"erosion_alert_threshold_atr ({self.defaults.erosion_alert_threshold_atr}) "
                f"must be less than erosion_threshold_atr ({self.defaults.erosion_threshold_atr})"
            )

        # Check trail_trigger <= breakeven_trigger (breakeven comes after trailing)
        # Actually, in our case trail can come before or after breakeven
        # No strict ordering required

        return errors


class ConfigFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handles file system events for config hot-reload."""

    def __init__(self, config_path: str, reload_callback: Callable):
        self.config_path = config_path
        self.reload_callback = reload_callback
        self._last_reload = datetime.now()
        self._debounce_seconds = 1.0  # Debounce rapid changes

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(self.config_path):
            now = datetime.now()
            if (now - self._last_reload).total_seconds() > self._debounce_seconds:
                logger.info(f"Config file modified, reloading: {event.src_path}")
                self._last_reload = now
                try:
                    self.reload_callback()
                except Exception as e:
                    logger.error(f"Error reloading config: {e}")


class ConfigLoader:
    """
    Thread-safe configuration loader with hot-reload support.

    Usage:
        loader = ConfigLoader()
        config = loader.get_config()

        # Get symbol-specific config
        crude_config = config.get_symbol_config("CrudeOIL")
    """

    _instance: Optional["ConfigLoader"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global config access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        config_path: Optional[str] = None,
        schema_path: Optional[str] = None,
        enable_hot_reload: bool = True
    ):
        if self._initialized:
            return

        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.schema_path = schema_path or DEFAULT_SCHEMA_PATH
        self.enable_hot_reload = enable_hot_reload and WATCHDOG_AVAILABLE

        self._config: Optional[StealthStopConfig] = None
        self._config_lock = threading.RLock()
        self._observer: Optional[Observer] = None
        self._reload_callbacks: List[Callable[[StealthStopConfig], None]] = []

        # Load initial configuration
        self._load_config()

        # Setup hot-reload if enabled
        if self.enable_hot_reload:
            self._setup_hot_reload()

        self._initialized = True

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        with self._config_lock:
            try:
                config_file = Path(self.config_path)

                if not config_file.exists():
                    logger.warning(f"Config file not found: {self.config_path}, using defaults")
                    self._config = StealthStopConfig()
                    return

                with open(config_file, 'r') as f:
                    raw_config = yaml.safe_load(f)

                # Validate against schema if available
                if JSONSCHEMA_AVAILABLE:
                    self._validate_schema(raw_config)

                # Parse configuration
                self._config = self._parse_config(raw_config)
                self._config.config_path = str(config_file.absolute())

                # Validate constraints
                errors = self._config.validate_constraints()
                if errors:
                    for error in errors:
                        logger.warning(f"Config constraint warning: {error}")

                logger.info(f"Configuration loaded from {self.config_path}")

            except Exception as e:
                logger.error(f"Error loading configuration: {e}")
                if self._config is None:
                    self._config = StealthStopConfig()

    def _validate_schema(self, raw_config: Dict[str, Any]) -> None:
        """Validate configuration against JSON schema."""
        schema_file = Path(self.schema_path)

        if not schema_file.exists():
            logger.warning(f"Schema file not found: {self.schema_path}, skipping validation")
            return

        try:
            with open(schema_file, 'r') as f:
                schema = yaml.safe_load(f)

            jsonschema.validate(raw_config, schema)
            logger.debug("Configuration validated against schema")

        except jsonschema.ValidationError as e:
            logger.error(f"Configuration validation failed: {e.message}")
            raise

    def _parse_config(self, raw_config: Dict[str, Any]) -> StealthStopConfig:
        """Parse raw YAML config into StealthStopConfig."""
        # Parse defaults
        defaults_dict = raw_config.get("defaults", {})
        defaults = SymbolConfig(
            disaster_stop_multiplier=defaults_dict.get("disaster_stop_multiplier", 3.0),
            trail_trigger_atr=defaults_dict.get("trail_trigger_atr", 0.5),
            breakeven_trigger_atr=defaults_dict.get("breakeven_trigger_atr", 0.5),
            erosion_threshold_atr=defaults_dict.get("erosion_threshold_atr", 0.5),
            erosion_alert_threshold_atr=defaults_dict.get("erosion_alert_threshold_atr", 0.3),
            atr_multiplier_trail=defaults_dict.get("atr_multiplier_trail", 1.5),
            trail_step_atr=defaults_dict.get("trail_step_atr", 0.5),
            breakeven_offset_pips=defaults_dict.get("breakeven_offset_pips", 10.0),
            monitoring_cycle_seconds=defaults_dict.get("monitoring_cycle_seconds", 60),
            max_volatility_adjustment=defaults_dict.get("max_volatility_adjustment", 0.5),
            atr_fallback_percentage=defaults_dict.get("atr_fallback_percentage", 0.02),
            manual_override_grace_period=defaults_dict.get("manual_override_grace_period", 60),
            min_offset_pips=defaults_dict.get("min_offset_pips", 5.0),
            max_offset_pips=defaults_dict.get("max_offset_pips", 15.0),
            pip_value=defaults_dict.get("pip_value", 0.01),
        )

        # Parse symbol overrides (merge with defaults)
        symbol_overrides = {}
        overrides_dict = raw_config.get("symbol_overrides", {})

        for symbol, override_values in overrides_dict.items():
            # Start with defaults and override specific values
            symbol_config = SymbolConfig(
                disaster_stop_multiplier=override_values.get(
                    "disaster_stop_multiplier", defaults.disaster_stop_multiplier
                ),
                trail_trigger_atr=override_values.get(
                    "trail_trigger_atr", defaults.trail_trigger_atr
                ),
                breakeven_trigger_atr=override_values.get(
                    "breakeven_trigger_atr", defaults.breakeven_trigger_atr
                ),
                erosion_threshold_atr=override_values.get(
                    "erosion_threshold_atr", defaults.erosion_threshold_atr
                ),
                erosion_alert_threshold_atr=override_values.get(
                    "erosion_alert_threshold_atr", defaults.erosion_alert_threshold_atr
                ),
                atr_multiplier_trail=override_values.get(
                    "atr_multiplier_trail", defaults.atr_multiplier_trail
                ),
                trail_step_atr=override_values.get(
                    "trail_step_atr", defaults.trail_step_atr
                ),
                breakeven_offset_pips=override_values.get(
                    "breakeven_offset_pips", defaults.breakeven_offset_pips
                ),
                monitoring_cycle_seconds=override_values.get(
                    "monitoring_cycle_seconds", defaults.monitoring_cycle_seconds
                ),
                max_volatility_adjustment=override_values.get(
                    "max_volatility_adjustment", defaults.max_volatility_adjustment
                ),
                atr_fallback_percentage=override_values.get(
                    "atr_fallback_percentage", defaults.atr_fallback_percentage
                ),
                manual_override_grace_period=override_values.get(
                    "manual_override_grace_period", defaults.manual_override_grace_period
                ),
                min_offset_pips=override_values.get(
                    "min_offset_pips", defaults.min_offset_pips
                ),
                max_offset_pips=override_values.get(
                    "max_offset_pips", defaults.max_offset_pips
                ),
                pip_value=override_values.get(
                    "pip_value", defaults.pip_value
                ),
            )
            symbol_overrides[symbol.upper()] = symbol_config

        # Parse feature flags
        features_dict = raw_config.get("features", {})
        features = FeatureFlags(
            enable_disaster_stops=features_dict.get("enable_disaster_stops", True),
            enable_profit_erosion=features_dict.get("enable_profit_erosion", True),
            enable_early_breakeven=features_dict.get("enable_early_breakeven", True),
            enable_audit_trail=features_dict.get("enable_audit_trail", False),
            enable_institutional_pricing=features_dict.get("enable_institutional_pricing", True),
        )

        return StealthStopConfig(
            defaults=defaults,
            symbol_overrides=symbol_overrides,
            features=features,
            loaded_at=datetime.now(),
        )

    def _setup_hot_reload(self) -> None:
        """Setup file watcher for configuration hot-reload."""
        if not WATCHDOG_AVAILABLE:
            return

        try:
            config_dir = str(Path(self.config_path).parent.absolute())
            config_file = Path(self.config_path).name

            handler = ConfigFileHandler(config_file, self._on_config_changed)

            self._observer = Observer()
            self._observer.schedule(handler, config_dir, recursive=False)
            self._observer.start()

            logger.info(f"Hot-reload enabled for {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to setup hot-reload: {e}")

    def _on_config_changed(self) -> None:
        """Handle configuration file changes."""
        logger.info("Reloading configuration...")
        old_config = self._config

        try:
            self._load_config()

            # Notify callbacks
            for callback in self._reload_callbacks:
                try:
                    callback(self._config)
                except Exception as e:
                    logger.error(f"Error in reload callback: {e}")

            logger.info("Configuration reloaded successfully")

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            # Keep old config on error
            self._config = old_config

    def get_config(self) -> StealthStopConfig:
        """
        Get current configuration.

        Thread-safe access to configuration.

        Returns:
            Current StealthStopConfig
        """
        with self._config_lock:
            return self._config

    def register_reload_callback(
        self,
        callback: Callable[[StealthStopConfig], None]
    ) -> None:
        """
        Register a callback for configuration reload events.

        Args:
            callback: Function called with new config on reload
        """
        self._reload_callbacks.append(callback)

    def unregister_reload_callback(
        self,
        callback: Callable[[StealthStopConfig], None]
    ) -> None:
        """Unregister a reload callback."""
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)

    def reload(self) -> StealthStopConfig:
        """
        Force configuration reload.

        Returns:
            Newly loaded configuration
        """
        self._on_config_changed()
        return self._config

    def stop(self) -> None:
        """Stop the configuration loader and file watcher."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Configuration hot-reload stopped")

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None


def get_config() -> StealthStopConfig:
    """
    Convenience function to get current configuration.

    Returns:
        Current StealthStopConfig
    """
    loader = ConfigLoader()
    return loader.get_config()


def get_symbol_config(symbol: str) -> SymbolConfig:
    """
    Convenience function to get symbol-specific configuration.

    Args:
        symbol: Trading symbol

    Returns:
        SymbolConfig for the specified symbol
    """
    config = get_config()
    return config.get_symbol_config(symbol)
