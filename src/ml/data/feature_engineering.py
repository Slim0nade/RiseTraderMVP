"""
FeatureEngineering - Create features for ML models
Implements lag features, rolling statistics, and technical indicators
Based on research.md TD-002 (XGBoost) and TD-001 (LSTM)
"""

from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler


class FeatureEngineering:
    """
    Feature engineering for ML forecasting models

    Creates:
    - Lag features for XGBoost
    - Rolling statistics (mean, std, min, max)
    - Technical indicators (RSI, MACD, Bollinger Bands, ATR)
    - Returns and volatility features
    - LSTM sequences
    """

    def __init__(self):
        """Initialize FeatureEngineering"""
        self.scaler = StandardScaler()
        self.feature_names = []

    def create_lag_features(
        self,
        df: pd.DataFrame,
        lag_periods: List[int],
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Create lag features for XGBoost

        Args:
            df: Input DataFrame
            lag_periods: List of lag periods (e.g., [1, 2, 3, 5, 10, 20, 60])
            columns: Columns to create lags for (defaults to ['close', 'volume'])

        Returns:
            DataFrame with lag features added
        """
        df = df.copy()

        if columns is None:
            columns = ['close', 'volume']

        for col in columns:
            if col in df.columns:
                for lag in lag_periods:
                    feature_name = f'{col}_lag_{lag}'
                    df[feature_name] = df[col].shift(lag)
                    self.feature_names.append(feature_name)

        return df

    def create_rolling_statistics(
        self,
        df: pd.DataFrame,
        windows: List[int],
        column: str = 'close'
    ) -> pd.DataFrame:
        """
        Create rolling window statistics

        Args:
            df: Input DataFrame
            windows: List of window sizes (e.g., [5, 10, 20])
            column: Column to calculate statistics for

        Returns:
            DataFrame with rolling statistics added
        """
        df = df.copy()

        for window in windows:
            # Rolling mean
            feature_name = f'{column}_rolling_mean_{window}'
            df[feature_name] = df[column].rolling(window=window).mean()
            self.feature_names.append(feature_name)

            # Rolling std
            feature_name = f'{column}_rolling_std_{window}'
            df[feature_name] = df[column].rolling(window=window).std()
            self.feature_names.append(feature_name)

            # Rolling min
            feature_name = f'{column}_rolling_min_{window}'
            df[feature_name] = df[column].rolling(window=window).min()
            self.feature_names.append(feature_name)

            # Rolling max
            feature_name = f'{column}_rolling_max_{window}'
            df[feature_name] = df[column].rolling(window=window).max()
            self.feature_names.append(feature_name)

        return df

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculate RSI (Relative Strength Index)

        Args:
            df: Input DataFrame with 'close' column
            period: RSI period (default: 14)

        Returns:
            DataFrame with RSI column added
        """
        df = df.copy()

        # Calculate price changes
        delta = df['close'].diff()

        # Separate gains and losses
        gains = delta.where(delta > 0, 0.0)
        losses = -delta.where(delta < 0, 0.0)

        # Calculate average gains and losses
        avg_gains = gains.rolling(window=period, min_periods=period).mean()
        avg_losses = losses.rolling(window=period, min_periods=period).mean()

        # Calculate RS and RSI
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))

        df[f'rsi_{period}'] = rsi
        self.feature_names.append(f'rsi_{period}')

        return df

    def calculate_macd(
        self,
        df: pd.DataFrame,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> pd.DataFrame:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Args:
            df: Input DataFrame with 'close' column
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line EMA period

        Returns:
            DataFrame with MACD columns added
        """
        df = df.copy()

        # Calculate EMAs
        ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()

        # MACD line
        df['macd'] = ema_fast - ema_slow

        # Signal line
        df['macd_signal'] = df['macd'].ewm(span=signal_period, adjust=False).mean()

        # Histogram
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        self.feature_names.extend(['macd', 'macd_signal', 'macd_histogram'])

        return df

    def calculate_bollinger_bands(
        self,
        df: pd.DataFrame,
        period: int = 20,
        std_dev: int = 2
    ) -> pd.DataFrame:
        """
        Calculate Bollinger Bands

        Args:
            df: Input DataFrame with 'close' column
            period: Moving average period
            std_dev: Number of standard deviations

        Returns:
            DataFrame with Bollinger Bands columns added
        """
        df = df.copy()

        # Middle band (SMA)
        df['bb_middle'] = df['close'].rolling(window=period).mean()

        # Standard deviation
        rolling_std = df['close'].rolling(window=period).std()

        # Upper and lower bands
        df['bb_upper'] = df['bb_middle'] + (rolling_std * std_dev)
        df['bb_lower'] = df['bb_middle'] - (rolling_std * std_dev)

        self.feature_names.extend(['bb_upper', 'bb_lower', 'bb_middle'])

        return df

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculate ATR (Average True Range)

        Args:
            df: Input DataFrame with 'high', 'low', 'close' columns
            period: ATR period

        Returns:
            DataFrame with ATR column added
        """
        df = df.copy()

        # True Range components
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())

        # True Range
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # ATR (moving average of True Range)
        df['atr'] = true_range.rolling(window=period).mean()
        self.feature_names.append('atr')

        return df

    def create_technical_indicators(
        self,
        df: pd.DataFrame,
        indicators: List[str]
    ) -> pd.DataFrame:
        """
        Create all specified technical indicators

        Args:
            df: Input DataFrame
            indicators: List of indicators to create

        Returns:
            DataFrame with indicators added
        """
        df = df.copy()

        if 'rsi_14' in indicators:
            df = self.calculate_rsi(df, period=14)

        if 'macd' in indicators:
            df = self.calculate_macd(df)

        if 'bb_upper' in indicators or 'bb_lower' in indicators:
            df = self.calculate_bollinger_bands(df)

        if 'atr' in indicators:
            df = self.calculate_atr(df)

        return df

    def create_returns(
        self,
        df: pd.DataFrame,
        periods: List[int],
        column: str = 'close'
    ) -> pd.DataFrame:
        """
        Create return features

        Args:
            df: Input DataFrame
            periods: List of periods for returns
            column: Column to calculate returns for

        Returns:
            DataFrame with return features added
        """
        df = df.copy()

        for period in periods:
            # Simple returns
            feature_name = f'returns_{period}'
            df[feature_name] = df[column].pct_change(periods=period)
            self.feature_names.append(feature_name)

            # Log returns
            feature_name = f'log_returns_{period}'
            df[feature_name] = np.log(df[column] / df[column].shift(period))
            self.feature_names.append(feature_name)

        return df

    def create_volatility(
        self,
        df: pd.DataFrame,
        window: int = 20,
        column: str = 'close'
    ) -> pd.DataFrame:
        """
        Create volatility features

        Args:
            df: Input DataFrame
            window: Rolling window for volatility calculation
            column: Column to calculate volatility for

        Returns:
            DataFrame with volatility features added
        """
        df = df.copy()

        # Calculate returns
        returns = df[column].pct_change()

        # Rolling volatility (std of returns)
        feature_name = f'volatility_{window}'
        df[feature_name] = returns.rolling(window=window).std()
        self.feature_names.append(feature_name)

        return df

    def normalize_features(
        self,
        df: pd.DataFrame,
        method: str = 'z-score'
    ) -> pd.DataFrame:
        """
        Normalize features using Z-score or min-max

        Args:
            df: Input DataFrame
            method: Normalization method ('z-score' or 'min-max')

        Returns:
            Normalized DataFrame
        """
        df = df.copy()

        # Get numeric columns (excluding timestamp)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        numeric_cols = [col for col in numeric_cols if col != 'timestamp']

        if method == 'z-score':
            df[numeric_cols] = self.scaler.fit_transform(df[numeric_cols])
        elif method == 'min-max':
            df[numeric_cols] = (df[numeric_cols] - df[numeric_cols].min()) / (
                df[numeric_cols].max() - df[numeric_cols].min()
            )

        return df

    def handle_missing_values(
        self,
        df: pd.DataFrame,
        method: str = 'forward_fill'
    ) -> pd.DataFrame:
        """
        Handle missing values

        Args:
            df: Input DataFrame
            method: Method for handling missing values

        Returns:
            DataFrame with missing values handled
        """
        df = df.copy()

        if method == 'forward_fill':
            df = df.fillna(method='ffill')
            df = df.fillna(method='bfill')  # Backward fill remaining
        elif method == 'drop':
            df = df.dropna()
        elif method == 'zero':
            df = df.fillna(0)

        return df

    def merge_exogenous_features(
        self,
        df: pd.DataFrame,
        exogenous_df: pd.DataFrame,
        normalize: bool = True
    ) -> pd.DataFrame:
        """
        Merge exogenous variables (DXY, VIX) with OHLCV data.

        Performs time-alignment and optional Z-score normalization
        per research.md TD-003.

        Args:
            df: OHLCV DataFrame with 'timestamp' index
            exogenous_df: Exogenous variables DataFrame with columns for each symbol
            normalize: Whether to apply Z-score normalization to exogenous features

        Returns:
            Merged DataFrame with exogenous features
        """
        df = df.copy()

        # Ensure timestamp is index for both
        if 'timestamp' in df.columns and df.index.name != 'timestamp':
            df = df.set_index('timestamp')

        if 'timestamp' in exogenous_df.columns and exogenous_df.index.name != 'timestamp':
            exogenous_df = exogenous_df.set_index('timestamp')

        # Merge on timestamp index (left join to keep all OHLCV rows)
        df = df.join(exogenous_df, how='left')

        # Forward fill missing exogenous values (handles minor time misalignments)
        exogenous_cols = exogenous_df.columns.tolist()
        df[exogenous_cols] = df[exogenous_cols].fillna(method='ffill')

        # Backward fill any remaining NaNs at the start
        df[exogenous_cols] = df[exogenous_cols].fillna(method='bfill')

        # Apply Z-score normalization to exogenous variables
        if normalize:
            df = self.normalize_exogenous_variables(df, exogenous_cols)

        return df

    def normalize_exogenous_variables(
        self,
        df: pd.DataFrame,
        exogenous_columns: List[str]
    ) -> pd.DataFrame:
        """
        Apply Z-score normalization to exogenous variables.

        Per research.md TD-003: DXY and VIX normalized using Z-score
        to ensure comparable scales with price features.

        Args:
            df: DataFrame with exogenous features
            exogenous_columns: List of exogenous column names

        Returns:
            DataFrame with normalized exogenous features
        """
        df = df.copy()

        for col in exogenous_columns:
            if col in df.columns:
                # Z-score normalization: (x - mean) / std
                mean = df[col].mean()
                std = df[col].std()

                if std > 0:  # Avoid division by zero
                    df[f'{col}_normalized'] = (df[col] - mean) / std
                    self.feature_names.append(f'{col}_normalized')
                else:
                    # If std is 0, feature is constant
                    df[f'{col}_normalized'] = 0
                    self.feature_names.append(f'{col}_normalized')

        return df

    def create_sequences_for_lstm(
        self,
        df: pd.DataFrame,
        lookback_window: int,
        target_column: str = 'close'
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for LSTM training

        Args:
            df: Input DataFrame
            lookback_window: Number of timesteps to look back
            target_column: Column to predict

        Returns:
            Tuple of (X, y) arrays for LSTM
        """
        # Get feature columns (exclude timestamp and target)
        feature_cols = [col for col in df.columns if col not in ['timestamp', target_column]]

        data = df[feature_cols + [target_column]].values

        X, y = [], []
        for i in range(lookback_window, len(data)):
            X.append(data[i-lookback_window:i, :-1])  # Features
            y.append(data[i, -1])  # Target

        return np.array(X), np.array(y)

    def create_features_for_xgboost(
        self,
        df: pd.DataFrame,
        lag_periods: List[int],
        rolling_windows: List[int],
        indicators: List[str]
    ) -> pd.DataFrame:
        """
        Create all features for XGBoost model

        Args:
            df: Input DataFrame
            lag_periods: Lag periods to create
            rolling_windows: Rolling window sizes
            indicators: Technical indicators to create

        Returns:
            DataFrame with all XGBoost features
        """
        df = df.copy()

        # Create lag features
        df = self.create_lag_features(df, lag_periods)

        # Create rolling statistics
        df = self.create_rolling_statistics(df, rolling_windows)

        # Create technical indicators
        df = self.create_technical_indicators(df, indicators)

        # Drop rows with NaN values created by windowing
        df = df.dropna()

        return df

    def transform(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """
        Complete feature engineering pipeline

        Args:
            df: Input DataFrame
            config: Configuration dictionary

        Returns:
            Transformed DataFrame
        """
        df = df.copy()

        # Lag features
        if 'lag_periods' in config:
            df = self.create_lag_features(df, config['lag_periods'])

        # Rolling statistics
        if 'rolling_windows' in config:
            df = self.create_rolling_statistics(df, config['rolling_windows'])

        # Technical indicators
        if 'indicators' in config:
            df = self.create_technical_indicators(df, config['indicators'])

        # Returns
        if 'return_periods' in config:
            df = self.create_returns(df, config['return_periods'])

        # Handle missing values
        df = self.handle_missing_values(df)

        # Normalize
        if config.get('normalize', False):
            df = self.normalize_features(df)

        return df

    def get_feature_names(self) -> List[str]:
        """Get list of created feature names"""
        return self.feature_names
