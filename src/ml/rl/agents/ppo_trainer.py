"""
PPOTrainer - Wrapper around stable-baselines3 PPO with MLflow integration.

Task T112: Phase 7, User Story 5.

Provides a clean interface for training PPO agents on any Gymnasium-compatible
trading environment. Logs hyperparameters, training curves, and final metrics
to MLflow. Supports model save/load for deployment.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback

    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    PPO = None

try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

import gymnasium

logger = logging.getLogger(__name__)


class _MLflowLoggingCallback(BaseCallback if SB3_AVAILABLE else object):
    """Callback that logs SB3 training metrics to MLflow every N steps."""

    def __init__(self, log_interval: int = 1000, verbose: int = 0):
        if SB3_AVAILABLE:
            super().__init__(verbose)
        self.log_interval = log_interval

    def _on_step(self) -> bool:
        if not MLFLOW_AVAILABLE:
            return True
        if self.num_timesteps % self.log_interval == 0:
            # Log latest info from the logger
            if len(self.model.ep_info_buffer) > 0:
                ep_rewards = [ep["r"] for ep in self.model.ep_info_buffer]
                ep_lengths = [ep["l"] for ep in self.model.ep_info_buffer]
                try:
                    mlflow.log_metrics(
                        {
                            "train/mean_reward": float(np.mean(ep_rewards)),
                            "train/mean_ep_length": float(np.mean(ep_lengths)),
                        },
                        step=self.num_timesteps,
                    )
                except Exception:
                    pass
        return True


class PPOTrainer:
    """
    PPO trainer wrapping stable-baselines3.

    Usage:
        trainer = PPOTrainer()
        model = trainer.train(env, total_timesteps=100_000)
        trainer.save("models/ppo_trading.zip")
        loaded = PPOTrainer.load("models/ppo_trading.zip", env)
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
        n_steps: int = 2048,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        ent_coef: float = 0.01,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        policy: str = "MlpPolicy",
        policy_kwargs: Optional[Dict[str, Any]] = None,
        mlflow_experiment: Optional[str] = None,
        mlflow_run_name: Optional[str] = None,
        log_interval: int = 1,
        seed: Optional[int] = None,
        verbose: int = 1,
    ) -> Any:
        """
        Train a PPO agent.

        Args:
            env: Gymnasium-compatible environment.
            total_timesteps: Total training timesteps.
            learning_rate: Learning rate.
            n_steps: Steps per rollout before update.
            batch_size: Mini-batch size for PPO updates.
            n_epochs: Number of PPO optimisation epochs per update.
            gamma: Discount factor.
            gae_lambda: GAE lambda parameter.
            clip_range: PPO clipping range.
            ent_coef: Entropy coefficient.
            vf_coef: Value function loss coefficient.
            max_grad_norm: Maximum gradient norm for clipping.
            policy: SB3 policy class name (e.g. "MlpPolicy", "MlpLstmPolicy").
            policy_kwargs: Additional keyword arguments for the policy network.
            mlflow_experiment: MLflow experiment name (None to skip logging).
            mlflow_run_name: Optional run name within the experiment.
            log_interval: Number of rollouts between console logs.
            seed: Random seed for reproducibility.
            verbose: SB3 verbosity level.

        Returns:
            Trained SB3 PPO model.
        """
        if not SB3_AVAILABLE:
            raise RuntimeError(
                "stable-baselines3 is required for PPOTrainer. "
                "Install with: pip install stable-baselines3"
            )

        params = {
            "total_timesteps": total_timesteps,
            "learning_rate": learning_rate,
            "n_steps": n_steps,
            "batch_size": batch_size,
            "n_epochs": n_epochs,
            "gamma": gamma,
            "gae_lambda": gae_lambda,
            "clip_range": clip_range,
            "ent_coef": ent_coef,
            "vf_coef": vf_coef,
            "max_grad_norm": max_grad_norm,
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
                callbacks.append(_MLflowLoggingCallback(log_interval=1000))
                mlflow_active = True
                logger.info(
                    "MLflow run started: experiment=%s, run_id=%s",
                    mlflow_experiment,
                    self._run_id,
                )
            except Exception as e:
                logger.warning("MLflow logging unavailable: %s", e)

        try:
            self.model = PPO(
                policy=policy,
                env=env,
                learning_rate=learning_rate,
                n_steps=n_steps,
                batch_size=batch_size,
                n_epochs=n_epochs,
                gamma=gamma,
                gae_lambda=gae_lambda,
                clip_range=clip_range,
                ent_coef=ent_coef,
                vf_coef=vf_coef,
                max_grad_norm=max_grad_norm,
                seed=seed,
                verbose=verbose,
                policy_kwargs=policy_kwargs or {},
            )

            self.model.learn(
                total_timesteps=total_timesteps,
                callback=callbacks if callbacks else None,
                log_interval=log_interval,
            )

            # Log final metrics
            if mlflow_active:
                try:
                    if len(self.model.ep_info_buffer) > 0:
                        final_rewards = [ep["r"] for ep in self.model.ep_info_buffer]
                        mlflow.log_metrics(
                            {
                                "final/mean_reward": float(np.mean(final_rewards)),
                                "final/std_reward": float(np.std(final_rewards)),
                                "final/max_reward": float(np.max(final_rewards)),
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

        logger.info("PPO training complete: %d timesteps", total_timesteps)
        return self.model

    def save(self, path: Union[str, Path]) -> None:
        """Save the trained PPO model to disk."""
        if self.model is None:
            raise RuntimeError("No model to save. Train first.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path))
        logger.info("PPO model saved to %s", path)

    @classmethod
    def load(
        cls, path: Union[str, Path], env: Optional[gymnasium.Env] = None
    ) -> "PPOTrainer":
        """Load a PPO model from disk."""
        if not SB3_AVAILABLE:
            raise RuntimeError("stable-baselines3 is required to load PPO models.")
        trainer = cls()
        trainer.model = PPO.load(str(path), env=env)
        logger.info("PPO model loaded from %s", path)
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
