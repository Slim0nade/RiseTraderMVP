"""
Temporal Models Package
Contains sequence-based models: TCN, BiGRU with Attention
"""

from .tcn import (
    TCN,
    TCNConfig,
    TemporalBlock,
    create_tcn_for_crude_oil,
    create_tcn_for_gold
)
from .gru import (
    BiGRUAttention,
    GRUConfig,
    create_bigru_for_crude_oil,
    create_bigru_for_gold
)

__all__ = [
    # TCN
    'TCN',
    'TCNConfig',
    'TemporalBlock',
    'create_tcn_for_crude_oil',
    'create_tcn_for_gold',
    # BiGRU
    'BiGRUAttention',
    'GRUConfig',
    'create_bigru_for_crude_oil',
    'create_bigru_for_gold',
]
