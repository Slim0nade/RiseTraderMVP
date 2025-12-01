"""
Model Configurations Package
Contains YAML config loaders and model configurations
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


CONFIG_DIR = Path(__file__).parent


def load_config(config_name: str) -> Dict[str, Any]:
    """
    Load a YAML configuration file.
    
    Args:
        config_name: Name of config file (with or without .yaml extension)
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    if not config_name.endswith('.yaml'):
        config_name = f"{config_name}.yaml"
    
    config_path = CONFIG_DIR / config_name
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def list_configs() -> list:
    """List all available configuration files."""
    return [f.stem for f in CONFIG_DIR.glob('*.yaml')]


def get_model_config(model_type: str, asset_type: str) -> Optional[Dict[str, Any]]:
    """
    Get configuration for a specific model and asset combination.
    
    Args:
        model_type: Model type (tcn, gru, fedformer, tft, moe, ppo)
        asset_type: Asset type (crude_oil, gold)
        
    Returns:
        Configuration dictionary or None if not found
    """
    config_name = f"{model_type}_{asset_type}"
    try:
        return load_config(config_name)
    except FileNotFoundError:
        return None


__all__ = ['load_config', 'list_configs', 'get_model_config', 'CONFIG_DIR']
