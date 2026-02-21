"""
WalkForwardValidator - Rolling-window out-of-sample validation for RL agents.

Tasks T115-T117: Phase 7, User Story 5.

Implements walk-forward cross-validation tailored for RL trading agents:
    - Rolling window: 252 train bars, 63 test bars, 21 step size (default).
    - Returns list of OOS (out-of-sample) Sharpe ratios.
    - Detects overfitting by comparing in-sample vs OOS Sharpe.
    - Computes p-value via a one-sided paired t-test for statistical significance.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

import numpy as np

try:
    from scipy import stats as sp_stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

import gymnasium

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardResult:
    """Container for walk-forward validation results."""

    oos_sharpe_ratios: List[float] = field(default_factory=list)
    is_sharpe_ratios: List[float] = field(default_factory=list)
    mean_oos_sharpe: float = 0.0
    mean_is_sharpe: float = 0.0
    sharpe_degradation: float = 0.0
    overfitting_detected: bool = False
    p_value: Optional[float] = None
    statistically_significant: bool = False
    n_folds: int = 0

    def summary(self) -> Dict[str, Any]:
        """Return a summary dictionary for logging."""
        return {
            "n_folds": self.n_folds,
            "mean_oos_sharpe": round(self.mean_oos_sharpe, 4),
            "mean_is_sharpe": round(self.mean_is_sharpe, 4),
            "sharpe_degradation_pct": round(self.sharpe_degradation * 100, 2),
            "overfitting_detected": self.overfitting_detected,
            "p_value": round(self.p_value, 6) if self.p_value is not None else None,
            "statistically_significant": self.statistically_significant,
        }


class WalkForwardValidator:
    """
    Walk-forward cross-validation for RL trading agents.

    Splits historical data into rolling train/test windows, trains a fresh
    agent on each training window, then evaluates it on the subsequent test
    window. Collects OOS Sharpe ratios and detects overfitting.

    Default window sizes follow the common financial convention of
    approximately 1 year training (252 bars) and 1 quarter testing (63 bars)
    with a monthly step (21 bars).
    """

    def __init__(
        self,
        train_size: int = 252,
        test_size: int = 63,
        step_size: int = 21,
        overfitting_threshold: float = 0.25,
        significance_level: float = 0.05,
    ):
        """
        Args:
            train_size: Number of bars in each training window.
            test_size: Number of bars in each test window.
            step_size: Number of bars to advance between folds.
            overfitting_threshold: Maximum acceptable relative degradation
                                   between IS and OOS Sharpe (0.25 = 25%).
            significance_level: P-value threshold for statistical significance.
        """
        self.train_size = int(train_size)
        self.test_size = int(test_size)
        self.step_size = int(step_size)
        self.overfitting_threshold = float(overfitting_threshold)
        self.significance_level = float(significance_level)

    def validate(
        self,
        trainer_class: type,
        env_class: Type[gymnasium.Env],
        prices: np.ndarray,
        features: np.ndarray,
        env_kwargs: Optional[Dict[str, Any]] = None,
        train_kwargs: Optional[Dict[str, Any]] = None,
        total_timesteps: int = 50_000,
    ) -> WalkForwardResult:
        """
        Run walk-forward validation.

        For each fold:
            1. Slice prices/features into train and test windows.
            2. Construct a fresh training environment.
            3. Train a new agent using trainer_class.
            4. Evaluate on the test window to compute OOS Sharpe.
            5. Also compute IS Sharpe from the training evaluation.

        Args:
            trainer_class: Class with a .train(env, ...) method (e.g. PPOTrainer).
            env_class: Gymnasium environment class (e.g. TradingEnvironment).
            prices: Full 1-D price array.
            features: Full 2-D feature array (T, num_features).
            env_kwargs: Additional keyword arguments for the environment constructor
                        (beyond prices and features).
            train_kwargs: Additional keyword arguments for trainer.train().
            total_timesteps: Training timesteps per fold.

        Returns:
            WalkForwardResult with OOS Sharpe ratios and overfitting diagnostics.
        """
        env_kwargs = env_kwargs or {}
        train_kwargs = train_kwargs or {}
        n = len(prices)
        window = self.train_size + self.test_size

        if n < window:
            raise ValueError(
                f"Data length {n} is too short for train_size={self.train_size} "
                f"+ test_size={self.test_size} = {window}"
            )

        result = WalkForwardResult()

        fold = 0
        start = 0
        while start + window <= n:
            train_end = start + self.train_size
            test_end = train_end + self.test_size

            train_prices = prices[start:train_end]
            train_features = features[start:train_end]
            test_prices = prices[train_end:test_end]
            test_features = features[train_end:test_end]

            logger.info(
                "Fold %d: train [%d:%d], test [%d:%d]",
                fold, start, train_end, train_end, test_end,
            )

            # Train
            train_env = env_class(
                prices=train_prices,
                features=train_features,
                **env_kwargs,
            )
            trainer = trainer_class()
            trainer.train(
                env=train_env,
                total_timesteps=total_timesteps,
                verbose=0,
                **train_kwargs,
            )

            # Evaluate in-sample
            is_sharpe = self._evaluate_sharpe(trainer, train_env, train_prices)
            result.is_sharpe_ratios.append(is_sharpe)

            # Evaluate out-of-sample
            # Adjust lookback for test env to avoid requiring padding
            test_lookback = min(
                env_kwargs.get("lookback_window", 30),
                len(test_prices) - 2,
            )
            test_env_kwargs = {**env_kwargs, "lookback_window": test_lookback}
            test_env = env_class(
                prices=test_prices,
                features=test_features,
                **test_env_kwargs,
            )
            oos_sharpe = self._evaluate_sharpe(trainer, test_env, test_prices)
            result.oos_sharpe_ratios.append(oos_sharpe)

            logger.info(
                "Fold %d: IS Sharpe=%.4f, OOS Sharpe=%.4f",
                fold, is_sharpe, oos_sharpe,
            )

            fold += 1
            start += self.step_size

        if fold == 0:
            logger.warning("No folds were generated. Check data length and window sizes.")
            return result

        result.n_folds = fold
        result.mean_oos_sharpe = float(np.mean(result.oos_sharpe_ratios))
        result.mean_is_sharpe = float(np.mean(result.is_sharpe_ratios))

        # Overfitting detection: relative degradation
        if abs(result.mean_is_sharpe) > 1e-8:
            result.sharpe_degradation = (
                (result.mean_is_sharpe - result.mean_oos_sharpe)
                / abs(result.mean_is_sharpe)
            )
        else:
            result.sharpe_degradation = 0.0

        result.overfitting_detected = (
            result.sharpe_degradation > self.overfitting_threshold
        )

        # Statistical significance via paired t-test
        result.p_value = self._compute_p_value(
            result.is_sharpe_ratios, result.oos_sharpe_ratios
        )
        if result.p_value is not None:
            result.statistically_significant = (
                result.p_value < self.significance_level
            )

        logger.info("Walk-forward validation complete: %s", result.summary())
        return result

    def _evaluate_sharpe(
        self,
        trainer: Any,
        env: gymnasium.Env,
        prices: np.ndarray,
    ) -> float:
        """Run the trained agent through an environment and compute annualised Sharpe."""
        obs, info = env.reset()
        returns = []
        done = False

        while not done:
            action, _ = trainer.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            returns.append(reward)
            done = terminated or truncated

        if len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns)
        mean_ret = returns_arr.mean()
        std_ret = returns_arr.std()
        if std_ret < 1e-10:
            return 0.0

        sharpe = (mean_ret / std_ret) * np.sqrt(252)
        return float(sharpe)

    @staticmethod
    def _compute_p_value(
        is_sharpe_list: List[float], oos_sharpe_list: List[float]
    ) -> Optional[float]:
        """
        Compute p-value using a one-sided paired t-test.

        H0: IS Sharpe <= OOS Sharpe (no overfitting)
        H1: IS Sharpe > OOS Sharpe (overfitting detected)

        Returns None if scipy is unavailable or too few samples.
        """
        if not SCIPY_AVAILABLE:
            logger.warning("scipy not installed; skipping p-value computation.")
            return None

        if len(is_sharpe_list) < 3 or len(oos_sharpe_list) < 3:
            return None

        is_arr = np.array(is_sharpe_list)
        oos_arr = np.array(oos_sharpe_list)
        diff = is_arr - oos_arr

        # One-sample t-test on the differences (is diff > 0?)
        t_stat, two_sided_p = sp_stats.ttest_1samp(diff, 0.0)
        # One-sided: H1 is diff > 0
        one_sided_p = two_sided_p / 2.0 if t_stat > 0 else 1.0 - two_sided_p / 2.0
        return float(one_sided_p)
