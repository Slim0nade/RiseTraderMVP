"""
TakeProfitEnvironment - Gymnasium environment for adaptive take-profit placement.

Task T107: Phase 7, User Story 5.

The agent selects a take-profit level expressed as a reward-to-risk ratio.
It observes market features and forecast quantiles, then decides the R:R
target for each trade.

Action space:
    Box(low=1.0, high=10.0, shape=(1,)) -- reward-to-risk ratio.

Observation space:
    [market_features_flat, forecast_q25, forecast_q50, forecast_q75,
     atr, position_direction]

Reward:
    Maximise expected value captured from profitable moves.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import gymnasium
import numpy as np
from gymnasium import spaces

logger = logging.getLogger(__name__)


class TakeProfitEnvironment(gymnasium.Env):
    """
    Gymnasium environment for learning optimal take-profit R:R ratios.

    Given a trade entry, the agent decides how far to set the take-profit
    relative to the risk (stop distance). The environment simulates bar-by-bar
    price action to determine whether TP is hit before the trade horizon expires.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        prices_high: np.ndarray,
        prices_low: np.ndarray,
        prices_close: np.ndarray,
        features: np.ndarray,
        atr_values: np.ndarray,
        forecast_q25: np.ndarray,
        forecast_q50: np.ndarray,
        forecast_q75: np.ndarray,
        trade_directions: np.ndarray,
        stop_atr_multiplier: float = 2.0,
        lookback_window: int = 30,
        trade_horizon: int = 40,
        initial_balance: float = 10_000.0,
    ):
        """
        Args:
            prices_high: 1-D high prices, length T.
            prices_low: 1-D low prices, length T.
            prices_close: 1-D close prices, length T.
            features: 2-D array (T, num_features).
            atr_values: 1-D ATR values, length T.
            forecast_q25: 1-D 25th percentile forecast, length T.
            forecast_q50: 1-D median forecast, length T.
            forecast_q75: 1-D 75th percentile forecast, length T.
            trade_directions: 1-D (+1 or -1), length T.
            stop_atr_multiplier: Fixed stop loss ATR multiplier (used to define risk).
            lookback_window: Past bars in observation.
            trade_horizon: Maximum bars to hold a trade.
            initial_balance: Starting capital.
        """
        super().__init__()

        n = len(prices_close)
        assert all(len(a) == n for a in [
            prices_high, prices_low, features, atr_values,
            forecast_q25, forecast_q50, forecast_q75, trade_directions
        ])
        assert lookback_window < n

        self.prices_high = np.asarray(prices_high, dtype=np.float64)
        self.prices_low = np.asarray(prices_low, dtype=np.float64)
        self.prices_close = np.asarray(prices_close, dtype=np.float64)
        self.features = np.asarray(features, dtype=np.float32)
        self.atr_values = np.asarray(atr_values, dtype=np.float64)
        self.forecast_q25 = np.asarray(forecast_q25, dtype=np.float32)
        self.forecast_q50 = np.asarray(forecast_q50, dtype=np.float32)
        self.forecast_q75 = np.asarray(forecast_q75, dtype=np.float32)
        self.trade_directions = np.asarray(trade_directions, dtype=np.float32)
        self.stop_atr_multiplier = float(stop_atr_multiplier)
        self.lookback_window = int(lookback_window)
        self.trade_horizon = int(trade_horizon)
        self.initial_balance = float(initial_balance)

        self.num_features = self.features.shape[1]

        # Observation: market features (flat) + q25 + q50 + q75 + atr + direction
        obs_size = self.lookback_window * self.num_features + 5
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        # Action: R:R ratio in [1.0, 10.0]
        self.action_space = spaces.Box(
            low=np.float32(1.0), high=np.float32(10.0), shape=(1,), dtype=np.float32
        )

        # State
        self._current_step: int = 0
        self._balance: float = self.initial_balance
        self._trade_count: int = 0
        self._tp_hits: int = 0
        self._total_ev_captured: float = 0.0

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        self._current_step = self.lookback_window
        self._balance = self.initial_balance
        self._trade_count = 0
        self._tp_hits = 0
        self._total_ev_captured = 0.0
        return self._get_observation(), self._get_info()

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        rr_ratio = float(np.clip(action[0], 1.0, 10.0))

        entry_price = self.prices_close[self._current_step]
        direction = float(self.trade_directions[self._current_step])
        atr = self.atr_values[self._current_step]
        risk = self.stop_atr_multiplier * atr

        # Compute TP and SL prices
        if direction > 0:
            stop_price = entry_price - risk
            tp_price = entry_price + rr_ratio * risk
        else:
            stop_price = entry_price + risk
            tp_price = entry_price - rr_ratio * risk

        # Simulate trade
        exit_price = entry_price
        tp_hit = False
        sl_hit = False
        bars_held = 0
        end_idx = min(self._current_step + self.trade_horizon, len(self.prices_close) - 1)

        for t in range(self._current_step + 1, end_idx + 1):
            bars_held += 1
            if direction > 0:
                if self.prices_high[t] >= tp_price:
                    exit_price = tp_price
                    tp_hit = True
                    break
                if self.prices_low[t] <= stop_price:
                    exit_price = stop_price
                    sl_hit = True
                    break
                exit_price = self.prices_close[t]
            else:
                if self.prices_low[t] <= tp_price:
                    exit_price = tp_price
                    tp_hit = True
                    break
                if self.prices_high[t] >= stop_price:
                    exit_price = stop_price
                    sl_hit = True
                    break
                exit_price = self.prices_close[t]

        # PnL
        if direction > 0:
            pnl_pct = (exit_price - entry_price) / (entry_price + 1e-10)
        else:
            pnl_pct = (entry_price - exit_price) / (entry_price + 1e-10)

        # Maximum favourable excursion during trade for EV comparison
        trade_slice = slice(self._current_step + 1, self._current_step + 1 + bars_held + 1)
        if direction > 0:
            max_price = np.max(self.prices_high[trade_slice]) if bars_held > 0 else entry_price
            max_pnl_pct = (max_price - entry_price) / (entry_price + 1e-10)
        else:
            min_price = np.min(self.prices_low[trade_slice]) if bars_held > 0 else entry_price
            max_pnl_pct = (entry_price - min_price) / (entry_price + 1e-10)

        profit_captured_pct = pnl_pct / (max_pnl_pct + 1e-10) if max_pnl_pct > 0 else 0.0
        profit_captured_pct = max(0.0, min(1.0, profit_captured_pct))

        # Expected value from forecast median
        expected_move = abs(float(self.forecast_q50[self._current_step]) - entry_price)
        expected_value = expected_move / (entry_price + 1e-10)

        # Reward
        from src.ml.rl.rewards.reward_functions import take_profit_reward
        reward = take_profit_reward(
            profit_captured_pct=profit_captured_pct,
            expected_value=expected_value,
            partial_fills=not tp_hit and not sl_hit,
        )

        # Update state
        self._balance += self._balance * pnl_pct
        self._trade_count += 1
        if tp_hit:
            self._tp_hits += 1
        self._total_ev_captured += profit_captured_pct

        # Advance
        self._current_step = min(
            self._current_step + max(bars_held, 1),
            len(self.prices_close) - 2,
        )
        terminated = self._current_step >= len(self.prices_close) - 2
        truncated = False

        return self._get_observation(), float(reward), terminated, truncated, self._get_info()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_observation(self) -> np.ndarray:
        idx = min(self._current_step, len(self.prices_close) - 1)
        start = max(0, idx - self.lookback_window)
        market_flat = self.features[start:idx].flatten()
        expected = self.lookback_window * self.num_features
        if len(market_flat) < expected:
            market_flat = np.pad(market_flat, (expected - len(market_flat), 0))

        extras = np.array([
            self.forecast_q25[idx],
            self.forecast_q50[idx],
            self.forecast_q75[idx],
            self.atr_values[idx],
            self.trade_directions[idx],
        ], dtype=np.float32)

        obs = np.concatenate([market_flat, extras])
        return obs.astype(np.float32)

    def _get_info(self) -> Dict[str, Any]:
        return {
            "step": self._current_step,
            "balance": self._balance,
            "trade_count": self._trade_count,
            "tp_hits": self._tp_hits,
            "avg_ev_captured": (
                self._total_ev_captured / max(1, self._trade_count)
            ),
        }
