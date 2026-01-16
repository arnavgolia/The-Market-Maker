"""
LSTM Strategy for Returns Prediction (Tier 3 - Research Only).

WARNING: This is RESEARCH ONLY. Do NOT use for production trading.

Key principles:
- Uses stationary transforms (log returns, not raw prices)
- Walk-forward validation MANDATORY
- Expect failure - most ML models fail on financial data
- Compare against trivial baselines (random walk, persistence)

This implements the lessons from Phase 1 research:
- LSTMs fail on non-stationary data
- Prediction accuracy ≠ trading profitability
- Better models can still lose money
"""

from datetime import datetime
from typing import Optional
import structlog

import numpy as np
import pandas as pd

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available - LSTM strategy disabled")

from src.strategy.base import Strategy, Signal, SignalType
from src.regime.detector import MarketRegime

logger = structlog.get_logger(__name__)


class LSTMReturnsStrategy(Strategy):
    """
    LSTM-based returns prediction strategy (RESEARCH ONLY).
    
    This strategy:
    - Uses LSTM to predict next-period returns
    - Trains on stationary transforms (log returns, realized vol)
    - Requires walk-forward validation
    - Is NOT enabled by default
    
    CRITICAL: This is for research insights, not production trading.
    Most implementations will fail - this is expected and informative.
    """
    
    def __init__(
        self,
        sequence_length: int = 60,
        hidden_size: int = 50,
        num_layers: int = 2,
        enabled: bool = False,  # DISABLED by default - research only
    ):
        """
        Initialize LSTM strategy.
        
        Args:
            sequence_length: Number of time steps to use as input
            hidden_size: LSTM hidden layer size
            num_layers: Number of LSTM layers
            enabled: MUST be False for production (research only)
        """
        super().__init__(
            name="lstm_returns",
            enabled=enabled,
            require_regime=True,
        )
        
        if enabled and not TORCH_AVAILABLE:
            logger.error("lstm_strategy_requires_pytorch")
            self.enabled = False
        
        self.sequence_length = sequence_length
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # Model (will be trained)
        self.model: Optional[nn.Module] = None
        self.is_trained = False
        
        # Research flag - explicit reminder this is research only
        self.RESEARCH_ONLY = True
        
        logger.warning(
            "lstm_strategy_initialized",
            message="LSTM strategy is RESEARCH ONLY - not for production trading",
            enabled=enabled,
        )
    
    def fit(self, bars: pd.DataFrame) -> None:
        """
        Train LSTM model on historical data.
        
        This should ONLY be called during walk-forward validation.
        Never train on full dataset - guaranteed overfitting.
        """
        if not TORCH_AVAILABLE:
            logger.error("pytorch_not_available")
            return
        
        logger.info("training_lstm_model", bars_count=len(bars))
        
        # Prepare data: use stationary transforms
        returns = self._prepare_stationary_data(bars)
        
        if len(returns) < self.sequence_length + 1:
            logger.warning("insufficient_data_for_training")
            return
        
        # Create sequences
        X, y = self._create_sequences(returns)
        
        if len(X) == 0:
            logger.warning("no_sequences_created")
            return
        
        # Initialize model
        self.model = LSTMPredictor(
            input_size=1,  # Single feature (returns)
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
        )
        
        # Train (simplified - would need proper training loop)
        # This is a placeholder - real implementation would include:
        # - Train/validation split
        # - Early stopping
        # - Learning rate scheduling
        # - Proper loss function (not just MSE)
        
        logger.warning(
            "lstm_training_placeholder",
            message="LSTM training is simplified - implement full training loop for research",
        )
        
        self.is_trained = True
    
    def generate_signals(
        self,
        symbol: str,
        bars: any,
        current_regime: Optional[MarketRegime] = None,
        current_position: Optional[dict] = None,
    ) -> list[Signal]:
        """
        Generate signals using LSTM predictions.
        
        WARNING: This is research only. Predictions may be meaningless.
        """
        signals = []
        
        # Check if strategy should generate signals
        if not self.should_generate_signals(current_regime):
            return signals
        
        # Check if model is trained
        if not self.is_trained or self.model is None:
            logger.warning("lstm_model_not_trained")
            return signals
        
        # Convert bars to DataFrame if needed
        if isinstance(bars, list):
            df = pd.DataFrame([
                {"close": b.close, "volume": b.volume}
                for b in bars
            ])
        else:
            df = bars.copy()
        
        if len(df) < self.sequence_length:
            logger.warning("insufficient_data_for_prediction")
            return signals
        
        # Prepare data
        returns = self._prepare_stationary_data(df)
        
        # Get prediction
        try:
            prediction = self._predict_next_return(returns)
            
            # Generate signal based on prediction
            # CRITICAL: Prediction accuracy ≠ trading profitability
            # We need to consider transaction costs, confidence, etc.
            
            if prediction > 0.001:  # Positive return prediction
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                    confidence=min(abs(prediction) * 10, 1.0),  # Scale to 0-1
                    metadata={
                        "predicted_return": prediction,
                        "research_only": True,
                    },
                )
                
                if self.validate_signal(signal):
                    signals.append(signal)
            
            elif prediction < -0.001:  # Negative return prediction
                if current_position and float(current_position.get("qty", 0)) > 0:
                    signal = Signal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE,
                        timestamp=datetime.now(),
                        strategy_name=self.name,
                        signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                        confidence=min(abs(prediction) * 10, 1.0),
                        metadata={
                            "predicted_return": prediction,
                            "research_only": True,
                        },
                    )
                    
                    if self.validate_signal(signal):
                        signals.append(signal)
        
        except Exception as e:
            logger.error("lstm_prediction_error", error=str(e))
        
        return signals
    
    def _prepare_stationary_data(self, bars: pd.DataFrame) -> pd.Series:
        """
        Prepare stationary data for LSTM.
        
        CRITICAL: Use log returns, not raw prices.
        Raw prices are non-stationary and will cause LSTM to fail.
        """
        # Calculate log returns (stationary)
        prices = bars["close"]
        log_returns = np.log(prices / prices.shift(1)).dropna()
        
        # Z-score normalization
        mean = log_returns.mean()
        std = log_returns.std()
        
        if std > 0:
            normalized = (log_returns - mean) / std
        else:
            normalized = log_returns
        
        return normalized
    
    def _create_sequences(
        self,
        returns: pd.Series,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Create input sequences for LSTM."""
        X = []
        y = []
        
        for i in range(len(returns) - self.sequence_length):
            seq = returns.iloc[i:i+self.sequence_length].values
            target = returns.iloc[i+self.sequence_length]
            
            X.append(seq)
            y.append(target)
        
        return np.array(X), np.array(y)
    
    def _predict_next_return(self, returns: pd.Series) -> float:
        """Predict next return using trained LSTM."""
        if not self.model:
            return 0.0
        
        # Get last sequence
        if len(returns) < self.sequence_length:
            return 0.0
        
        sequence = returns.tail(self.sequence_length).values
        sequence_tensor = torch.FloatTensor(sequence).unsqueeze(0).unsqueeze(-1)
        
        # Predict
        with torch.no_grad():
            prediction = self.model(sequence_tensor)
        
        return float(prediction.item())


class LSTMPredictor(nn.Module):
    """Simple LSTM model for returns prediction."""
    
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
    ):
        super().__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
        )
        
        self.fc = nn.Linear(hidden_size, 1)
    
    def forward(self, x):
        """Forward pass."""
        lstm_out, _ = self.lstm(x)
        last_output = lstm_out[:, -1, :]
        prediction = self.fc(last_output)
        return prediction
