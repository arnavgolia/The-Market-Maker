"""
Drawdown monitoring and control.

Tracks portfolio drawdown and triggers alerts/actions when limits are breached.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DrawdownMetrics:
    """Drawdown metrics for a portfolio."""
    current_equity: float
    peak_equity: float
    initial_equity: float
    
    current_drawdown_pct: float  # From peak
    total_drawdown_pct: float     # From initial
    
    days_since_peak: int
    max_drawdown_pct: float       # Historical maximum


class DrawdownMonitor:
    """
    Monitors portfolio drawdown and enforces limits.
    
    Drawdown limits:
    - Daily: Soft limit (reduce exposure)
    - Total: Hard limit (halt trading)
    """
    
    def __init__(
        self,
        max_daily_drawdown_pct: float = 3.0,
        max_total_drawdown_pct: float = 10.0,
        initial_equity: Optional[float] = None,
    ):
        """
        Initialize drawdown monitor.
        
        Args:
            max_daily_drawdown_pct: Maximum daily drawdown before reducing exposure
            max_total_drawdown_pct: Maximum total drawdown before halting trading
            initial_equity: Initial portfolio equity (for total drawdown calculation)
        """
        self.max_daily_drawdown = max_daily_drawdown_pct
        self.max_total_drawdown = max_total_drawdown_pct
        self.initial_equity = initial_equity
        
        # Track peak equity
        self.peak_equity: Optional[float] = None
        self.peak_date: Optional[datetime] = None
        
        # Track maximum drawdown
        self.max_drawdown_pct: float = 0.0
        
        logger.info(
            "drawdown_monitor_initialized",
            max_daily=max_daily_drawdown_pct,
            max_total=max_total_drawdown_pct,
            initial_equity=initial_equity,
        )
    
    def update(
        self,
        current_equity: float,
        last_equity: Optional[float] = None,
    ) -> DrawdownMetrics:
        """
        Update drawdown metrics.
        
        Args:
            current_equity: Current portfolio equity
            last_equity: Previous day's equity (for daily drawdown)
        
        Returns:
            DrawdownMetrics with current state
        """
        # Initialize peak if first update
        if self.peak_equity is None:
            self.peak_equity = current_equity
            self.peak_date = datetime.now()
        
        # Update peak if new high
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.peak_date = datetime.now()
        
        # Calculate drawdowns
        current_drawdown_pct = (
            ((current_equity - self.peak_equity) / self.peak_equity) * 100
            if self.peak_equity > 0
            else 0.0
        )
        
        total_drawdown_pct = (
            ((current_equity - self.initial_equity) / self.initial_equity) * 100
            if self.initial_equity and self.initial_equity > 0
            else 0.0
        )
        
        # Update max drawdown
        if abs(current_drawdown_pct) > abs(self.max_drawdown_pct):
            self.max_drawdown_pct = current_drawdown_pct
        
        # Calculate days since peak
        days_since_peak = (
            (datetime.now() - self.peak_date).days
            if self.peak_date
            else 0
        )
        
        metrics = DrawdownMetrics(
            current_equity=current_equity,
            peak_equity=self.peak_equity,
            initial_equity=self.initial_equity or current_equity,
            current_drawdown_pct=current_drawdown_pct,
            total_drawdown_pct=total_drawdown_pct,
            days_since_peak=days_since_peak,
            max_drawdown_pct=self.max_drawdown_pct,
        )
        
        # Check limits
        self._check_limits(metrics, last_equity)
        
        return metrics
    
    def _check_limits(
        self,
        metrics: DrawdownMetrics,
        last_equity: Optional[float],
    ) -> None:
        """Check drawdown limits and log warnings."""
        # Daily drawdown check
        if last_equity:
            daily_drawdown_pct = (
                ((metrics.current_equity - last_equity) / last_equity) * 100
                if last_equity > 0
                else 0.0
            )
            
            if daily_drawdown_pct < -self.max_daily_drawdown:
                logger.warning(
                    "daily_drawdown_limit_breached",
                    daily_drawdown_pct=daily_drawdown_pct,
                    limit=-self.max_daily_drawdown,
                    action="reducing_exposure",
                )
        
        # Total drawdown check
        if abs(metrics.total_drawdown_pct) > self.max_total_drawdown:
            logger.critical(
                "total_drawdown_limit_breached",
                total_drawdown_pct=metrics.total_drawdown_pct,
                limit=self.max_total_drawdown,
                action="halt_trading",
            )
    
    def should_halt_trading(self, metrics: DrawdownMetrics) -> bool:
        """
        Check if trading should be halted.
        
        Returns True if total drawdown exceeds limit.
        """
        return abs(metrics.total_drawdown_pct) > self.max_total_drawdown
    
    def should_reduce_exposure(self, metrics: DrawdownMetrics) -> bool:
        """
        Check if exposure should be reduced.
        
        Returns True if current drawdown exceeds daily limit.
        """
        return abs(metrics.current_drawdown_pct) > self.max_daily_drawdown
    
    def get_position_scale(self, metrics: DrawdownMetrics) -> float:
        """
        Calculate position size scaling based on drawdown.
        
        Returns a multiplier (0.0 to 1.0) to scale position sizes.
        """
        if self.should_halt_trading(metrics):
            return 0.0  # No trading
        
        if self.should_reduce_exposure(metrics):
            # Reduce by drawdown severity
            reduction = abs(metrics.current_drawdown_pct) / self.max_daily_drawdown
            return max(0.25, 1.0 - reduction)  # At least 25% of normal size
        
        return 1.0  # Normal sizing
