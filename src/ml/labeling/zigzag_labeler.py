"""
ZigZag Labeler

Ports the MT4 ZigZag indicator logic to Python for labeling
historical candles with peak/valley markers for ML training.

ZigZag Parameters (MT4 defaults):
- depth: 12 (minimum bars between swing points)
- deviation: 5 (minimum price deviation in points)  
- backstep: 3 (bars to look back for confirmation)

Label Values:
-  1 = PEAK (local high, potential short/sell)
-  0 = NEITHER (no reversal)
- -1 = VALLEY (local low, potential long/buy)
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ZigZagConfig:
    """ZigZag indicator configuration."""
    depth: int = 12      # Minimum bars between swings
    deviation: int = 5   # Minimum deviation in points (pips * 10)
    backstep: int = 3    # Bars to look back for swing confirmation
    point: float = 0.01  # Point size (0.01 for most pairs, 0.0001 for JPY)


class ZigZagLabeler:
    """
    Labels candles with ZigZag peaks and valleys.
    
    This is a direct port of the MT4 ZigZag indicator logic,
    designed to create training labels for ML models.
    
    Usage:
        labeler = ZigZagLabeler()
        df = labeler.label_dataframe(candles_df)
        # df now has 'zigzag_label' column with -1, 0, 1 values
    """
    
    def __init__(self, config: Optional[ZigZagConfig] = None):
        self.config = config or ZigZagConfig()
    
    def label_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply ZigZag labels to a DataFrame of candles.
        
        Args:
            df: DataFrame with columns: time, open, high, low, close
                Must be sorted by time ascending.
        
        Returns:
            DataFrame with added 'zigzag_label' column
        """
        df = df.copy()
        
        # Ensure sorted by time
        if 'time' in df.columns:
            df = df.sort_values('time').reset_index(drop=True)
        
        # Get OHLC as numpy arrays (faster)
        high = df['high'].astype(float).values
        low = df['low'].astype(float).values
        
        # Calculate ZigZag
        zigzag, labels = self._calculate_zigzag(high, low)
        
        df['zigzag_value'] = zigzag    # The actual price at reversal
        df['zigzag_label'] = labels    # -1, 0, or 1
        
        return df
    
    def _calculate_zigzag(
        self, 
        high: np.ndarray, 
        low: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Core ZigZag calculation - ported from MQL4.
        
        Args:
            high: Array of high prices
            low: Array of low prices
            
        Returns:
            Tuple of (zigzag_values, labels)
        """
        depth = self.config.depth
        deviation = self.config.deviation
        backstep = self.config.backstep
        point = self.config.point
        
        n = len(high)
        
        # Buffers (matching MQL4 structure)
        zigzag_buffer = np.zeros(n)
        high_buffer = np.zeros(n)
        low_buffer = np.zeros(n)
        labels = np.zeros(n, dtype=int)
        
        if n < depth:
            return zigzag_buffer, labels
        
        # Track last high/low values
        last_high = 0.0
        last_low = 0.0
        
        # First pass: identify potential extremums
        for i in range(depth, n):
            # Find lowest low in depth window
            lowest_idx = i - depth + np.argmin(low[i-depth+1:i+1]) + 1
            extremum = low[lowest_idx]
            
            if extremum != last_low:
                last_low = extremum
                # Check if current low is close enough to the extremum
                if low[i] - extremum > deviation * point:
                    extremum = 0.0
                else:
                    # Clear previous lows in backstep range
                    for back in range(1, min(backstep + 1, i + 1)):
                        if low_buffer[i - back] != 0 and low_buffer[i - back] > extremum:
                            low_buffer[i - back] = 0.0
            else:
                extremum = 0.0
            
            if low[i] == extremum:
                low_buffer[i] = extremum
            
            # Find highest high in depth window
            highest_idx = i - depth + np.argmax(high[i-depth+1:i+1]) + 1
            extremum = high[highest_idx]
            
            if extremum != last_high:
                last_high = extremum
                # Check if current high is close enough to the extremum
                if extremum - high[i] > deviation * point:
                    extremum = 0.0
                else:
                    # Clear previous highs in backstep range
                    for back in range(1, min(backstep + 1, i + 1)):
                        if high_buffer[i - back] != 0 and high_buffer[i - back] < extremum:
                            high_buffer[i - back] = 0.0
            else:
                extremum = 0.0
            
            if high[i] == extremum:
                high_buffer[i] = extremum
        
        # Second pass: finalize zigzag by alternating between highs and lows
        last_high = 0.0
        last_low = 0.0
        last_high_pos = 0
        last_low_pos = 0
        whatlookfor = 0  # 0=either, 1=peak, -1=valley
        
        for i in range(depth, n):
            if whatlookfor == 0:
                # Looking for first extremum
                if high_buffer[i] != 0:
                    last_high = high[i]
                    last_high_pos = i
                    whatlookfor = -1  # Now look for valley
                    zigzag_buffer[i] = last_high
                    labels[i] = 1  # PEAK
                elif low_buffer[i] != 0:
                    last_low = low[i]
                    last_low_pos = i
                    whatlookfor = 1  # Now look for peak
                    zigzag_buffer[i] = last_low
                    labels[i] = -1  # VALLEY
                    
            elif whatlookfor == 1:
                # Looking for peak
                if low_buffer[i] != 0 and low_buffer[i] < last_low and high_buffer[i] == 0:
                    # Found lower low - update valley position
                    zigzag_buffer[last_low_pos] = 0
                    labels[last_low_pos] = 0
                    last_low_pos = i
                    last_low = low_buffer[i]
                    zigzag_buffer[i] = last_low
                    labels[i] = -1  # VALLEY
                    
                if high_buffer[i] != 0 and low_buffer[i] == 0:
                    # Found peak
                    last_high = high_buffer[i]
                    last_high_pos = i
                    zigzag_buffer[i] = last_high
                    labels[i] = 1  # PEAK
                    whatlookfor = -1  # Now look for valley
                    
            elif whatlookfor == -1:
                # Looking for valley
                if high_buffer[i] != 0 and high_buffer[i] > last_high and low_buffer[i] == 0:
                    # Found higher high - update peak position
                    zigzag_buffer[last_high_pos] = 0
                    labels[last_high_pos] = 0
                    last_high_pos = i
                    last_high = high_buffer[i]
                    zigzag_buffer[i] = last_high
                    labels[i] = 1  # PEAK
                    
                if low_buffer[i] != 0 and high_buffer[i] == 0:
                    # Found valley
                    last_low = low_buffer[i]
                    last_low_pos = i
                    zigzag_buffer[i] = last_low
                    labels[i] = -1  # VALLEY
                    whatlookfor = 1  # Now look for peak
        
        return zigzag_buffer, labels
    
    def get_reversals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get only the reversal points (peaks and valleys).
        
        Args:
            df: DataFrame that has been labeled with label_dataframe()
            
        Returns:
            DataFrame containing only rows where zigzag_label != 0
        """
        if 'zigzag_label' not in df.columns:
            df = self.label_dataframe(df)
        
        return df[df['zigzag_label'] != 0].copy()
    
    def get_statistics(self, df: pd.DataFrame) -> dict:
        """
        Get labeling statistics.
        
        Args:
            df: DataFrame that has been labeled
            
        Returns:
            Dict with counts and percentages
        """
        if 'zigzag_label' not in df.columns:
            df = self.label_dataframe(df)
        
        total = len(df)
        peaks = (df['zigzag_label'] == 1).sum()
        valleys = (df['zigzag_label'] == -1).sum()
        neither = (df['zigzag_label'] == 0).sum()
        
        return {
            'total_candles': total,
            'peaks': peaks,
            'valleys': valleys,
            'neither': neither,
            'peak_pct': round(100 * peaks / total, 2) if total > 0 else 0,
            'valley_pct': round(100 * valleys / total, 2) if total > 0 else 0,
            'reversal_pct': round(100 * (peaks + valleys) / total, 2) if total > 0 else 0,
            'avg_bars_between_reversals': round(total / (peaks + valleys), 1) if (peaks + valleys) > 0 else 0
        }


def label_candles_simple(
    high: np.ndarray,
    low: np.ndarray,
    depth: int = 12,
    deviation: int = 5,
    backstep: int = 3,
    point: float = 0.01
) -> np.ndarray:
    """
    Simple function interface for labeling candles.
    
    Args:
        high: Array of high prices
        low: Array of low prices
        depth: ZigZag depth parameter
        deviation: ZigZag deviation parameter
        backstep: ZigZag backstep parameter
        point: Point size
        
    Returns:
        Array of labels (-1, 0, 1)
    """
    config = ZigZagConfig(
        depth=depth,
        deviation=deviation,
        backstep=backstep,
        point=point
    )
    labeler = ZigZagLabeler(config)
    _, labels = labeler._calculate_zigzag(high, low)
    return labels
