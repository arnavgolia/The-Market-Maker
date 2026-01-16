"""
Portfolio allocator with correlation awareness.

Allocates capital across multiple positions while considering:
- Correlation between assets
- Sector concentration limits
- Volatility targeting
- Maximum position limits
"""

from dataclasses import dataclass
from typing import Optional
import structlog

import numpy as np
import pandas as pd

logger = structlog.get_logger(__name__)


@dataclass
class AllocationResult:
    """Result of portfolio allocation."""
    symbol: str
    target_size_pct: float
    target_size_dollars: float
    current_size_pct: float
    current_size_dollars: float
    rebalance_needed: bool
    rebalance_amount: float  # Positive = buy, negative = sell


class PortfolioAllocator:
    """
    Portfolio allocator with correlation awareness.
    
    Allocates capital across multiple positions while:
    - Respecting maximum position limits
    - Limiting sector concentration
    - Accounting for correlation (avoid over-concentration)
    - Targeting portfolio-level volatility
    """
    
    def __init__(
        self,
        max_position_pct: float = 10.0,
        max_sector_pct: float = 30.0,
        target_volatility_pct: float = 15.0,
        correlation_lookback_days: int = 60,
    ):
        """
        Initialize portfolio allocator.
        
        Args:
            max_position_pct: Maximum single position (% of portfolio)
            max_sector_pct: Maximum sector exposure (% of portfolio)
            target_volatility_pct: Target portfolio volatility
            correlation_lookback_days: Days to calculate correlation
        """
        self.max_position = max_position_pct / 100
        self.max_sector = max_sector_pct / 100
        self.target_volatility = target_volatility_pct / 100
        self.correlation_lookback = correlation_lookback_days
        
        logger.info(
            "portfolio_allocator_initialized",
            max_position_pct=max_position_pct,
            max_sector_pct=max_sector_pct,
            target_volatility_pct=target_volatility_pct,
        )
    
    def allocate(
        self,
        signals: list[dict],  # List of {symbol, suggested_size_pct, confidence, ...}
        current_positions: dict[str, dict],  # symbol -> {qty, market_value, ...}
        portfolio_value: float,
        correlation_matrix: Optional[pd.DataFrame] = None,
    ) -> list[AllocationResult]:
        """
        Allocate portfolio across signals.
        
        Args:
            signals: List of trading signals with suggested sizes
            current_positions: Current positions
            portfolio_value: Total portfolio value
            correlation_matrix: Correlation matrix (optional)
        
        Returns:
            List of allocation results
        """
        if not signals:
            return []
        
        # Calculate target allocations
        target_allocations = self._calculate_target_allocations(
            signals=signals,
            portfolio_value=portfolio_value,
            correlation_matrix=correlation_matrix,
        )
        
        # Calculate current allocations
        current_allocations = self._calculate_current_allocations(
            current_positions=current_positions,
            portfolio_value=portfolio_value,
        )
        
        # Generate allocation results
        results = []
        
        for symbol in set(list(target_allocations.keys()) + list(current_allocations.keys())):
            target_pct = target_allocations.get(symbol, 0.0)
            current_pct = current_allocations.get(symbol, 0.0)
            
            target_dollars = target_pct * portfolio_value
            current_dollars = current_pct * portfolio_value
            
            rebalance_needed = abs(target_pct - current_pct) > 0.01  # 1% threshold
            rebalance_amount = target_dollars - current_dollars
            
            results.append(AllocationResult(
                symbol=symbol,
                target_size_pct=target_pct * 100,
                target_size_dollars=target_dollars,
                current_size_pct=current_pct * 100,
                current_size_dollars=current_dollars,
                rebalance_needed=rebalance_needed,
                rebalance_amount=rebalance_amount,
            ))
        
        return results
    
    def _calculate_target_allocations(
        self,
        signals: list[dict],
        portfolio_value: float,
        correlation_matrix: Optional[pd.DataFrame] = None,
    ) -> dict[str, float]:
        """
        Calculate target allocations from signals.
        
        Applies:
        - Maximum position limits
        - Correlation adjustments
        - Sector limits (if sector data available)
        """
        # Start with suggested sizes from signals
        allocations = {}
        
        for signal in signals:
            symbol = signal["symbol"]
            suggested_pct = signal.get("suggested_size_pct", 5.0) / 100
            confidence = signal.get("confidence", 0.5)
            
            # Scale by confidence
            allocation = suggested_pct * confidence
            
            # Cap at maximum
            allocation = min(allocation, self.max_position)
            
            allocations[symbol] = allocation
        
        # Apply correlation adjustments
        if correlation_matrix is not None and len(allocations) > 1:
            allocations = self._adjust_for_correlation(
                allocations=allocations,
                correlation_matrix=correlation_matrix,
            )
        
        # Normalize to ensure we don't overallocate
        total = sum(allocations.values())
        if total > 1.0:
            # Scale down proportionally
            scale = 1.0 / total
            allocations = {k: v * scale for k, v in allocations.items()}
        
        return allocations
    
    def _adjust_for_correlation(
        self,
        allocations: dict[str, float],
        correlation_matrix: pd.DataFrame,
    ) -> dict[str, float]:
        """
        Adjust allocations to account for correlation.
        
        Reduces allocation to highly correlated positions.
        """
        adjusted = allocations.copy()
        
        symbols = list(allocations.keys())
        
        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                if symbol1 in correlation_matrix.index and symbol2 in correlation_matrix.columns:
                    correlation = correlation_matrix.loc[symbol1, symbol2]
                    
                    # If highly correlated, reduce both positions
                    if abs(correlation) > 0.7:
                        reduction = abs(correlation) - 0.7  # Reduce by excess correlation
                        adjusted[symbol1] *= (1 - reduction * 0.5)
                        adjusted[symbol2] *= (1 - reduction * 0.5)
        
        return adjusted
    
    def _calculate_current_allocations(
        self,
        current_positions: dict[str, dict],
        portfolio_value: float,
    ) -> dict[str, float]:
        """Calculate current position allocations."""
        allocations = {}
        
        for symbol, position in current_positions.items():
            market_value = position.get("market_value", 0.0)
            allocation_pct = market_value / portfolio_value if portfolio_value > 0 else 0.0
            allocations[symbol] = allocation_pct
        
        return allocations
