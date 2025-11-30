"""
PPO (Proximal Policy Optimization) for RiseTrader
RL-based trading agent that learns optimal actions from market forecasts.
Research: CLSTM-PPO shows 5-52% improvement in cumulative returns.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical, Normal

from .base import BaseForecaster, ForecastResult, ModelConfig


class TradingAction(int, Enum):
    """Discrete trading actions"""
    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass
class PPOConfig(ModelConfig):
    """PPO-specific configuration"""
    # Network architecture
    hidden_size: int = 256
    num_lstm_layers: int = 2
    
    # PPO hyperparameters
    clip_epsilon: float = 0.2
    value_loss_coef: float = 0.5
    entropy_coef: float = 0.01
    gamma: float = 0.99  # Discount factor
    gae_lambda: float = 0.95  # GAE parameter
    
    # Training
    ppo_epochs: int = 10  # Updates per rollout
    rollout_length: int = 256  # Steps before update
    num_envs: int = 8  # Parallel environments
    
    # Action space
    action_type: str = "discrete"  # "discrete" or "continuous"
    max_position: float = 1.0  # Maximum position size
    
    # Reward shaping
    use_sharpe_reward: bool = True
    transaction_cost: float = 0.001


class LSTMFeatureExtractor(nn.Module):
    """LSTM-based feature extractor for sequential market data."""
    
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int = 2,
        dropout: float = 0.2
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0
        )
        self.output_size = hidden_size * 2
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_size)
        Returns:
            features: (batch, hidden_size * 2)
        """
        out, _ = self.lstm(x)
        return out[:, -1, :]


