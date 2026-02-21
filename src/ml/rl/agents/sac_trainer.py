"""
SACTrainer - Wrapper around stable-baselines3 SAC with MLflow integration.

Task T113: Phase 7, User Story 5.

Soft Actor-Critic is suited for continuous action spaces (position sizing,
stop-loss / take-profit environments). Provides the same interface as
PPOTrainer for consistency.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

try:
    from stable_baselines3 import SAC
    from stable_baselines3.common.callbacks import BaseCallback

    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    SAC = None

try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

import gymnasium

logger = logging.getLogger(__name__)


class _SACMLflowCallback(BaseCallback if SB3_AVAILABLE else object):
    """Callback that logs SAC training metrics to MLflow."""

    def __init__(self, log_interval: int = 1000, verbose: int = 0):
        if SB3_AVAILABLE:
            super().__init__(verbose)
        self.log_interval = log_interval

    def _on_step(self) -> bool:
        if not MLFLOW_AVAILABLE:
            return True
        if self.num_timesteps % self.log_interval == 0:
            if len(self.model.ep_info_buffer) > 0:
                ep_rewards = [ep["r"] for ep in self.model.ep_info_buffer]
                try:
                    mlflow.log_metrics(
                        {
                            "train/mean_reward": float(np.mean(ep_rewards)),
                        },
                        step=self.num_timesteps,
                    )
                except Exception:
                    pass
        return True


class SACTrainer:
    """
    SAC trainer wrapping stable-baselines3.

    Usage:
        trainer = SACTrainer()
        model = trainer.train(env, total_timesteps=100_000)
        trainer.save("models/sac_position_sizing.zip")
        loaded = SACTrainer.load("models/sac_position_sizing.zip", env)
    """

    def __init__(self):
        if not SB3_AVAILABLE:
            logger.warning(
                "stable-baselines3 is not installed. "
                "Install with: pip install stable-baselines3"
            )
        self.model: Optional[Any] = None
        self._run_id: Optional[str] = None

    def train(
        self,
        env: gymnasium.Env,
        total_timesteps: int = 100_000,
        learning_rate: float = 3e-4,
        buffer_size: int = 100_000,
        learning_starts: int = 1000,
        batch_size: int = 256,
        tau: float = 0.005,
        gamma: float = 0.99,
        ent_coef: str = "auto",
        target_entropy: str = "auto",
        train_freq: int = 1,
        gradient_steps: int = 1,
        policy: str = "MlpPolicy",
        policy_kwargs: Optional[Dict[str, Any]] = None,
        mlflow_experiment: Optional[str] = None,
        mlflow_run_name: Optional[str] = None,
        log_interval: int = 4,
        seed: Optional[int] = None,
        verbose: int = 1,
    ) -> Any:
        """
        Train a SAC agent.

        Args:
            env: Gymnasium-compatible environment with continuous action space.
            total_timesteps: Total training timesteps.
            learning_rate: Learning rate for actor and critic networks.
            buffer_size: Replay buffer capacity.
            learning_starts: Steps before training begins (random exploration).
            batch_size: Mini-batch size for updates.
            tau: Soft update coefficient for target networks.
            gamma: Discount factor.
            ent_coef: Entropy regularisation coefficient ("auto" for automatic).
            target_entropy: Target entropy ("auto" for -dim(action)).
            train_freq: Number of environment steps between gradient updates.
            gradient_steps: Gradient steps per update.
            policy: SB3 policy class name.
            policy_kwargs: Additional keyword arguments for the policy network.
            mlflow_experiment: MLflow experiment name (None to skip logging).
            mlflow_run_name: Optional run name.
            log_interval: Number of episodes between console logs.
            seed: Random seed for reproducibility.
            verbose: SB3 verbosity level.

        Returns:
            Trained SB3 SAC model.
        """
        if not SB3_AVAILABLE:
            raise RuntimeError(
                "stable-baselines3 is required for SACTrainer. "
                "Install with: pip install stable-baselines3"
            )

        params = {
            "total_timesteps": total_timesteps,
            "learning_rate": learning_rate,
            "buffer_size": buffer_size,
            "learning_starts": learning_starts,
            "batch_size": batch_size,
            "tau": tau,
            "gamma": gamma,
            "ent_coef": str(ent_coef),
            "train_freq": train_freq,
            "gradient_steps": gradient_steps,
            "policy": policy,
        }

        callbacks = []
        mlflow_active = False

        if mlflow_experiment and MLFLOW_AVAILABLE:
            try:
                mlflow.set_experiment(mlflow_experiment)
                mlflow.start_run(run_name=mlflow_run_name)
                mlflow.log_params(params)
                self._run_id = mlflow.active_run().info.run_id
                callbacks.append(_SACMLflowCallback(log_interval=1000))
                mlflow_active = True
                logger.info(
                    "MLflow run started: experiment=%s, run_id=%s",
                    mlflow_experiment,
                    self._run_id,
                )
            except Exception as e:
                logger.warning("MLflow logging unavailable: %s", e)

        try:
            self.model = SAC(
                policy=policy,
                env=env,
                learning_rate=learning_rate,
                buffer_size=buffer_size,
                learning_starts=learning_starts,
                batch_size=batch_size,
                tau=tau,
                gamma=gamma,
                ent_coef=ent_coef,
                target_entropy=target_entropy,
                train_freq=train_freq,
                gradient_steps=gradient_steps,
                seed=seed,
                verbose=verbose,
                policy_kwargs=policy_kwargs or {},
            )

            self.model.learn(
                total_timesteps=total_timesteps,
                callback=callbacks if callbacks else None,
                log_interval=log_interval,
            )

            if mlflow_active:
                try:
                    if len(self.model.ep_info_buffer) > 0:
                        final_rewards = [ep["r"] for ep in self.model.ep_info_buffer]
                        mlflow.log_metrics(
                            {
                                "final/mean_reward": float(np.mean(final_rewards)),
                                "final/std_reward": float(np.std(final_rewards)),
                            }
                        )
                except Exception as e:
                    logger.warning("Failed to log final metrics: %s", e)

        finally:
            if mlflow_active:
                try:
                    mlflow.end_run()
                except Exception:
                    pass

        logger.info("SAC training complete: %d timesteps", total_timesteps)
        return self.model

    def save(self, path: Union[str, Path]) -> None:
        """Save the trained SAC model to disk."""
        if self.model is None:
            raise RuntimeError("No model to save. Train first.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path))
        logger.info("SAC model saved to %s", path)

    @classmethod
    def load(
        cls, path: Union[str, Path], env: Optional[gymnasium.Env] = None
    ) -> "SACTrainer":
        """Load a SAC model from disk."""
        if not SB3_AVAILABLE:
            raise RuntimeError("stable-baselines3 is required to load SAC models.")
        trainer = cls()
        trainer.model = SAC.load(str(path), env=env)
        logger.info("SAC model loaded from %s", path)
        return trainer

    def predict(
        self, observation: np.ndarray, deterministic: bool = True
    ) -> tuple:
        """
        Generate a prediction from the trained model.

        Args:
            observation: Current environment observation.
            deterministic: If True, use the greedy policy.

        Returns:
            (action, state) tuple.
        """
        if self.model is None:
            raise RuntimeError("No model available. Train or load first.")
        return self.model.predict(observation, deterministic=deterministic)
