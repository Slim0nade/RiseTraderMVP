"""
Example 3: RL Agent Training

Demonstrates training a reinforcement learning agent:
1. Create Gymnasium environment
2. Train PPO agent with Stable-Baselines3
3. Evaluate trained agent
4. Compare to random policy

Requires: pip install stable-baselines3
"""
import asyncio
import numpy as np
from datetime import datetime, timezone

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_checker import check_env
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    print("⚠️  stable-baselines3 not installed. Run: pip install stable-baselines3")

from src.services.backtesting import BacktestTradingEnv


def train_rl_agent():
    """Train an RL agent using PPO algorithm."""

    if not SB3_AVAILABLE:
        print("Cannot run RL training without stable-baselines3")
        return

    # Create environment
    print("Creating RL environment...")
    env_config = {
        "symbol": "EURUSD",
        "timeframe": "M5",
        "initial_capital": 10000.0,
        "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2024, 3, 1, tzinfo=timezone.utc),  # 2 months
        "lookback_window": 10,
        "max_steps": 1000,
        "reward_type": "risk_adjusted",  # Sharpe-like rewards
    }

    env = BacktestTradingEnv(config=env_config)

    # Check environment compliance
    print("Checking Gymnasium API compliance...")
    try:
        check_env(env.unwrapped, skip_render_check=True)
        print("✅ Environment passes Gymnasium checks")
    except Exception as e:
        print(f"❌ Environment check failed: {e}")
        return

    # Baseline: Test random policy
    print("\n" + "="*60)
    print("BASELINE: Random Policy")
    print("="*60)

    random_rewards = []
    for episode in range(10):
        obs, _ = env.reset(seed=episode)
        episode_reward = 0
        terminated = False
        truncated = False

        while not (terminated or truncated):
            action = env.action_space.sample()  # Random action
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward

        random_rewards.append(episode_reward)

    print(f"Random Policy - Avg Reward: {np.mean(random_rewards):.2f}")
    print(f"Random Policy - Std Reward: {np.std(random_rewards):.2f}")

    # Train PPO agent
    print("\n" + "="*60)
    print("TRAINING PPO AGENT")
    print("="*60)

    model = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        verbose=1,
    )

    print("Training for 50,000 timesteps...")
    model.learn(total_timesteps=50_000, progress_bar=True)
    print("✅ Training complete")

    # Evaluate trained agent
    print("\n" + "="*60)
    print("EVALUATING TRAINED AGENT")
    print("="*60)

    trained_rewards = []
    for episode in range(10):
        obs, _ = env.reset(seed=episode + 100)  # Different seeds from baseline
        episode_reward = 0
        terminated = False
        truncated = False

        while not (terminated or truncated):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward

        trained_rewards.append(episode_reward)

    print(f"Trained Agent - Avg Reward: {np.mean(trained_rewards):.2f}")
    print(f"Trained Agent - Std Reward: {np.std(trained_rewards):.2f}")

    # Compare
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"Random Policy:  {np.mean(random_rewards):.2f} ± {np.std(random_rewards):.2f}")
    print(f"Trained Agent:  {np.mean(trained_rewards):.2f} ± {np.std(trained_rewards):.2f}")

    improvement = ((np.mean(trained_rewards) - np.mean(random_rewards)) /
                   abs(np.mean(random_rewards)) * 100
                   if np.mean(random_rewards) != 0 else 0)

    if improvement > 10:
        print(f"\n✅ Trained agent improved by {improvement:.1f}%!")
    elif improvement > 0:
        print(f"\n⚠️  Marginal improvement: {improvement:.1f}%")
    else:
        print(f"\n❌ No improvement (possibly needs more training)")

    # Cleanup
    env.close()


if __name__ == "__main__":
    train_rl_agent()
