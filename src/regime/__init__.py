"""
Market regime detection module.

Detects market regimes to enable/disable strategies appropriately.
Uses dual-speed architecture:
- Fast (3-day ATR): Crisis detection
- Slow (20-day realized vol): Trend context

Implements Gemini's recommendation to prevent strategies from trading
during flash crashes before the slow regime detector catches up.
"""

from src.regime.detector import RegimeDetector, MarketRegime, TrendRegime, VolRegime

__all__ = ["RegimeDetector", "MarketRegime", "TrendRegime", "VolRegime"]
