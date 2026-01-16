"""
Strategy module for trading strategies.

Tier 1: Deterministic (EMA, RSI)
Tier 2: Probabilistic (Sentiment-enhanced)
Tier 3: Learned (ML research only)
"""

from src.strategy.base import Strategy, Signal, SignalType

__all__ = ["Strategy", "Signal", "SignalType"]