class ActorCritic(nn.Module):
    """
    Actor-Critic network for PPO.
    Separate heads for policy (actor) and value function (critic).
    """
    
    def __init__(
        self,
        feature_extractor: nn.Module,
        feature_size: int,
        action_type: str = "discrete",
        num_actions: int = 3
    ):
        super().__init__()
        self.feature_extractor = feature_extractor
        self.action_type = action_type
        
        # Shared layers
        self.shared = nn.Sequential(
            nn.Linear(feature_size, 256),
            nn.ReLU(),
            nn.LayerNorm(256)
        )
        
        # Actor head (policy)
        if action_type == "discrete":
            self.actor = nn.Sequential(
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Linear(128, num_actions)
            )
        else:
            # Continuous action (position size)
            self.actor_mean = nn.Linear(256, 1)
            self.actor_log_std = nn.Parameter(torch.zeros(1))
            
        # Critic head (value function)
        self.critic = nn.Sequential(
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )
        
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute policy and value.
        
        Returns:
            action_logits: Logits for discrete or mean for continuous
            value: State value estimate
        """
        features = self.feature_extractor(x)
        shared = self.shared(features)
        
        if self.action_type == "discrete":
            action_logits = self.actor(shared)
        else:
            action_logits = self.actor_mean(shared)
            
        value = self.critic(shared)
        
        return action_logits, value
    
    def get_action(
        self,
        x: torch.Tensor,
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample action from policy.
        
        Returns:
            action: Selected action
            log_prob: Log probability of action
            value: Value estimate
        """
        action_logits, value = self.forward(x)
        
        if self.action_type == "discrete":
            dist = Categorical(logits=action_logits)
            if deterministic:
                action = action_logits.argmax(dim=-1)
            else:
                action = dist.sample()
            log_prob = dist.log_prob(action)
        else:
            mean = action_logits
            std = torch.exp(self.actor_log_std)
            dist = Normal(mean, std)
            if deterministic:
                action = mean
            else:
                action = dist.sample()
            action = torch.tanh(action)  # Bound to [-1, 1]
            log_prob = dist.log_prob(action).sum(dim=-1)
            
        return action, log_prob, value.squeeze(-1)
    
    def evaluate_actions(
        self,
        x: torch.Tensor,
        actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluate actions for PPO update.
        
        Returns:
            log_prob: Log probability of actions
            value: Value estimates
            entropy: Policy entropy
        """
        action_logits, value = self.forward(x)
        
        if self.action_type == "discrete":
            dist = Categorical(logits=action_logits)
            log_prob = dist.log_prob(actions)
            entropy = dist.entropy()
        else:
            mean = action_logits
            std = torch.exp(self.actor_log_std)
            dist = Normal(mean, std)
            log_prob = dist.log_prob(actions).sum(dim=-1)
            entropy = dist.entropy().sum(dim=-1)
            
        return log_prob, value.squeeze(-1), entropy


class TradingEnvironment:
    """
    Simplified trading environment for RL training.
    Simulates market execution and tracks portfolio.
    """
    
    def __init__(
        self,
        data: pd.DataFrame,
        lookback_window: int,
        transaction_cost: float = 0.001,
        max_position: float = 1.0,
        use_sharpe_reward: bool = True
    ):
        self.data = data
        self.lookback = lookback_window
        self.transaction_cost = transaction_cost
        self.max_position = max_position
        self.use_sharpe_reward = use_sharpe_reward
        
        # Extract prices
        self.prices = data["close"].values
        self.features = data.drop(columns=["close", "symbol", "time"], errors="ignore").values
        
        # State
        self.current_step = lookback_window
        self.position = 0.0
        self.entry_price = 0.0
        self.returns_history = []
        
    def reset(self) -> np.ndarray:
        """Reset environment to initial state."""
        self.current_step = self.lookback
        self.position = 0.0
        self.entry_price = 0.0
        self.returns_history = []
        return self._get_observation()
    
    def _get_observation(self) -> np.ndarray:
        """Get current observation (lookback window of features)."""
        start = self.current_step - self.lookback
        end = self.current_step
        return self.features[start:end]
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute action and return next state.
        
        Args:
            action: 0=hold, 1=buy, 2=sell (discrete)
                   or position size (continuous)
        
        Returns:
            observation: Next state
            reward: Step reward
            done: Episode finished
            info: Additional info
        """
        current_price = self.prices[self.current_step]
        prev_price = self.prices[self.current_step - 1]
        
        # Execute action
        prev_position = self.position
        
        if isinstance(action, (int, np.integer)):
            # Discrete actions
            if action == TradingAction.BUY and self.position <= 0:
                self.position = self.max_position
                self.entry_price = current_price
            elif action == TradingAction.SELL and self.position >= 0:
                self.position = -self.max_position
                self.entry_price = current_price
        else:
            # Continuous position sizing
            self.position = float(action) * self.max_position
            
        # Calculate reward
        price_return = (current_price - prev_price) / prev_price
        position_return = prev_position * price_return
        
        # Transaction costs
        position_change = abs(self.position - prev_position)
        costs = position_change * self.transaction_cost
        
        net_return = position_return - costs
        self.returns_history.append(net_return)
        
        # Reward shaping
        if self.use_sharpe_reward and len(self.returns_history) > 10:
            # Rolling Sharpe ratio as reward
            returns = np.array(self.returns_history[-20:])
            sharpe = returns.mean() / (returns.std() + 1e-8) * np.sqrt(252)
            reward = sharpe * 0.1 + net_return  # Combine Sharpe and immediate return
        else:
            reward = net_return
            
        # Advance step
        self.current_step += 1
        done = self.current_step >= len(self.prices) - 1
        
        info = {
            "position": self.position,
            "price": current_price,
            "return": net_return,
            "cumulative_return": sum(self.returns_history)
        }
        
        obs = self._get_observation() if not done else np.zeros_like(self._get_observation())
        
        return obs, reward, done, info


class PPOTrader(BaseForecaster):
    """
    PPO-based Trading Agent
    
    Combines LSTM feature extraction with PPO reinforcement learning
    for end-to-end trading decisions.
    
    Research performance:
    - CLSTM-PPO: 5-52% improvement in cumulative returns
    - Chinese markets: 84.4% cumulative return improvement
    - Optimal lookback: 30 days
    
    Key features:
    - Learns trading policy directly from data
    - Handles transaction costs and position limits
    - Uses Sharpe ratio-based reward shaping
    
    Usage:
        config = PPOConfig.for_crude_oil()
        agent = PPOTrader(config, input_size=10)
        history = agent.fit(train_df, val_df)
        action = agent.get_trading_signal(recent_data)
    """
    
    def __init__(self, config: PPOConfig, input_size: int):
        super().__init__(config)
        self.input_size = input_size
        self.config: PPOConfig = config
        
        # Feature extractor
        self.feature_extractor = LSTMFeatureExtractor(
            input_size=input_size,
            hidden_size=config.hidden_size,
            num_layers=config.num_lstm_layers
        )
        
        # Actor-Critic network
        self.ac_network = ActorCritic(
            feature_extractor=self.feature_extractor,
            feature_size=config.hidden_size * 2,
            action_type=config.action_type,
            num_actions=3 if config.action_type == "discrete" else 1
        )
        
        self.optimizer = torch.optim.Adam(
            self.ac_network.parameters(),
            lr=config.learning_rate
        )
        
        self.to(self.device)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass returns value estimate."""
        _, value = self.ac_network(x)
        return value
    
    def _compute_gae(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
        dones: torch.Tensor,
        next_value: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute Generalized Advantage Estimation.
        
        Returns:
            advantages: GAE advantages
            returns: Discounted returns
        """
        advantages = torch.zeros_like(rewards)
        lastgaelam = 0
        
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                nextnonterminal = 1.0 - dones[t]
                nextvalues = next_value
            else:
                nextnonterminal = 1.0 - dones[t + 1]
                nextvalues = values[t + 1]
                
            delta = rewards[t] + self.config.gamma * nextvalues * nextnonterminal - values[t]
            advantages[t] = lastgaelam = delta + self.config.gamma * self.config.gae_lambda * nextnonterminal * lastgaelam
            
        returns = advantages + values
        return advantages, returns
    
    def _ppo_update(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        old_log_probs: torch.Tensor,
        advantages: torch.Tensor,
        returns: torch.Tensor
    ) -> Dict[str, float]:
        """
        Perform PPO update.
        
        Returns:
            losses: Dict with policy, value, and entropy losses
        """
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        total_policy_loss = 0
        total_value_loss = 0
        total_entropy = 0
        
        for _ in range(self.config.ppo_epochs):
            # Evaluate current policy
            log_probs, values, entropy = self.ac_network.evaluate_actions(obs, actions)
            
            # Policy loss with clipping
            ratio = torch.exp(log_probs - old_log_probs)
            surr1 = ratio * advantages
            surr2 = torch.clamp(
                ratio,
                1 - self.config.clip_epsilon,
                1 + self.config.clip_epsilon
            ) * advantages
            policy_loss = -torch.min(surr1, surr2).mean()
            
            # Value loss
            value_loss = F.mse_loss(values, returns)
            
            # Entropy bonus
            entropy_loss = -entropy.mean()
            
            # Combined loss
            loss = (
                policy_loss +
                self.config.value_loss_coef * value_loss +
                self.config.entropy_coef * entropy_loss
            )
            
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.ac_network.parameters(), 0.5)
            self.optimizer.step()
            
            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            total_entropy += entropy.mean().item()
            
        n = self.config.ppo_epochs
        return {
            "policy_loss": total_policy_loss / n,
            "value_loss": total_value_loss / n,
            "entropy": total_entropy / n
        }
    
    def fit(
        self,
        train_data: pd.DataFrame,
        val_data: Optional[pd.DataFrame] = None,
        target_col: str = "close",
        **kwargs
    ) -> Dict[str, List[float]]:
        """
        Train PPO agent through environment interaction.
        
        Args:
            train_data: DataFrame with OHLCV + features
            val_data: Optional validation data
            target_col: Price column name
            
        Returns:
            Training history with returns and losses
        """
        self.train()
        
        # Create environment
        env = TradingEnvironment(
            data=train_data,
            lookback_window=self.config.lookback_window,
            transaction_cost=self.config.transaction_cost,
            max_position=self.config.max_position,
            use_sharpe_reward=self.config.use_sharpe_reward
        )
        
        history = {
            "episode_return": [],
            "policy_loss": [],
            "value_loss": [],
            "sharpe_ratio": []
        }
        
        num_episodes = self.config.max_epochs
        
        for episode in range(num_episodes):
            # Collect rollout
            obs_list = []
            action_list = []
            log_prob_list = []
            reward_list = []
            value_list = []
            done_list = []
            
            obs = env.reset()
            episode_return = 0
            
            for step in range(self.config.rollout_length):
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
                
                with torch.no_grad():
                    action, log_prob, value = self.ac_network.get_action(obs_tensor)
                    
                action_np = action.cpu().numpy()[0]
                
                next_obs, reward, done, info = env.step(action_np)
                
                obs_list.append(obs)
                action_list.append(action_np)
                log_prob_list.append(log_prob.cpu().numpy()[0])
                reward_list.append(reward)
                value_list.append(value.cpu().numpy()[0])
                done_list.append(float(done))
                
                episode_return += reward
                obs = next_obs
                
                if done:
                    obs = env.reset()
                    
            # Get final value for GAE
            final_obs = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
            with torch.no_grad():
                _, _, final_value = self.ac_network.get_action(final_obs)
                
            # Convert to tensors
            obs_tensor = torch.FloatTensor(np.array(obs_list)).to(self.device)
            actions_tensor = torch.LongTensor(action_list).to(self.device) if self.config.action_type == "discrete" else torch.FloatTensor(action_list).to(self.device)
            old_log_probs = torch.FloatTensor(log_prob_list).to(self.device)
            rewards = torch.FloatTensor(reward_list).to(self.device)
            values = torch.FloatTensor(value_list).to(self.device)
            dones = torch.FloatTensor(done_list).to(self.device)
            
            # Compute advantages
            advantages, returns = self._compute_gae(
                rewards, values, dones, final_value.cpu()
            )
            advantages = advantages.to(self.device)
            returns = returns.to(self.device)
            
            # PPO update
            losses = self._ppo_update(
                obs_tensor, actions_tensor, old_log_probs, advantages, returns
            )
            
            # Record metrics
            history["episode_return"].append(episode_return)
            history["policy_loss"].append(losses["policy_loss"])
            history["value_loss"].append(losses["value_loss"])
            
            # Calculate Sharpe
            returns_np = rewards.cpu().numpy()
            sharpe = returns_np.mean() / (returns_np.std() + 1e-8) * np.sqrt(252)
            history["sharpe_ratio"].append(sharpe)
            
            if (episode + 1) % 10 == 0:
                print(f"Episode {episode+1}: return={episode_return:.4f}, "
                      f"sharpe={sharpe:.2f}, policy_loss={losses['policy_loss']:.4f}")
                
        self._is_fitted = True
        return history
    
    def get_trading_signal(
        self,
        data: pd.DataFrame,
        target_col: str = "close"
    ) -> Dict:
        """
        Get trading signal from current market state.
        
        Returns:
            Dict with action, confidence, and predicted value
        """
        self.eval()
        
        feature_cols = [c for c in data.columns if c not in [target_col, "symbol", "time"]]
        features = data[feature_cols].values[-self.config.lookback_window:]
        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            action, log_prob, value = self.ac_network.get_action(X, deterministic=True)
            
        action_np = action.cpu().numpy()[0]
        confidence = np.exp(log_prob.cpu().numpy()[0])
        
        if self.config.action_type == "discrete":
            action_name = TradingAction(action_np).name
            position = {
                TradingAction.HOLD.value: 0.0,
                TradingAction.BUY.value: 1.0,
                TradingAction.SELL.value: -1.0
            }[action_np]
        else:
            action_name = "POSITION"
            position = float(action_np)
            
        return {
            "action": action_name,
            "position": position,
            "confidence": float(confidence),
            "value_estimate": float(value.cpu().numpy()[0]),
            "timestamp": datetime.now()
        }
    
    def predict(
        self,
        data: pd.DataFrame,
        target_col: str = "close",
        return_uncertainty: bool = True
    ) -> ForecastResult:
        """
        Generate forecast (returns trading signal as prediction).
        """
        signal = self.get_trading_signal(data, target_col)
        
        # Convert signal to forecast format
        predictions = np.array([signal["position"]] * self.config.prediction_length)
        
        return ForecastResult(
            timestamp=signal["timestamp"],
            symbol=data.get("symbol", ["UNKNOWN"])[0] if "symbol" in data.columns else "UNKNOWN",
            model_name="PPOTrader",
            model_version=self.model_version,
            predictions=predictions,
            lower_bound=None,
            upper_bound=None,
            confidence_scores=np.array([signal["confidence"]] * self.config.prediction_length),
            direction_prob=float(signal["position"] > 0),
            inference_time_ms=0.0,
            feature_importance={"action": signal["action"], "value": signal["value_estimate"]}
        )


