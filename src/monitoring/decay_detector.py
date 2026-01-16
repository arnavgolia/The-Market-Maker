"""
Strategy decay detection.

Detects when strategies are losing effectiveness and should be disabled.
Implements Gemini's recommendation: detect strategy death, not ignore it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import structlog

import numpy as np

logger = structlog.get_logger(__name__)


@dataclass
class DecayStatus:
    """Strategy decay status."""
    strategy_name: str
    is_decaying: bool
    is_dead: bool
    
    # Metrics
    current_sharpe: float
    historical_sharpe: float
    degradation_pct: float
    
    # Recommendations
    should_disable: bool
    recommendation: str


class StrategyDecayDetector:
    """
    Detects strategy decay and death.
    
    A strategy is "decaying" if current performance < 50% of historical.
    A strategy is "dead" if Sharpe < 0 for extended period.
    
    This implements Gemini's recommendation to detect strategy death
    rather than continuing to trade a dead strategy.
    """
    
    def __init__(
        self,
        rolling_window_days: int = 30,
        degradation_threshold: float = 0.5,
        disable_threshold_days: int = 20,
    ):
        """
        Initialize decay detector.
        
        Args:
            rolling_window_days: Window for current performance
            degradation_threshold: Current < threshold * historical = decaying
            disable_threshold_days: Sharpe < 0 for this many days = disable
        """
        self.rolling_window = rolling_window_days
        self.degradation_threshold = degradation_threshold
        self.disable_threshold_days = disable_threshold_days
        
        # Track strategy performance
        self.strategy_performance: dict[str, list[dict]] = {}
        
        logger.info(
            "decay_detector_initialized",
            rolling_window=rolling_window_days,
            degradation_threshold=degradation_threshold,
        )
    
    def check_strategy(
        self,
        strategy_name: str,
        current_sharpe: float,
        historical_sharpe: float,
    ) -> DecayStatus:
        """
        Check if strategy is decaying.
        
        Args:
            strategy_name: Strategy name
            current_sharpe: Current rolling Sharpe (30-day)
            historical_sharpe: Historical Sharpe (full period)
        
        Returns:
            DecayStatus with recommendations
        """
        # Calculate degradation
        if historical_sharpe != 0:
            degradation_pct = (historical_sharpe - current_sharpe) / abs(historical_sharpe)
        else:
            degradation_pct = 0.0
        
        # Check for decay
        is_decaying = (
            current_sharpe < self.degradation_threshold * historical_sharpe
            if historical_sharpe > 0
            else current_sharpe < 0
        )
        
        # Check for death (Sharpe < 0 for extended period)
        is_dead = self._check_strategy_death(strategy_name, current_sharpe)
        
        # Recommendations
        should_disable = is_dead
        if is_dead:
            recommendation = f"Strategy {strategy_name} is DEAD - disable immediately"
        elif is_decaying:
            recommendation = f"Strategy {strategy_name} is DECAYING - monitor closely"
        else:
            recommendation = f"Strategy {strategy_name} is healthy"
        
        status = DecayStatus(
            strategy_name=strategy_name,
            is_decaying=is_decaying,
            is_dead=is_dead,
            current_sharpe=current_sharpe,
            historical_sharpe=historical_sharpe,
            degradation_pct=degradation_pct * 100,
            should_disable=should_disable,
            recommendation=recommendation,
        )
        
        # Log if decaying
        if is_decaying or is_dead:
            logger.warning(
                "strategy_decay_detected",
                strategy=strategy_name,
                current_sharpe=current_sharpe,
                historical_sharpe=historical_sharpe,
                degradation_pct=degradation_pct * 100,
                is_dead=is_dead,
            )
        
        return status
    
    def _check_strategy_death(
        self,
        strategy_name: str,
        current_sharpe: float,
    ) -> bool:
        """
        Check if strategy is dead (Sharpe < 0 for extended period).
        
        Tracks consecutive days with negative Sharpe.
        """
        if strategy_name not in self.strategy_performance:
            self.strategy_performance[strategy_name] = []
        
        # Record current performance
        self.strategy_performance[strategy_name].append({
            "timestamp": datetime.now(),
            "sharpe": current_sharpe,
        })
        
        # Keep only recent data
        cutoff = datetime.now() - timedelta(days=self.disable_threshold_days + 10)
        self.strategy_performance[strategy_name] = [
            p for p in self.strategy_performance[strategy_name]
            if p["timestamp"] > cutoff
        ]
        
        # Check consecutive negative Sharpe days
        recent_performance = self.strategy_performance[strategy_name][-self.disable_threshold_days:]
        
        if len(recent_performance) < self.disable_threshold_days:
            return False  # Not enough data
        
        # All recent Sharpe values < 0?
        all_negative = all(p["sharpe"] < 0 for p in recent_performance)
        
        return all_negative
    
    def get_all_statuses(self) -> dict[str, DecayStatus]:
        """Get decay status for all tracked strategies."""
        # This would be called with actual strategy performance data
        # For now, return empty dict
        return {}
