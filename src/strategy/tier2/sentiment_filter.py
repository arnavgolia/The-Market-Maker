"""
Sentiment Filter Strategy (Tier 2 - Probabilistic).

This strategy uses sentiment as a REGIME FILTER, not a signal.
It only trades when:
1. Base strategy (Tier 1) generates a signal
2. Sentiment confirms the signal (if calibrated)
3. Sentiment is not stale (decay model)

Sentiment is NOT used as a standalone signal - it only filters
existing signals from Tier 1 strategies.
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog

from src.strategy.base import Strategy, Signal, SignalType
from src.regime.detector import MarketRegime
from src.sentiment.calibration.lead_lag import SentimentMode

logger = structlog.get_logger(__name__)


class SentimentFilterStrategy(Strategy):
    """
    Sentiment filter that enhances Tier 1 strategies.
    
    This is NOT a standalone strategy - it wraps other strategies
    and filters their signals based on sentiment.
    
    Key principles:
    - Sentiment is a filter, not a signal
    - Only enabled if calibration validates
    - Respects sentiment decay (staleness)
    - Uses sentiment mode (confirming vs contrarian)
    """
    
    def __init__(
        self,
        base_strategy: Strategy,
        sentiment_mode: SentimentMode,
        min_sentiment_score: float = 0.3,
        max_sentiment_age_hours: float = 24.0,
        enabled: bool = True,
    ):
        """
        Initialize sentiment filter strategy.
        
        Args:
            base_strategy: Base strategy to filter (e.g., EMA crossover)
            sentiment_mode: How to use sentiment (from calibration)
            min_sentiment_score: Minimum sentiment score to pass filter
            max_sentiment_age_hours: Maximum age of sentiment data
            enabled: Whether strategy is enabled
        """
        super().__init__(
            name=f"sentiment_filter_{base_strategy.name}",
            enabled=enabled,
            require_regime=True,
        )
        
        self.base_strategy = base_strategy
        self.sentiment_mode = sentiment_mode
        self.min_sentiment_score = min_sentiment_score
        self.max_sentiment_age_hours = max_sentiment_age_hours
        
        # Sentiment data (would be populated by sentiment engine)
        self.sentiment_data: dict[str, dict] = {}  # symbol -> sentiment info
        
        logger.info(
            "sentiment_filter_initialized",
            base_strategy=base_strategy.name,
            sentiment_mode=sentiment_mode.value,
            enabled=enabled,
        )
    
    def generate_signals(
        self,
        symbol: str,
        bars: any,
        current_regime: Optional[MarketRegime] = None,
        current_position: Optional[dict] = None,
    ) -> list[Signal]:
        """
        Generate signals by filtering base strategy with sentiment.
        
        Process:
        1. Get signals from base strategy
        2. Filter by sentiment (if available and valid)
        3. Return filtered signals
        """
        signals = []
        
        # Check if strategy should generate signals
        if not self.should_generate_signals(current_regime):
            return signals
        
        # Check if sentiment is enabled (calibration passed)
        if self.sentiment_mode == SentimentMode.DISABLED:
            # Sentiment not validated - just use base strategy
            return self.base_strategy.generate_signals(
                symbol=symbol,
                bars=bars,
                current_regime=current_regime,
                current_position=current_position,
            )
        
        # Get base signals
        base_signals = self.base_strategy.generate_signals(
            symbol=symbol,
            bars=bars,
            current_regime=current_regime,
            current_position=current_position,
        )
        
        if not base_signals:
            return signals
        
        # Filter by sentiment
        for signal in base_signals:
            if self._passes_sentiment_filter(signal, symbol):
                signals.append(signal)
                logger.debug(
                    "signal_passed_sentiment_filter",
                    symbol=symbol,
                    signal_type=signal.signal_type.value,
                )
            else:
                logger.debug(
                    "signal_filtered_by_sentiment",
                    symbol=symbol,
                    signal_type=signal.signal_type.value,
                )
        
        return signals
    
    def _passes_sentiment_filter(
        self,
        signal: Signal,
        symbol: str,
    ) -> bool:
        """
        Check if signal passes sentiment filter.
        
        Returns True if:
        - Sentiment data is available and fresh
        - Sentiment confirms the signal (based on mode)
        - Sentiment score meets threshold
        """
        # Get sentiment data for symbol
        sentiment_info = self.sentiment_data.get(symbol)
        
        if not sentiment_info:
            # No sentiment data - pass through (don't block)
            return True
        
        # Check age
        sentiment_time = sentiment_info.get("timestamp")
        if sentiment_time:
            age_hours = (datetime.now() - sentiment_time).total_seconds() / 3600
            if age_hours > self.max_sentiment_age_hours:
                logger.debug(
                    "sentiment_too_stale",
                    symbol=symbol,
                    age_hours=age_hours,
                )
                return True  # Pass through if stale (don't block)
        
        # Get sentiment score
        sentiment_score = sentiment_info.get("score", 0.0)
        
        # Apply filter based on sentiment mode
        if self.sentiment_mode == SentimentMode.CONFIRMING:
            # Positive sentiment confirms buy signals
            if signal.signal_type == SignalType.BUY:
                return sentiment_score >= self.min_sentiment_score
            elif signal.signal_type in (SignalType.SELL, SignalType.CLOSE):
                return sentiment_score <= -self.min_sentiment_score
            else:
                return True  # HOLD signals pass through
        
        elif self.sentiment_mode == SentimentMode.CONTRARIAN:
            # Positive sentiment contradicts buy signals (crowded trade)
            if signal.signal_type == SignalType.BUY:
                return sentiment_score <= -self.min_sentiment_score  # Negative sentiment = buy
            elif signal.signal_type in (SignalType.SELL, SignalType.CLOSE):
                return sentiment_score >= self.min_sentiment_score  # Positive sentiment = sell
            else:
                return True
        
        else:
            # DISABLED mode - pass through
            return True
    
    def update_sentiment(
        self,
        symbol: str,
        score: float,
        timestamp: datetime,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Update sentiment data for a symbol.
        
        Called by sentiment engine to provide fresh sentiment data.
        """
        self.sentiment_data[symbol] = {
            "score": score,
            "timestamp": timestamp,
            "metadata": metadata or {},
        }
        
        logger.debug(
            "sentiment_updated",
            symbol=symbol,
            score=score,
        )
    
    def clear_stale_sentiment(self, max_age_hours: Optional[float] = None) -> None:
        """Clear sentiment data that is too stale."""
        if max_age_hours is None:
            max_age_hours = self.max_sentiment_age_hours
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        cleared = []
        for symbol, sentiment_info in list(self.sentiment_data.items()):
            sentiment_time = sentiment_info.get("timestamp")
            if sentiment_time and sentiment_time < cutoff_time:
                del self.sentiment_data[symbol]
                cleared.append(symbol)
        
        if cleared:
            logger.info("stale_sentiment_cleared", symbols=cleared, count=len(cleared))
