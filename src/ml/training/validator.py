"""
Walk-Forward Validator for time series cross-validation.
Implements 70/15/15 train/val/test split with rolling windows.
Based on research.md TD-004
"""

from typing import List, Tuple
import numpy as np
import pandas as pd
from datetime import timedelta


class WalkForwardValidator:
    """
    Walk-forward cross-validation for time series data.
    Prevents look-ahead bias by maintaining temporal ordering.
    """
    
    def __init__(
        self,
        train_window_days: int = 30,
        val_window_days: int = 5,
        test_window_days: int = 5,
        slide_days: int = 5
    ):
        self.train_window_days = train_window_days
        self.val_window_days = val_window_days
        self.test_window_days = test_window_days
        self.slide_days = slide_days
    
    def split(self, df: pd.DataFrame) -> List[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
        """Generate train/val/test splits using walk-forward approach."""
        df = df.sort_values('timestamp')
        
        splits = []
        total_window = self.train_window_days + self.val_window_days + self.test_window_days
        
        start_idx = 0
        while start_idx + total_window <= len(df):
            train_end = start_idx + self.train_window_days
            val_end = train_end + self.val_window_days
            test_end = val_end + self.test_window_days
            
            train = df.iloc[start_idx:train_end]
            val = df.iloc[train_end:val_end]
            test = df.iloc[val_end:test_end]
            
            splits.append((train, val, test))
            start_idx += self.slide_days
        
        return splits
