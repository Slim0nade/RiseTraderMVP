"""
PositionSizingEnvironment - Gymnasium environment for learning optimal position sizes.

Task T105: Phase 7, User Story 5.

Given a pre-determined trade direction (signal already generated), the agent
decides what fraction of available capital to allocate. The observation includes
market features, a conviction score from the signal generator, and the current
market regime.

Action space:
    Box(low=0.0, high=1.0, shape=(1,)) -- fraction of capital to risk.

Observation space:
    [market_features_flat, conviction_score, regime_encoding, volatility,
     current_drawdown, balance_pct]

Reward:
    Risk-adjusted return: Sharpe contribution - drawdown penalty - transaction costs.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import gymnasium
import numpy as np
from gymnasium import spaces

logger = logging.getLogger(__name__)


class PositionSizingEnvironment(gymnasium.Env):
    """
    Gymnasium environment for continuous position sizing decisions.

    The agent receives a trade signal (direction is predetermined) and
    decides the fraction of capital to allocate. Reward is shaped to
    maximise risk-adjusted returns while penalising drawdown.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        prices: np.ndarray,
        features: np.ndarray,
        signals: np.ndarray,
        conviction_scores: np.ndarray,
        regime_labels: np.ndarray,
        initial_balance: float = 10_000.0,
        transaction_cost: float = 0.001,
        lookback_window: int = 30,
        max_drawdown_penalty: float = 2.0,
    ):
        """
        Args:
            prices: 1-D close prices array of length T.
            features: 2-D array (T, num_features).
            signals: 1-D array of trade directions (+1 long, -1 short, 0 flat).
            conviction_scores: 1-D array in [0, 1] indicating signal confidence.
            regime_labels: 1-D integer array encoding market regime
                           (e.g. 0=trending, 1=ranging, 2=volatile).
            initial_balance: Starting account balance.
            transaction_cost: Proportional cost per trade.
            lookback_window: Number of historical bars in observation.
            max_drawdown_penalty: Coefficient for drawdown penalty in reward.
        """
        super().__init__()

        n = len(prices)
        assert len(features) == n
        assert len(signals) == n
        assert len(conviction_scores) == n
        assert len(regime_labels) == n
        assert lookback_window < n

        self.prices = np.asarray(prices, dtype=np.float64)
        self.features = np.asarray(features, dtype=np.float32)
        self.signals = np.asarray(signals, dtype=np.float32)
        self.conviction_scores = np.asarray(conviction_scores, dtype=np.float32)
        self.regime_labels = np.asarray(regime_labels, dtype=np.int32)
        self.initial_balance = float(initial_balance)
        self.transaction_cost = float(transaction_cost)
        self.lookback_window = int(lookback_window)
        self.max_drawdown_penalty = float(max_drawdown_penalty)

        self.num_features = self.features.shape[1]
        # Number of unique regimes for one-hot encoding
        self.num_regimes = int(np.max(self.regime_labels)) + 1

        # Observation: flattened lookback features + conviction + regime_onehot
        #              + volatility + drawdown + balance_pct
        obs_size = (
            self.lookback_window * self.num_features
            + 1  # conviction
            + self.num_regimes  # regime one-hot
            + 1  # recent volatility
            + 1  # current drawdown
            + 1  # balance_pct
        )
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        # Action: fraction of capital to allocate [0, 1]
        self.action_space = spaces.Box(
            low=np.float32(0.0), high=np.float32(1.0), shape=(1,), dtype=np.float32
        )

        # State
        self._current_step: int = 0
        self._balance: float = self.initial_balance
        self._peak_balance: float = self.initial_balance
        self._returns_history: list = []
        self._trade_count: int = 0

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
        self._peak_balance = self.initial_balance
        self._returns_history = []
        self._trade_count = 0

        return self._get_observation(), self._get_info()

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        fraction = float(np.clip(action[0], 0.0, 1.0))

        current_price = self.prices[self._current_step]
        prev_price = self.prices[self._current_step - 1]
        signal = float(self.signals[self._current_step])

        # Position direction comes from signal; sizing from the agent
        position_size = fraction * signal  # can be negative (short)
        price_return = (current_price - prev_price) / (prev_price + 1e-10)
        gross_return = position_size * price_return

        # Transaction cost proportional to absolute position change
        cost = abs(fraction) * self.transaction_cost
        net_return = gross_return - cost

        self._balance += self._balance * net_return
        self._peak_balance = max(self._peak_balance, self._balance)
        self._returns_history.append(net_return)
        if fraction > 0.01:
            self._trade_count += 1

        # Reward: Sharpe contribution - drawdown penalty - cost
        drawdown = (self._peak_balance - self._balance) / (self._peak_balance + 1e-10)
        reward = net_return - self.max_drawdown_penalty * max(0.0, drawdown - 0.05)

        self._current_step += 1
        terminated = self._current_step >= len(self.prices) - 1
        truncated = False

        return self._get_observation(), float(reward), terminated, truncated, self._get_info()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_observation(self) -> np.ndarray:
        start = self._current_step - self.lookback_window
        end = self._current_step
        market_flat = self.features[start:end].flatten()

        conviction = np.array([self.conviction_scores[self._current_step]], dtype=np.float32)

        regime_onehot = np.zeros(self.num_regimes, dtype=np.float32)
        regime_idx = int(self.regime_labels[self._current_step])
        if 0 <= regime_idx < self.num_regimes:
            regime_onehot[regime_idx] = 1.0

        # Recent volatility (std of last 20 returns)
        if len(self._returns_history) >= 20:
            vol = np.std(self._returns_history[-20:])
        else:
            vol = 0.0
        volatility = np.array([vol], dtype=np.float32)

        drawdown = (self._peak_balance - self._balance) / (self._peak_balance + 1e-10)
        balance_pct = self._balance / (self.initial_balance + 1e-10)

        obs = np.concatenate([
            market_flat,
            conviction,
            regime_onehot,
            volatility,
            np.array([drawdown], dtype=np.float32),
            np.array([balance_pct], dtype=np.float32),
        ])
        return obs.astype(np.float32)

    def _get_info(self) -> Dict[str, Any]:
        drawdown = (self._peak_balance - self._balance) / (self._peak_balance + 1e-10)
        return {
            "step": self._current_step,
            "balance": self._balance,
            "drawdown": drawdown,
            "trade_count": self._trade_count,
            "price": float(self.prices[min(self._current_step, len(self.prices) - 1)]),
        }
