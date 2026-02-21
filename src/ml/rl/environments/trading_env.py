"""
TradingEnvironment - Gymnasium-compatible environment for RL trade decisions.

Task T104: Phase 7, User Story 5 of the intelligent agent trading system.

The agent observes market features (OHLCV + technical indicators),
current position state, and account state, then chooses among
HOLD (0), BUY (1), or SELL (2).

Observation space:
    - Market features: lookback_window rows x num_features columns (flattened)
    - Position state: [position_direction, unrealized_pnl_pct]
    - Account state: [balance_pct_of_initial, current_drawdown]

Action space:
    Discrete(3) -- HOLD=0, BUY=1, SELL=2

Reward:
    Net return per step after transaction costs, with optional Sharpe shaping.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import gymnasium
import numpy as np
from gymnasium import spaces

logger = logging.getLogger(__name__)

# Action constants
HOLD = 0
BUY = 1
SELL = 2


class TradingEnvironment(gymnasium.Env):
    """
    Gymnasium-compatible trading environment for discrete trade decisions.

    Steps through historical candles maintaining a single position at a time.
    Tracks PnL, drawdown, and trade count. Observation includes a lookback
    window of market features plus position and account state vectors.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        prices: np.ndarray,
        features: np.ndarray,
        initial_balance: float = 10_000.0,
        transaction_cost: float = 0.001,
        lookback_window: int = 30,
        max_position: float = 1.0,
        use_sharpe_reward: bool = True,
        sharpe_window: int = 20,
    ):
        """
        Args:
            prices: 1-D array of close prices, length T.
            features: 2-D array (T, num_features) of market features.
                      Must NOT contain future information.
            initial_balance: Starting account balance for PnL tracking.
            transaction_cost: Proportional cost per trade (e.g. 0.001 = 0.1%).
            lookback_window: Number of past bars included in observation.
            max_position: Maximum position size in lots (always 1 unit here).
            use_sharpe_reward: If True, blend rolling Sharpe into the reward.
            sharpe_window: Window length for rolling Sharpe calculation.
        """
        super().__init__()

        assert len(prices) == len(features), (
            f"prices length {len(prices)} != features length {len(features)}"
        )
        assert lookback_window < len(prices), (
            f"lookback_window {lookback_window} >= data length {len(prices)}"
        )

        self.prices = np.asarray(prices, dtype=np.float64)
        self.features = np.asarray(features, dtype=np.float32)
        self.initial_balance = float(initial_balance)
        self.transaction_cost = float(transaction_cost)
        self.lookback_window = int(lookback_window)
        self.max_position = float(max_position)
        self.use_sharpe_reward = bool(use_sharpe_reward)
        self.sharpe_window = int(sharpe_window)

        self.num_features = self.features.shape[1]

        # Observation = flattened lookback features + position state (2) + account state (2)
        obs_size = self.lookback_window * self.num_features + 4
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        # Discrete actions: HOLD=0, BUY=1, SELL=2
        self.action_space = spaces.Discrete(3)

        # Internal state (set on reset)
        self._current_step: int = 0
        self._position: float = 0.0  # -1, 0, or +1
        self._entry_price: float = 0.0
        self._balance: float = self.initial_balance
        self._peak_balance: float = self.initial_balance
        self._returns_history: list = []
        self._trade_count: int = 0
        self._total_pnl: float = 0.0

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Reset the environment to the beginning of the data."""
        super().reset(seed=seed)

        self._current_step = self.lookback_window
        self._position = 0.0
        self._entry_price = 0.0
        self._balance = self.initial_balance
        self._peak_balance = self.initial_balance
        self._returns_history = []
        self._trade_count = 0
        self._total_pnl = 0.0

        obs = self._get_observation()
        info = self._get_info()
        return obs, info

    def step(
        self, action: int
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Execute one step: apply action, compute reward, advance time.

        Returns:
            observation, reward, terminated, truncated, info
        """
        assert self.action_space.contains(action), f"Invalid action {action}"

        current_price = self.prices[self._current_step]
        prev_price = self.prices[self._current_step - 1]
        prev_position = self._position

        # --- Execute action ---
        cost = 0.0
        if action == BUY and self._position <= 0:
            cost = self.transaction_cost * current_price
            if self._position < 0:
                # Close short, realise PnL
                pnl = (self._entry_price - current_price) * abs(self._position)
                self._balance += pnl
                self._total_pnl += pnl
                cost += self.transaction_cost * current_price  # extra leg
            self._position = self.max_position
            self._entry_price = current_price
            self._trade_count += 1

        elif action == SELL and self._position >= 0:
            cost = self.transaction_cost * current_price
            if self._position > 0:
                # Close long, realise PnL
                pnl = (current_price - self._entry_price) * abs(self._position)
                self._balance += pnl
                self._total_pnl += pnl
                cost += self.transaction_cost * current_price
            self._position = -self.max_position
            self._entry_price = current_price
            self._trade_count += 1

        # --- Compute step return ---
        price_return = (current_price - prev_price) / (prev_price + 1e-10)
        position_return = prev_position * price_return
        net_return = position_return - cost / (self._balance + 1e-10)

        self._balance += self._balance * net_return
        self._peak_balance = max(self._peak_balance, self._balance)
        self._returns_history.append(net_return)

        # --- Reward ---
        reward = self._compute_reward(net_return)

        # --- Advance ---
        self._current_step += 1
        terminated = self._current_step >= len(self.prices) - 1
        truncated = False

        obs = self._get_observation()
        info = self._get_info()

        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_observation(self) -> np.ndarray:
        """Build the observation vector."""
        start = self._current_step - self.lookback_window
        end = self._current_step
        market_features = self.features[start:end].flatten()

        # Position state
        unrealized_pnl_pct = 0.0
        if self._position != 0.0 and self._entry_price > 0:
            current_price = self.prices[self._current_step]
            if self._position > 0:
                unrealized_pnl_pct = (current_price - self._entry_price) / self._entry_price
            else:
                unrealized_pnl_pct = (self._entry_price - current_price) / self._entry_price

        position_state = np.array(
            [self._position, unrealized_pnl_pct], dtype=np.float32
        )

        # Account state
        balance_pct = self._balance / (self.initial_balance + 1e-10)
        drawdown = (self._peak_balance - self._balance) / (self._peak_balance + 1e-10)
        account_state = np.array([balance_pct, drawdown], dtype=np.float32)

        obs = np.concatenate([market_features, position_state, account_state])
        return obs.astype(np.float32)

    def _compute_reward(self, net_return: float) -> float:
        """Compute reward from net return with optional Sharpe shaping."""
        if self.use_sharpe_reward and len(self._returns_history) > self.sharpe_window:
            window = np.array(self._returns_history[-self.sharpe_window:])
            sharpe = window.mean() / (window.std() + 1e-8) * np.sqrt(252)
            reward = net_return + 0.1 * sharpe
        else:
            reward = net_return
        return float(reward)

    def _get_info(self) -> Dict[str, Any]:
        """Return diagnostic info dict."""
        drawdown = (self._peak_balance - self._balance) / (self._peak_balance + 1e-10)
        return {
            "step": self._current_step,
            "position": self._position,
            "balance": self._balance,
            "total_pnl": self._total_pnl,
            "drawdown": drawdown,
            "trade_count": self._trade_count,
            "price": float(self.prices[min(self._current_step, len(self.prices) - 1)]),
        }
