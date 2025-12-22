"""
Gymnasium Environment for Backtesting (User Story 3).

Wraps the backtesting engine as a Gymnasium Env for RL training.
Compatible with Stable-Baselines3 and other RL libraries.

Features:
- Observation space: Market state (candles, indicators, position)
- Action space: Trading actions (HOLD, BUY, SELL)
- Reward: Configurable (simple P&L, risk-adjusted, sparse)
- Episode management: Handles termination and truncation
- Normalization: Observations normalized to [-1, 1]

T084: Create BacktestTradingEnv class implementing gymnasium.Env
T085: Implement reset() method with random starting point and seed support
T086: Implement step(action) method with trade execution and reward calculation
T087: Define observation_space (Box for continuous market state)
T088: Define action_space (Discrete or Box based on config)
T089: Implement episode management (termination on bankruptcy or max steps)
T090: Add observation normalization (scale to [-1, 1] range)
T091: Implement reward shaping options (simple P&L, risk-adjusted, sparse)
T092: Add render() method for visualization (optional, text-based)
T093: Implement close() method for cleanup
T094: Add episode statistics tracking (cumulative reward, Sharpe, drawdown)
"""
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from src.services.backtesting.data_replay_engine import DataReplayEngine, MarketTick
from src.services.backtesting.portfolio_state import PortfolioState
from src.services.backtesting.trade_simulator import TradeSimulator
from src.services.backtesting.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


@dataclass
class EpisodeStatistics:
    """Statistics for a single episode."""

    episode_number: int = 0
    total_reward: float = 0.0
    episode_length: int = 0
    final_capital: Decimal = Decimal("0")
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0
    rewards_history: List[float] = field(default_factory=list)


