"""
Portfolio management module.

Handles:
- Multi-asset portfolio allocation
- Correlation-aware position sizing
- Rebalancing logic
"""

from src.portfolio.allocator import PortfolioAllocator
from src.portfolio.correlation_matrix import CorrelationMatrix

__all__ = ["PortfolioAllocator", "CorrelationMatrix"]
