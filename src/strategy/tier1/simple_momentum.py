"""
Simple Momentum Strategy - Always generates signals for active trading.

This is a demo strategy that generates trades more frequently
to show the system working. It uses simple price momentum.
"""

from datetime import datetime
from typing import Optional
import structlog

import pandas as pd

from src.strategy.base import Strategy, Signal, SignalType
from src.regime.detector import MarketRegime

logger = structlog.get_logger(__name__)


class SimpleMomentumStrategy(Strategy):
    """
    Simple momentum strategy for active trading demonstration.
    
    This strategy generates signals more frequently to show
    the trading system in action.
    """
    
    def __init__(
        self,
        lookback_periods: int = 5,
        momentum_threshold: float = 0.01,  # 1% price change
        enabled: bool = True,
    ):
        """
        Initialize simple momentum strategy.
        
        Args:
            lookback_periods: Number of periods to look back
            momentum_threshold: Minimum price change to trigger signal
            enabled: Whether strategy is enabled
        """
        super().__init__(
            name="simple_momentum",
            enabled=enabled,
            require_regime=False,  # Don't require regime - always active
        )
        
        self.lookback_periods = lookback_periods
        self.momentum_threshold = momentum_threshold
        
        logger.info(
            "simple_momentum_initialized",
            lookback_periods=lookback_periods,
            momentum_threshold=momentum_threshold,
        )
    
    def generate_signals(
        self,
        symbol: str,
        bars: any,
        current_regime: Optional[MarketRegime] = None,
        current_position: Optional[dict] = None,
    ) -> list[Signal]:
        """
        Generate signals based on simple price momentum.
        
        Buy if price increased > threshold over lookback period.
        Sell if price decreased > threshold.
        """
        signals = []
        
        if not self.enabled:
            return signals
        
        # Convert bars to DataFrame if needed
        if isinstance(bars, list):
            df = pd.DataFrame([
                {"close": b.close}
                for b in bars
            ])
        else:
            df = bars.copy()
        
        if len(df) < self.lookback_periods + 1:
            return signals
        
        # Calculate momentum
        current_price = float(df["close"].iloc[-1])
        past_price = float(df["close"].iloc[-self.lookback_periods - 1])
        momentum = (current_price - past_price) / past_price
        
        # Generate signals
        if momentum > self.momentum_threshold:
            # Positive momentum: Buy signal
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                timestamp=datetime.now(),
                strategy_name=self.name,
                signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                confidence=min(abs(momentum) * 10, 1.0),  # Scale to 0-1
                entry_price=current_price,
                metadata={
                    "momentum": float(momentum),
                    "lookback_periods": self.lookback_periods,
                },
            )
            
            if self.validate_signal(signal):
                signals.append(signal)
                logger.info(
                    "simple_momentum_buy_signal",
                    symbol=symbol,
                    momentum=momentum,
                    price=current_price,
                )
        
        elif momentum < -self.momentum_threshold and current_position:
            # Negative momentum: Close position if we have one
            if float(current_position.get("qty", 0)) > 0:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                    confidence=min(abs(momentum) * 10, 1.0),
                    metadata={
                        "momentum": float(momentum),
                        "lookback_periods": self.lookback_periods,
                    },
                )
                
                if self.validate_signal(signal):
                    signals.append(signal)
                    logger.info(
                        "simple_momentum_close_signal",
                        symbol=symbol,
                        momentum=momentum,
                    )
        
        return signals
