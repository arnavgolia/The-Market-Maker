"""
Correlation matrix calculator.

Calculates correlation between assets for portfolio allocation.
High correlation = redundant positions = reduce allocation.
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog

import pandas as pd
import numpy as np

logger = structlog.get_logger(__name__)


class CorrelationMatrix:
    """
    Calculates and maintains correlation matrix for portfolio.
    
    High correlation between positions means redundant risk.
    Portfolio allocator uses this to reduce over-concentration.
    """
    
    def __init__(
        self,
        lookback_days: int = 60,
        min_data_points: int = 30,
    ):
        """
        Initialize correlation calculator.
        
        Args:
            lookback_days: Days to look back for correlation
            min_data_points: Minimum data points required
        """
        self.lookback_days = lookback_days
        self.min_data_points = min_data_points
        
        logger.info(
            "correlation_matrix_initialized",
            lookback_days=lookback_days,
            min_data_points=min_data_points,
        )
    
    def calculate_correlation(
        self,
        returns_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix from returns data.
        
        Args:
            returns_data: DataFrame with columns = symbols, rows = dates
        
        Returns:
            Correlation matrix (symmetric, 1.0 on diagonal)
        """
        if returns_data.empty:
            return pd.DataFrame()
        
        # Calculate correlation
        correlation = returns_data.corr()
        
        # Fill diagonal with 1.0 (asset perfectly correlated with itself)
        np.fill_diagonal(correlation.values, 1.0)
        
        logger.debug(
            "correlation_calculated",
            symbols=len(correlation.columns),
        )
        
        return correlation
    
    def calculate_from_bars(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Calculate correlation from bar data.
        
        Args:
            bars_by_symbol: Dict mapping symbol to DataFrame with close prices
        
        Returns:
            Correlation matrix
        """
        # Convert to returns
        returns_data = {}
        
        for symbol, bars in bars_by_symbol.items():
            if "close" not in bars.columns:
                continue
            
            # Calculate returns
            returns = bars["close"].pct_change().dropna()
            
            if len(returns) >= self.min_data_points:
                returns_data[symbol] = returns
        
        if not returns_data:
            logger.warning("insufficient_data_for_correlation")
            return pd.DataFrame()
        
        # Align by date
        returns_df = pd.DataFrame(returns_data)
        returns_df = returns_df.dropna()  # Remove rows with missing data
        
        if len(returns_df) < self.min_data_points:
            logger.warning("insufficient_aligned_data_for_correlation")
            return pd.DataFrame()
        
        # Calculate correlation
        return self.calculate_correlation(returns_df)
    
    def get_correlation(
        self,
        symbol1: str,
        symbol2: str,
        correlation_matrix: pd.DataFrame,
    ) -> float:
        """
        Get correlation between two symbols.
        
        Returns:
            Correlation coefficient (-1 to +1)
        """
        if correlation_matrix.empty:
            return 0.0
        
        if symbol1 not in correlation_matrix.index or symbol2 not in correlation_matrix.columns:
            return 0.0
        
        return float(correlation_matrix.loc[symbol1, symbol2])
    
    def identify_highly_correlated(
        self,
        correlation_matrix: pd.DataFrame,
        threshold: float = 0.7,
    ) -> list[tuple[str, str, float]]:
        """
        Identify pairs of highly correlated assets.
        
        Returns:
            List of (symbol1, symbol2, correlation) tuples
        """
        if correlation_matrix.empty:
            return []
        
        highly_correlated = []
        
        for i, symbol1 in enumerate(correlation_matrix.index):
            for symbol2 in correlation_matrix.columns[i+1:]:
                corr = correlation_matrix.loc[symbol1, symbol2]
                
                if abs(corr) >= threshold:
                    highly_correlated.append((symbol1, symbol2, corr))
        
        return highly_correlated
