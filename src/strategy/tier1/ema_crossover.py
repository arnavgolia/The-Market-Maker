"""
EMA Crossover Strategy (Tier 1 - Deterministic).

This is a classic momentum strategy:
- Buy when fast EMA crosses above slow EMA (golden cross)
- Sell when fast EMA crosses below slow EMA (death cross)

The strategy is regime-gated: only trades when momentum_enabled=True.
"""

from datetime import datetime
from typing import Optional
import structlog

import numpy as np
import pandas as pd

from src.strategy.base import Strategy, Signal, SignalType
from src.regime.detector import MarketRegime

logger = structlog.get_logger(__name__)


class EMACrossoverStrategy(Strategy):
    """
    EMA Crossover momentum strategy.
    
    This is a baseline strategy that should work in trending markets
    and fail in choppy markets. The regime detector disables it
    when ADX < 20 (choppy market).
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        enabled: bool = True,
    ):
        """
        Initialize EMA crossover strategy.
        
        Args:
            fast_period: Fast EMA period (default 12 days)
            slow_period: Slow EMA period (default 26 days)
            signal_period: Signal line period (default 9 days, for MACD)
            enabled: Whether strategy is enabled
        """
        super().__init__(
            name="ema_crossover",
            enabled=enabled,
            require_regime=True,  # Only trade when regime allows
        )
        
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
        logger.info(
            "ema_crossover_initialized",
            fast_period=fast_period,
            slow_period=slow_period,
        )
    
    def generate_signals(
        self,
        symbol: str,
        bars: any,
        current_regime: Optional[MarketRegime] = None,
        current_position: Optional[dict] = None,
    ) -> list[Signal]:
        """
        Generate signals based on EMA crossover.
        
        Returns:
            List of signals (buy, sell, or empty)
        """
        signals = []
        
        # Check if strategy should generate signals
        # For active trading, allow EMA even in choppy markets (just less confident)
        if not self.enabled:
            return signals
        
        # Log regime for debugging
        if current_regime:
            logger.debug(
                "ema_strategy_checking",
                symbol=symbol,
                momentum_enabled=current_regime.momentum_enabled,
                regime=current_regime.combined_regime,
            )
        
        # Convert bars to DataFrame if needed
        if isinstance(bars, list):
            df = pd.DataFrame([
                {
                    "timestamp": b.timestamp,
                    "close": b.close,
                }
                for b in bars
            ])
        else:
            df = bars.copy()
        
        if len(df) < self.slow_period + 1:
            logger.warning(
                "insufficient_data_for_ema",
                symbol=symbol,
                bars_count=len(df),
                required=self.slow_period + 1,
            )
            return signals
        
        # Calculate EMAs
        df["ema_fast"] = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        
        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        ema_fast_current = latest["ema_fast"]
        ema_slow_current = latest["ema_slow"]
        ema_fast_prev = prev["ema_fast"]
        ema_slow_prev = prev["ema_slow"]
        
        # Check for crossover
        # Golden cross: fast crosses above slow (bullish)
        # Death cross: fast crosses below slow (bearish)
        
        golden_cross = (
            ema_fast_prev <= ema_slow_prev and
            ema_fast_current > ema_slow_current
        )
        
        death_cross = (
            ema_fast_prev >= ema_slow_prev and
            ema_fast_current < ema_slow_current
        )
        
        # Calculate signal strength (distance between EMAs)
        ema_distance = abs(ema_fast_current - ema_slow_current) / ema_slow_current
        confidence = min(ema_distance * 10, 1.0)  # Scale to 0-1
        
        # Generate signals
        if golden_cross:
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                timestamp=datetime.now(),
                strategy_name=self.name,
                signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                confidence=confidence,
                entry_price=float(latest["close"]),
                metadata={
                    "ema_fast": float(ema_fast_current),
                    "ema_slow": float(ema_slow_current),
                    "crossover_type": "golden_cross",
                },
            )
            
            if self.validate_signal(signal):
                signals.append(signal)
                logger.info(
                    "ema_golden_cross",
                    symbol=symbol,
                    confidence=confidence,
                    ema_fast=ema_fast_current,
                    ema_slow=ema_slow_current,
                )
        
        elif death_cross:
            # If we have a position, close it
            if current_position and float(current_position.get("qty", 0)) > 0:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    signal_id=f"{self.name}_{symbol}_{datetime.now().timestamp()}",
                    confidence=confidence,
                    metadata={
                        "ema_fast": float(ema_fast_current),
                        "ema_slow": float(ema_slow_current),
                        "crossover_type": "death_cross",
                    },
                )
                
                if self.validate_signal(signal):
                    signals.append(signal)
                    logger.info(
                        "ema_death_cross",
                        symbol=symbol,
                        confidence=confidence,
                    )
        
        return signals
    
    def calculate_macd(
        self,
        bars: any,
    ) -> Optional[dict]:
        """
        Calculate MACD indicator (optional enhancement).
        
        MACD = Fast EMA - Slow EMA
        Signal = EMA of MACD
        Histogram = MACD - Signal
        
        Returns MACD values for additional confirmation.
        """
        if isinstance(bars, list):
            df = pd.DataFrame([
                {"close": b.close}
                for b in bars
            ])
        else:
            df = bars.copy()
        
        if len(df) < self.slow_period + self.signal_period:
            return None
        
        # Calculate EMAs
        ema_fast = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        
        # MACD line
        macd = ema_fast - ema_slow
        
        # Signal line
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        
        # Histogram
        histogram = macd - signal
        
        return {
            "macd": float(macd.iloc[-1]),
            "signal": float(signal.iloc[-1]),
            "histogram": float(histogram.iloc[-1]),
        }
