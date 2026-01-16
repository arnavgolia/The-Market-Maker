"""
Market regime detector with dual-speed architecture.

Fast regime (3-day ATR) detects crises immediately.
Slow regime (20-day realized vol) provides trend context.

This prevents the "lag mismatch" problem where a flash crash
blows through positions before the slow detector responds.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import structlog

import numpy as np
import pandas as pd

logger = structlog.get_logger(__name__)


class TrendRegime(Enum):
    """Trend strength classification."""
    CHOPPY = "choppy"          # ADX < 20 - Momentum strategies OFF
    WEAK_TREND = "weak_trend"  # 20 <= ADX < 40
    STRONG_TREND = "strong_trend"  # ADX >= 40 - Momentum strategies ON


class VolRegime(Enum):
    """Volatility regime classification."""
    LOW_VOL = "low_vol"        # < 20th percentile
    NORMAL = "normal"          # 20th - 80th percentile
    HIGH_VOL = "high_vol"      # > 80th percentile
    CRISIS = "crisis"          # Fast vol > 2x slow vol (override)


@dataclass
class MarketRegime:
    """
    Complete market regime classification.
    
    This determines:
    - Whether momentum strategies should be enabled
    - Position sizing adjustments
    - Risk management parameters
    """
    timestamp: datetime
    symbol: Optional[str] = None  # None for market-wide regime
    
    # Regime classifications
    trend: TrendRegime = TrendRegime.CHOPPY
    volatility: VolRegime = VolRegime.NORMAL
    
    # Raw indicators
    adx: Optional[float] = None
    fast_vol: Optional[float] = None
    slow_vol: Optional[float] = None
    vol_ratio: Optional[float] = None  # fast_vol / slow_vol
    
    # Trading implications
    momentum_enabled: bool = False
    position_scale: float = 1.0  # Multiplier for position sizes
    
    @property
    def combined_regime(self) -> str:
        """Human-readable combined regime."""
        return f"{self.trend.value}_{self.volatility.value}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "trend_regime": self.trend.value,
            "vol_regime": self.volatility.value,
            "combined_regime": self.combined_regime,
            "adx": self.adx,
            "fast_vol": self.fast_vol,
            "slow_vol": self.slow_vol,
            "vol_ratio": self.vol_ratio,
            "momentum_enabled": self.momentum_enabled,
            "position_scale": self.position_scale,
        }


class RegimeDetector:
    """
    Market regime detector with dual-speed architecture.
    
    Design principles:
    - Fast regime (3-day) catches crises immediately
    - Slow regime (20-day) provides trend context
    - Crisis override: If fast > 2x slow, force CRISIS regime
    - Regime determines strategy enable/disable and position sizing
    """
    
    def __init__(
        self,
        fast_window_days: int = 3,
        slow_window_days: int = 20,
        fast_percentile_lookback: int = 60,
        slow_percentile_lookback: int = 252,
        crisis_multiplier: float = 2.0,
        adx_period: int = 14,
        adx_trending_threshold: float = 25.0,
        adx_choppy_threshold: float = 20.0,
    ):
        """
        Initialize regime detector.
        
        Args:
            fast_window_days: Window for fast volatility (crisis detection)
            slow_window_days: Window for slow volatility (trend context)
            fast_percentile_lookback: Days to look back for fast vol percentile
            slow_percentile_lookback: Days to look back for slow vol percentile
            crisis_multiplier: Fast vol must exceed slow vol by this factor to trigger crisis
            adx_period: Period for ADX calculation
            adx_trending_threshold: ADX > this = trending
            adx_choppy_threshold: ADX < this = choppy
        """
        self.fast_window = fast_window_days
        self.slow_window = slow_window_days
        self.fast_percentile_lookback = fast_percentile_lookback
        self.slow_percentile_lookback = slow_percentile_lookback
        self.crisis_multiplier = crisis_multiplier
        self.adx_period = adx_period
        self.adx_trending = adx_trending_threshold
        self.adx_choppy = adx_choppy_threshold
        
        logger.info(
            "regime_detector_initialized",
            fast_window=fast_window_days,
            slow_window=slow_window_days,
            crisis_multiplier=crisis_multiplier,
        )
    
    def detect_regime(
        self,
        bars: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> MarketRegime:
        """
        Detect current market regime from price bars.
        
        Args:
            bars: DataFrame with columns: timestamp, open, high, low, close, volume
            symbol: Optional symbol for symbol-specific regime
        
        Returns:
            MarketRegime classification
        """
        if len(bars) < max(self.slow_window, self.adx_period * 2):
            logger.warning(
                "insufficient_data_for_regime",
                bars_count=len(bars),
                required=max(self.slow_window, self.adx_period * 2),
            )
            # Return conservative default
            return MarketRegime(
                timestamp=datetime.now(),
                symbol=symbol,
                trend=TrendRegime.CHOPPY,
                volatility=VolRegime.NORMAL,
                momentum_enabled=False,
                position_scale=0.5,
            )
        
        # Calculate indicators
        fast_vol = self._calculate_fast_volatility(bars)
        slow_vol = self._calculate_slow_volatility(bars)
        adx = self._calculate_adx(bars)
        
        # Check for crisis override (Gemini's recommendation)
        vol_ratio = fast_vol / slow_vol if slow_vol > 0 else 1.0
        
        if vol_ratio > self.crisis_multiplier:
            # CRISIS MODE: Fast vol > 2x slow vol
            logger.warning(
                "crisis_regime_detected",
                symbol=symbol,
                fast_vol=fast_vol,
                slow_vol=slow_vol,
                ratio=vol_ratio,
            )
            
            return MarketRegime(
                timestamp=datetime.now(),
                symbol=symbol,
                trend=TrendRegime.CHOPPY,  # Force choppy in crisis
                volatility=VolRegime.CRISIS,
                adx=adx,
                fast_vol=fast_vol,
                slow_vol=slow_vol,
                vol_ratio=vol_ratio,
                momentum_enabled=False,  # Disable momentum in crisis
                position_scale=0.25,  # Reduce position sizes by 75%
            )
        
        # Normal regime detection
        vol_percentile = self._calculate_vol_percentile(bars, slow_vol)
        trend_regime = self._classify_trend(adx)
        vol_regime = self._classify_volatility(vol_percentile)
        
        # Determine momentum enablement
        momentum_enabled = trend_regime != TrendRegime.CHOPPY
        
        # Position scale based on volatility
        position_scale = self._calculate_position_scale(vol_regime)
        
        return MarketRegime(
            timestamp=datetime.now(),
            symbol=symbol,
            trend=trend_regime,
            volatility=vol_regime,
            adx=adx,
            fast_vol=fast_vol,
            slow_vol=slow_vol,
            vol_ratio=vol_ratio,
            momentum_enabled=momentum_enabled,
            position_scale=position_scale,
        )
    
    def _calculate_fast_volatility(self, bars: pd.DataFrame) -> float:
        """
        Calculate fast volatility using ATR (Average True Range).
        
        This is the 3-day ATR that catches crises immediately.
        """
        # Calculate True Range
        high = bars["high"].values
        low = bars["low"].values
        close = bars["close"].values
        
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        true_range[0] = tr1[0]  # First value is just high - low
        
        # Calculate ATR over fast window
        atr = pd.Series(true_range).rolling(window=self.fast_window).mean().iloc[-1]
        
        return float(atr)
    
    def _calculate_slow_volatility(self, bars: pd.DataFrame) -> float:
        """
        Calculate slow volatility using realized volatility.
        
        This is the 20-day realized volatility for trend context.
        """
        # Calculate returns
        returns = bars["close"].pct_change().dropna()
        
        # Realized volatility (annualized)
        if len(returns) < self.slow_window:
            return 0.0
        
        realized_vol = returns.tail(self.slow_window).std() * np.sqrt(252)  # Annualized
        
        return float(realized_vol)
    
    def _calculate_vol_percentile(
        self,
        bars: pd.DataFrame,
        current_vol: float,
    ) -> float:
        """
        Calculate current volatility percentile.
        
        This determines if we're in a low/normal/high vol regime.
        """
        # Calculate historical volatility values
        returns = bars["close"].pct_change().dropna()
        
        if len(returns) < self.slow_percentile_lookback:
            return 50.0  # Default to median if insufficient data
        
        # Calculate rolling realized vol
        rolling_vol = (
            returns
            .rolling(window=self.slow_window)
            .std()
            .dropna()
            * np.sqrt(252)  # Annualized
        )
        
        if len(rolling_vol) == 0:
            return 50.0
        
        # Calculate percentile
        percentile = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100
        
        return float(percentile)
    
    def _calculate_adx(self, bars: pd.DataFrame) -> float:
        """
        Calculate ADX (Average Directional Index).
        
        ADX measures trend strength, not direction.
        High ADX = strong trend (momentum strategies work)
        Low ADX = choppy market (momentum strategies fail)
        """
        high = bars["high"].values
        low = bars["low"].values
        close = bars["close"].values
        
        # Calculate +DM and -DM
        plus_dm = high - np.roll(high, 1)
        minus_dm = np.roll(low, 1) - low
        
        plus_dm[0] = 0
        minus_dm[0] = 0
        
        # Only count if one is positive and larger
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        # Calculate True Range (same as ATR)
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        true_range[0] = tr1[0]
        
        # Smooth +DM, -DM, and TR
        period = self.adx_period
        plus_di = pd.Series(plus_dm).rolling(window=period).mean()
        minus_di = pd.Series(minus_dm).rolling(window=period).mean()
        atr = pd.Series(true_range).rolling(window=period).mean()
        
        # Calculate DI+ and DI-
        plus_di_pct = (plus_di / atr) * 100
        minus_di_pct = (minus_di / atr) * 100
        
        # Calculate DX
        dx = 100 * np.abs(plus_di_pct - minus_di_pct) / (plus_di_pct + minus_di_pct)
        
        # Calculate ADX (smoothed DX)
        adx = dx.rolling(window=period).mean().iloc[-1]
        
        return float(adx) if not pd.isna(adx) else 0.0
    
    def _classify_trend(self, adx: float) -> TrendRegime:
        """Classify trend strength based on ADX."""
        if adx < self.adx_choppy:
            return TrendRegime.CHOPPY
        elif adx < self.adx_trending:
            return TrendRegime.WEAK_TREND
        else:
            return TrendRegime.STRONG_TREND
    
    def _classify_volatility(self, percentile: float) -> VolRegime:
        """Classify volatility regime based on percentile."""
        if percentile < 20:
            return VolRegime.LOW_VOL
        elif percentile > 80:
            return VolRegime.HIGH_VOL
        else:
            return VolRegime.NORMAL
    
    def _calculate_position_scale(self, vol_regime: VolRegime) -> float:
        """
        Calculate position size scaling based on volatility regime.
        
        High vol = smaller positions
        Low vol = normal positions
        """
        scales = {
            VolRegime.LOW_VOL: 1.0,
            VolRegime.NORMAL: 1.0,
            VolRegime.HIGH_VOL: 0.5,  # Reduce by 50% in high vol
            VolRegime.CRISIS: 0.25,  # Reduce by 75% in crisis
        }
        return scales.get(vol_regime, 1.0)
    
    def detect_regime_from_duckdb(
        self,
        duckdb_store,
        symbol: str,
        lookback_days: int = 60,
    ) -> Optional[MarketRegime]:
        """
        Detect regime using data from DuckDB.
        
        Convenience method that fetches bars and detects regime.
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        
        try:
            bars = duckdb_store.get_bars(
                symbol=symbol,
                start=start,
                end=end,
                timeframe="1Day",
            )
            
            if bars.empty:
                logger.warning("no_bars_for_regime", symbol=symbol)
                return None
            
            return self.detect_regime(bars, symbol=symbol)
            
        except Exception as e:
            logger.error("regime_detection_error", symbol=symbol, error=str(e))
            return None
