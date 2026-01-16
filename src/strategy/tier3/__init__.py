"""
Tier 3: ML Research Strategies.

WARNING: These are RESEARCH ONLY - NOT for production trading.
All ML models must pass walk-forward validation before consideration.
Most ML models will fail - this is expected and informative.
"""

from src.strategy.tier3.lstm_returns import LSTMReturnsStrategy

__all__ = ["LSTMReturnsStrategy"]
