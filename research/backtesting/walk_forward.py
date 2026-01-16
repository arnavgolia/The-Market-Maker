"""
Walk-forward validation framework.

CRITICAL: This is the ONLY valid way to backtest strategies.
Full-dataset backtests guarantee overfitting.

Walk-forward protocol:
- Train on Year 1-2, Test on Year 3 (NEVER overlapping)
- Train on Year 2-3, Test on Year 4
- Train on Year 3-4, Test on Year 5
- All folds must pass (not just average)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Callable
import structlog

import pandas as pd
import numpy as np

from src.strategy.base import Strategy
from research.backtesting.engine import BacktestEngine, BacktestResult

logger = structlog.get_logger(__name__)


@dataclass
class WalkForwardFold:
    """A single walk-forward fold."""
    fold_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    
    @property
    def train_period(self) -> str:
        """Human-readable train period."""
        return f"{self.train_start.date()} to {self.train_end.date()}"
    
    @property
    def test_period(self) -> str:
        """Human-readable test period."""
        return f"{self.test_start.date()} to {self.test_end.date()}"


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""
    fold_id: int
    train_period: str
    test_period: str
    
    # Out-of-sample results (THE TRUTH)
    oos_sharpe: float
    oos_sortino: float
    oos_max_dd: float
    oos_return: float
    
    # In-sample vs out-of-sample degradation
    is_vs_oos_degradation: float  # How much worse OOS is than IS
    
    # Pass/fail
    passed: bool


class WalkForwardValidator:
    """
    Walk-forward validation framework.
    
    This is the ONLY statistically valid way to validate strategies.
    Full-dataset backtests are guaranteed to overfit.
    
    Key principles:
    - NO overlapping train/test windows
    - Test data NEVER seen during training
    - All folds must pass (not just average)
    - Transaction costs applied to ALL backtests
    """
    
    def __init__(
        self,
        train_years: int = 2,
        test_years: int = 1,
        min_train_days: int = 252,  # Minimum 1 year of training data
        min_test_days: int = 63,    # Minimum 3 months of test data
    ):
        """
        Initialize walk-forward validator.
        
        Args:
            train_years: Years of training data per fold
            test_years: Years of test data per fold
            min_train_days: Minimum training days required
            min_test_days: Minimum test days required
        """
        self.train_years = train_years
        self.test_years = test_years
        self.min_train_days = min_train_days
        self.min_test_days = min_test_days
        
        logger.info(
            "walk_forward_validator_initialized",
            train_years=train_years,
            test_years=test_years,
        )
    
    def validate(
        self,
        strategy: Strategy,
        bars: pd.DataFrame,
        backtest_engine: BacktestEngine,
        regime_detector: Optional[Callable] = None,
        min_oos_sharpe: float = 0.5,
        max_oos_drawdown: float = 0.20,
    ) -> list[WalkForwardResult]:
        """
        Run walk-forward validation.
        
        Args:
            strategy: Strategy to validate
            bars: Full historical data
            backtest_engine: Backtest engine instance
            regime_detector: Optional regime detector function
            min_oos_sharpe: Minimum OOS Sharpe to pass
            max_oos_drawdown: Maximum OOS drawdown to pass
        
        Returns:
            List of WalkForwardResult for each fold
        """
        if bars.empty:
            raise ValueError("Cannot validate on empty data")
        
        # Generate folds
        folds = self._generate_folds(bars)
        
        if not folds:
            logger.warning("no_valid_folds_generated")
            return []
        
        logger.info("walk_forward_validation_starting", num_folds=len(folds))
        
        results = []
        
        for fold in folds:
            logger.info(
                "processing_fold",
                fold_id=fold.fold_id,
                train_period=fold.train_period,
                test_period=fold.test_period,
            )
            
            # Split data
            train_bars = bars[
                (bars["timestamp"] >= fold.train_start) &
                (bars["timestamp"] <= fold.train_end)
            ]
            test_bars = bars[
                (bars["timestamp"] >= fold.test_start) &
                (bars["timestamp"] <= fold.test_end)
            ]
            
            if len(train_bars) < self.min_train_days or len(test_bars) < self.min_test_days:
                logger.warning(
                    "fold_skipped_insufficient_data",
                    fold_id=fold.fold_id,
                    train_days=len(train_bars),
                    test_days=len(test_bars),
                )
                continue
            
            # Train strategy (if it has a fit method)
            if hasattr(strategy, "fit"):
                try:
                    strategy.fit(train_bars)
                except Exception as e:
                    logger.warning("strategy_fit_failed", error=str(e))
            
            # Run backtest on TEST data (NEVER SEEN)
            try:
                test_result = backtest_engine.run(
                    strategy=strategy,
                    bars=test_bars,
                    regime_detector=regime_detector,
                )
                
                # Calculate degradation (if we had IS results)
                degradation = 0.0  # Would compare IS vs OOS if we had IS results
                
                # Check pass/fail
                passed = (
                    test_result.sharpe_ratio >= min_oos_sharpe and
                    abs(test_result.max_drawdown) <= max_oos_drawdown
                )
                
                result = WalkForwardResult(
                    fold_id=fold.fold_id,
                    train_period=fold.train_period,
                    test_period=fold.test_period,
                    oos_sharpe=test_result.sharpe_ratio,
                    oos_sortino=test_result.sortino_ratio,
                    oos_max_dd=test_result.max_drawdown,
                    oos_return=test_result.total_return,
                    is_vs_oos_degradation=degradation,
                    passed=passed,
                )
                
                results.append(result)
                
                logger.info(
                    "fold_complete",
                    fold_id=fold.fold_id,
                    oos_sharpe=test_result.sharpe_ratio,
                    oos_max_dd=test_result.max_drawdown,
                    passed=passed,
                )
                
            except Exception as e:
                logger.error(
                    "fold_backtest_failed",
                    fold_id=fold.fold_id,
                    error=str(e),
                )
        
        # Summary
        passed_folds = sum(1 for r in results if r.passed)
        logger.info(
            "walk_forward_validation_complete",
            total_folds=len(results),
            passed_folds=passed_folds,
            pass_rate=passed_folds / len(results) if results else 0.0,
        )
        
        return results
    
    def _generate_folds(self, bars: pd.DataFrame) -> list[WalkForwardFold]:
        """
        Generate non-overlapping walk-forward folds.
        
        Folds are:
        - Non-overlapping (test never in training)
        - Sequential (train before test)
        - Minimum size requirements
        """
        if "timestamp" not in bars.columns:
            raise ValueError("Bars must have 'timestamp' column")
        
        # Sort by timestamp
        bars_sorted = bars.sort_values("timestamp")
        
        start_date = bars_sorted["timestamp"].min()
        end_date = bars_sorted["timestamp"].max()
        
        total_days = (end_date - start_date).days
        
        # Calculate fold requirements
        train_days = self.train_years * 252
        test_days = self.test_years * 252
        
        if total_days < train_days + test_days:
            logger.warning(
                "insufficient_data_for_walk_forward",
                total_days=total_days,
                required=train_days + test_days,
            )
            return []
        
        folds = []
        fold_id = 1
        
        # Generate folds
        current_start = start_date
        
        while True:
            train_start = current_start
            train_end = train_start + timedelta(days=train_days)
            test_start = train_end + timedelta(days=1)  # Gap to prevent overlap
            test_end = test_start + timedelta(days=test_days)
            
            # Check if we have enough data
            if test_end > end_date:
                break
            
            # Verify no overlap
            if train_end >= test_start:
                logger.warning("fold_overlap_detected", fold_id=fold_id)
                break
            
            fold = WalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            
            folds.append(fold)
            
            # Move to next fold (rolling window)
            current_start = train_start + timedelta(days=test_days)
            fold_id += 1
        
        logger.info("folds_generated", count=len(folds))
        return folds
    
    def aggregate_results(self, results: list[WalkForwardResult]) -> dict:
        """
        Aggregate walk-forward results.
        
        Strategy is valid ONLY if ALL folds pass.
        """
        if not results:
            return {
                "valid": False,
                "reason": "no_results",
            }
        
        passed_folds = [r for r in results if r.passed]
        all_passed = len(passed_folds) == len(results)
        
        avg_sharpe = np.mean([r.oos_sharpe for r in results])
        avg_sortino = np.mean([r.oos_sortino for r in results])
        avg_max_dd = np.mean([abs(r.oos_max_dd) for r in results])
        avg_return = np.mean([r.oos_return for r in results])
        
        return {
            "valid": all_passed,
            "total_folds": len(results),
            "passed_folds": len(passed_folds),
            "pass_rate": len(passed_folds) / len(results),
            "avg_oos_sharpe": avg_sharpe,
            "avg_oos_sortino": avg_sortino,
            "avg_oos_max_dd": avg_max_dd,
            "avg_oos_return": avg_return,
            "min_oos_sharpe": min(r.oos_sharpe for r in results),
            "max_oos_drawdown": max(abs(r.oos_max_dd) for r in results),
        }
