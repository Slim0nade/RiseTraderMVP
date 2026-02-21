"""
Reinforcement Learning Module for RiseTrader

Contains Gymnasium-compatible trading environments, reward functions,
RL trainers (PPO, SAC), and walk-forward validation infrastructure.

Sub-packages:
    environments: Trading, position sizing, stop loss, take profit envs
    rewards: Reward shaping functions for each RL task
    agents: PPO and SAC trainer wrappers around stable-baselines3
    validation: Walk-forward cross-validation with overfitting detection
"""