class BacktestTradingEnv(gym.Env):
    """
    Gymnasium environment for backtesting-based RL training.

    This environment allows RL agents to learn trading strategies by
    interacting with historical market data through the backtesting engine.

    Args:
        config: Environment configuration dictionary
            - symbol: Trading symbol (e.g., "EURUSD")
            - timeframe: Timeframe (e.g., "M5")
            - initial_capital: Starting capital (default: 10000.0)
            - start_date: Data start date
            - end_date: Data end date
            - lookback_window: Number of candles in observation (default: 10)
            - max_steps: Maximum steps per episode (default: 1000)
            - observation_type: "candles" or "indicators" (default: "candles")
            - action_type: "discrete" or "continuous" (default: "discrete")
            - reward_type: "simple_pnl", "risk_adjusted", or "sparse" (default: "simple_pnl")
            - position_size: Fixed position size (default: 1.0)
            - render_mode: "human" or None (default: None)

    Observation Space:
        Box(shape=(lookback_window, 5), dtype=float32) for candles (OHLCV)
        or Box(shape=(n_indicators,), dtype=float32) for indicators

    Action Space:
        Discrete(3): 0=HOLD, 1=BUY, 2=SELL
        or Box for continuous position sizing

    Rewards:
        - simple_pnl: Change in capital (realized + unrealized)
        - risk_adjusted: P&L scaled by volatility (Sharpe-like)
        - sparse: Reward only on trade close
    """

    metadata = {"render_modes": ["human"], "render_fps": 1}

    def __init__(
        self,
        config: Dict[str, Any],
        market_data: Optional[List[Any]] = None,
        render_mode: Optional[str] = None,
    ):
        """
        Initialize the trading environment (T084).

        Args:
            config: Environment configuration
            market_data: Pre-loaded market data (optional, for testing)
            render_mode: Rendering mode ("human" or None)
        """
        super().__init__()

        # Store configuration
        self.config = config
        self.symbol = config.get("symbol", "EURUSD")
        self.timeframe = config.get("timeframe", "M5")
        self.initial_capital = Decimal(str(config.get("initial_capital", 10000.0)))
        self.lookback_window = config.get("lookback_window", 10)
        self.max_steps = config.get("max_steps", 1000)
        self.observation_type = config.get("observation_type", "candles")
        self.action_type = config.get("action_type", "discrete")
        self.reward_type = config.get("reward_type", "simple_pnl")
        self.position_size = Decimal(str(config.get("position_size", 1.0)))
        self.render_mode = render_mode or config.get("render_mode")

        # Market data
        self.market_data = market_data or []
        self.data_index = 0

        # Define observation space (T087)
        if self.observation_type == "candles":
            # OHLCV for lookback_window candles, normalized to [-1, 1]
            self.observation_space = spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(self.lookback_window, 5),  # (lookback, OHLCV)
                dtype=np.float32,
            )
        else:  # indicators
            # Custom indicator features
            num_indicators = 10  # RSI, MACD, EMA, etc.
            self.observation_space = spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(num_indicators,),
                dtype=np.float32,
            )

        # Define action space (T088)
        if self.action_type == "discrete":
            self.action_space = spaces.Discrete(3)  # 0=HOLD, 1=BUY, 2=SELL
        else:  # continuous
            # Continuous position sizing [-1, 1] (negative = sell, positive = buy)
            self.action_space = spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(1,),
                dtype=np.float32,
            )

        # Environment state
        self.current_step = 0
        self.current_capital = self.initial_capital
        self.current_position: Optional[Dict[str, Any]] = None
        self.episode_number = 0
        self.episode_history: List[Dict[str, Any]] = []
        self.cumulative_reward = 0.0

        # Episode statistics tracking (T094)
        self.episode_statistics: List[EpisodeStatistics] = []
        self.current_episode_stats = EpisodeStatistics()

        # Portfolio and trade simulation
        self.portfolio = PortfolioState(initial_capital=self.initial_capital)
        self.trade_simulator = TradeSimulator(
            commission_pct=Decimal("0.0002"),  # 0.02% commission
            slippage_pct=Decimal("0.0001"),    # 0.01% slippage
        )

        # For normalization (T090)
        self.price_history: List[Decimal] = []
        self.price_mean = Decimal("0")
        self.price_std = Decimal("1")

        # Random number generator
        self._np_random = None

        logger.info(
            "backtesting_env_initialized",
            symbol=self.symbol,
            timeframe=self.timeframe,
            lookback=self.lookback_window,
            max_steps=self.max_steps,
        )

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reset the environment to start a new episode (T085).

        Args:
            seed: Random seed for reproducibility
            options: Additional reset options

        Returns:
            observation: Initial observation
            info: Additional information dictionary
        """
        # Set random seed
        super().reset(seed=seed)
        if seed is not None:
            self._np_random = np.random.RandomState(seed)
        else:
            self._np_random = np.random.RandomState()

        # Save previous episode statistics
        if self.episode_number > 0:
            self.episode_statistics.append(self.current_episode_stats)

        # Reset episode state
        self.current_step = 0
        self.current_capital = self.initial_capital
        self.current_position = None
        self.episode_history = []
        self.cumulative_reward = 0.0
        self.episode_number += 1

        # Reset statistics
        self.current_episode_stats = EpisodeStatistics(
            episode_number=self.episode_number
        )

        # Reset portfolio
        self.portfolio = PortfolioState(initial_capital=self.initial_capital)

        # Choose random starting point in data (for episode diversity)
        if len(self.market_data) > self.lookback_window + self.max_steps:
            max_start = len(self.market_data) - self.lookback_window - self.max_steps
            self.data_index = self._np_random.randint(0, max_start)
        else:
            self.data_index = 0

        # Reset price history for normalization
        self.price_history = []

        # Get initial observation
        observation = self._get_observation()

        # Build info dict
        info = {
            "timestamp": self._get_current_timestamp(),
            "capital": float(self.current_capital),
            "position": self.current_position,
            "episode": self.episode_number,
        }

        logger.debug(
            "episode_reset",
            episode=self.episode_number,
            starting_index=self.data_index,
        )

        return observation, info

    def step(
        self, action: int | np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Execute one step in the environment (T086).

        Args:
            action: Action to take (0=HOLD, 1=BUY, 2=SELL for discrete)

        Returns:
            observation: Next observation
            reward: Reward for this step
            terminated: Whether episode ended (bankruptcy)
            truncated: Whether episode was truncated (max steps)
            info: Additional information
        """
        # Convert action to int if discrete
        if self.action_type == "discrete":
            action = int(action)

        # Execute trade based on action
        current_tick = self._get_current_tick()
        previous_capital = self.current_capital

        if self.action_type == "discrete":
            self._execute_discrete_action(action, current_tick)
        else:
            self._execute_continuous_action(action, current_tick)

        # Calculate reward (T091)
        reward = self._calculate_reward(previous_capital, current_tick)
        self.cumulative_reward += reward
        self.current_episode_stats.total_reward += reward
        self.current_episode_stats.rewards_history.append(reward)

        # Advance to next step
        self.current_step += 1
        self.data_index += 1
        self.current_episode_stats.episode_length += 1

        # Check termination conditions (T089)
        terminated = self._check_termination()
        truncated = self.current_step >= self.max_steps

        # Get next observation
        observation = self._get_observation()

        # Build info dict
        info = {
            "timestamp": self._get_current_timestamp(),
            "capital": float(self.current_capital),
            "position": self.current_position,
            "reward": reward,
            "cumulative_reward": self.cumulative_reward,
            "step": self.current_step,
        }

        # Update episode statistics if episode ended
        if terminated or truncated:
            self._finalize_episode_statistics()
            if terminated:
                info["termination_reason"] = "bankruptcy" if self.current_capital <= 0 else "completed"

        return observation, reward, terminated, truncated, info

    def render(self) -> Optional[str]:
        """
        Render the environment (T092).

        Returns text-based rendering of current state.
        """
        if self.render_mode != "human":
            return None

        output = f"\n{'='*60}\n"
        output += f"Episode: {self.episode_number} | Step: {self.current_step}\n"
        output += f"Capital: ${self.current_capital:,.2f}\n"

        if self.current_position:
            output += f"Position: {self.current_position['type']} @ ${self.current_position['entry_price']:.5f}\n"
            unrealized_pnl = self._calculate_unrealized_pnl(self._get_current_tick())
            output += f"Unrealized P&L: ${unrealized_pnl:,.2f}\n"
        else:
            output += "Position: None\n"

        output += f"Cumulative Reward: {self.cumulative_reward:.2f}\n"
        output += f"{'='*60}\n"

        print(output)
        return output

    def close(self) -> None:
        """
        Clean up resources (T093).
        """
        self.market_data = []
        self.episode_history = []
        self.price_history = []
        logger.info("backtesting_env_closed", episodes=self.episode_number)

    def get_episode_statistics(self) -> Dict[str, Any]:
        """
        Get episode statistics (T094).

        Returns:
            Dictionary with episode statistics
        """
        if not self.episode_statistics:
            return {
                "total_episodes": 0,
                "avg_reward": 0.0,
                "avg_length": 0.0,
                "avg_sharpe": 0.0,
            }

        return {
            "total_episodes": len(self.episode_statistics),
            "avg_reward": np.mean([s.total_reward for s in self.episode_statistics]),
            "avg_length": np.mean([s.episode_length for s in self.episode_statistics]),
            "avg_sharpe": np.mean([s.sharpe_ratio for s in self.episode_statistics]),
            "avg_win_rate": np.mean([s.win_rate for s in self.episode_statistics]),
            "best_reward": max([s.total_reward for s in self.episode_statistics]),
            "worst_reward": min([s.total_reward for s in self.episode_statistics]),
        }

    # Private helper methods

    def _get_observation(self) -> np.ndarray:
        """
        Get current observation (T090 - with normalization).

        Returns normalized observation in [-1, 1] range.
        """
        if self.observation_type == "candles":
            # Get last lookback_window candles
            start_idx = max(0, self.data_index - self.lookback_window)
            end_idx = self.data_index

            if end_idx > len(self.market_data):
                # Pad with zeros if not enough data
                obs = np.zeros((self.lookback_window, 5), dtype=np.float32)
            else:
                candles = self.market_data[start_idx:end_idx]

                # Convert to numpy array (OHLCV)
                candle_array = np.array([
                    [
                        float(c.open_price),
                        float(c.high_price),
                        float(c.low_price),
                        float(c.close_price),
                        float(c.volume),
                    ]
                    for c in candles
                ], dtype=np.float32)

                # Normalize using z-score on prices
                if len(candle_array) > 0:
                    # Use close prices for normalization
                    close_prices = candle_array[:, 3]
                    mean = np.mean(close_prices)
                    std = np.std(close_prices) if np.std(close_prices) > 0 else 1.0

                    # Normalize OHLC relative to mean/std
                    candle_array[:, :4] = (candle_array[:, :4] - mean) / std

                    # Normalize volume separately
                    vol_mean = np.mean(candle_array[:, 4])
                    vol_std = np.std(candle_array[:, 4]) if np.std(candle_array[:, 4]) > 0 else 1.0
                    candle_array[:, 4] = (candle_array[:, 4] - vol_mean) / vol_std

                    # Clip to [-1, 1]
                    candle_array = np.clip(candle_array, -1.0, 1.0)

                # Pad if needed
                if len(candle_array) < self.lookback_window:
                    padding = np.zeros((self.lookback_window - len(candle_array), 5), dtype=np.float32)
                    obs = np.vstack([padding, candle_array])
                else:
                    obs = candle_array[-self.lookback_window:]

            return obs
        else:
            # Indicator-based observation
            # Placeholder - would calculate RSI, MACD, etc.
            return np.zeros(self.observation_space.shape, dtype=np.float32)

    def _get_current_tick(self) -> Optional[Any]:
        """Get current market tick."""
        if self.data_index < len(self.market_data):
            return self.market_data[self.data_index]
        return None

    def _get_current_timestamp(self) -> Optional[datetime]:
        """Get current timestamp."""
        tick = self._get_current_tick()
        return tick.timestamp if tick else None

    def _execute_discrete_action(self, action: int, tick: Any) -> None:
        """Execute discrete action (HOLD=0, BUY=1, SELL=2)."""
        if action == 1:  # BUY
            if self.current_position is None:
                self.current_position = {
                    "type": "LONG",
                    "entry_price": tick.close_price,
                    "quantity": self.position_size,
                    "timestamp": tick.timestamp,
                }
        elif action == 2:  # SELL
            if self.current_position is not None:
                # Close position and realize P&L
                pnl = (tick.close_price - self.current_position["entry_price"]) * self.current_position["quantity"]
                self.current_capital += pnl
                self.current_episode_stats.num_trades += 1
                self.current_position = None
        # action == 0 (HOLD) does nothing

    def _execute_continuous_action(self, action: np.ndarray, tick: Any) -> None:
        """Execute continuous action (position size in [-1, 1])."""
        # Placeholder for continuous action space
        pass

    def _calculate_reward(self, previous_capital: Decimal, tick: Any) -> float:
        """
        Calculate reward based on reward_type (T091).
        """
        if self.reward_type == "simple_pnl":
            # Change in capital (realized + unrealized)
            current_value = self.current_capital
            if self.current_position:
                current_value += self._calculate_unrealized_pnl(tick)
            return float(current_value - previous_capital)

        elif self.reward_type == "risk_adjusted":
            # Sharpe-like reward (returns scaled by volatility)
            simple_reward = float(self.current_capital - previous_capital)
            if len(self.current_episode_stats.rewards_history) > 1:
                std = np.std(self.current_episode_stats.rewards_history)
                if std > 0:
                    return simple_reward / std
            return simple_reward

        elif self.reward_type == "sparse":
            # Reward only on trade close
            if self.current_position is None and len(self.episode_history) > 0:
                # Just closed a position
                return float(self.current_capital - previous_capital)
            return 0.0

        return 0.0

    def _calculate_unrealized_pnl(self, tick: Any) -> Decimal:
        """Calculate unrealized P&L for open position."""
        if self.current_position is None or tick is None:
            return Decimal("0")

        return (tick.close_price - self.current_position["entry_price"]) * self.current_position["quantity"]

    def _check_termination(self) -> bool:
        """
        Check if episode should terminate (T089).

        Returns True if bankrupt or data exhausted.
        """
        # Bankruptcy
        if self.current_capital <= 0:
            return True

        # Data exhausted
        if self.data_index >= len(self.market_data):
            return True

        return False

    def _finalize_episode_statistics(self) -> None:
        """Finalize statistics for completed episode (T094)."""
        stats = self.current_episode_stats
        stats.final_capital = self.current_capital

        # Calculate Sharpe ratio
        if len(stats.rewards_history) > 1:
            mean_reward = np.mean(stats.rewards_history)
            std_reward = np.std(stats.rewards_history)
            if std_reward > 0:
                stats.sharpe_ratio = mean_reward / std_reward

        # Calculate win rate
        if stats.num_trades > 0:
            # Would need to track individual trade outcomes
            stats.win_rate = 0.5  # Placeholder

        logger.info(
            "episode_completed",
            episode=stats.episode_number,
            reward=stats.total_reward,
            length=stats.episode_length,
            sharpe=stats.sharpe_ratio,
        )
