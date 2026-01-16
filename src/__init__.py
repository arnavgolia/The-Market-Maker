"""
The Market Maker - A failure-aware, research-driven paper trading system.

This system is designed for survivability over profitability. It assumes:
- Backtests lie
- Markets are adversarial
- Most strategies die
- Most ML models fail

The goal is to run for 3 months, lose ~2% to transaction costs,
and have perfect logs explaining why.
"""

__version__ = "0.1.0"
__author__ = "Market Maker Team"
