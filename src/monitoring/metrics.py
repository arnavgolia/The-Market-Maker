"""
Metrics collection for monitoring.

Collects and exports performance metrics for:
- Portfolio performance
- Strategy attribution
- Risk metrics
- Trading statistics
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
import structlog

import pandas as pd
import numpy as np

logger = structlog.get_logger(__name__)


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics."""
    timestamp: datetime
    
    # Portfolio values
    equity: float
    cash: float
    positions_value: float
    
    # Returns
    daily_return: float
    cumulative_return: float
    
    # Risk metrics
    sharpe_30d: Optional[float] = None
    sortino_30d: Optional[float] = None
    max_drawdown: Optional[float] = None
    current_drawdown: Optional[float] = None
    
    # Trading metrics
    num_positions: int = 0
    num_open_orders: int = 0
    
    # Strategy attribution
    strategy_attribution: dict = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "daily_return": self.daily_return,
            "cumulative_return": self.cumulative_return,
            "sharpe_30d": self.sharpe_30d,
            "sortino_30d": self.sortino_30d,
            "max_drawdown": self.max_drawdown,
            "current_drawdown": self.current_drawdown,
            "num_positions": self.num_positions,
            "num_open_orders": self.num_open_orders,
            "strategy_attribution": self.strategy_attribution or {},
        }


class MetricsCollector:
    """
    Collects and calculates performance metrics.
    
    Metrics are exported for:
    - Real-time monitoring
    - Historical analysis
    - Alerting triggers
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.metrics_history: list[PortfolioMetrics] = []
        logger.info("metrics_collector_initialized")
    
    def calculate_metrics(
        self,
        equity: float,
        cash: float,
        positions_value: float,
        initial_equity: float,
        returns_history: Optional[pd.Series] = None,
        num_positions: int = 0,
        num_open_orders: int = 0,
        strategy_attribution: Optional[dict] = None,
    ) -> PortfolioMetrics:
        """
        Calculate current portfolio metrics.
        
        Args:
            equity: Current portfolio equity
            cash: Current cash
            positions_value: Current positions value
            initial_equity: Initial equity (for returns calculation)
            returns_history: Historical returns (for Sharpe/Sortino)
            num_positions: Number of open positions
            num_open_orders: Number of open orders
            strategy_attribution: Strategy performance breakdown
        
        Returns:
            PortfolioMetrics with all calculated metrics
        """
        # Returns
        cumulative_return = (equity / initial_equity) - 1 if initial_equity > 0 else 0.0
        
        # Daily return (from last metric if available)
        daily_return = 0.0
        if self.metrics_history:
            last_equity = self.metrics_history[-1].equity
            if last_equity > 0:
                daily_return = (equity / last_equity) - 1
        
        # Risk metrics from returns history
        sharpe_30d = None
        sortino_30d = None
        max_drawdown = None
        current_drawdown = None
        
        if returns_history is not None and len(returns_history) > 0:
            # Rolling 30-day metrics
            if len(returns_history) >= 30:
                recent_returns = returns_history.tail(30)
                sharpe_30d = self._calculate_sharpe(recent_returns)
                sortino_30d = self._calculate_sortino(recent_returns)
            
            # Drawdown
            equity_series = self._returns_to_equity(returns_history, initial_equity)
            max_drawdown = self._calculate_max_drawdown(equity_series)
            current_drawdown = self._calculate_current_drawdown(equity_series)
        
        metrics = PortfolioMetrics(
            timestamp=datetime.now(),
            equity=equity,
            cash=cash,
            positions_value=positions_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            sharpe_30d=sharpe_30d,
            sortino_30d=sortino_30d,
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            num_positions=num_positions,
            num_open_orders=num_open_orders,
            strategy_attribution=strategy_attribution or {},
        )
        
        # Store in history
        self.metrics_history.append(metrics)
        
        # Keep only last 1000 metrics (prevent memory bloat)
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]
        
        return metrics
    
    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        excess_returns = returns.mean() - (risk_free_rate / 252)
        sharpe = (excess_returns / returns.std()) * np.sqrt(252)
        
        return float(sharpe)
    
    def _calculate_sortino(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio."""
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns.mean() - (risk_free_rate / 252)
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return float('inf') if excess_returns > 0 else 0.0
        
        downside_std = downside_returns.std()
        sortino = (excess_returns / downside_std) * np.sqrt(252)
        
        return float(sortino)
    
    def _calculate_max_drawdown(self, equity: pd.Series) -> float:
        """Calculate maximum drawdown."""
        if len(equity) == 0:
            return 0.0
        
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max
        max_dd = abs(drawdown.min())
        
        return float(max_dd)
    
    def _calculate_current_drawdown(self, equity: pd.Series) -> float:
        """Calculate current drawdown from peak."""
        if len(equity) == 0:
            return 0.0
        
        peak = equity.max()
        current = equity.iloc[-1]
        drawdown = (current - peak) / peak
        
        return float(drawdown)
    
    def _returns_to_equity(self, returns: pd.Series, initial_equity: float) -> pd.Series:
        """Convert returns series to equity series."""
        equity = initial_equity * (1 + returns).cumprod()
        return equity
    
    def get_latest_metrics(self) -> Optional[PortfolioMetrics]:
        """Get most recent metrics."""
        return self.metrics_history[-1] if self.metrics_history else None
    
    def get_metrics_history(self, days: int = 30) -> list[PortfolioMetrics]:
        """Get metrics history for last N days."""
        cutoff = datetime.now() - pd.Timedelta(days=days)
        return [
            m for m in self.metrics_history
            if m.timestamp >= cutoff
        ]
