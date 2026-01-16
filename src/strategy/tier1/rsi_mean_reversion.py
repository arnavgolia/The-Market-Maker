"""
RSI Mean Reversion Strategy (Tier 1 - Deterministic).

This strategy trades mean reversion:
- Buy when RSI < oversold threshold (e.g., 30)
- Sell when RSI > overbought threshold (e.g., 70)

The strategy is regime-gated: only trades when momentum_enabled=False
(i.e., in choppy markets where mean reversion works better).
"""

from datetime import datetime
from typing import Optional
import structlog

import numpy as np
import pandas as pd

from src.strategy.base import Strategy, Signal, SignalType
from src.regime.detector import MarketRegime

logger = structlog.get_logger(__name__)


class RSIMeanReversionStrategy(Strategy):
    """
    RSI Mean Reversion strategy.
    
    This strategy works in choppy markets where momentum fails.
    It's the complement to EMA crossover (which works in trending markets).
    """
    
    def __init__(
        self,
        period: int = 14,
        oversold_threshold: float = 30.0,
        overbought_threshold: float = 70.0,
        enabled: bool = True,
    ):
        """
        Initialize RSI mean reversion strategy.
        
        Args:
            period: RSI calculation period (default 14)
            oversold_threshold: RSI < this = oversold (buy signal)
            overbought_threshold: RSI > this = overbought (sell signal)
            enabled: Whether strategy is enabled
        """
        super().__init__(
            name="rsi_mean_reversion",
            enabled=enabled,
            require_regime=True,
        )
        
        self.period = period
        # Lower thresholds for more active trading (demo mode)
        # Make RSI more sensitive: 40/60 instead of 30/70
        self.oversold_threshold = 40.0  # More sensitive (was 30)
        self.overbought_threshold = 60.0  # More sensitive (was 70)
        
        logger.info(
            "rsi_mean_reversion_initialized",
            period=period,
            oversold=oversold_threshold,
            overbought=overbought_threshold,
        )
    
    def generate_signals(
        self,
        symbol: str,
        bars: any,
        current_regime: Optional[MarketRegime] = None,
        current_position: Optional[dict] = None,
    ) -> list[Signal]:
        """
        Generate signals based on RSI mean reversion.
        
        Note: This strategy works best in CHOPPY markets.
        In trending markets, RSI can stay overbought/oversold for extended periods.
        """
        signals = []
        
        # Check if strategy should generate signals
        # For mean reversion, we want CHOPPY markets (momentum_enabled=False)
        if not self.enabled:
            return signals
        
        # Mean reversion works in choppy markets
        # For active trading, allow RSI to work even in trending markets (just less confident)
        # Only skip if we're in a clear strong trend
        if (current_regime and 
            current_regime.momentum_enabled and
            hasattr(current_regime, "trend") and
            current_regime.trend.value == "strong_trend"):
            logger.debug(
                "rsi_disabled_in_strong_trend",
                symbol=symbol,
                regime=current_regime.combined_regime,
            )
            return signals
        
        # Convert bars to DataFrame if needed
        if isinstance(bars, list):
            df = pd.DataFrame([
                {"close": b.close}
                for b in bars
            ])
        else:
            df = bars.copy()
        
        if len(df) < self.period + 1:
            logger.warning(
                "insufficient_data_for_rsi",
                symbol=symbol,
                bars_count=len(df),
                required=self.period + 1,
            )
            return signals
        
        # Calculate RSI
        rsi = self._calculate_rsi(df["close"], self.period)
        current_rsi = rsi.iloc[-1]
        
        # Calculate signal strength based on how extreme RSI is
        if current_rsi < self.oversold_threshold:
            # Oversold: Buy signal
            # Signal strength: how far below oversold threshold
            oversold_distance = (self.oversold_threshold - current_rsi) / self.oversold_threshold
            confidence = min(oversold_distance * 2, 1.0)  # Scale to 0-1
            
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                timestamp=datetime.now(),
                strategy_name=self.name,
                signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                confidence=confidence,
                entry_price=float(df["close"].iloc[-1]),
                metadata={
                    "rsi": float(current_rsi),
                    "oversold_threshold": self.oversold_threshold,
                },
            )
            
            if self.validate_signal(signal):
                signals.append(signal)
                logger.info(
                    "rsi_oversold_signal",
                    symbol=symbol,
                    rsi=current_rsi,
                    confidence=confidence,
                )
        
        elif current_rsi > self.overbought_threshold:
            # Overbought: Sell/Close signal
            # Signal strength: how far above overbought threshold
            overbought_distance = (current_rsi - self.overbought_threshold) / (100 - self.overbought_threshold)
            confidence = min(overbought_distance * 2, 1.0)
            
            # Only close if we have a position
            if current_position and float(current_position.get("qty", 0)) > 0:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                    confidence=confidence,
                    metadata={
                        "rsi": float(current_rsi),
                        "overbought_threshold": self.overbought_threshold,
                    },
                )
                
                if self.validate_signal(signal):
                    signals.append(signal)
                    logger.info(
                        "rsi_overbought_signal",
                        symbol=symbol,
                        rsi=current_rsi,
                        confidence=confidence,
                    )
        
        return signals
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """
        Calculate RSI (Relative Strength Index).
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        
        Args:
            prices: Series of closing prices
            period: RSI period
        
        Returns:
            Series of RSI values
        """
        delta = prices.diff()
        
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # Calculate average gain and loss using exponential moving average
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
