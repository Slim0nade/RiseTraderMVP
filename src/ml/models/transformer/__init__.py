"""
Transformer Models Package
Contains attention-based models: FEDformer, TFT
"""

from .fedformer import (
    FEDformer,
    FEDformerConfig,
    create_fedformer_for_crude_oil,
    create_fedformer_for_gold
)
from .tft import (
    TemporalFusionTransformer,
    TFTConfig,
    GatedResidualNetwork,
    VariableSelectionNetwork,
    InterpretableMultiHeadAttention,
    create_tft_for_crude_oil,
    create_tft_for_gold
)

__all__ = [
    # FEDformer
    'FEDformer',
    'FEDformerConfig',
    'create_fedformer_for_crude_oil',
    'create_fedformer_for_gold',
    # TFT
    'TemporalFusionTransformer',
    'TFTConfig',
    'GatedResidualNetwork',
    'VariableSelectionNetwork',
    'InterpretableMultiHeadAttention',
    'create_tft_for_crude_oil',
    'create_tft_for_gold',
]
