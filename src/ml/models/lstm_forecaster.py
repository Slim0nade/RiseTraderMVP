"""
LSTM Forecaster - Bidirectional LSTM with attention mechanism
Based on research.md TD-001: Stacked bidirectional LSTM with attention
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Any, Optional
from pathlib import Path

from .base_model import BaseModel


class AttentionLayer(nn.Module):
    """Attention mechanism for LSTM outputs."""
    
    def __init__(self, hidden_size: int):
        super().__init__()
        self.attention = nn.Linear(hidden_size, 1)
    
    def forward(self, lstm_output):
        # lstm_output shape: (batch, seq_len, hidden_size)
        attention_weights = torch.softmax(self.attention(lstm_output), dim=1)
        # attention_weights shape: (batch, seq_len, 1)
        
        # Weighted sum
        context = torch.sum(attention_weights * lstm_output, dim=1)
        # context shape: (batch, hidden_size)
        
        return context, attention_weights


class LSTMForecaster(BaseModel):
    """
    Bidirectional LSTM forecaster with attention mechanism.
    
    Architecture:
    - Stacked bidirectional LSTM layers
    - Attention mechanism over sequence
    - Fully connected output layer
    - Dropout regularization
    
    Based on research.md TD-001.
    """
    
    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        bidirectional: bool = True,
        attention: bool = True,
        device: Optional[str] = None
    ):
        """
        Initialize LSTM forecaster.
        
        Args:
            input_size: Number of input features
            hidden_size: LSTM hidden dimension size
            num_layers: Number of LSTM layers (1-5)
            dropout: Dropout rate between LSTM layers (0-0.5)
            bidirectional: Use bidirectional LSTM
            attention: Use attention mechanism
            device: Device to run model on ('cpu' or 'cuda')
        """
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.bidirectional = bidirectional
        self.attention = attention if attention else None
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        
        # LSTM layer
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=bidirectional,
            batch_first=True
        )
        
        # Attention layer
        lstm_output_size = hidden_size * 2 if bidirectional else hidden_size
        if self.attention:
            self.attention = AttentionLayer(lstm_output_size)
        
        # Fully connected output layer
        self.fc = nn.Linear(lstm_output_size, 1)
        
        # Move model to device
        self.to(self.device)
        
        # Training state
        self.optimizer = None
        self.criterion = None
    
    def forward(self, x):
        """Forward pass through the network."""
        # x shape: (batch, seq_len, input_size)
        
        # LSTM forward pass
        lstm_out, _ = self.lstm(x)
        # lstm_out shape: (batch, seq_len, hidden_size * num_directions)
        
        # Apply attention or use last output
        if self.attention:
            context, _ = self.attention(lstm_out)
        else:
            context = lstm_out[:, -1, :]  # Last time step
        
        # Fully connected layer
        output = self.fc(context)
        
        return output
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        learning_rate: float = 0.001,
        batch_size: int = 64,
        early_stopping_patience: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Train the LSTM model.
        
        Args:
            X: Training features (batch, seq_len, features)
            y: Training targets (batch, 1)
            X_val: Validation features
            y_val: Validation targets
            epochs: Maximum number of training epochs
            learning_rate: Learning rate for optimizer
            batch_size: Batch size for training
            early_stopping_patience: Patience for early stopping
            
        Returns:
            Dictionary of training metrics
        """
        # Validate input shape
        if X.ndim != 3:
            raise ValueError(
                f"X must be 3D array with shape (batch, seq_len, features), "
                f"got shape {X.shape}"
            )
        
        # Convert to tensors
        X_train = torch.FloatTensor(X).to(self.device)
        y_train = torch.FloatTensor(y).to(self.device)
        
        if X_val is not None:
            X_val = torch.FloatTensor(X_val).to(self.device)
            y_val = torch.FloatTensor(y_val).to(self.device)
        
        # Setup optimizer and loss
        self.optimizer = torch.optim.Adam(self.parameters(), lr=learning_rate)
        self.criterion = nn.MSELoss()
        
        # Training loop
        best_val_loss = float('inf')
        patience_counter = 0
        train_losses = []
        val_losses = []
        
        for epoch in range(epochs):
            # Set to training mode
            self.training = True
            
            # Mini-batch training
            epoch_loss = 0
            num_batches = 0
            
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train[i:i+batch_size]
                batch_y = y_train[i:i+batch_size]
                
                # Forward pass
                self.optimizer.zero_grad()
                predictions = self(batch_X)
                loss = self.criterion(predictions, batch_y)
                
                # Backward pass
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), max_norm=1.0)
                self.optimizer.step()
                
                epoch_loss += loss.item()
                num_batches += 1
            
            avg_train_loss = epoch_loss / num_batches
            train_losses.append(avg_train_loss)
            
            # Validation
            if X_val is not None:
                self.eval()
                with torch.no_grad():
                    val_predictions = self(X_val)
                    val_loss = self.criterion(val_predictions, y_val).item()
                    val_losses.append(val_loss)
                
                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                else:
                    patience_counter += 1
                    if patience_counter >= early_stopping_patience:
                        break
        
        self.is_trained = True
        
        metrics = {
            'train_loss': train_losses[-1],
            'epochs_trained': epoch + 1
        }
        
        if X_val is not None:
            metrics['val_loss'] = val_losses[-1]
            metrics['best_val_loss'] = best_val_loss
        
        return metrics
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.
        
        Args:
            X: Input features (batch, seq_len, features)
            
        Returns:
            Predictions array (batch, 1)
        """
        if not self.is_trained:
            raise ValueError("Model has not been trained yet")
        
        self.eval()
        
        X_tensor = torch.FloatTensor(X).to(self.device)
        
        with torch.no_grad():
            predictions = self(X_tensor)
        
        return predictions.cpu().numpy()
    
    def save(self, filepath: str) -> bool:
        """
        Save model checkpoint to disk.
        
        Args:
            filepath: Path to save model
            
        Returns:
            True if successful
        """
        checkpoint = {
            'model_state_dict': self.state_dict(),
            'input_size': self.input_size,
            'hidden_size': self.hidden_size,
            'num_layers': self.num_layers,
            'dropout': self.dropout,
            'bidirectional': self.bidirectional,
            'attention': self.attention is not None,
            'is_trained': self.is_trained
        }
        
        torch.save(checkpoint, filepath)
        return True
    
    def load(self, filepath: str) -> bool:
        """
        Load model checkpoint from disk.
        
        Args:
            filepath: Path to load model from
            
        Returns:
            True if successful
        """
        checkpoint = torch.load(filepath, map_location=self.device)
        
        # Verify architecture matches
        assert checkpoint['input_size'] == self.input_size
        assert checkpoint['hidden_size'] == self.hidden_size
        assert checkpoint['num_layers'] == self.num_layers
        
        # Load state
        self.load_state_dict(checkpoint['model_state_dict'])
        self.is_trained = checkpoint['is_trained']
        
        return True
