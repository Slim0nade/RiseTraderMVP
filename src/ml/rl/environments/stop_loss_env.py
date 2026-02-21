"""
StopLossEnvironment - Gymnasium environment for adaptive stop-loss placement.

Task T106: Phase 7, User Story 5.

The agent chooses a stop-loss distance expressed as an ATR multiplier.
It observes market features, current volatility (ATR), and distances to
nearby support/resistance levels, then decides where to place the stop.

Action space:
    Box(low=0.5, high=5.0, shape=(1,)) -- ATR multiplier for stop distance.

Observation space:
    [market_features_flat, atr, support_distance, resistance_distance,
     position_direction, unrealized_pnl_pct]

Reward:
    Rewards capital protection on adverse moves and penalises unnecessary
    stop-outs that cause whipsaw losses.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import gymnasium
import numpy as np
from gymnasium import spaces

logger = logging.getLogger(__name__)


class StopLossEnvironment(gymnasium.Env):
    """
    Gymnasium environment for learning optimal stop-loss ATR multipliers.

    Each episode simulates a sequence of trades where the agent sets the
    stop-loss level at entry. The stop is then evaluated bar-by-bar until
    it is hit or the trade reaches the end of the window.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        prices_high: np.ndarray,
        prices_low: np.ndarray,
        prices_close: np.ndarray,
        features: np.ndarray,
        atr_values: np.ndarray,
        support_distances: np.ndarray,
        resistance_distances: np.ndarray,
        trade_directions: np.ndarray,
        lookback_window: int = 30,
        trade_horizon: int = 20,
        initial_balance: float = 10_000.0,
    ):
        """
        Args:
            prices_high: 1-D high prices, length T.
            prices_low: 1-D low prices, length T.
            prices_close: 1-D close prices, length T.
            features: 2-D array (T, num_features).
            atr_values: 1-D ATR values, length T.
            support_distances: 1-D distance-to-support in price units, length T.
            resistance_distances: 1-D distance-to-resistance in price units, length T.
            trade_directions: 1-D (+1 or -1) indicating trade direction per bar.
            lookback_window: Past bars in observation.
            trade_horizon: Maximum bars to hold a trade before forced exit.
            initial_balance: Starting capital.
        """
        super().__init__()

        n = len(prices_close)
        assert all(len(a) == n for a in [
            prices_high, prices_low, features, atr_values,
            support_distances, resistance_distances, trade_directions
        ])
        assert lookback_window < n

        self.prices_high = np.asarray(prices_high, dtype=np.float64)
        self.prices_low = np.asarray(prices_low, dtype=np.float64)
        self.prices_close = np.asarray(prices_close, dtype=np.float64)
        self.features = np.asarray(features, dtype=np.float32)
        self.atr_values = np.asarray(atr_values, dtype=np.float64)
        self.support_distances = np.asarray(support_distances, dtype=np.float32)
        self.resistance_distances = np.asarray(resistance_distances, dtype=np.float32)
        self.trade_directions = np.asarray(trade_directions, dtype=np.float32)
        self.lookback_window = int(lookback_window)
        self.trade_horizon = int(trade_horizon)
        self.initial_balance = float(initial_balance)

        self.num_features = self.features.shape[1]

        # Observation: market features (flat) + atr + support_dist + resistance_dist
        #              + position_dir + unrealized_pnl_pct
        obs_size = self.lookback_window * self.num_features + 5
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        # Action: ATR multiplier in [0.5, 5.0]
        self.action_space = spaces.Box(
            low=np.float32(0.5), high=np.float32(5.0), shape=(1,), dtype=np.float32
        )

        # State
        self._current_step: int = 0
        self._balance: float = self.initial_balance
        self._trade_count: int = 0
        self._stop_outs: int = 0
        self._unnecessary_stops: int = 0

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
        self._stop_outs = 0
        self._unnecessary_stops = 0
        return self._get_observation(), self._get_info()

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        atr_mult = float(np.clip(action[0], 0.5, 5.0))

        entry_price = self.prices_close[self._current_step]
        direction = float(self.trade_directions[self._current_step])
        atr = self.atr_values[self._current_step]
        stop_distance = atr_mult * atr

        if direction > 0:
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        # Simulate the trade forward up to trade_horizon bars
        stopped_out = False
        exit_price = entry_price
        bars_held = 0
        end_idx = min(self._current_step + self.trade_horizon, len(self.prices_close) - 1)

        for t in range(self._current_step + 1, end_idx + 1):
            bars_held += 1
            if direction > 0:
                # Long: stop if low breaches stop_price
                if self.prices_low[t] <= stop_price:
                    exit_price = stop_price
                    stopped_out = True
                    break
                exit_price = self.prices_close[t]
            else:
                # Short: stop if high breaches stop_price
                if self.prices_high[t] >= stop_price:
                    exit_price = stop_price
                    stopped_out = True
                    break
                exit_price = self.prices_close[t]

        # Compute PnL
        if direction > 0:
            pnl = (exit_price - entry_price) / (entry_price + 1e-10)
        else:
            pnl = (entry_price - exit_price) / (entry_price + 1e-10)

        capital_protected_pct = max(0.0, -pnl) if stopped_out and pnl < 0 else 0.0

        # Check if the stop was unnecessary: price reversed back in favour
        # after hitting the stop
        unnecessary_stop = False
        if stopped_out:
            # Check remaining bars after the stop
            stop_bar = self._current_step + bars_held
            remaining_end = min(stop_bar + self.trade_horizon, len(self.prices_close) - 1)
            if remaining_end > stop_bar:
                if direction > 0:
                    best_after = np.max(self.prices_high[stop_bar:remaining_end + 1])
                    if best_after > entry_price:
                        unnecessary_stop = True
                else:
                    best_after = np.min(self.prices_low[stop_bar:remaining_end + 1])
                    if best_after < entry_price:
                        unnecessary_stop = True

        # Update stats
        self._balance += self._balance * pnl
        self._trade_count += 1
        if stopped_out:
            self._stop_outs += 1
        if unnecessary_stop:
            self._unnecessary_stops += 1

        # Reward: capital protection + penalise unnecessary stops
        from src.ml.rl.rewards.reward_functions import stop_loss_reward
        reward = stop_loss_reward(
            stopped_out=stopped_out,
            capital_protected_pct=capital_protected_pct,
            unnecessary_stop=unnecessary_stop,
        )

        # Advance by trade_horizon or until next trade opportunity
        self._current_step = min(self._current_step + max(bars_held, 1), len(self.prices_close) - 2)
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
        # Pad if not enough history
        expected = self.lookback_window * self.num_features
        if len(market_flat) < expected:
            market_flat = np.pad(market_flat, (expected - len(market_flat), 0))

        extras = np.array([
            self.atr_values[idx],
            self.support_distances[idx],
            self.resistance_distances[idx],
            self.trade_directions[idx],
            0.0,  # unrealized PnL placeholder (evaluated at entry)
        ], dtype=np.float32)

        obs = np.concatenate([market_flat, extras])
        return obs.astype(np.float32)

    def _get_info(self) -> Dict[str, Any]:
        return {
            "step": self._current_step,
            "balance": self._balance,
            "trade_count": self._trade_count,
            "stop_outs": self._stop_outs,
            "unnecessary_stops": self._unnecessary_stops,
        }