# =============================================================================
# Factory Functions
# =============================================================================

def create_ppo_for_crude_oil(input_features: int = 10) -> PPOTrader:
    """Create PPO agent for crude oil trading."""
    config = PPOConfig(
        model_name="ppo_crude_oil",
        asset_type="crude_oil",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=1,
        hidden_size=256,
        num_lstm_layers=2,
        clip_epsilon=0.2,
        value_loss_coef=0.5,
        entropy_coef=0.01,
        gamma=0.99,
        gae_lambda=0.95,
        ppo_epochs=10,
        rollout_length=256,
        action_type="discrete",
        use_sharpe_reward=True,
        transaction_cost=0.001,
        learning_rate=3e-4,
        batch_size=64,
        max_epochs=100,
    )
    return PPOTrader(config, input_size=input_features)


def create_ppo_for_gold(input_features: int = 10) -> PPOTrader:
    """Create PPO agent for gold trading."""
    config = PPOConfig(
        model_name="ppo_gold",
        asset_type="gold",
        forecast_horizon="daily",
        lookback_window=30,
        prediction_length=1,
        hidden_size=256,
        num_lstm_layers=2,
        clip_epsilon=0.2,
        value_loss_coef=0.5,
        entropy_coef=0.01,
        gamma=0.99,
        gae_lambda=0.95,
        ppo_epochs=10,
        rollout_length=256,
        action_type="discrete",
        use_sharpe_reward=True,
        transaction_cost=0.0005,  # Lower for gold
        learning_rate=3e-4,
        batch_size=64,
        max_epochs=100,
    )
    return PPOTrader(config, input_size=input_features)
